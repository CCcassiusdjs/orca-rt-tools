from sys import argv

from rttools.gsl.graph import Graph, GraphEdge, GraphNode
from rttools.gff.orca import import_graph as orca_import
from rttools.terminal.terminal import header, info 
from rttools.gcpa.method import calculate_gcpa

def gcpa_main(filename: str):

    graph = orca_import(filename)

    dct = calculate_gcpa(graph)
    
    for k in dct.keys():
        print(k, dct[k])


if __name__ == "__main__":
    args = argv[1::]

    usage_note = "gcpa <ifile>"


    if(len(argv) != 2 ):
        header("RTTOOLS.GCPA")
        info("Usage:")
        info(usage_note)
    else:
        gcpa_main(args[0])