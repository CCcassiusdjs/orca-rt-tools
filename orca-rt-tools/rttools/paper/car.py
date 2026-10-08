"""Clustering of CAR on 16 clusters and choice of the criterion for
application E (Sec. 7.2 and 7.4 of the article).

    python -m rttools.paper.car --config <car.json> --apps <apps dir> --out <dir>

CAR (apps/shi-2010/shi-2010.txt): metrics of the reference mapping of
Shi et al. (the tasks of each core merged into one cluster) and of the
output of GraphICC.collapse (rttools/gcm) until |V| = 16 for each
criterion. Application E (apps/synthetic-app-e/synthetic-app-e.txt):
the same metrics for |V| = 4; the chosen criterion is the one with the
lowest M2.

M1, M2, M3 are the functions of rttools/gde that reproduce Table 7.1
(population standard deviations; parallel edges between two clusters
count as separate edges). NoC volume is the sum of the inter-cluster edge
values; load is the sum of the WCETs of a cluster divided by the cycles
of the hyperperiod (config: load_capacity_cycles).

Outputs: metrics.json, car.csv, appe.csv and tab-car-rows.tex (rows of
the table of the article, in its column order).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

from rttools.gcm.gicc import CriteriaICC, GraphICC
from rttools.gde import __main__ as gde
from rttools.gsl.graph import Graph, GraphEdge, GraphNode
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


def write(out_dir, car, appe, cfg):
    os.makedirs(out_dir, exist_ok=True)
    m = {"car": car, "appe": appe}
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
    write(a.out, car, appe, cfg)
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
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
