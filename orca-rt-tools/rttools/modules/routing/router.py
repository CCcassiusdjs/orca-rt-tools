import networkx as nx
import sys
import os
import os.path
from os import path

from rttools.terminal.terminal import error


# address decode
def decodeNodeID(id, width, height):
    noc_addr = [0, 0]
    noc_addr[0] = int(id % width)
    noc_addr[1] = int(id / width)
    return noc_addr


# bytes per flit (32-bit flits)
FLIT_BYTES = 4

# bytes of the packet header that the kernel prepends to the payload
# (noc_packet_t, ucx-os include/lib/noc.h); the DDMA sends header and
# payload as payload flits of the router
KERNEL_HEADER_BYTES = 12


#!cycles
def getRoutingTime():
    """Header latency of one Hermes router without contention, in cycles.

    GHDL simulation of the Hermes of the repository (8 x 3 mesh, ideal
    source and sink at the LOCAL ports): the header takes 6 cycles in each
    of the m + 1 routers of an m-hop path."""
    return 6


#!bits PAYLOAD ONLY
def getNumFlits(datasize):
    # BUS_WIDTH = 32
    BUS_WIDTH = FLIT_BYTES

    if datasize % BUS_WIDTH == 0:
        return (int)((datasize / BUS_WIDTH))
    else:
        return (int)((datasize / BUS_WIDTH) + 1)


def getPacketFlits(datasize):
    """Payload flits p of the router for a message of `datasize` bytes:
    ceil((12 + payload rounded up to a multiple of 4) / 4). The kernel
    rounds the payload up to whole words (ucx_noc_create_packet) and the
    driver converts bytes into flits by ceiling (_ddma_send)."""
    payload = getNumFlits(int(datasize)) * FLIT_BYTES
    return getNumFlits(KERNEL_HEADER_BYTES + payload)


# Header wait at the SwitchControl of one router (GHDL, make -C
# experiments/zll contention, experiments/zll/reference_contention.json).
# The SwitchControl routes one header at a time in five states (S1, S2,
# S3, S4/S5/S6, S7; pkt-sim/hw/router/hermes/Hermes_switchcontrol.vhd:
# 126-141) and selects the next input port in round-robin order from the
# last port served (:44-78). When the link schedule keeps the packets that
# share a link disjoint in time, the headers that meet a header at a router
# come from the other four input ports, so a header waits at most
# 4 x 5 = 20 cycles in each router.
HEADER_SERVICE_CYCLES = 5
MAX_COMPETING_HEADERS = 4
HEADER_WAIT_CYCLES = HEADER_SERVICE_CYCLES * MAX_COMPETING_HEADERS

# Selection of the header wait w_h of occupancy(), in cycles per router:
# set_header_wait() in the process, otherwise the environment variable
# RTTOOLS_HEADER_WAIT. Values: "bound" (default when unset or empty: w_h =
# HEADER_WAIT_CYCLES = 20, o_i = L0 + 20 (m + 1), the occupancy of the
# paper results), "0" or "off" (w_h = 0, o_i = L0, the zero-load latency
# alone), or a nonnegative integer.
HEADER_WAIT_ENV = "RTTOOLS_HEADER_WAIT"
HEADER_WAIT_DEFAULT = HEADER_WAIT_CYCLES
_header_wait = None


def parse_header_wait(value):
    """Cycles of header wait per router for a value of RTTOOLS_HEADER_WAIT
    or of the --header-wait option: None and "" give HEADER_WAIT_DEFAULT
    (the bound, 20), "0" or "off" give 0, "bound" gives HEADER_WAIT_CYCLES,
    an integer (or integer string) gives itself."""
    if value is None:
        return HEADER_WAIT_DEFAULT
    if isinstance(value, bool):
        raise ValueError("header wait: expected off, bound or an integer, got " + repr(value))
    if isinstance(value, int):
        w = value
    else:
        v = str(value).strip().lower()
        if v == "":
            return HEADER_WAIT_DEFAULT
        if v == "off":
            return 0
        if v == "bound":
            return HEADER_WAIT_CYCLES
        try:
            w = int(v)
        except ValueError:
            raise ValueError("header wait: expected off, bound or an integer, got " + repr(value)) from None
    if w < 0:
        raise ValueError("header wait: negative value " + repr(value))
    return w


def set_header_wait(value):
    """Selects w_h for this process (see parse_header_wait); None returns
    to the environment variable. Returns the previous selection."""
    global _header_wait
    prev = _header_wait
    _header_wait = None if value is None else parse_header_wait(value)
    return prev


