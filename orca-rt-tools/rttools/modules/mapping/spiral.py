"""ORT/SM: Spiral Mapping (thesis, Section 8.1.2 and Fig. 8.2).

Input: the clusters of an application (one cluster per node, output of
ORT/GCM), the network volume of each cluster and the mesh dimensions.
Output: cluster -> node index (y * width + x, as in arch/hermes-*.gml).

Rule (Fig. 8.2): the clusters enter in increasing network volume; a tie
keeps the order of the cluster list (Table 8.1 numbering). The k-th
cluster takes the k-th node of the spiral: bottom row left to right,
right column upwards, top row right to left, left column downwards, then
the next ring inside in the same way, so the clusters with the largest
volume end in the center of the mesh.

The network volume of a cluster is the sum of the payloads of the edges
of the application graph that enter or leave the cluster; edges inside
the cluster do not count (note of Table 8.1).

`cluster_application` runs step 1 of Fig. 8.1 (ORT/GCM with the criteria
of Chapter 7, smallest standard deviation of the cluster WCET sums) so the
command line can map an application without a mapping file.
"""
from __future__ import annotations

import copy
import statistics

from rttools.gcm.gicc import CriteriaICC, GraphICC
from rttools.gsl.graph import Graph, GraphEdge, GraphNode

# criteria of Chapter 7 (Section 8.1.1 runs all of them)
CRITERIA = ("MIN_COMM", "MAX_COMM", "MIN_PROC", "MAX_PROC")


def spiral_order(width, height):
    """Node indices (y * width + x) in the order of Fig. 8.2."""
    if width < 1 or height < 1:
        raise ValueError(f"mesh {width}x{height}")
    out = []
    x0, y0, x1, y1 = 0, 0, width - 1, height - 1
    while x0 <= x1 and y0 <= y1:
        ring = [(x, y0) for x in range(x0, x1 + 1)]
        ring += [(x1, y) for y in range(y0 + 1, y1 + 1)]
        if y1 > y0:
            ring += [(x, y1) for x in range(x1 - 1, x0 - 1, -1)]
        if x1 > x0:
            ring += [(x0, y) for y in range(y1 - 1, y0, -1)]
        out += [y * width + x for x, y in ring]
        x0, y0, x1, y1 = x0 + 1, y0 + 1, x1 - 1, y1 - 1
    return out


def spiral_map(clusters, volumes, width, height):
    """Cluster -> node index. `clusters` is a list of cluster names,
    `volumes` maps each name to its network volume. The cluster with the
    smallest volume takes the first node of the spiral; a tie keeps the
    order of `clusters`."""
    clusters = list(clusters)
    if len(set(clusters)) != len(clusters):
        raise ValueError("repeated cluster name")
    if len(clusters) > width * height:
        raise ValueError(f"{len(clusters)} clusters for {width * height} nodes")
    ranked = sorted(range(len(clusters)), key=lambda i: (volumes[clusters[i]], i))
    nodes = spiral_order(width, height)
    return {clusters[i]: nodes[k] for k, i in enumerate(ranked)}


def cluster_volumes(clusters, edges):
    """Network volume of each cluster. `clusters` maps a cluster name to
    its tasks; `edges` is a list of (source task, target task, payload)."""
    owner = {}
    for name, tasks in clusters.items():
        for t in tasks:
            if t in owner:
                raise ValueError(f"task {t} in clusters {owner[t]} and {name}")
            owner[t] = name
    vol = {name: 0 for name in clusters}
    for a, b, w in edges:
        ca, cb = owner[a], owner[b]
        if ca != cb:
            vol[ca] += int(w)
            vol[cb] += int(w)
    return vol


# ------------------------------------------------------------ clustering

def _graph(tasks, edges):
    """rttools.gsl Graph with the node and edge order of the input (the
    order decides the ties of ORT/GCM, as in rttools.gff.orca)."""
    g = Graph()
    nodes = {}
    for name, wcet in tasks:
        n = GraphNode(g.get_new_id(), {"label": name, "wcet": str(int(wcet))})
        nodes[name] = n
        g._nodes.append(n)
    for a, b, w in edges:
        g._edges.append(GraphEdge(g.get_new_id(), {"payload": str(int(w))}, nodes[a], nodes[b]))
    return g


def gcm(tasks, edges, n_clusters, criterion):
    """ORT/GCM loop (rttools.gcm) with one criterion. Returns the clusters
    as an ordered dict name -> tasks; the name joins the tasks with ':' and
    the order is the node order of the clustered graph."""
    g = copy.deepcopy(_graph(tasks, edges))
    crit = getattr(CriteriaICC, criterion)
    while len(g._nodes) > n_clusters and g._edges:
        g = GraphICC.collapse(g, crit)
    return {n._data["label"]: n._data["label"].split(":") for n in g._nodes}


def cluster_application(tasks, edges, n_clusters, criteria=CRITERIA):
    """Step 1 of Fig. 8.1: ORT/GCM with each criterion; the result with the
    smallest standard deviation of the cluster WCET sums wins (population
    deviation, as ORT/GDE; the choice is the same with n - 1). A tie keeps
    the order of `criteria`. Returns (chosen criterion, clusters, rows),
    one row per criterion with its clusters, WCET sums and deviation."""
    wcet = {name: int(w) for name, w in tasks}
    rows = []
    for c in criteria:
        cl = gcm(tasks, edges, n_clusters, c)
        sums = [sum(wcet[t] for t in ts) for ts in cl.values()]
        sigma = statistics.pstdev(sums) if len(sums) > 1 else 0.0
        rows.append({"criterion": c, "clusters": cl, "wcet": sums, "sigma": sigma})
    best = min(rows, key=lambda r: r["sigma"])
    return best["criterion"], best["clusters"], rows


def map_application(tasks, edges, width, height, criteria=CRITERIA):
    """Steps 1 and 2 of Fig. 8.1. `tasks` is a list of (name, wcet),
    `edges` a list of (source, target, payload). Returns a dict with the
    chosen criterion, the clusters, their volumes, cluster -> node and
    task -> node."""
    criterion, clusters, rows = cluster_application(tasks, edges, width * height, criteria)
    vol = cluster_volumes(clusters, edges)
    cnodes = spiral_map(list(clusters), vol, width, height)
    tmap = {t: cnodes[c] for c, ts in clusters.items() for t in ts}
    return {"criterion": criterion, "rows": rows, "clusters": clusters, "volumes": vol,
            "cluster_nodes": cnodes, "mapping": tmap}


def from_orca(graph):
    """(tasks, edges) of a graph read by rttools.gff.orca.import_graph
    (the .txt format of apps/, e.g. apps/synthetic-app-e/synthetic-app-e.txt)."""
    tasks = [(n._data["label"], int(n._data["wcet"])) for n in graph._nodes]
    edges = [(e._from._data["label"], e._to._data["label"], int(e._data["payload"])) for e in graph._edges]
    return tasks, edges


def from_networkx(app):
    """(tasks, edges) of an application graph read by
    rttools.modules.io.appparser (node attribute wcet, edge attribute
    datasize). The edges follow the flow order of the file (labels f1,
    f2, ...), which decides the ties of ORT/GCM; networkx lists them by
    source node."""
    tasks = [(n, int(d["wcet"])) for n, d in app.nodes(data=True)]

    def flow_index(e):
        label = str(e[2].get("label", ""))
        return int(label[1:]) if label[:1] == "f" and label[1:].isdigit() else 0
    edges = [(a, b, int(d["datasize"])) for a, b, d in sorted(app.edges(data=True), key=flow_index)]
    return tasks, edges
