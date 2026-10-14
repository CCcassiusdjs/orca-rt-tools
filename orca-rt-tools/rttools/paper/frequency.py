"""Minimum frequency of application E with the analysis flow of the paper.

    python -m rttools.paper.frequency run --app <app.csv> --arch <arch.gml> --map <file.map|spiral> [--map ...]
        [--f0 <Hz>] [--config <exp23 config.json>] [--header-wait off|bound|<cycles>] [--costs <costs.json>]
        --out <dir>
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

For each mapping (a .map file, or `spiral` for ORT/GCM and the Spiral
Mapping of the command line), the pipeline runs the same steps as
`python -m rttools <app> <map> <arch> <f0>` (rttools/__main__.py, same
search parameters): the CPU test once (f_CPU = max_k c^(V_k) / T,
release.cpu_bound), the bisection of the network schedule (f*) and the
result max(f*, f_CPU) (search.minimum_frequency). When f_CPU > f*, the
network is evaluated once more at f_CPU (final_check: verdict, packets,
skipped packets, hyperperiod); when it is not feasible there, the search
continues above f_CPU and the result is the first feasible frequency.

| File | Content |
|---|---|
| metrics.json | Per mapping: mapping entries, dispatch order per node (phase model), CPU demand per node, f_CPU, f*, the lower bound of the bisection, the attempts, the network check at f_CPU and the minimum frequency |
| frequency.csv | One row per mapping with f*, f_CPU, the verdict of the network at f_CPU and the minimum (Hz) |
| values.tex | LaTeX macros with the frequencies in MHz and the network check at f_CPU |

With --costs (a costs file of rttools.wcet), the pipeline takes the
static t(v) of each task and the dispatch term as scheduler_cycles
(rttools/wcet/costs.py) in place of the Capacity column of the CSV.

With --config (experiments/exp23/config.json), metrics.json also records
whether f_CPU equals the f_CPU of the exp-23 analysis (characterized costs
of the config).

--header-wait selects the header wait w_h per router of the link
occupancy o_i = L0 + w_h (m + 1) (rttools/modules/routing/router.py):
`bound` (w_h = router.HEADER_WAIT_CYCLES = 20, measured by make -C
experiments/zll contention; the default), `off` or 0 (o_i = L0) or a
number of cycles. Without the option, the pipeline uses the selection of
the process (router.header_wait(): environment variable
RTTOOLS_HEADER_WAIT, default bound). metrics.json records w_h in
header_wait_cycles.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

from rttools import __main__ as cli
from rttools.modules.frequency import search
from rttools.modules.instances import release
from rttools.modules.io import appparser, mapparser, nocparser
from rttools.modules.mapping import mapfile, spiral
from rttools.modules.routing import router
from rttools.tui.model import network


def search_config(f0):
    """Search parameters of the command line (rttools/__main__.py)."""
    return {"frequency": f0, "pruning_factor": cli.RTTOOLS_PRUNNING_FACTOR,
            "fail_threshold": cli.RTTOOLS_FAIL_THRESHOULD, "heuristic": cli.RTTOOLS_HEURISTIC,
            "scaling_tolerance": cli.RTTOOLS_SCALING_TOLERANCE}


def mapping_entries(map_arg, app, noc):
    """Entries {"node", "tasks"} of a .map file, or of the Spiral Mapping
    (the steps of cli.load_mapping, without writing the .map file)."""
    if map_arg == cli.MAP_SPIRAL:
        width, height = cli.mesh_size(noc)
        tasks, edges = spiral.from_networkx(app)
        res = spiral.map_application(tasks, edges, width, height)
        return mapfile.from_dict(res["mapping"]), res["criterion"]
    return mapparser.loadFromFile(map_arg), None


def run_one(app_file, map_arg, arch_file, f0, costs=None):
    with network.quiet():
        app, appname = appparser.loadFromFile(app_file)
    if costs is not None:
        # static t(v) of rttools.wcet in place of the Capacity column
        from rttools.wcet import costs as wcosts
        wcosts.apply(app, costs)
    with network.quiet():
        noc = nocparser.loadFromFile(arch_file)
        entries, criterion = mapping_entries(map_arg, app, noc)
    bad = mapfile.problems(entries, list(app.nodes), list(noc.nodes))
    if bad:
        raise ValueError("mapping " + map_arg + ": " + "; ".join(bad))
    with network.quiet():
        res = search.minimum_frequency(app, noc, entries, appname, search_config(f0))
    net = res["network"]
    cpu = res["cpu"]
    rel = release.settings(app.graph)
    seqs = None
    if rel["model"] == release.PHASE:
        seqs = release.pe_sequences(list(app.nodes), list(app.edges()), entries, rel["sequences"], rel["creation"])
    return {
        "map": map_arg if map_arg == cli.MAP_SPIRAL else os.path.basename(map_arg),
        "criterion": criterion,
        "mapping": {str(e["node"]): list(e["tasks"]) for e in entries},
        "sequences": None if seqs is None else {str(k): v for k, v in seqs.items()},
        "cpu_demand_cycles": {str(k): v for k, v in cpu["demand"].items()} if cpu else None,
        "period_s": cpu["period_s"] if cpu else None,
        "f_cpu_hz": res["f_cpu_hz"],
        "f_star_hz": res["f_star_hz"],
        "f_star_lower_hz": net["lower"] if net else None,
        "attempts": [[f, ok, n] for f, ok, n in net["attempts"]] if net else None,
        "final_check": res["final_check"],
        "final_search_attempts": ([[f, ok, n] for f, ok, n in res["final_search"]["attempts"]]
                                  if res["final_search"] else None),
        "frequency_hz": res["frequency_hz"],
        "binding": None if res["frequency_hz"] is None else
        ("cpu" if res["f_cpu_hz"] is not None and res["frequency_hz"] == res["f_cpu_hz"]
         and res["f_cpu_hz"] > res["f_star_hz"] else "network"),
    }


def run(app_file, maps, arch_file, f0, out_dir, config=None, header_wait=None, costs=None):
    """Runs every mapping of `maps`; `header_wait` selects w_h of the link
    occupancy for this run (router.parse_header_wait; None keeps the
    selection of the process); `costs`: costs file of rttools.wcet (static
    t(v), rttools/wcet/costs.py) in place of the costs of the CSV."""
    prev = router.set_header_wait(header_wait) if header_wait is not None else None
    try:
        w = router.header_wait()
        m = {"app": os.path.basename(app_file), "arch": os.path.basename(arch_file), "f0_hz": f0,
             "search": {k: v for k, v in search_config(f0).items() if k != "heuristic"},
             "heuristic": cli.RTTOOLS_HEURISTIC.__name__, "header_wait_cycles": w,
             "occupancy": "L0 + %d (m + 1)" % w if w else "L0", "runs": {}}
        if costs is not None:
            m["costs"] = os.path.basename(costs)
        for mp in maps:
            r = run_one(app_file, mp, arch_file, f0, costs)
            m["runs"][r["map"]] = r
    finally:
        if header_wait is not None:
            router.set_header_wait(prev)
    if config is not None:
        from rttools.paper import exp23
        cfg = exp23.load_config(config)
        f_exp = exp23.cpu_check(cfg, exp23.estimates(cfg))["f_cpu_hz"]
        m["f_cpu_exp23_hz"] = f_exp
        m["f_cpu_equals_exp23"] = all(r["f_cpu_hz"] == f_exp for r in m["runs"].values())
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
    with open(os.path.join(out_dir, "frequency.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["map", "criterion", "f_star_hz", "f_cpu_hz", "network_at_f_cpu", "packets", "skipped",
                    "frequency_hz", "binding"])
        for r in m["runs"].values():
            c = r["final_check"] or {}
            verdict = "" if not c else ("feasible" if c["feasible"] else "not feasible")
            w.writerow([r["map"], r["criterion"] or "", r["f_star_hz"], r["f_cpu_hz"], verdict,
                        c.get("packets", ""), c.get("skipped", ""), r["frequency_hz"], r["binding"]])
    write_values(os.path.join(out_dir, "values.tex"), m)
    return m


def write_values(path, m):
    from rttools.paper.exp23 import macro_name
    lines = ["% generated by python -m rttools.paper.frequency; do not edit",
             f"\\newcommand{{\\{macro_name('frequency', 'header', 'wait', 'cycles')}}}{{{m['header_wait_cycles']}}}"]
    for key, r in m["runs"].items():
        tag = "spiral" if key == cli.MAP_SPIRAL else "map"
        for name, field in (("network", "f_star_hz"), ("cpu", "f_cpu_hz"), ("minimum", "frequency_hz")):
            v = r[field]
            text = "-" if v is None else f"{v / 1e6:.1f}"
            lines.append(f"\\newcommand{{\\{macro_name('frequency', tag, name, 'mhz')}}}{{{text}}}")
        c = r["final_check"]
        verdict = "-" if c is None else ("feasible" if c["feasible"] else "not feasible")
        lines.append(f"\\newcommand{{\\{macro_name('frequency', tag, 'cpu', 'network')}}}{{{verdict}}}")
        for name in ("packets", "skipped"):
            v = "-" if c is None or c[name] is None else str(c[name])
            lines.append(f"\\newcommand{{\\{macro_name('frequency', tag, 'cpu', name)}}}{{{v}}}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def mhz(v):
    return "none" if v is None else f"{v / 1e6:.3f} MHz"


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.frequency", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--app", required=True)
    r.add_argument("--arch", required=True)
    r.add_argument("--map", action="append", required=True, help=".map file or `spiral`; repeat for more")
    r.add_argument("--f0", type=int, default=500000000, help="first frequency of the search (Hz)")
    r.add_argument("--config", default=None, help="experiments/exp23/config.json (f_CPU cross-check)")
    r.add_argument("--header-wait", default=None,
                   help="header wait per router w_h of o_i = L0 + w_h (m + 1): bound (default, "
                        f"{router.HEADER_WAIT_CYCLES} cycles), off or a number of cycles")
    r.add_argument("--costs", default=None,
                   help="costs file of rttools.wcet (static t(v)); default: the Capacity column of the CSV")
    r.add_argument("--out", required=True)
    a = p.parse_args(argv)
    m = run(a.app, a.map, a.arch, a.f0, a.out, a.config, a.header_wait, a.costs)
    print(f"  link occupancy o_i = {m['occupancy']}")
    for key, r in m["runs"].items():
        c = r["final_check"]
        net = "" if c is None else (f"; network at f_CPU {'feasible' if c['feasible'] else 'not feasible'} "
                                    f"({c['packets']} packets, {c['skipped']} skipped)")
        print(f"  {key}: f* {mhz(r['f_star_hz'])} ({len(r['attempts'] or [])} attempts), "
              f"f_CPU {mhz(r['f_cpu_hz'])}{net}, minimum {mhz(r['frequency_hz'])} ({r['binding']})")
    if "f_cpu_equals_exp23" in m:
        print(f"  f_CPU equal to the exp23 analysis ({mhz(m['f_cpu_exp23_hz'])}): {m['f_cpu_equals_exp23']}")
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
