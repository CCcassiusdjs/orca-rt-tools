"""Task graphs (ORCA format) for the TUI: GDE metrics, GCPA costs and
critical path, GCM clustering and topological layers."""
from __future__ import annotations

import copy

from rttools.gcm.gicc import CriteriaICC, GraphICC
from rttools.gcpa.method import calculate_gcpa
from rttools.gde import __main__ as gde
from rttools.gff.orca import export_graph, import_graph

CRITERIA = ("MIN_COMM", "MAX_COMM", "MIN_PROC", "MAX_PROC", "MPMC")


def load(path):
    return import_graph(path)


def label(n):
    return n._data["label"]


def metrics(graph):
    """GDE metrics (same functions as `python -m rttools.gde`)."""
    out = {"number_of_vertices": len(graph._nodes), "number_of_edges": len(graph._edges)}
    if len(graph._nodes) > 1:
        out["graph_density"] = gde.edge_density(graph)
    if graph._nodes:
        out["vertices_std_dev"] = gde.node_standard_deviation(graph)
    if graph._edges:
        out["edges_std_dev"] = gde.edge_standard_deviation(graph)
        if sum(int(e._data["payload"]) for e in graph._edges) > 0:
            out["vertex_edge_rating"] = gde.node_edge_rate(graph)
    return out


def preds(graph, n):
    return [e._from for e in graph._edges if e._to is n]


def succs(graph, n):
    return [e._to for e in graph._edges if e._from is n]


def gcpa(graph):
    """GCPA cost of each node (label -> cost) and the critical path that
    ends at the node with the highest cost. GCPA adds, for each node, its
    WCET, the payload of ALL its incoming edges and the highest cost among
    its predecessors (rttools/gcpa/method.py); the path follows that
    predecessor."""
    dct = calculate_gcpa(graph)
    cost = {label(n): c for n, c in dct.items()}
    if not dct:
        return cost, []
    end = max(dct, key=lambda n: dct[n])
    path = [end]
    cur = end
    while True:
        ps = [p for p in preds(graph, cur) if dct.get(p, -1) >= 0]
        if not ps:
            break
        cur = max(ps, key=lambda p: dct[p])
        if cur in path:
            break
        path.append(cur)
    path.reverse()
    return cost, [label(n) for n in path]


def layers(graph):
    """Longest-path layer of each node (sources at layer 0). Nodes in a
    cycle keep the layer reached before the cycle."""
    layer = {n: 0 for n in graph._nodes}
    for _ in range(len(graph._nodes)):
        changed = False
        for e in graph._edges:
            if layer[e._to] < layer[e._from] + 1 and layer[e._from] + 1 < len(graph._nodes):
                layer[e._to] = layer[e._from] + 1
                changed = True
        if not changed:
            break
    out = {}
    for n in graph._nodes:
        out.setdefault(layer[n], []).append(label(n))
    return [out[k] for k in sorted(out)]


def cluster(graph, n_clusters, criterion):
    """GCM clustering (same loop as `python -m rttools.gcm`) on a copy of
    the graph. Returns the clustered graph; node labels join the member
    labels with ':'."""
    g = copy.deepcopy(graph)
    if criterion == "MPMC":
        sub = CriteriaICC.MAX_PROC
        while len(g._nodes) > n_clusters and g._edges:
            g = GraphICC.collapse(g, sub)
            sub = CriteriaICC.MIN_COMM if sub == CriteriaICC.MAX_PROC else CriteriaICC.MAX_PROC
    else:
        crit = getattr(CriteriaICC, criterion)
        while len(g._nodes) > n_clusters and g._edges:
            g = GraphICC.collapse(g, crit)
    return g


def cluster_rows(original, clustered):
    """One row per cluster: members, WCET sum, payload inside the cluster,
    payload in and out of the cluster (edges of the original graph)."""
    owner = {}
    for n in clustered._nodes:
        for m in label(n).split(":"):
            owner[m] = label(n)
    rows = []
    for n in clustered._nodes:
        name = label(n)
        members = name.split(":")
        inner = inn = out = 0
        for e in original._edges:
            a, b = owner.get(label(e._from)), owner.get(label(e._to))
            w = int(e._data["payload"])
            if a == name and b == name:
                inner += w
            elif b == name:
                inn += w
            elif a == name:
                out += w
        rows.append({"cluster": name, "members": members, "wcet": int(n._data["wcet"]),
                     "inner": inner, "in": inn, "out": out})
    return rows


def save(path, graph):
    export_graph(path, graph)
