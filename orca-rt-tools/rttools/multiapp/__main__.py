"""Command line of rttools.multiapp (see the package docstring).

    python -m rttools.multiapp <composition.json> [--f0 <Hz>] [--out <dir>]
                               [--costs <application>=<costs.json> ...]

Prints the placement of each application, f_CPU per application, f_NoC of
the union of the packets, the frequency of the platform, the network check
at f_CPU and R_bound of each application at that frequency (with several
release periods or a cycle, the general phase model: the largest data age
over the cause-effect chains of each application). --costs (or the key
"costs" of an application in the composition file) gives the static t(v)
of rttools.wcet: t(v) = max(Capacity column, static t(v)) (rule max of
rttools/wcet/costs.py; the key "cost_rule" of the application selects
another rule). With --out,
writes <dir>/<application>.map (node indices of the mesh) for each
application. Exit status 1 when the composition has a mapping problem or
the flow finds no frequency.
"""
from __future__ import annotations

import argparse
import os
import sys

from rttools.modules.mapping import mapfile
from rttools.multiapp import compose


def hz(v):
    return "none" if v is None else f"{v:.0f} Hz ({v / 1e6:.3f} MHz)"


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m rttools.multiapp", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("composition")
    p.add_argument("--f0", type=int, default=500000000, help="first frequency of the search (Hz)")
    p.add_argument("--out", default=None, help="directory for the .map file of each application")
    p.add_argument("--costs", action="append", default=[], metavar="APP=FILE",
                   help="static t(v) of rttools.wcet for application APP (repeat for several applications)")
    a = p.parse_args(argv)
    costs = {}
    for item in a.costs:
        name, sep, path = item.partition("=")
        if not sep or not name or not path:
            p.error(f"--costs expects APP=FILE, got {item!r}")
        costs[name] = path
    from rttools import __main__ as cli
    from rttools.tui.model import network
    cfg = {"frequency": a.f0, "pruning_factor": cli.RTTOOLS_PRUNNING_FACTOR,
           "fail_threshold": cli.RTTOOLS_FAIL_THRESHOULD, "heuristic": cli.RTTOOLS_HEURISTIC,
           "scaling_tolerance": cli.RTTOOLS_SCALING_TOLERANCE}
    try:
        with network.quiet():
            comp = compose.load(compose.set_costs(compose.read_spec(a.composition), costs))
    except compose.CompositionError as e:
        print("error: " + str(e), file=sys.stderr)
        return 1
    print(f"mesh {comp['width']}x{comp['height']} ({os.path.basename(comp['arch'])})")
    for x in comp["apps"]:
        pl = x["placement"]
        how = pl["method"] if pl["method"] != compose.MAP_SPIRAL else f"spiral, {pl['criterion']}"
        print(f"{x['name']}: {x['pes']} PEs ({how}): "
              + "; ".join(f"{e['node']}:{','.join(e['tasks'])}" for e in x["entries"]))
    try:
        with network.quiet():
            r = compose.minimum_frequency(comp["apps"], comp["noc"], cfg)
    except compose.CompositionError as e:
        print("error: " + str(e), file=sys.stderr)
        return 1
    if r.get("model") == "multirate":
        c = next(iter(r["cpu"].values()))
        print(f"general phase model: phase {c['period_s'] * 1e3:.6g} ms, hyperperiod {c['hyper_s'] * 1e3:.6g} ms")
    for n, f in r["f_cpu_by_app"].items():
        print(f"{n}: f_CPU = {hz(f)}")
    print(f"union: f_NoC = {hz(r['f_star_hz'])}")
    c = r["final_check"]
    if c is not None:
        print(f"network at f_CPU: {'feasible' if c['feasible'] else 'not feasible'} ({c['packets']} packets, "
              f"{c['skipped']} skipped, H = {c['hyperperiod']} cycles)")
    f = r["frequency_hz"]
    print(f"frequency of the platform = {hz(f)}")
    if f is not None:
        with network.quiet():
            rbs = compose.response_bounds(comp["apps"], comp["noc"], f)
        for x in comp["apps"]:
            rb = rbs[x["name"]]
            if rb.get("model") == "multirate":
                print(f"{x['name']}: largest data age = {rb['cycles']} cycles ({rb['s'] * 1e3:.3f} ms), chain "
                      f"{'-'.join(rb['chain'])} ({rb['chains']} chains)")
            else:
                print(f"{x['name']}: R_bound = {rb['cycles']} cycles ({rb['s'] * 1e3:.3f} ms), v_last {rb['v_last']}, "
                      f"n(v_last) = {rb['phase']}")
    if a.out:
        os.makedirs(a.out, exist_ok=True)
        for x in comp["apps"]:
            path = os.path.join(a.out, x["name"] + ".map")
            mapfile.write(path, x["entries"])
            print("wrote " + path)
    return 0 if f is not None else 1


if __name__ == "__main__":
    sys.exit(main())
