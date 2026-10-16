from rttools.gsl.graph import Graph, GraphEdge, GraphNode

def export_graph(self, filename):
    with (open(filename, mode="w+") as f):
        f.write("digraph {\n")
        for n in self._nodes:
            f.write("  \"" + n._data["label"] + "\"\n")
        for e in self._edges:
            f.write("  \"" + e._from._data["label"] + "\" -> \""
                    + e._to._data["label"] + "\"\n")
        f.write("\n}")
        
