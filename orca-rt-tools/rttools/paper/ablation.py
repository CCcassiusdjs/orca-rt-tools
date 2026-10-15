"""Ablation of the terms of the analysis flow and a baseline with
event-triggered injection (experiments/ablation).

For each application of experiments/tt/config.json (the models of the runs of
round r11g), the minimum frequency of the flow (search.minimum_frequency,
compose.minimum_frequency) under each setting:

| Setting | Model |
|---|---|
| flow | the model of the runs: w_h = 20, the network interface as a resource with w_NI = 15,169, the handlers of Eq. (9) |
| no_wh | w_h = 0 |
| no_wni | w_NI = 0 (the network interface of each PE stays a resource of the link schedule, which keeps the deadline model tick and the handlers of Eq. (9)) |
| no_handlers | no handler charge of Eq. (9) (no handlers file) |
| links_only | the three removed: o_i = L0 |
| event_triggered | single-period applications: no link schedule; each packet enters the NoC when its job sends it, and a candidate is feasible when F(u) + WCTT_i <= a_{i,j} for every packet (rttools/modules/routing/wctt.py) and every task ends within its phase with the handlers |

Skew (single-period applications, at the clock of the run: the lowest clock at or above the minimum whose phase is
a whole number of 16-cycle steps): the largest skew between the ticks of two PEs that the link schedule tolerates
(skew_tolerance); and the minimum frequency with a bound sigma on the skew added to w_NI (skew_sigma_cycles of the
config), which keeps every reservation of a packet sigma cycles apart from the reservations of the packets of other
PEs and every arrival sigma cycles before its deadline.

Deadline sweep (deadline_sweep_s of the config: application -> list of D in s): the minimum frequency with
the end-to-end deadline D of every task set to each value (the search requires n(v) P + F(v) <= D,
release.deadline_fits), and R_bound at that frequency.

    python -m rttools.paper.ablation run --config experiments/ablation/config.json --out <dir>
    python -m rttools.paper.ablation check <dir>/metrics.json experiments/ablation/reference.json
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys

from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.routing import router, wctt
from rttools.modules.unwrapper import flowUnwrapper
from rttools.paper import cputime, ttflow
from rttools.paper.frequency import search_config
from rttools.tui.model import network as tnet
from rttools.wcet import costs as wcosts

SETTINGS = {
    "flow": {"wait": "bound", "ni": "tt", "handlers": True},
    "no_wh": {"wait": 0, "ni": "tt", "handlers": True},
    "no_wni": {"wait": "bound", "ni": (True, 0), "handlers": True},
    "no_handlers": {"wait": "bound", "ni": "tt", "handlers": False},
    "links_only": {"wait": 0, "ni": (True, 0), "handlers": False},
}


@contextlib.contextmanager
def setting(s):
    prev_w = router.set_header_wait(s["wait"])
    prev_n = router.set_ni(s["ni"])
    load = wcosts.load_handlers
    if not s["handlers"]:
        wcosts.load_handlers = lambda *a, **k: None
    try:
        yield
    finally:
        wcosts.load_handlers = load
        router.set_header_wait(prev_w)
        router.set_ni(prev_n)


def event_triggered_at(app, noc, mapping, appname, frequency, cfg):
    """Attempt of search (keys of schedule_at) for event-triggered injection:
    feasible when every packet of the phase meets its deadline with its
    WCTT from the finish of its source and every task fits its phase with
    the handlers."""
    instance = instantiator.createInstance(app, noc, frequency)
    packets, hp, _ = flowUnwrapper.unwrap(instance, noc, mapping)
    if hp == 0:
        return None
    bound = wctt.wctt(packets)
    late = {p["name"] for p in packets if p["name"] in bound
            and p["min_start"] + bound[p["name"]] > p["abs_deadline"]}
    ok = not late and release.handlers_fit(instance, mapping) and release.deadline_fits(instance, mapping)
    return {"frequency": frequency, "hyperperiod": hp, "problem": {"packets": packets},
            "schedule": {} if ok else None, "skipped": late, "wctt": bound}


def _single(a, schedule=None):
    g, appname, noc, entries, _ = ttflow.load_app(a["csv"], a["map"], a["arch"], a["costs"])
    with tnet.quiet():
        f = search.minimum_frequency(g, noc, entries, appname, search_config(a["f0_hz"]), schedule=schedule)
    return f


def _composition(a):
    from rttools.multiapp import compose
    spec = compose.read_spec(a["composition"])
    compose.set_costs(spec, {x["name"]: a["costs"] for x in spec["apps"]})
    with tnet.quiet():
        comp = compose.load(spec)
        return compose.minimum_frequency(comp["apps"], comp["noc"], search_config(a["f0_hz"]))


def minimum(a):
    f = _composition(a) if a["kind"] == "composition" else _single(a)
    return {"f_cpu_hz": f["f_cpu_hz"], "minimum_hz": f["frequency_hz"]}


def deadline_sweep(a, deadlines_s):
    """Minimum frequency of a single-period application with the
    end-to-end deadline D of every task replaced by each value of
    deadlines_s (s), and R_bound at that frequency (ttflow.phase_model)."""
    out = {}
    for d in deadlines_s:
        g, appname, noc, entries, _ = ttflow.load_app(a["csv"], a["map"], a["arch"], a["costs"])
        g.graph["task_deadlines"] = {str(dd.get("label", n)): repr(d) for n, dd in g.nodes(data=True)}
        with tnet.quiet():
            f = search.minimum_frequency(g, noc, entries, appname, search_config(a["f0_hz"]))
        row = {"minimum_hz": f["frequency_hz"], "f_cpu_hz": f["f_cpu_hz"]}
        if f["frequency_hz"] is not None:
            with tnet.quiet():
                m = ttflow.phase_model(g, noc, entries, f["frequency_hz"])
            row["response_bound_ms"] = m["response_bound"]["ms"]
        out[f"{d * 1e3:.3f}"] = row
    return out


def skew_tolerance(a, frequency):
    """Largest skew sigma (cycles) between the ticks of two PEs that the
    link schedule of a single-period application at `frequency` tolerates:
    a skew shifts the packets of a sender by up to sigma in the frame of
    the receiver and of the other senders, so sigma is the smallest of the
    deadline slack a - (s + o_i) of a packet and the gap between the
    reservations of two packets of different source PEs on one link or
    network interface (modulo the hyperperiod)."""
    g, appname, noc, entries, _ = ttflow.load_app(a["csv"], a["map"], a["arch"], a["costs"])
    with tnet.quiet():
        at = search.schedule_at(g, noc, entries, appname, frequency, search_config(frequency))
    pr, sched, hp = at["problem"], at["schedule"], at["hyperperiod"]
    pk = pr["packets"]
    src = [p["path"][0]["data"]["label"] for p in pk]
    occ, dl = pr["occupancy"], pr["deadline"]
    slack = None
    gap = None
    for r, row in enumerate(sched):
        used = [i for i, x in enumerate(row) if x is not None]
        for i in used:
            d = dl[r][i] - (row[i] + occ[r][i])
            slack = d if slack is None else min(slack, d)
        for x in used:
            for y in used:
                if x < y and src[x] != src[y]:
                    a1, b1, a2, b2 = row[x], row[x] + occ[r][x], row[y], row[y] + occ[r][y]
                    d = min((a2 - b1) % hp, (a1 - b2) % hp)
                    gap = d if gap is None else min(gap, d)
    sigma = slack if gap is None else min(slack, gap)
    return {"frequency_hz": frequency, "deadline_slack_min": slack, "gap_min": gap, "sigma_cycles": sigma,
            "sigma_us": sigma / frequency * 1e6}


def wctt_rows(a, frequency):
    """WCTT and occupancy of every packet between PEs at `frequency`."""
    g, appname, noc, entries, _ = ttflow.load_app(a["csv"], a["map"], a["arch"], a["costs"])
    with tnet.quiet():
        inst = instantiator.createInstance(g, noc, frequency)
        packets, _, _ = flowUnwrapper.unwrap(inst, noc, entries)
    bound = wctt.wctt(packets)
    return {p["name"]: {"wctt": bound[p["name"]], "occupancy": p["net_time"], "release": p["min_start"],
                        "deadline": p["abs_deadline"]} for p in packets if p["name"] in bound}


def run(cfg_path, out_dir):
    with open(cfg_path) as fh:
        own = json.load(fh)
    if "include" in own:
        cfg = ttflow.load_config(os.path.join(os.path.dirname(os.path.abspath(cfg_path)), own["include"]))
        cfg["deadline_sweep_s"] = own.get("deadline_sweep_s", {})
        cfg["skew_sigma_cycles"] = own.get("skew_sigma_cycles")
    else:
        cfg = ttflow.load_config(cfg_path)
    out = {"_doc": "rttools.paper.ablation run --config " + os.path.basename(cfg_path), "apps": {}}
    for name, a in cfg["apps"].items():
        row = {}
        for sname, s in SETTINGS.items():
            with setting(s):
                row[sname] = minimum(a)
        if a["kind"] == "single":
            with setting(SETTINGS["flow"]):
                et = _single(a, schedule=event_triggered_at)
                row["event_triggered"] = {"f_cpu_hz": et["f_cpu_hz"], "minimum_hz": et["frequency_hz"]}
                if et["frequency_hz"] is not None:
                    row["event_triggered"]["packets"] = wctt_rows(a, et["frequency_hz"])
        if a["kind"] == "single":
            from rttools.paper import exp23
            with setting(SETTINGS["flow"]):
                clock = exp23.flow_clock(row["flow"]["minimum_hz"], a["period_s"])["f_clk_hz"]
                row["skew"] = skew_tolerance(a, clock)
        sig = cfg.get("skew_sigma_cycles")
        if sig and a["kind"] in ("single", "composition"):
            row["skew_sweep"] = {}
            for sigma in sig:
                st = dict(SETTINGS["flow"], ni=(True, router.NI_WAIT_CYCLES + sigma))
                with setting(st):
                    row["skew_sweep"][str(sigma)] = minimum(a)
        sweep = cfg.get("deadline_sweep_s", {}).get(name)
        if sweep:
            with setting(SETTINGS["flow"]):
                row["deadline_sweep"] = deadline_sweep(a, sweep)
        out["apps"][name] = row
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    return out


def summary(m):
    for name, row in m["apps"].items():
        cells = ", ".join(f"{k} {v['minimum_hz'] / 1e6:.3f}" if v["minimum_hz"] else f"{k} none"
                          for k, v in row.items() if k not in ("deadline_sweep", "skew", "skew_sweep"))
        for sg, v in row.get("skew_sweep", {}).items():
            cells += f"; sigma {sg}: {v['minimum_hz'] / 1e6:.3f} MHz"
        if "skew" in row:
            cells += f"; skew {row['skew']['sigma_cycles']} cycles at {row['skew']['frequency_hz'] / 1e6:.3f} MHz"
        for d, v in row.get("deadline_sweep", {}).items():
            cells += (f"; D {d} ms: " + (f"{v['minimum_hz'] / 1e6:.3f} MHz, R_bound {v['response_bound_ms']:.4f} ms"
                                         if v["minimum_hz"] else "none"))
        print(f"{name}: f_CPU {row['flow']['f_cpu_hz'] / 1e6:.3f} MHz; {cells} MHz")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rttools.paper.ablation")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        summary(run(args.config, args.out))
        return 0
    return 0 if cputime.check(args.metrics, args.reference) else 1


if __name__ == "__main__":
    sys.exit(main())
