from os.path import exists
from sys import argv
from rttools.gsl.graph import Graph
from rttools.gcm.gicc import GraphICC, CriteriaICC
from rttools.gcm.terminal import error, info, warn, debug, header
from rttools.gff.orca import export_graph as orca_export
from rttools.gff.orca import import_graph as orca_import

def gcm_main(filename, numnodes, criteria):

    

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

    g: Graph = orca_import(filename)

    if(p_criteria == CriteriaICC.MPMC):
        criteria_sub = CriteriaICC.MAX_PROC
        while (len(g._nodes) > numnodes):
            g = GraphICC.collapse(g, criteria_sub)
            if(criteria_sub == CriteriaICC.MAX_PROC):
                criteria_sub = CriteriaICC.MIN_COMM
            else: 
                criteria_sub = CriteriaICC.MAX_PROC
    else:
        while (len(g._nodes) > numnodes):
            g = GraphICC.collapse(g, p_criteria)

    clustered_filename = filename.replace(".txt", ".clustered."+criteria)
    orca_export(clustered_filename, g)

if __name__ == "__main__":
    
    usage_note = "gcm <ifile> <nvertices> <criteria>"

    if(len(argv) != 4):
        header("RTTOOLS.GCM")
        info("Usage:")
        info(usage_note)
    else:
      filename: str = argv[1]
      numnodes: int = int(argv[2])
      criteria: str = argv[3]

      g = gcm_main(filename, numnodes, criteria)


