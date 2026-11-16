"""Clustering of CAR on 16 clusters and choice of the criterion for
application E (Sec. 7.2 and 7.4 of the article).

    python -m rttools.paper.car --config <car.json> --apps <apps dir> --out <dir>

CAR (apps/shi-2010/shi-2010.txt): metrics of the reference mapping of
Shi et al. (the tasks of each core merged into one cluster) and of the
output of GraphICC.collapse (rttools/gcm) until |V| = 16 for each
criterion. Application E (apps/synthetic-app-e/synthetic-app-e.txt):
the same metrics for |V| = 4; the chosen criterion is the one with the
lowest M2.

M1, M2, M3 are the functions of rttools/gde that reproduce the table of the random graphs
(population standard deviations; parallel edges between two clusters
count as separate edges). NoC volume is the sum of the inter-cluster edge
values; load is the sum of the WCETs of a cluster divided by the cycles
of the hyperperiod (config: load_capacity_cycles).

Spiral Mapping of CAR (Sec. 6.2, config key "spiral"): steps 1 and 2 of
the analysis flow (rttools.modules.mapping.spiral.map_application) on the
mesh of the config; per position k of the spiral: node, tile (x, y), mean
XY distance from the node to the other nodes, cluster, tasks and network
volume. Placement cost: sum over the inter-cluster edges of payload times
XY hops, for the Spiral, for the reversed spiral (the k-th smallest volume
on position n + 1 - k) and for random placements (random.Random(seed),
one random.sample of the nodes per placement, clusters in step-1 order);
share of the volume on the nodes off the outer ring.

Outputs: metrics.json, car.csv, appe.csv, tab-car-rows.tex (rows of the
table of the article, in its column order), spiral.csv (one row per
position), spiral-edges.csv (inter-cluster edges with hops) and values.tex
(LaTeX macros ExpCarSpiral... for the text).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import statistics
import sys

from rttools.gcm.gicc import CriteriaICC, GraphICC
from rttools.gde import __main__ as gde
from rttools.gsl.graph import Graph, GraphEdge, GraphNode
from rttools.modules.mapping import spiral as sm
from rttools.paper.ch7 import load_graph

NAMES = {"MAX_PROC": "MAX-PROC", "MIN_PROC": "MIN-PROC", "MAX_COMM": "MAX-COMM", "MIN_COMM": "MIN-COMM"}


def read_map(path):
    """Mapping file `<core>:<task>,<task>` -> {task: core}."""
    core = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c, tasks = line.split(":")
            for t in tasks.split(","):
                core[t.strip()] = int(c)
    return core


def merge_by_map(g, core):
    """Graph with one vertex per core (WCETs summed, labels joined with
    ':') and the edges between different cores; returns the graph and the
    volume of the edges inside a core."""
    h = Graph()
    cluster = {}
    for c in sorted(set(core.values())):
        members = [v for v in g._nodes if core[v._data["label"]] == c]
        v = GraphNode(h.get_new_id(), {"label": ":".join(m._data["label"] for m in members),
                                       "wcet": str(sum(int(m._data["wcet"]) for m in members))})
        h._nodes.append(v)
        for m in members:
            cluster[m._data["label"]] = v
    intra = 0
    for e in g._edges:
        a, b = cluster[e._from._data["label"]], cluster[e._to._data["label"]]
        if a is b:
            intra += int(e._data["payload"])
            continue
        h._edges.append(GraphEdge(h.get_new_id(), dict(e._data), a, b))
    return h, intra


def contract(path, criterion, n):
    g = load_graph(path)
    crit = getattr(CriteriaICC, criterion)
    steps = 0
    while len(g._nodes) > n:
        g = GraphICC.collapse(g, crit)
        steps += 1
    return g, steps


def summary(g, total_volume, capacity=None):
    loads = sorted(((int(v._data["wcet"]), v._data["label"]) for v in g._nodes), key=lambda x: (-x[0], x[1]))
    pairs = {(e._from._data["label"], e._to._data["label"]) for e in g._edges}
    volume = sum(int(e._data["payload"]) for e in g._edges)
    r = {"V": len(g._nodes), "E": len(g._edges), "E_pairs": len(pairs),
         "M1": gde.edge_standard_deviation(g), "M2": gde.node_standard_deviation(g),
         "M3": gde.node_edge_rate(g),
         "noc_volume": volume, "noc_volume_percent": 100 * volume / total_volume,
         "largest_load": loads[0][0], "smallest_load": loads[-1][0],
         "clusters": [{"tasks": lab.split(":"), "load": w} for w, lab in loads]}
    if capacity:
        r["largest_load_percent"] = 100 * loads[0][0] / capacity
        r["loads_above_capacity"] = sum(1 for w, _ in loads if w > capacity)
    return r


def run_car(cfg, apps):
    path = os.path.join(apps, cfg["graph"])
    cap = cfg["load_capacity_cycles"]
    g = load_graph(path)
    total = sum(int(e._data["payload"]) for e in g._edges)
    out = {"input": summary(g, total, cap), "total_volume": total, "n": cfg["n"], "rows": {}}
    h, intra = merge_by_map(g, read_map(os.path.join(apps, cfg["reference_map"])))
    out["rows"]["Reference"] = dict(summary(h, total, cap), intra_volume=intra, contractions=0)
    for crit in cfg["criteria"]:
        c, steps = contract(path, crit, cfg["n"])
        out["rows"][crit] = dict(summary(c, total, cap), contractions=steps)
    return out


def run_appe(cfg, apps):
    path = os.path.join(apps, cfg["graph"])
    g = load_graph(path)
    total = sum(int(e._data["payload"]) for e in g._edges)
    out = {"input": summary(g, total), "total_volume": total, "n": cfg["n"], "rows": {}}
    for crit in cfg["criteria"]:
        c, steps = contract(path, crit, cfg["n"])
        out["rows"][crit] = dict(summary(c, total), contractions=steps)
    out["chosen"] = min(cfg["criteria"], key=lambda k: out["rows"][k]["M2"])
    return out


def xy(node, width):
    return node % width, node // width


def hops(a, b, width):
    """XY hops between node indices a and b (y * width + x)."""
    (xa, ya), (xb, yb) = xy(a, width), xy(b, width)
    return abs(xa - xb) + abs(ya - yb)


def mean_xy(node, width, height):
    """Mean XY distance from `node` to the other nodes of the mesh."""
    n = width * height
    return sum(hops(node, m, width) for m in range(n) if m != node) / (n - 1)


def outer_ring(node, width, height):
    x, y = xy(node, width)
    return x in (0, width - 1) or y in (0, height - 1)


def placement_cost(inter, place, width):
    """Sum of payload times XY hops over the inter-cluster edges
    (cluster a, cluster b, payload) for the placement cluster -> node."""
    return sum(p * hops(place[a], place[b], width) for a, b, p in inter)


def run_spiral(cfg, apps):
    """Spiral Mapping of CAR on the mesh of cfg (graph, width, height,
    permutations, seed)."""
    w, h = cfg["width"], cfg["height"]
    tasks, edges = sm.from_orca(load_graph(os.path.join(apps, cfg["graph"])))
    r = sm.map_application(tasks, edges, w, h)
    clusters, vol, cn = r["clusters"], r["volumes"], r["cluster_nodes"]
    wcet = dict(tasks)
    owner = {t: c for c, ts in clusters.items() for t in ts}
    inter = [(owner[a], owner[b], p) for a, b, p in edges if owner[a] != owner[b]]
    order = sm.spiral_order(w, h)
    pos = {node: k + 1 for k, node in enumerate(order)}
    rows = []
    for c in sorted(cn, key=lambda c: pos[cn[c]]):
        node = cn[c]
        x, y = xy(node, w)
        rows.append({"position": pos[node], "node": node, "x": x, "y": y,
                     "mean_xy": mean_xy(node, w, h), "outer_ring": outer_ring(node, w, h),
                     "cluster": c, "tasks": clusters[c], "volume": vol[c],
                     "demand": sum(wcet[t] for t in clusters[c]),
                     "inter_edges": sum(1 for a, b, _ in inter if c in (a, b))})
    total = sum(vol.values())
    w_noc = sum(p for _, _, p in inter)
    inner = sum(row["volume"] for row in rows if not row["outer_ring"])
    cost = placement_cost(inter, cn, w)
    ranked = [row["cluster"] for row in rows]
    reverse = {c: order[len(ranked) - 1 - k] for k, c in enumerate(ranked)}
    rng = random.Random(cfg["seed"])
    step1 = list(clusters)
    vals = sorted(placement_cost(inter, dict(zip(step1, rng.sample(range(w * h), len(step1)))), w)
                  for _ in range(cfg["permutations"]))
    median = statistics.median(vals)
    median = int(median) if float(median).is_integer() else median
    dist = {"outer": [row["mean_xy"] for row in rows if row["outer_ring"]],
            "inner": [row["mean_xy"] for row in rows if not row["outer_ring"]]}
    return {
        "graph": cfg["graph"], "width": w, "height": h, "criterion": r["criterion"],
        "step1_sigma": {row["criterion"]: row["sigma"] for row in r["rows"]},
        "order": order, "rows": rows,
        "edges": [{"source": a, "target": b, "payload": p, "source_node": cn[a], "target_node": cn[b],
                   "hops": hops(cn[a], cn[b], w)} for a, b, p in inter],
        "volume_sum": total, "w_noc": w_noc,
        "inner_nodes": sorted(row["node"] for row in rows if not row["outer_ring"]),
        "inner_volume": inner, "inner_volume_percent": 100 * inner / total,
        "mean_xy": {k: {"min": min(v), "max": max(v)} for k, v in dist.items() if v},
        "payload_hops": {
            "spiral": cost, "spiral_mean_hops": cost / w_noc,
            "reverse_spiral": placement_cost(inter, reverse, w),
            "random": {"permutations": cfg["permutations"], "seed": cfg["seed"], "min": vals[0],
                       "median": median, "max": vals[-1],
                       "below_spiral": sum(1 for v in vals if v < cost),
                       "equal_spiral": sum(1 for v in vals if v == cost)}},
    }


def write_spiral(out_dir, s):
    """spiral.csv, spiral-edges.csv and values.tex of the Spiral Mapping."""
    from rttools.paper.exp23 import fmt_int, macro_name
    cols = ["position", "node", "x", "y", "mean_xy", "outer_ring", "cluster", "volume", "demand", "inter_edges"]
    with open(os.path.join(out_dir, "spiral.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols + ["tasks"])
        for row in s["rows"]:
            w.writerow([row[c] for c in cols] + [" ".join(row["tasks"])])
    cols = ["source", "target", "payload", "source_node", "target_node", "hops"]
    with open(os.path.join(out_dir, "spiral-edges.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for e in s["edges"]:
            w.writerow([e[c] for c in cols])
    ph, rnd = s["payload_hops"], s["payload_hops"]["random"]
    vals = [("criterion", NAMES.get(s["criterion"], s["criterion"])),
            ("mesh", f"\\ensuremath{{{s['width']}\\times{s['height']}}}"),
            ("volume sum", fmt_int(s["volume_sum"])), ("w noc", fmt_int(s["w_noc"])),
            ("inner volume", fmt_int(s["inner_volume"])),
            ("inner volume percent", f"{s['inner_volume_percent']:.1f}"),
            ("payload hops", fmt_int(ph["spiral"])), ("mean hops", f"{ph['spiral_mean_hops']:.2f}"),
            ("reverse payload hops", fmt_int(ph["reverse_spiral"])),
            ("random permutations", fmt_int(rnd["permutations"])), ("random seed", str(rnd["seed"])),
            ("random min", fmt_int(rnd["min"])), ("random median", fmt_int(rnd["median"])),
            ("random max", fmt_int(rnd["max"])), ("random below", fmt_int(rnd["below_spiral"]))]
    for ring, d in s["mean_xy"].items():
        vals += [(f"mean xy {ring} min", f"{d['min']:.2f}"), (f"mean xy {ring} max", f"{d['max']:.2f}")]
    lines = ["% generated by python -m rttools.paper.car; do not edit"]
    lines += [f"\\newcommand{{\\{macro_name('car', 'spiral', *k.split())}}}{{{v}}}" for k, v in vals]
    with open(os.path.join(out_dir, "values.tex"), "w") as f:
        f.write("\n".join(lines) + "\n")


def num(x, d=0):
    return f"{x:,.{d}f}"


def tab_rows(car, order):
    """Rows of the CAR table: clustering, inter-cluster edges, NoC volume
    (%), M1, M2, M3, largest load (%), loads above 100 %."""
    lines = []
    for key in order:
        r = car["rows"][key]
        m2 = f"{r['M2']:.2f}" if r["M2"] < 10 else num(r["M2"])
        cells = [NAMES.get(key, key), str(r["E"]), f"{r['noc_volume_percent']:.1f}", num(r["M1"]), m2,
                 f"{r['M3']:.3f}", f"{r['largest_load_percent']:.1f}", str(r["loads_above_capacity"])]
        lines.append(" & ".join(cells) + r" \\")
    return lines


def write(out_dir, car, appe, cfg, spiral=None):
    os.makedirs(out_dir, exist_ok=True)
    m = {"car": car, "appe": appe}
    if spiral is not None:
        m["spiral"] = spiral
        write_spiral(out_dir, spiral)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
    cols = ["clustering", "V", "E", "E_pairs", "noc_volume", "noc_volume_percent", "M1", "M2", "M3",
            "largest_load", "largest_load_percent", "loads_above_capacity", "contractions"]
    with open(os.path.join(out_dir, "car.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for k, r in car["rows"].items():
            w.writerow([k] + [r.get(c) for c in cols[1:]])
    cols = ["criterion", "V", "E", "noc_volume", "noc_volume_percent", "M1", "M2", "M3", "largest_load",
            "clusters", "chosen"]
    with open(os.path.join(out_dir, "appe.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for k, r in appe["rows"].items():
            cl = " ".join("".join(sorted(c["tasks"])) + "=" + str(c["load"]) for c in r["clusters"])
            w.writerow([k] + [r[c] for c in cols[1:-2]] + [cl, k == appe["chosen"]])
    with open(os.path.join(out_dir, "tab-car-rows.tex"), "w") as f:
        f.write("% generated by python -m rttools.paper.car; do not edit\n")
        f.write("\n".join(tab_rows(car, cfg["car"]["table"])) + "\n")
    return m


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.car", description=__doc__.split("\n\n")[0])
    p.add_argument("--config", required=True)
    p.add_argument("--apps", required=True, help="directory apps/ of the repository")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    with open(a.config) as f:
        cfg = json.load(f)
    car = run_car(cfg["car"], a.apps)
    appe = run_appe(cfg["appe"], a.apps)
    spiral = run_spiral(cfg["spiral"], a.apps) if "spiral" in cfg else None
    write(a.out, car, appe, cfg, spiral)
    print(f"CAR ({car['input']['V']} tasks, {car['input']['E']} edges, volume {car['total_volume']:,}) "
          f"on {car['n']} clusters")
    for k, r in car["rows"].items():
        print(f"  {k:9s} |E| {r['E']:3d}  NoC {r['noc_volume_percent']:6.2f}%  M1 {r['M1']:12.2f}  "
              f"M2 {r['M2']:13.2f}  M3 {r['M3']:7.3f}  largest {r['largest_load_percent']:6.1f}%  "
              f"above 100% {r['loads_above_capacity']}")
    print(f"application E on {appe['n']} clusters")
    for k, r in appe["rows"].items():
        cl = ", ".join("".join(sorted(c["tasks"])) + f" {c['load']}" for c in r["clusters"])
        print(f"  {k:9s} M2 {r['M2']:10.2f}  NoC {r['noc_volume']} ({r['noc_volume_percent']:.1f}%)  {cl}")
    print(f"  chosen (lowest M2): {appe['chosen']}")
    if spiral is not None:
        s = spiral
        print(f"Spiral Mapping of CAR on {s['width']}x{s['height']} (step 1: {s['criterion']})")
        for row in s["rows"]:
            print(f"  k {row['position']:2d}  node {row['node']:2d} ({row['x']},{row['y']})  mean XY "
                  f"{row['mean_xy']:.3f}  volume {row['volume']:8d}  {row['cluster']}")
        ph, rnd = s["payload_hops"], s["payload_hops"]["random"]
        print(f"  volume {s['volume_sum']:,} (W_NoC {s['w_noc']:,}); inner nodes {s['inner_volume']:,} "
              f"({s['inner_volume_percent']:.1f}%)")
        print(f"  payload x hops: spiral {ph['spiral']:,} (mean {ph['spiral_mean_hops']:.4f} hops), reversed "
              f"{ph['reverse_spiral']:,}, {rnd['permutations']} random (seed {rnd['seed']}): min {rnd['min']:,} "
              f"median {rnd['median']:,} max {rnd['max']:,}, {rnd['below_spiral']} below the spiral")
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
