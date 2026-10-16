from rttools.gsl.graph import Graph, GraphEdge, GraphNode

# convert graph to ORCA notation
def to_orca(app):
    
    # create new graph
    graph : Graph = Graph()

    # create vertices
    for n in app["tasks"]:
      id, data = n
      node: GraphNode = GraphNode(id, data={"wcet": data["wcet"]})
      graph._nodes.append(node)

    #create edges
    for e in app["flows"]:
      source, target, data = e
      nfrom = [x for x in graph._nodes if x._id == source][0]
      nto = [x for x in graph._nodes if x._id == target][0]
      edge: GraphEdge = GraphEdge(graph.get_new_id(), {"payload": data["datasize"]}, nfrom, nto)
      graph._edges.append(edge)
      
    return graph
