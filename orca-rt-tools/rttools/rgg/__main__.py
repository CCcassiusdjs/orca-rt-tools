from sys import argv
import random as pyrandom
import numpy
from math import floor

from rttools.gsl.graph import Graph, GraphNode, GraphEdge
from rttools.gff.orca import export_graph as orca_export

def linear_scale(source: float, r_min: float, r_max: float, t_min: float, t_max: float) -> float:
    return ((source - r_min) / (r_max - r_min)) * (t_max - t_min) + t_min

# nnodes : number of nodes in the graph
# pedges : mean number of edges per node
# dwcet  : normal distribution for node values (task wcet)
# dnet   : normal distribution for edge values (comm load)
def generate_random_graph(num_nodes: int, node_lim: list[float], pedges: int, edge_lim: list[float], seed: int = None) -> Graph:

    # local generators; seed None keeps the unseeded random draw
    random = numpy.random.RandomState(seed)
    randint = pyrandom.Random(seed).randint

    # create new graph
    graph : Graph = Graph()

    # generate normal curve for node wcet
    wcet_distrib = random.normal(size=(num_nodes))

    # adjust curve to min-max values
    node_min = node_lim[0]
    node_max = node_lim[1]
    distrib_min = min(wcet_distrib)
    distrib_max = max(wcet_distrib)

    # scale distribution to wcet limits
    wcet_distrib_scaled = [linear_scale(x, distrib_min, distrib_max, node_min, node_max) for x in wcet_distrib]

    # generate n nodes using the scaled distribution
    for i in range(num_nodes):
        wcet = floor(abs(wcet_distrib_scaled[i]))
        graph._nodes.append(
            GraphNode(id=i, data={"wcet": str(wcet), "label": str(i)})
        )

    # generate number of edges
    # num_edges = num_nodes * (num_nodes -1)  # fully connected graph
    # num_edges = num_edges * pedges      # adjust to density
    #num_edges = floor(num_edges)
    num_edges: int = num_nodes * pedges

    # generate normal curve for edge comm
    comm_distrib = random.normal(size=(num_edges))

    # adjust curve to min-max values
    edge_min = edge_lim[0]
    edge_max = edge_lim[1]
    distrib_min = min(comm_distrib)
    distrib_max = max(comm_distrib)

    # scale distribution to comm limits
    comm_distrib_scaled = [linear_scale(x, distrib_min, distrib_max, edge_min, edge_max) for x in comm_distrib]

    # create edges
    for i in range(num_edges):
        nfrom = randint(0, len(graph._nodes) -1)
        nto = nfrom 
        while(nto == nfrom):
            nto = randint(0, len(graph._nodes) -1)

        id_edge = i + len(graph._nodes)
        comm = floor(abs(comm_distrib_scaled[i]))
        edge : GraphEdge = GraphEdge(str(id_edge), {"label": str(id_edge), "payload": str(comm)}, 
            nfrom=[x for x in graph._nodes if x._id == nfrom][0], 
            nto=[x for x in graph._nodes if x._id == nto][0])
        graph._edges.append(edge)

    return graph


if __name__ == "__main__":

    usage_notice = "Usage: rgg <a> <b> <c> <x> <y> <z> <ofile> [<seed>]\n"
    usage_notice = usage_notice + "`a`: number of vertices\n"
    usage_notice = usage_notice + "`b`: vertices minimum value\n"
    usage_notice = usage_notice + "`c`: vertices maximum value\n"
    usage_notice = usage_notice + "`x`: edges per vertex\n"
    usage_notice = usage_notice + "`y`: edges minimum value\n"
    usage_notice = usage_notice + "`z`: edges maximum value\n"
    usage_notice = usage_notice + "`ofile`: output file name\n"
    usage_notice = usage_notice + "`seed`: random seed (optional)\n"

    if(len(argv) not in (8, 9)):
        raise Exception(usage_notice)

    num_nodes: int = int(argv[1])
    min_wcet: int = int(argv[2])
    max_wcet: int = int(argv[3])

    density_edges: int = int(argv[4])
    min_comm: int = int(argv[5])
    max_comm: int = int(argv[6])

    graph_file = str(argv[7])
    seed = int(argv[8]) if len(argv) == 9 else None

    graph = generate_random_graph(num_nodes, [min_wcet, max_wcet], density_edges, [min_comm, max_comm], seed)
    orca_export(graph_file, graph)

    