"""Reproduction of the table of the random graphs (ORT/GCM and ORT/GDE, Ch. 7).

    python -m rttools.paper.ch7 run --config <config.json> --graphs <dir> --out <dir> [--sizes 20,30] [--n 4]
    python -m rttools.paper.ch7 check <dir>/metrics.json <reference.json>

For each input graph (graphs/10_<|V|>.txt, ORCA format) the tool computes
|E|, M1 (population standard deviation of the edge values), M2 (of the
vertex values) and M3 (sum of vertex values / sum of edge values) with the
functions of rttools/gde, collapses the graph with GraphICC.collapse
(rttools/gcm) until |V| <= N for MIN_COMM and MAX_PROC, and computes the
same metrics on the result.

Comparison with the printed table, in the form the table uses: |E| exact;
M1, M2 and M3 of the input with 3 decimals (rows 1 to 15 truncate, rows
16 and 17 round); M1 and M2 of the
outputs truncated to integers (the note of the table says "rounded up");
M3 of the outputs rounded to 3 decimals.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time

from rttools.gcm.gicc import CriteriaICC, GraphICC
from rttools.gde import __main__ as gde
from rttools.gsl.graph import Graph, GraphEdge, GraphNode
from rttools.paper.exp23 import check as check_metrics

CRITERIA = (("mc", "MIN_COMM"), ("mp", "MAX_PROC"))


def load_graph(path):
    """Same result as rttools.gff.orca.import_graph (first node with a
    label wins), with a dictionary instead of a linear search per edge."""
    g = Graph()
    state = 1
    idx = {}
    with open(path) as f:
        for line in f:
            if line.strip() == "":
                continue
            if state == 1:
                if line.startswith("#"):
                    state = 2
            elif state == 2:
                if line.startswith("#"):
                    state = 3
                else:
                    v = line.split()
                    n = GraphNode(g.get_new_id(), {"label": v[0], "wcet": v[1]})
                    g._nodes.append(n)
                    idx.setdefault(v[0], n)
            else:
                v = line.split()
                g._edges.append(GraphEdge(g.get_new_id(), {"label": v[0] + "-" + v[1], "payload": v[2]},
                                          idx[v[0]], idx[v[1]]))
    return g


def measure(g):
    return {"E": len(g._edges), "V": len(g._nodes), "M1": gde.edge_standard_deviation(g),
            "M2": gde.node_standard_deviation(g), "M3": gde.node_edge_rate(g)}


def collapse(path, criterion, n):
    g = load_graph(path)
    crit = getattr(CriteriaICC, criterion)
    while len(g._nodes) > n:
        g = GraphICC.collapse(g, crit)
    return g


def cluster_sizes(g):
    """Number of input vertices in each cluster of a collapsed graph,
    ascending (GraphICC.collapse joins the labels with ':')."""
    return sorted(len(str(v._data["label"]).split(":")) for v in g._nodes)


def trunc(x, digits):
    k = 10 ** digits
    return math.floor(x * k + 1e-9) / k


def compare_row(calc, th):
    """Cell-by-cell agreement with the printed row."""
    def printed(v, t):
        # rows 1 to 15 of the table truncate the input metrics; rows 16
        # and 17 round them
        return t in (trunc(v, 3), round(v, 3))

    ok = {
        "E": calc["E"] == th["E"],
        "M1": printed(calc["M1"], th["M1"]),
        "M2": printed(calc["M2"], th["M2"]),
        "M3": printed(calc["M3"], th["M3"]),
    }
    for p, _ in CRITERIA:
        c = calc[p]
        ok[p + "_E"] = c["E"] == th[p + "_E"]
        ok[p + "_M1"] = math.floor(c["M1"]) == th[p + "_M1"]
        ok[p + "_M2"] = math.floor(c["M2"]) == th[p + "_M2"]
        ok[p + "_M3"] = round(c["M3"], 3) == th[p + "_M3"]
    return ok


def run(cfg, graphs_dir, out_dir, sizes=None, n=None):
    n = n or cfg["n"]
    sizes = sizes or cfg["sizes"]
    thesis = {r["V"]: r for r in cfg["thesis_rows"]}
    rows = []
    for size in sizes:
        path = os.path.join(graphs_dir, f"10_{size}.txt")
        t0 = time.time()
        calc = measure(load_graph(path))
        for p, crit in CRITERIA:
            g = collapse(path, crit, n)
            calc[p] = measure(g)
            calc[p]["cluster_sizes"] = cluster_sizes(g)
        calc["seconds"] = round(time.time() - t0, 2)
        th = thesis.get(size)
        agree = compare_row(calc, th) if th and n == cfg["n"] else None
        rows.append({"V": size, "calc": calc, "thesis": th, "agree": agree,
                     "all_agree": None if agree is None else all(agree.values())})
    m = {"n": n, "rows": rows,
         "summary": {"rows": len(rows), "rows_agree": sum(1 for r in rows if r["all_agree"]),
                     "cells_agree": sum(sum(r["agree"].values()) for r in rows if r["agree"]),
                     "cells": sum(len(r["agree"]) for r in rows if r["agree"])}}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
    write_table(m, os.path.join(out_dir, "tab71"))
    return m


def write_table(m, base):
    import csv
    cols = ["V", "E", "M1", "M2", "M3", "mc_E", "mc_M1", "mc_M2", "mc_M3", "mp_E", "mp_M1", "mp_M2", "mp_M3"]

    def cells(r):
        c = r["calc"]
        return [r["V"], c["E"], trunc(c["M1"], 3), trunc(c["M2"], 3), trunc(c["M3"], 3),
                c["mc"]["E"], math.floor(c["mc"]["M1"]), math.floor(c["mc"]["M2"]), round(c["mc"]["M3"], 3),
                c["mp"]["E"], math.floor(c["mp"]["M1"]), math.floor(c["mp"]["M2"]), round(c["mp"]["M3"], 3)]

    with open(base + ".csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols + ["agrees_with_thesis"])
        for r in m["rows"]:
            w.writerow(cells(r) + [r["all_agree"]])
    with open(base + ".tex", "w") as f:
        f.write("% generated by python -m rttools.paper.ch7; do not edit\n")
        f.write("\\begin{table}[t]\n\\centering\n")
        f.write(f"\\caption{{Input graphs and graphs collapsed to $N = {m['n']}$ by MIN-COMM and MAX-PROC "
                "(M1 and M2 of the outputs truncated to integers).}\n\\label{tab:ch7-gcm}\n")
        f.write("\\begin{tabular}{rrrrr|rrrr|rrrr}\n\\toprule\n")
        f.write("\\multicolumn{5}{c|}{Input} & \\multicolumn{4}{c|}{MIN-COMM} & \\multicolumn{4}{c}{MAX-PROC} \\\\\n")
        f.write("$|V|$ & $|E|$ & M1 & M2 & M3 & $|E|$ & M1 & M2 & M3 & $|E|$ & M1 & M2 & M3 \\\\\n\\midrule\n")
        for r in m["rows"]:
            out = []
            for v in cells(r):
                if isinstance(v, float):
                    out.append(f"{v:.3f}")
                else:
                    out.append(f"{v:,}".replace(",", "\\,"))
            f.write(" & ".join(out) + " \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.ch7", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--graphs", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--sizes", default=None, help="comma-separated |V| values (default: config sizes)")
    r.add_argument("--n", type=int, default=None, help="target number of clusters (default: config n)")
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    a = p.parse_args(argv)
    if a.cmd == "run":
        with open(a.config) as f:
            cfg = json.load(f)
        sizes = [int(x) for x in a.sizes.split(",")] if a.sizes else None
        m = run(cfg, a.graphs, a.out, sizes, a.n)
        for row in m["rows"]:
            c = row["calc"]
            print(f"|V| {row['V']:4d} |E| {c['E']:7d}  MIN_COMM |E| {c['mc']['E']:6d}  MAX_PROC |E| {c['mp']['E']:6d}  "
                  f"agrees {row['all_agree']}  {c['seconds']} s", flush=True)
        s = m["summary"]
        if s["cells"]:
            print(f"N = {m['n']}: {s['rows_agree']}/{s['rows']} rows and {s['cells_agree']}/{s['cells']} cells agree")
        else:
            print(f"N = {m['n']}: no comparison (the printed values correspond to N = {cfg['n']})")
        return 0
    diffs = check_metrics(a.metrics, a.reference)
    for d in diffs:
        print(d)
    print("match" if not diffs else f"{len(diffs)} differences")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
