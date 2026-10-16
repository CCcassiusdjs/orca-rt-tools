class GraphNode():
    _data: object
    _id: int

    def __init__(self, id, data):
        self._id = id
        self._data = data

    def __str__(self):
        return "({0}) {1}".format(self._id, self._data)


class GraphEdge():
    _data: object
    _id: int
    _from: GraphNode = None
    _to: GraphNode = None

    def __init__(self, id, data, nfrom, nto):
        self._data = data
        self._id = id
        self._from = nfrom
        self._to = nto

    def __str__(self):
        return "({0}, {1}-{2}) {3}".format(
            self._id, self._from, self._to, self._data)


class Graph():
    _edges: list[GraphEdge]
    _nodes: list[GraphNode]
    __unique_id_counter: int

    def __str__(self):
        lines = []
        for n in self._nodes:
            lines.append(str(n))
        for e in self._edges:
            lines.append(str(e))
        return "\n".join(lines)

    def __init__(self):
        self._edges = []
        self._nodes = []
        self.__unique_id_counter = 0

    def get_new_id(self):
        self.__unique_id_counter = self.__unique_id_counter + 1
        return self.__unique_id_counter
