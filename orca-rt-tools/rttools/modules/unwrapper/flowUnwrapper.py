import networkx as nx
import json
from os import path
import os.path

from rttools.lcm.lcm import lcm
from rttools.strgen.string import wsfill
from rttools.terminal.terminal import error, warn, debug, info
from rttools.gff.rttools import to_orca
from rttools.gcpa.method import calculate_gcpa

from rttools.modules.mapping import mapper
from rttools.modules.instances import release
from rttools.modules.routing import router
from rttools.modules.io import svg, vhdl, znc


# extract flows from a given application graph edges
# returns a list of flows
def extractFlows(edges):

    flows = []
    for e in edges:
        source, target, data = e

        flow = {
            "name": data["label"],  # name of the flow, must be unique among the flows
            "source": source,  # task that generates the flow (task id)
            "target": target,  # task that will receive the packets (task id)
            "period": data["period"],  # packets injection period
            "datasize": data["datasize"],  # number of bytes to send
            "deadline": data["deadline"],
        }  # deadline
        flows.append(flow)

    # sort flows by label (usually f1, f2, ...)
    flows.sort(key=lambda x: x["name"], reverse=False)

    return flows


def task_wcet_table(app):
    """GCPA cost of each task of the application instance (task id -> cost).

    The table is computed per application, so two applications in the same
    process read their own costs."""
    graph = to_orca(app)
    table = {}
    tmp_task_wcet = calculate_gcpa(graph)
    for wcet in tmp_task_wcet:
        table[wcet._id] = tmp_task_wcet[wcet]
    return table


def get_task_wcet(task_id, tasks, app):
    return task_wcet_table(app)[task_id]


# def get_task_wcet(task_id, tasks, app):    
#     for t in tasks:
#         tname, tinfo = t
#         if(task_id == tname):
#             return tinfo["wcet"]
#     raise Exception("Could not locate source task for target flow")




    

# release window (offset, end) of the first packet of each flow, in cycles
# from the start of its period (rttools/modules/instances/release.py)
def releaseWindows(flows, app, mapping):
    rel = app.get("release") or release.settings({})
    if rel["model"] == release.PHASE:
        return release.phase_flows(app, mapping)
    wcet_table = task_wcet_table(app)
    return {f["name"]: (wcet_table[f["source"]], wcet_table[f["source"]] + f["deadline"]) for f in flows}


# generates packets for a given list of flows. packets
# are generated for the whole hyperperiod hp
def getPacketsFromFlows(flows, hp, tasks, app, mapping=None):
    packets = []
    windows = releaseWindows(flows, app, mapping)
    for f in flows:
        offset, end = windows[f["name"]]
        min_start = 0
        i = 0
        while min_start < hp:
            packet = {
                "name": f["name"] + ":" + str(i),
                "flow": f["name"],
                "source": f["source"],
                "target": f["target"],
                "min_start": min_start + offset,
                "abs_deadline": min_start + end,
                "datasize": f["datasize"],
            }
            packets.append(packet)
            min_start = min_start + f["period"]
            i = i + 1

    return packets


# generate a list of packets from an app instance
def unwrap(app, arch, mapping):
    
    # for a in app["tasks"]:
    #     print(a)
    # print("-------")
    # for a in app["flows"]:
    #     print(a)
    # print("-------")
    # print(arch)
    # print("-------")
    # for a in mapping:
    #     print(a)
   

    flows = extractFlows(app["flows"])
    # for a in flows:
    #     print(a)
    
    # calculate hyperperiod
    periods = []
    for f in flows:
        periods.append(f["period"])

    hp = lcm(periods)
    if hp != 0:
        info("Hyperperiod for the entered flow set is " + str(hp) + " cycles")
    else:
        error("Unable to compute hyperperiod for the entered flow set.")
        pp = []
        [pp.append(x) for x in periods if x not in pp]
        error(str(pp))

        return None, 0, None

    # get packets from flows
    packets = getPacketsFromFlows(flows, hp, app["tasks"], app, mapping)
    info(
        "Extracted " + str(len(packets)) + " packets from " + str(len(flows)) + " flows"
    )

    # get traversal path of each packet
    info("Discovering packets routes...")

    for p in packets:
        sourceTaskName = ""
        targetTaskName = ""

        for n in app["tasks"]:
            id, data = n
            if id == p["source"]:
                sourceTaskName = id
            if id == p["target"]:
                targetTaskName = id

        sourceNode = mapper.getMap(sourceTaskName, mapping)
        targetNode = mapper.getMap(targetTaskName, mapping)

        ppath = router.XY(sourceNode, targetNode, arch)

        p["path"] = ppath
        debug(p["name"] + ": hops=" + str(len(ppath)))
        for p in ppath:
            debug("    " + str(p))

    info("Enumerating network links...")

    # enumerate network links
    nlinks = []
    for e in arch.edges(data=True):
        nlinks.append(e)

    # add local-to/from links
    for n in arch.nodes(data=True):
        x, y = n
        nlinks.append((x, "L", {"label": str(x) + "-L"}))
        nlinks.append(("L", x, {"label": "L-" + str(x)}))

    for n in nlinks:
        debug(str(n))

    info("... Discovered " + str(len(nlinks)) + " links")

    # calculate net_time
    info("Calculating networking time...")

    for p in packets:
        sourceTaskName = ""
        targetTaskName = ""

        for n in app["tasks"]:
            id, data = n
            if id == p["source"]:
                sourceTaskName = id
            if id == p["target"]:
                targetTaskName = id

        source = mapper.getMap(sourceTaskName, mapping)
        target = mapper.getMap(targetTaskName, mapping)

        delta_m = router.manhattan(source, target, arch)
        routing_time = (delta_m + 1) * router.getRoutingTime()
        payload = router.getPacketFlits(int(p["datasize"]))
        p["net_time"] = router.occupancy(delta_m, int(p["datasize"]))

        debug(
            p["name"]
            + " => network_time="
            + str(p["net_time"])
            + ", manhattan="
            + str(delta_m)
            + ", routing_time="
            + str(routing_time)
            + ", payload="
            + str(payload)
        )

    packets = [p for p in packets if len(p["path"]) != 0]

    return packets, hp, nlinks