def header_wait():
    """Header wait w_h per router (cycles) that occupancy() adds."""
    if _header_wait is not None:
        return _header_wait
    return parse_header_wait(os.environ.get(HEADER_WAIT_ENV))


# Network interface of a PE (pkt-sim/hw/ddma/ddma.sv) under the
# time-triggered injection of UCX-OS (pkt-sim/software/ucx-os/lib/noc_tt.c).
# The DDMA reads and writes the memory of the PE through one port, which it
# interleaves between the send and the receive of two packets; it waits
# for the CPU after the size flit of a received packet (irq2: the address
# of the buffer; the credit of the local port stays low) and after its last
# flit (irq3: the handshake that lets the next packet in), and the CPU
# injects a packet at the compare interrupt of TIMER1 at the instant of the
# link schedule rounded up to its 16-cycle step. The model of the analysis
# flow takes the network interface of each PE as one resource of the link
# schedule (ni_resources: the packets that a PE sends or receives never
# hold it in the same cycle) and adds to the occupancy the bound w_NI of
# these three waits: o_i = L0 + w_h (m + 1) + w_NI.
#
# The three terms of w_NI (cycles; rttools/wcet/ucx.py, ni_terms): the
# largest value of each term in the static analysis of the UCX-OS images
# with the time-triggered injection (experiments/wcet, config_tt.json,
# make analyze-tt check-tt: every term of every image at or below its
# constant; car_full built with riscv64-unknown-elf-gcc 13.2.0 has the three
# largest). The analysis of a run (rttools.paper.ttcheck) compares each
# measured wait with its term.
NI_INJECT_CYCLES = 3899     # instant s to the injection (compare interrupt of TIMER1)
NI_RX_SIZE_CYCLES = 7113    # size flit to the buffer of irq2_handler (credit withheld)
NI_RX_END_CYCLES = 4157     # last flit to the handshake of irq3_handler
NI_WAIT_CYCLES = NI_INJECT_CYCLES + NI_RX_SIZE_CYCLES + NI_RX_END_CYCLES
NI_ENV = "RTTOOLS_NI"
# selection of the network-interface model, as the header wait: set_ni() in
# the process, otherwise RTTOOLS_NI. "off" (default when unset or empty: no
# resource, w_NI = 0, the model of the runs up to tag r11-rc5, whose images
# injected each packet when its job sent it), "tt" (the network interface
# as a resource and w_NI = NI_WAIT_CYCLES: images built with
# INJECTION=tt, the default of pkt-sim/software/ucx-os/Makefile) or a
# nonnegative integer (the resource and that w_NI). rttools.ucxgen tt and
# the analysis of a run whose RUN_INFO has injection=tt select "tt".
NI_TT = "tt"
NI_OFF = "off"
_ni = None


def parse_ni(value):
    """(resource, w_NI) for a value of RTTOOLS_NI or of set_ni: None and ""
    give the default ("off"), "tt" gives (True, NI_WAIT_CYCLES), "off" gives
    (False, 0), an integer n gives (True, n)."""
    if value is None:
        return False, 0
    if isinstance(value, tuple):
        return bool(value[0]), int(value[1])
    if isinstance(value, bool):
        raise ValueError("network interface model: expected tt, off or an integer, got " + repr(value))
    if isinstance(value, int):
        w = value
    else:
        v = str(value).strip().lower()
        if v == NI_TT:
            return True, NI_WAIT_CYCLES
        if v in ("", NI_OFF):
            return False, 0
        try:
            w = int(v)
        except ValueError:
            raise ValueError("network interface model: expected tt, off or an integer, got "
                             + repr(value)) from None
    if w < 0:
        raise ValueError("network interface model: negative wait " + repr(value))
    return True, w


def set_ni(value):
    """Selects the network-interface model for this process (see parse_ni);
    None returns to the environment variable. Returns the previous
    selection."""
    global _ni
    prev = _ni
    _ni = None if value is None else parse_ni(value)
    return prev


def ni_model():
    """(resource, w_NI) of the network-interface model in use."""
    if _ni is not None:
        return _ni
    return parse_ni(os.environ.get(NI_ENV))


def ni_wait():
    """w_NI (cycles) that occupancy() adds."""
    return ni_model()[1]


def ni_resources():
    """True when the link schedule takes the network interface of each PE
    as one resource (ni_label)."""
    return ni_model()[0]


def ni_label(node):
    """Label of the network-interface resource of PE `node` in the link
    schedule (the paths keep their links; the resource is extra)."""
    return "NI-" + str(node)


