import subprocess
from sys import argv

from rttools.gff.orca import import_graph as orca_import
from rttools.gff.orca import export_graph as orca_export
from rttools.gff.dot import export_graph as dot_export

from rttools.terminal.terminal import header, info

def convert_graph(ifile: str, iformat: str, oformat: str, ofile: str) -> None:

    graph: Graph = None

    if(iformat not in ["ORCA", "DOT"]):
        raise ValueError("Invalid input format: " + str(iformat))

    if(iformat != "DOT" and oformat not in ["ORCA", "DOT"]):
        raise ValueError("Invalid output format: " + str(oformat))

    match iformat:
        case "ORCA":
            graph = orca_import(ifile)
        case "DOT":
            oformat = oformat.lower()
            cline = f"dot -T{oformat} {ifile} -o {ofile}"
            subprocess.run(cline.split(" "))

    if(iformat != "DOT"):
        match oformat:
            case "ORCA":
                orca_export(ofile, graph)
            case "DOT":
                dot_export(graph, ofile)


if __name__ == "__main__":
    
    usage_note = "gff <ifile> <iformat> <oformat> <ofile>"

    if(len(argv) != 5 ):
        header("RTTOOLS.GFF")
        info("Usage:")
        info(usage_note)
    else:
        input_file = str(argv[1])
        i_format = argv[2]
        o_format = argv[3]
        output_file = str(argv[4])

        convert_graph(input_file, i_format, o_format, output_file)