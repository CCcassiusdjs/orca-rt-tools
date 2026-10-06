"""Reproduction of Tables 6.5, 6.6 and 6.7 (ORT/FNS, Ch. 6).

    python -m rttools.paper.ch6 run --config <config.json> --out <dir> [--apps a,b] [--jobs N]
    python -m rttools.paper.ch6 check <dir>/metrics.json <reference.json>

Tables 6.5 and 6.6 (search effort): the AGS backend on the problem files of
rttools/modules/backend/ags (problem_*.py), for each criterion (LSTF, MBCF,
MCPF) and pruning factor (PF). The threshold equals the PF (Sec. 6.5); for
CAR the PF and the threshold are multiplied by 100. "Visited" is
hsearch.entered and "skipped" is hsearch.ignored (search3.py).

Table 6.7 (minimum frequency): the frequency search of
rttools/modules/frequency/search.py on the application files (CSV, map,
GML), from the start frequency of the config, with the same criteria and
PF values.

Each table puts the thesis value next to the value of the run and marks
the cells that agree.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

from rttools.paper.exp23 import check as check_metrics

HEURISTICS = ("lstf", "mbcf", "mcpf")
AGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modules", "backend", "ags")


def load_problem(name):
    """Problem dict of rttools/modules/backend/ags/<name>.py."""
    path = os.path.normpath(os.path.join(AGS_DIR, name + ".py"))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    p = {k: getattr(mod, k) for k in ("min_start", "occupancy", "deadline", "packets", "links", "hyperperiod")}
    p["packets"] = [{"name": x} if isinstance(x, str) else x for x in p["packets"]]
    return p


def effort(problem_name, heuristic, pf, tries):
    """One AGS run. Returns visited (entered), skipped (ignored), number of
    discarded packets, whether a schedule came out, and the time."""
    from rttools.modules.backend.ags import heuristics, search3
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 100000))
    p = load_problem(problem_name)
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        res = search3.search3(p, getattr(heuristics, heuristic), tries, pf)
    return {"visited": search3.hsearch.entered, "skipped": search3.hsearch.ignored,
            "discarded": None if res is None else len(res[1]), "schedule": res is not None,
            "seconds": round(time.time() - t0, 3)}


def min_frequency(files, heuristic, pf, tries, start, tolerance):
    """Frequency search on the application files."""
    from rttools.modules.backend.ags import heuristics
    from rttools.modules.frequency import search
    from rttools.tui.model.network import load_case, quiet
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 100000))
    case = load_case(*files)
    cfg = {"frequency": start, "pruning_factor": pf, "fail_threshold": tries,
           "heuristic": getattr(heuristics, heuristic), "scaling_tolerance": tolerance}
    t0 = time.time()
    with quiet():
        res = search.search_minimum_frequency(case["app"], case["noc"], case["mapping"], case["appname"], cfg)
    if res is None:
        return {"frequency_hz": None, "attempts": 0, "seconds": round(time.time() - t0, 3)}
    feas = [f for (f, ok, _) in res["attempts"] if ok]
    return {"frequency_hz": res["frequency"], "lowest_feasible_hz": min(feas),
            "attempts": len(res["attempts"]), "seconds": round(time.time() - t0, 3)}


def _job(args):
    kind, payload = args
    if kind == "effort":
        return effort(*payload)
    return min_frequency(*payload)


def agree(thesis, value):
    if thesis is None or value is None:
        return None
    return thesis == value


def run(cfg, out_dir, apps=None, jobs=1, repo_root=None):
    repo_root = repo_root or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                           "..", "..", ".."))
    apps = apps or [a for a, v in cfg["apps"].items() if v.get("default", True)]
    tasks = []
    keys = []
    for app in apps:
        a = cfg["apps"][app]
        for pf in cfg["pruning_factors"]:
            pfx = pf * a.get("pf_multiplier", 1)
            for h in HEURISTICS:
                if a.get("problem"):
                    keys.append(("effort", app, pf, h))
                    tasks.append(("effort", (a["problem"], h, pfx, pfx)))
                if a.get("files"):
                    files = tuple(os.path.join(repo_root, f) for f in a["files"])
                    keys.append(("frequency", app, pf, h))
                    tasks.append(("frequency", (files, h, pfx, pfx, cfg["start_frequency_hz"],
                                                cfg["tolerance_hz"])))
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            results = list(ex.map(_job, tasks))
    else:
        results = [_job(t) for t in tasks]

    rows65, rows66, rows67 = [], [], []
    for (kind, app, pf, h), r in zip(keys, results):
        th = cfg["apps"][app].get("thesis", {})
        if kind == "effort":
            tv = th.get("visited", {}).get(h, {}).get(str(pf))
            ts = th.get("skipped", {}).get(h, {}).get(str(pf))
            rows65.append({"app": app, "pf": pf, "criterion": h.upper(), "thesis": tv, "run": r["visited"],
                           "agrees": agree(tv, r["visited"]), "discarded": r["discarded"], "seconds": r["seconds"]})
            rows66.append({"app": app, "pf": pf, "criterion": h.upper(), "thesis": ts, "run": r["skipped"],
                           "agrees": agree(ts, r["skipped"]), "discarded": r["discarded"], "seconds": r["seconds"]})
        else:
            tf = th.get("frequency", {}).get(h, {}).get(str(pf))
            rows67.append({"app": app, "pf": pf, "criterion": h.upper(), "thesis_printed": tf,
                           "run_hz": r["frequency_hz"], "run_khz": None if r["frequency_hz"] is None
                           else round(r["frequency_hz"] / 1e3, 3),
                           "lowest_feasible_hz": r.get("lowest_feasible_hz"), "attempts": r["attempts"],
                           "seconds": r["seconds"]})
    m = {"apps": apps, "pruning_factors": cfg["pruning_factors"], "tab65": rows65, "tab66": rows66,
         "tab67": rows67,
         "summary": {
             "tab65_agree": sum(1 for r in rows65 if r["agrees"]), "tab65_cells": len(rows65),
             "tab66_agree": sum(1 for r in rows66 if r["agrees"]), "tab66_cells": len(rows66)}}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
    write_tables(m, out_dir)
    return m


def _tex_escape(s):
    return str(s).replace("_", "\\_").replace("%", "\\%")


def write_tables(m, out_dir):
    import csv
    for name, rows, cols, caption in (
        ("tab65", m["tab65"], ("app", "criterion", "pf", "thesis", "run", "agrees", "discarded"),
         "Visited solutions (Table 6.5): thesis and run."),
        ("tab66", m["tab66"], ("app", "criterion", "pf", "thesis", "run", "agrees", "discarded"),
         "Skipped solutions (Table 6.6): thesis and run."),
        ("tab67", m["tab67"], ("app", "criterion", "pf", "thesis_printed", "run_hz", "lowest_feasible_hz",
                               "attempts"),
         "Minimum frequency (Table 6.7): value printed in the thesis (labeled MHz) and frequency of the run in Hz."),
    ):
        with open(os.path.join(out_dir, name + ".csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([r[c] for c in cols])
        with open(os.path.join(out_dir, name + ".tex"), "w") as f:
            f.write("% generated by python -m rttools.paper.ch6; do not edit\n")
            f.write("\\begin{table}[t]\n\\centering\n")
            f.write(f"\\caption{{{caption}}}\n\\label{{tab:ch6-{name}}}\n")
            f.write("\\begin{tabular}{" + "l" * 3 + "r" * (len(cols) - 3) + "}\n\\toprule\n")
            f.write(" & ".join(_tex_escape(c) for c in cols) + " \\\\\n\\midrule\n")
            for r in rows:
                cells = []
                for c in cols:
                    v = r[c]
                    if v is None:
                        cells.append("-")
                    elif isinstance(v, bool):
                        cells.append("yes" if v else "no")
                    elif isinstance(v, float):
                        cells.append(f"{v:,.3f}".replace(",", "\\,"))
                    elif isinstance(v, int):
                        cells.append(f"{v:,}".replace(",", "\\,"))
                    else:
                        cells.append(_tex_escape(v))
                f.write(" & ".join(cells) + " \\\\\n")
            f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.ch6", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--apps", default=None, help="comma-separated keys of config apps (default: the default ones)")
    r.add_argument("--jobs", type=int, default=1)
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    a = p.parse_args(argv)
    if a.cmd == "run":
        with open(a.config) as f:
            cfg = json.load(f)
        m = run(cfg, a.out, a.apps.split(",") if a.apps else None, a.jobs)
        s = m["summary"]
        print(f"apps {', '.join(m['apps'])}: Table 6.5 {s['tab65_agree']}/{s['tab65_cells']} cells agree; "
              f"Table 6.6 {s['tab66_agree']}/{s['tab66_cells']}")
        for r in m["tab67"]:
            print(f"  6.7 {r['app']} {r['criterion']} PF {r['pf']}: thesis {r['thesis_printed']}, "
                  f"run {r['run_hz']} Hz")
        print("wrote " + a.out)
        return 0
    diffs = check_metrics(a.metrics, a.reference)
    for d in diffs:
        print(d)
    print("match" if not diffs else f"{len(diffs)} differences")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
