from os import system
from os.path import exists
from sys import argv
from glob import glob
from gcm.graph import Graph
from gcm.gicc import GraphICC, CriteriaICC
from gcm.terminal import error, info, warn, debug, header
from gcm.sim import AppTask, AppMessage, AppMessageType, UCX_OS, KernelTracer


def adjust_time_deps(args):

    node_wcet = {}

    # load dependency graph
    g = Graph.parse_from_file(args[0])

    for n in g._nodes:
        node_wcet[n._data["label"]] = 0

    # load combined traces
    traces = []
    with open(args[0].replace(".txt", ".X.trace")) as f:
        for line in f.readlines():
            traces.append(line.replace("\n", "").split("\t"))

    bins = {}
    # pack events into bins
    for t in traces:
        if (t[2] not in bins.keys()):
            bins[t[2]] = []
            node_wcet[t[2]] = 0
        bins[t[2]].append(t)

    # calculate the time spent per node
    for b in bins.keys():
        events = bins[b]

        max_time = 0
        for e in events:
            if int(e[0]) > max_time:
                max_time = int(e[0])
        node_wcet[b] = max_time

    # get clustered graph
    h = Graph.parse_from_file(args[0].replace(".txt", ".clustered"))

    cluster_wcet = {}

    for n in h._nodes:
        header(n)
        nodes = n._data["label"].split(':')
        max_cluster_wcet = 0
        for b in node_wcet.keys():
            if node_wcet[b] > max_cluster_wcet and b in nodes:
                max_cluster_wcet = node_wcet[b]
        cluster_wcet[n] = max_cluster_wcet

    for c in cluster_wcet:
        print(c, cluster_wcet[c])
            

    #for b in node_wcet.keys():
        

        # sender = b
        #     if (e[1] == "SystemEventType.RECV_ISR_2"):
        #         print(e)

    # # locate send events

    # sends = []
    # for t in traces:
    #     if t[1] == "SystemEventType.RECV_ISR_2":
    #         sends.append(t)

    # # locate senders

    # for p in sends:
    #     print(p)


def bench_analysis_main(args):

    trace_filename_filter = args[0].replace(".txt", "*.trace")
    trace_files = glob(trace_filename_filter)

    # extract trace info
    trace_infos = []
    for trace_file in trace_files:

        # read trace lines
        trace = []
        with open(trace_file) as trace_:
            for line in trace_.readlines():
                trace.append(line)

        for t in trace:
            trace_info_ = t.split("\t")

            trace_info = [
                trace_info_[0],   # start_time
                trace_info_[1],   # type
                trace_info_[3].replace("\n", ""),    # assoc. task
                trace_file,       # cluster
                trace_info_[2],   # data
            ]
            trace_infos.append(trace_info)

        # for f in trace_infos:
        #     print(f)

    merged_trace_info = trace_files[0].split('.')[0] + ".X.trace"
    with open(merged_trace_info, "w+") as f:
        for line in trace_infos:
            f.write("\t".join(line) + "\n")


def bench_main(args):

    # import collapsed graph
    g = Graph.parse_from_file(args[0].replace(".txt", ".clustered"))
    h = Graph.parse_from_file(args[0])

    # for each clustered node
    for cn in g._nodes:

        # get tasks in that cluster
        task_set = cn._data["label"].split(":")

        # collect nodes from the non-clustered graph
        task_nodes = [n for n in h._nodes if n._data["label"] in task_set]

        msgs = []
        tasks = []

        # add tasks to the trace model
        for n in task_nodes:
            tasks.append(AppTask(
                n._data["label"],
                int(n._data["wcet"])
            ))

        # for each node, find edges that goes in-out the cluster
        for e in h._edges:
            if (e._from in task_nodes and e._to not in task_nodes):
                msgs.append(AppMessage(
                    e._data["payload"],
                    [x for x in tasks if x._name == e._from._data["label"]][0],
                    AppTask(
                        e._to._data["label"],
                        e._to._data["wcet"]
                    )
                ))
            elif (e._to in task_nodes and e._from not in task_nodes):
                msgs.append(AppMessage(
                    e._data["payload"],
                    AppTask(
                        e._from._data["label"],
                        e._from._data["wcet"]
                    ),
                    [x for x in tasks if x._name == e._to._data["label"]][0],
                ))

        # create a kernel trace from nodes and messages
        sim = KernelTracer(tasks, msgs, UCX_OS)

        filename = args[0].replace("txt", str(g._nodes.index(cn)) + ".trace")
        with open(filename, "w+") as f:
            f.write(sim.trace())


def gcm_main(argv):

    filename: str = argv[0]
    numnodes: int = int(argv[1])
    criteria: str = argv[2]

    if (not exists(filename)):
        error(f"Unable to open file `{filename}`. Aborting.")
        exit(0)

    p_criteria = None

    if (criteria == "MIN_COMM"):
        p_criteria = CriteriaICC.MIN_COMM
    elif (criteria == "MAX_COMM"):
        p_criteria = CriteriaICC.MAX_COMM
    elif (criteria == "MIN_PROC"):
        p_criteria = CriteriaICC.MIN_PROC
    elif (criteria == "MAX_PROC"):
        p_criteria = CriteriaICC.MAX_PROC
    elif (criteria == "MPMC"):
        p_criteria = CriteriaICC.MPMC
    else:
        raise error("Invalid criterion informed. Must be one of: MIN_CPU_USAGE, MAX_CPU_USAGE, MIN_NET_USAGE, MAX_NET_USAGE, MPMC")

    g: Graph = Graph.parse_from_file(filename)

    g_dot_name = filename.replace(".txt", ".dot")
    #g.export_to_dot(g_dot_name)

    if(p_criteria != CriteriaICC.MPMC):
        while (len(g._nodes) > numnodes):
            g = GraphICC.collapse(g, p_criteria)
    else:
        criteria_sub = CriteriaICC.MAX_PROC
        while (len(g._nodes) > numnodes):
            g = GraphICC.collapse(g, criteria_sub)
            if(criteria_sub == CriteriaICC.MAX_PROC):
                criteria_sub = CriteriaICC.MIN_COMM
            else: 
                criteria_sub = CriteriaICC.MAX_PROC


    clustered_filename = filename.replace(".txt", ".clustered")
    dot_filename = filename.replace(".txt", ".clustered.dot")

    Graph.save_to_file(clustered_filename, g)
    exit(0)
    g.export_to_dot(dot_filename)

    # export dots to png
    system(f"dot -Tpng {dot_filename} > {dot_filename}.png")
    system(f"dot -Tpng {g_dot_name} > "
           + f"{g_dot_name}.png")


if __name__ == "__main__":
    g = gcm_main(argv[1::])
    bench_main(argv[1::])
    bench_analysis_main(argv[1::])
    adjust_time_deps(argv[1::])
