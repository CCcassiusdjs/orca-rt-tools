from rttools.gsl.graph import Graph, GraphNode, GraphEdge


class CriteriaICC():

    @classmethod
    def MIN_COMM(cls, g: Graph):
        # locate highest network flow
        edge: GraphEdge = None
        for e in g._edges:
            if (edge is None):
                edge = e
            elif (int(e._data["payload"]) > int(edge._data["payload"])):
                edge = e
        return edge

    @classmethod
    def MAX_COMM(cls, g: Graph):
        # locate highest network flow
        edge: GraphEdge = None
        for e in g._edges:
            if (edge is None):
                edge = e
            elif (int(e._data["payload"]) < int(edge._data["payload"])):
                edge = e
        return edge


    @classmethod
    def MIN_PROC(cls, g: Graph):
        min_usage: int = 0
        edge: GraphEdge = None

        for e in g._edges:
            if (edge is None):
                edge = e
                min_usage = int(e._from._data["wcet"]) \
                    + int(e._to._data["wcet"])
            else:
                tsum: int = int(e._from._data["wcet"]) \
                    + int(e._to._data["wcet"])
                if tsum > min_usage:
                    edge = e
                    min_usage = tsum
        return edge

    @classmethod
    def MAX_PROC(cls, g: Graph):
        min_usage: int = 0
        edge: GraphEdge = None

        for e in g._edges:
            if (edge is None):
                edge = e
                min_usage = int(e._from._data["wcet"]) \
                    + int(e._to._data["wcet"])
            else:
                tsum: int = int(e._from._data["wcet"]) \
                    + int(e._to._data["wcet"])
                if tsum < min_usage:
                    edge = e
                    min_usage = tsum
        return edge



    @classmethod
    def MPMC(cls, g: Graph):
        return None

class GraphICC():

    @classmethod
    def collapse(cls, g: Graph, c: CriteriaICC) -> Graph:
        edge: GraphEdge = c(g)

        # make both sender and receiver the same node
        ln = edge._from
        rn = edge._to

        new_node: GraphNode = GraphNode(g.get_new_id(), {
            "label": ln._data["label"] + ":" + rn._data["label"],
            "wcet": str(int(ln._data["wcet"]) + int(rn._data["wcet"]))
        })

        # redirect edges from ln and rn nodes to the new node
        for e in g._edges:
            if (e._to == ln or e._to == rn):
                e._to = new_node
            if (e._from == ln or e._from == rn):
                e._from = new_node

        # remove dangling nodes from the graph
        g._nodes = [x for x in g._nodes if (
            x._id != ln._id and x._id != rn._id)]
        g._nodes.append(new_node)

        # remove circular edges (from == to)
        g._edges = [x for x in g._edges if (x._to != x._from)]

        return g
