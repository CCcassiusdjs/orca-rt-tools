from __future__ import annotations
#graph data extractor

from math import sqrt
from sys import argv

from rttools.gsl.graph import Graph, GraphNode, GraphEdge
from rttools.gff.orca import import_graph as orca_import
from rttools.terminal.terminal import header, info


# standard deviation for edge values
def edge_standard_deviation(graph: Graph) -> float:
    edge_values = [int(x["payload"]) for x in [y._data for y in graph._edges]]
    edge_values_avg = sum(edge_values) / len(edge_values)

    edge_values_avg_diff = [(x - edge_values_avg) for x in edge_values]

    m2 = sum([pow(x, 2) for x in edge_values_avg_diff])
    m2 = sqrt(m2 / len(graph._edges))
    return m2


# standard deviation for node values
def node_standard_deviation(graph: Graph) -> float:
    node_values = [int(x["wcet"]) for x in [y._data for y in graph._nodes]]
    node_values_avg = sum(node_values) / len(node_values)

    node_values_avg_diff = [(x - node_values_avg) for x in node_values]

    m1 = sum([pow(x, 2) for x in node_values_avg_diff])
    m1 = sqrt(m1 / len(graph._nodes))
    return m1


def node_edge_rate(graph: Graph) -> float:
    node_values = [int(x["wcet"]) for x in [y._data for y in graph._nodes]]
    edge_values = [int(x["payload"]) for x in [y._data for y in graph._edges]]
    
    m3 =  sum(node_values) / sum(edge_values)
    return m3


def edge_density(graph: Graph) -> float:
    num_nodes: float = len(graph._nodes)
    full_connected_factor: float = num_nodes * (num_nodes -1)

    m4 = len(graph._edges) / full_connected_factor
    return m4


def graph_analyser(filename: str) -> list[float]:
    graph = orca_import(filename)

    results = {
        "number_of_edges" : len(graph._edges),
        "number_of_vertices" : len(graph._nodes),
        "graph_density" : edge_density(graph),
        "edges_std_dev" : edge_standard_deviation(graph),
        "vertices_std_dev" : node_standard_deviation(graph),
        "vertex_edge_rating" : node_edge_rate(graph)
    }

    return results


if __name__ == "__main__":

    usage_note = "gde <ifile>"

    if(len(argv) != 2 ):
        header("RTTOOLS.GDE")
        info("Usage:")
        info(usage_note)
    else:
        # stddev edge, stddev node, rating
        res = graph_analyser(argv[1])
        
        #print(" & ".join([str(round(x, 3)) for x in res]))
        for k in res.keys():
            print(k, res[k])