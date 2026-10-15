"""Workloads in which the links set f_NoC (experiments/linkload): the
applications E and CAR-V of experiments/tt/config.json with the payload of
every flow multiplied by a factor, analysis only.

For each application and factor: f_CPU; the minimum frequency of the flow
(the model of the runs) and with the links alone (w_h = 0, w_NI = 0, no
handler charge: o_i = L0, the network interfaces stay resources of AGS);
the lowest frequency at which every packet alone fits its window
(F(u) + o_i <= a_{i,j} with the links alone, bisection to 5 kHz); the
number of packets between PEs; and the time of the search. A minimum of the
links above both f_CPU and the isolated frequency comes from the contention
of packets on links and network interfaces, which AGS separates.

    python -m rttools.paper.linkload run --config experiments/linkload/config.json --out <dir>
    python -m rttools.paper.linkload check <dir>/metrics.json experiments/linkload/reference.json
"""
import argparse
import json
import os
import re
import sys
import time

from rttools.modules.instances import instantiator
from rttools.modules.unwrapper import flowUnwrapper
from rttools.paper import ablation, cputime, ttflow
from rttools.tui.model import network as tnet


def scaled_csv(src, factor, out):
    """Copy of the application file `src` with the Data column of every flow
    row multiplied by `factor`."""
    rows, section = [], None
    with open(src) as fh:
        for line in fh.read().split("\n"):
            if line.startswith("#tasks"):
                section = "tasks"
            elif line.startswith("#flows"):
                section = "flows"
            elif line.startswith("#parameters"):
                section = "parameters"
            elif section == "flows" and re.match(r"^\d+,", line):
                f = line.split(",")
                f[2] = str(int(f[2]) * factor)
                line = ",".join(f)
            rows.append(line)
    with open(out, "w") as fh:
        fh.write("\n".join(rows))
    return out


def isolated(a, lo=1e8, hi=2e9, tol=5e3):
    """Lowest frequency (Hz, bisection) at which every packet between PEs
    alone fits its window with the occupancy of the links alone."""
    g, _, noc, entries, _ = ttflow.load_app(a["csv"], a["map"], a["arch"], a["costs"])

    def ok(f):
        with tnet.quiet():
            pk, _, _ = flowUnwrapper.unwrap(instantiator.createInstance(g, noc, f), noc, entries)
        return all(p["min_start"] + p["net_time"] <= p["abs_deadline"] for p in pk if len(p["path"]) >= 2)
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if ok(mid) else (mid, hi)
    return hi


def packets(a, f):
    g, _, noc, entries, _ = ttflow.load_app(a["csv"], a["map"], a["arch"], a["costs"])
    with tnet.quiet():
        pk, _, _ = flowUnwrapper.unwrap(instantiator.createInstance(g, noc, f), noc, entries)
    return sum(1 for p in pk if len(p["path"]) >= 2)


def run(cfg_path, out_dir):
    base = os.path.dirname(os.path.abspath(cfg_path))
    own = json.load(open(cfg_path))
    apps = ttflow.load_config(os.path.join(base, own["include"]))["apps"]
    os.makedirs(out_dir, exist_ok=True)
    out = {"_doc": "rttools.paper.linkload run --config " + os.path.basename(cfg_path), "apps": {}}
    timing = {}
    for name, factors in own["factors"].items():
        rows = {}
        for k in factors:
            a = dict(apps[name])
            a["csv"] = scaled_csv(a["csv"], k, os.path.join(out_dir, f"{name}-x{k}.csv"))
            row = {}
            for s in ("flow", "links_only"):
                t = time.time()
                with ablation.setting(ablation.SETTINGS[s]):
                    f = ablation._single(a)
                timing[f"{name} x{k} {s}"] = round(time.time() - t, 2)
                row[s] = {"f_cpu_hz": f["f_cpu_hz"], "minimum_hz": f["frequency_hz"]}
            with ablation.setting(ablation.SETTINGS["links_only"]):
                row["isolated_hz"] = isolated(a)
                row["packets"] = packets(a, row["links_only"]["minimum_hz"])
            f_l = row["links_only"]["minimum_hz"]
            row["links_bind"] = f_l > max(row["flow"]["f_cpu_hz"], row["isolated_hz"]) + 5e3
            rows[str(k)] = row
        out["apps"][name] = rows
    with open(os.path.join(out_dir, "metrics.json"), "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    with open(os.path.join(out_dir, "timing.json"), "w") as fh:
        json.dump(timing, fh, indent=1)
    return out, timing


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rttools.paper.linkload")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        m, timing = run(args.config, args.out)
        for name, rows in m["apps"].items():
            for k, r in rows.items():
                print(f"{name} x{k}: f_CPU {r['flow']['f_cpu_hz'] / 1e6:.3f}, flow {r['flow']['minimum_hz'] / 1e6:.3f}, "
                      f"links {r['links_only']['minimum_hz'] / 1e6:.3f}, isolated {r['isolated_hz'] / 1e6:.3f} MHz, "
                      f"{r['packets']} packets, links bind: {r['links_bind']}")
        print("time (s):", timing)
        return 0
    return 0 if cputime.check(args.metrics, args.reference) else 1


if __name__ == "__main__":
    sys.exit(main())