def occupancy(hops, datasize, wait=None, ni=None):
    """Cycles a packet of `datasize` payload bytes holds each link of an
    XY path with `hops` hops: o_i = L0 + w_h (m + 1) + w_NI, with the
    zero-load latency of the Hermes L0 = 6 (m + 1) + p + 1 (p from
    getPacketFlits; the GHDL simulation of the router reproduces L0 for m
    from 1 to 9 hops), the header wait w_h per router of each of the m + 1
    routers of the path and the bound w_NI of the waits of the network
    interfaces (NI_WAIT_CYCLES). `wait` gives w_h; None takes header_wait()
    (default HEADER_WAIT_CYCLES = 20, the bound of the wait of the Hermes;
    "off" or 0 gives w_h = 0). `ni` gives the network-interface model
    (parse_ni); None takes ni_model() (default off, w_NI = 0; "tt" gives
    NI_WAIT_CYCLES)."""
    w = header_wait() if wait is None else parse_header_wait(wait)
    n = ni_wait() if ni is None else parse_ni(ni)[1]
    return getRoutingTime() * (hops + 1) + getPacketFlits(datasize) + 1 + w * (hops + 1) + n


def manhattan(source, target, graph):
    src = getNodeById(source, graph)
    trg = getNodeById(target, graph)
    x1 = src["data"]["X"]
    x2 = trg["data"]["X"]
    y1 = src["data"]["Y"]
    y2 = trg["data"]["Y"]
    dx = x2 - x1
    dy = y2 - y1
    return abs(dx) + abs(dy)


# return an object edge from the graph with given soruce and target nodes
def getEdge(source, target, graph):
    for e in graph.edges(data=True):
        esource, etarget, data = e
        if source["node"] == esource and target["node"] == etarget:
            return {"edge": {"source": source, "target": target}, "data": data}


# return an object node from the graph with given X and Y coordinates
def getNodeByXY(x, y, graph):
    for n in graph.nodes(data=True):
        node, data = n
        if data["X"] == x and data["Y"] == y:
            return {"node": node, "data": data}
    return None


# return an object node from the graph with given id
def getNodeById(nodeid, graph):
    tnode = None

    for n in graph.nodes(data=True):
        node, data = n

        if node == nodeid:
            tnode = {"node": node, "data": {"X": data["X"], "Y": data["Y"]}}

    return tnode


# returns a list of paths from source to target node on a given topology
def parse_XY(source, target, topology):
    if not path.exists(topology):
        print("unable to read input file")
        exit(0)

    graph = nx.read_gml(topology)
    XY(source, target, graph)


def XY(source, target, graph):
    # locate source and target nodes within the graph
    sourceNode = getNodeById(source, graph)
    targetNode = getNodeById(target, graph)

    # starting search
    currentNode = sourceNode

    # apply routing until reaching target destination
    paths = []
    while currentNode != targetNode:
        # X coordinate is aligned
        if currentNode["data"]["X"] == targetNode["data"]["X"]:
            if currentNode["data"]["Y"] > targetNode["data"]["Y"]:
                nextNode = getNodeByXY(
                    currentNode["data"]["X"], currentNode["data"]["Y"] - 1, graph
                )
            elif currentNode["data"]["Y"] < targetNode["data"]["Y"]:
                nextNode = getNodeByXY(
                    currentNode["data"]["X"], currentNode["data"]["Y"] + 1, graph
                )
            else:
                nextNode = targetNode

        # X coordinate is not aligned yet, move left
        elif currentNode["data"]["X"] > targetNode["data"]["X"]:
            nextNode = getNodeByXY(
                currentNode["data"]["X"] - 1, currentNode["data"]["Y"], graph
            )

        # X coordinate is not aligned yet, move right
        else:
            nextNode = getNodeByXY(
                currentNode["data"]["X"] + 1, currentNode["data"]["Y"], graph
            )

        # get edge (path), adds path to the output list
        edge = getEdge(currentNode, nextNode, graph)

        if edge == None:
            break  # TODO: remove workaround

        paths.append(edge)

        # hops one node towards target
        currentNode = nextNode

    if(len(paths) != 0):
      # add the LOCAL links of the source and target nodes
      source = paths[0]["edge"]["source"]
      paths.insert(
          0,
          {
              "edge": {
                  "source": {"node": "L", "data": {"X": -1, "Y": -1}},
                  "target": source,
              },
              "data": {"label": "L-" + source["node"]},
          },
      )

      target = paths[-1]["edge"]["target"]
      paths.append(
          {
              "edge": {
                  "source": target,
                  "target": {"node": "L", "data": {"X": -1, "Y": -1}},
              },
              "data": {"label": target["node"] + "-L"},
          }
      )

    return paths
