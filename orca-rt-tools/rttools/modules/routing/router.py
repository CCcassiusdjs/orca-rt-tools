import networkx as nx
import sys
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


def occupancy(hops, datasize):
    """Cycles a packet of `datasize` payload bytes holds each link of an
    XY path with `hops` hops: the zero-load latency of the Hermes,
    L0 = 6 (m + 1) + p + 1, with p from getPacketFlits. The GHDL
    simulation of the router reproduces L0 for m from 1 to 9 hops."""
    return getRoutingTime() * (hops + 1) + getPacketFlits(datasize) + 1


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
      # fix missing local source and target nodes
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
