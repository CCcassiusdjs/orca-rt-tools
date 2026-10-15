"""CAR (Shi et al. 2010, 33 tasks, 38 flows, periods 0.04 to 1 s, two
cycles) on the time scale of CAR-V, and the analysis flow of the paper with
the general phase model (rttools/bench_t/multirate.py), without RTL.

    python -m rttools.paper.carfull generate --config <config.json> --apps <apps dir> [--check]
    python -m rttools.paper.carfull run --config <config.json> --apps <apps dir> --arch <arch.gml> --out <dir>
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

Scale rule (`scale`), the rule of CAR-V (rttools/paper/carv.py) for every
period:

| Quantity | CAR | CAR-full |
|---|---|---|
| Flow period | T_e (SHI2010.csv): 0.04, 0.1, 0.5, 1 s | T_e / ratio, ratio = 0.04 s / period_s (80: 0.5, 1.25, 6.25, 12.5 ms) |
| Task period | none in SHI2010.csv | T_v: the smallest period of the flows that v sends, else of the flows that v receives (multirate.task_periods), scaled by the same ratio |
| Task cost | w(v) cycles per hyperperiod H = 1 s on the 1 MHz basis of shi-2010.txt | c^(v) = k round(w(v) T_v / H) + sigma: the cycles of one job on the basis times the cost factor k, plus one scheduler event sigma |
| Payload | d bytes per packet | floor(d / q) |
| Feedback edges | the cycles NAVC-OBDB-NAVC and OBDB-OBMG-OBDB | the back edges of the depth-first search of multirate.feedback_edges (task order of SHI2010.csv, flow order), written as feedback rows of the CSV |

Mapping: the MAX-PROC clusters of CAR on 16 nodes (ORT/GCM on the weights
of shi-2010.txt: cycles and words per hyperperiod) and their Spiral Mapping
on the 4x4 mesh, the mapping of Figure 4 of the paper
(rttools.paper.car.run_spiral, spiral.map_application).

The flow (`run`), for each candidate cost factor and payload divisor:
CPU test of the general model (multirate.cpu_test: f_CPU from the ORT/BENCH
sequences of the 16 PEs over the hyperperiod), the frequency search
(search.minimum_frequency: network at f_CPU, search above f_CPU when it is
not feasible), the network check at the platform clock, the largest data
age of every cause-effect chain (multirate.data_age) at the clock and at
the minimum frequency, the packets of one hyperperiod, and the heap per PE
of the generated UCX-OS application (rttools.ucxgen.memory). The chosen
factor follows carv.choose (largest k with f_CPU / clock <= max_utilization
and a feasible network at the clock).

Outputs of `run`: metrics.json, factors.csv, chains.csv, pes.csv,
flows.csv and values.tex (LaTeX macros \\ExpCarFull...).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import sys
from fractions import Fraction

from rttools.bench_t import multirate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator
from rttools.modules.io import appparser, nocparser
from rttools.modules.mapping import mapfile, spiral
from rttools.modules.routing import router
from rttools.modules.unwrapper import flowUnwrapper
from rttools.paper import carv
from rttools.paper.ch7 import load_graph
from rttools.paper.exp23 import macro_name
from rttools.paper.frequency import search_config
from rttools.tui.model import network


# ------------------------------------------------------------ application

def build(cfg, apps, cost_factor=None, payload_divisor=None):
    """CAR on the scale of the config: {"tasks": [(name, T_v (s), c^(v),
    T_src (s))], "flows": [(src, dst, T_e (s), bytes)], "feedback": [(u, v)],
    "ratio", ...} in the task order of SHI2010.csv and its flow order."""
    src, sc = cfg["source"], cfg["scale"]
    k = sc["cost_factor"] if cost_factor is None else cost_factor
    q = sc["payload_divisor"] if payload_divisor is None else payload_divisor
    if int(k) != k or k < 1 or int(q) != q or q < 1:
        raise ValueError("cost factor and payload divisor must be positive integers")
    wcet, _ = carv.read_wcet(os.path.join(apps, src["graph"]))
    flows = carv.read_flows(os.path.join(apps, src["flows"]))
    order = task_order(os.path.join(apps, src["flows"]))
    used = {f["src"] for f in flows} | {f["dst"] for f in flows}
    tasks = [t for t in order if t in used]
    missing = sorted(set(tasks) - set(wcet))
    if missing:
        raise ValueError("tasks without WCET: " + ", ".join(missing))
    ratio = Fraction(str(src["reference_period_s"])) / Fraction(str(sc["period_s"]))
    T_src = multirate.task_periods(tasks, [(f["src"], f["dst"], f["period"]) for f in flows])
    sigma = int(sc["scheduler_cycles"])
    out_tasks = [(t, T_src[t] / ratio, int(k) * carv.job_cycles(wcet[t], T_src[t], sc["hyperperiod_s"]) + sigma,
                  T_src[t]) for t in tasks]
    out_flows = [(f["src"], f["dst"], f["period"] / ratio, f["data"] // int(q)) for f in flows]
    fb = multirate.feedback_edges(tasks, [(a, b) for a, b, _, _ in out_flows])
    return {"tasks": out_tasks, "flows": out_flows, "feedback": fb, "ratio": ratio, "cost_factor": int(k),
            "payload_divisor": int(q), "scheduler_cycles": sigma, "raw_bytes": [f["data"] for f in flows],
            "source_flow_periods": [f["period"] for f in flows]}


def task_order(path):
    """Task acronyms in the order of the #tasks section of SHI2010.csv."""
    out, mode = [], 0
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0] == "#tasks":
                mode = 1
                continue
            if row[0].startswith("#"):
                mode = 0
                continue
            if mode == 1:
                mode = 2
                continue
            if mode == 2:
                out.append(row[4])
    return out


def csv_text(app, cfg):
    """CSV in the format of apps/car-v/car-v.csv, with task periods and
    feedback rows."""
    dec = carv.dec
    sc = cfg["scale"]
    buf = io.StringIO()
    buf.write("# CAR-full: CAR (apps/shi-2010, 33 tasks, 38 flows) on the time scale of CAR-V; generated by "
              "python -m rttools.paper.carfull generate (config experiments/car-full/config.json); do not edit\n")
    buf.write(f"# Periods: the periods of SHI2010.csv divided by {app['ratio']} "
              f"({dec(Fraction(str(cfg['source']['reference_period_s'])))} s -> {dec(Fraction(str(sc['period_s'])))} s)\n")
    buf.write(f"# Task rows: Period = T_v (s), the smallest period of the flows that v sends, else of the flows "
              f"that v receives; Capacity = c^(v) = {app['cost_factor']} round(w(v) T_src(v) / "
              f"{dec(Fraction(str(sc['hyperperiod_s'])))}) + {app['scheduler_cycles']} cycles (w(v) of "
              f"shi-2010.txt, T_src(v) the period before the scale); Deadline = T_v (s), not used by the model\n")
    buf.write(f"# Flow rows: Period = T_e (s); Data = floor(bytes of SHI2010.csv / {app['payload_divisor']}); "
              "Deadline = T_e (s), not used by the model\n")
    buf.write("# feedback rows: back edges of the depth-first search of rttools.bench_t.multirate.feedback_edges\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["#tasks", "", "", "", "", ""])
    w.writerow(["Task", "Period", "Capacity", "Deadline", "Acronym", "Description"])
    for i, (t, T, c, _) in enumerate(app["tasks"], 1):
        w.writerow([i, dec(T), c, dec(T), t, "Task " + t])
    w.writerow(["#flows", "", "", "", "", ""])
    w.writerow(["Flow", "Period", "Data", "Deadline", "Source", "Target"])
    for i, (a, b, T, d) in enumerate(app["flows"], 1):
        w.writerow([i, dec(T), d, dec(T), a, b])
    w.writerow(["#parameters", "", "", "", "", ""])
    w.writerow(["Parameter", "Value", "", "", "", ""])
    w.writerow(["release_model", "phase", "", "", "", ""])
    w.writerow(["scheduler_cycles", app["scheduler_cycles"], "", "", "", ""])
    for a, b in app["feedback"]:
        w.writerow(["feedback", a, b, "", "", ""])
    return buf.getvalue()


def mapping(cfg, apps):
    """Spiral Mapping of the clusters of CAR (Figure 4): (criterion,
    clusters, cluster -> node, task -> node)."""
    mp = cfg["mapping"]
    tasks, edges = spiral.from_orca(load_graph(os.path.join(apps, mp["graph"])))
    r = spiral.map_application(tasks, edges, mp["width"], mp["height"])
    if r["criterion"] != mp["criterion"]:
        raise ValueError(f"step 1 chose {r['criterion']}, the config expects {mp['criterion']}")
    return r


def map_text(tmap):
    return mapfile.to_text(mapfile.from_dict(tmap))


# ------------------------------------------------------------ flow

def load(path, arch):
    with network.quiet():
        g, name = appparser.loadFromFile(path)
        noc = nocparser.loadFromFile(arch)
    return g, name, noc


def at_frequency(g, noc, entries, f, spec):
    """Schedule of the general model at f: phase in cycles, CPU
    feasibility, data age of every chain, packets of one hyperperiod. On
    the time-triggered platform with the handlers of the image, the
    schedule carries the charges of the fixed point with the link schedule
    at f (search.schedule_at, handler_extra)."""
    P = math.floor(spec.phase_s * Fraction(f))
    sched = multirate.schedule(spec, P, extra=handler_extra(g, noc, entries, f, spec))
    out = {"frequency_hz": f, "phase_cycles": P, "hyper_cycles": sched.H, "cpu_feasible": sched.feasible,
           "periodic_from_hyperperiod": sched.h0, "misses": len(sched.misses)}
    if not sched.feasible:
        return out, sched, None
    ages = multirate.data_age(spec, sched)
    busy = sched.busy_per_phase()
    out["busy_per_phase_max"] = {str(n): max(b) for n, b in busy.items()}
    out["busy_per_hyperperiod"] = {str(n): sum(b) for n, b in busy.items()}
    out["data_age"] = [{"chain": "-".join(a["chain"]), "source": a["chain"][0], "sink": a["chain"][-1],
                        "length": len(a["chain"]) - 1, "max_cycles": a["max_cycles"], "min_cycles": a["min_cycles"],
                        "max_ms": a["max_cycles"] / f * 1e3, "output_job": a["output_job"]} for a in ages]
    worst = max(ages, key=lambda a: (a["max_cycles"], "-".join(a["chain"])))
    out["data_age_max"] = {"chain": "-".join(worst["chain"]), "cycles": worst["max_cycles"],
                           "ms": worst["max_cycles"] / f * 1e3}
    return out, sched, ages


def handler_extra(g, noc, entries, f, spec):
    """Charges of the handlers of the packet events at f (the fixed point of
    search.schedule_at), None without handlers or off the time-triggered
    platform, or without a link schedule at f."""
    if not (spec.tick and spec.handlers):
        return None
    with network.quiet():
        a = search.schedule_at(g, noc, entries, "car_full", f, search_config(f))
    return None if a is None else a.get("handler_extra")


def run_factor(cfg, apps, arch, k, q, tmp, tmap):
    app = build(cfg, apps, k, q)
    path = os.path.join(tmp, f"car-full-k{k}-q{q}.csv")
    with open(path, "w") as f:
        f.write(csv_text(app, cfg))
    g, appname, noc = load(path, arch)
    entries = mapfile.from_dict(tmap)
    plat = cfg["platform"]
    clock = plat["clock_hz"]
    r = multirate.graph_rates(g)
    spec = multirate.spec_from_graph(g, entries, r, noc)
    scfg = search_config(plat["f0_hz"])
    with network.quiet():
        freq = search.minimum_frequency(g, noc, entries, appname, scfg)
        at_clock = search.network_check(g, noc, entries, appname, clock, scfg)
    cpu = freq["cpu"]
    fmin = freq["frequency_hz"]
    clk, sched_clk, _ = at_frequency(g, noc, entries, clock, spec)
    mn = None
    if fmin is not None:
        mn, _, _ = at_frequency(g, noc, entries, fmin, spec)
    # packets of one hyperperiod at the clock (instance of the flow)
    flows = []
    if sched_clk.feasible:
        inst = instantiator.createInstance(g, noc, clock)
        win = multirate.packet_windows(spec, sched_clk)
        with network.quiet():
            packets, hp, _ = flowUnwrapper.unwrap(inst, noc, entries)
        net = {}
        for p in packets:
            net.setdefault(p["flow"], []).append(p)
        for i, (a, b, T, d) in enumerate(app["flows"], 1):
            label = f"f{i}"
            rows = win[label]
            ps = net.get(label, [])
            slack = [p["abs_deadline"] - p["min_start"] - p["net_time"] for p in ps]
            flows.append({"flow": label, "source": a, "target": b, "period_ms": float(T) * 1e3, "bytes": d,
                          "src_pe": spec.node_of[a], "dst_pe": spec.node_of[b],
                          "on_noc": spec.node_of[a] != spec.node_of[b], "packets": len(rows),
                          "window_min_cycles": min(dl - rl for _, rl, dl, _ in rows),
                          "window_max_cycles": max(dl - rl for _, rl, dl, _ in rows),
                          "hops": len(ps[0]["path"]) if ps else None,
                          "net_time_cycles": ps[0]["net_time"] if ps else None,
                          "slack_min_cycles": min(slack) if slack else None})
    demand = {str(n): v for n, v in cpu["demand"].items()}
    f_cpu = cpu["f_cpu_hz"]
    mem = memory_report(app, tmap, cfg)
    out = {
        "cost_factor": k, "payload_divisor": q,
        "tasks": len(app["tasks"]), "flows": len(app["flows"]),
        "costs": {t: c for t, _, c, _ in app["tasks"]},
        "task_period_ms": {t: float(T) * 1e3 for t, T, _, _ in app["tasks"]},
        "rates": {"phase_ms": float(r["phase_s"]) * 1e3, "hyperperiod_ms": float(r["hyper_s"]) * 1e3,
                  "phases_per_hyperperiod": r["hyper_ticks"], "ticks": r["ticks"],
                  "flow_jobs": r["flow_jobs"]},
        "feedback": ["-".join(e) for e in r["feedback"]],
        "sequences": {str(n): ts for n, ts in spec.orders.items()},
        "cpu": {"f_cpu_hz": f_cpu, "phase_cycles": cpu["phase_cycles"],
                "utilization_bound_cycles": cpu["utilization_cycles"],
                "utilization_bound_hz": cpu["utilization_cycles"] / float(r["phase_s"]),
                "f_cpu_phase_hz": cpu["f_cpu_phase_hz"], "steps": cpu["steps"],
                "demand_per_hyperperiod_cycles": demand,
                "utilization_at_clock": f_cpu / clock},
        "search": {"f_cpu_hz": f_cpu, "network_at_f_cpu": freq["final_check"],
                   "frequency_hz": fmin, "f_noc_hz": freq["f_star_hz"],
                   "search_above_f_cpu": None if freq["final_search"] is None else
                   {"attempts": len(freq["final_search"]["attempts"]), "lower_hz": freq["final_search"]["lower"]},
                   "binding": None if fmin is None else ("cpu" if fmin == f_cpu else "network")},
        "network_at_clock": at_clock,
        "at_clock": clk,
        "at_minimum": mn,
        "flow_windows": flows,
        "packets_per_hyperperiod": sum(f["packets"] for f in flows if f["on_noc"]),
        "local_flows": sum(1 for f in flows if not f["on_noc"]),
        "memory": mem,
    }
    return out, app


def memory_report(app, tmap, cfg):
    """Heap per PE of the UCX-OS application (rttools.ucxgen.memory model)
    with the payloads of `app`."""
    from rttools.ucxgen import memory as umem
    flows = [{"src_pe": tmap[a], "dst_pe": tmap[b], "local": tmap[a] == tmap[b], "bytes": d, "csv_bytes": d}
             for a, b, _, d in app["flows"]]
    man = {"tasks": [{"name": t, "pe": tmap[t]} for t, _, _, _ in app["tasks"]], "flows": flows}
    mem = cfg["memory"]
    dem = umem.pe_demand(man, mem["in_flight"])
    usable = umem.usable(mem["heap_bytes"])
    worst = max(dem, key=lambda n: (dem[n]["bytes"], -n))
    largest = max(f["bytes"] for f in flows)
    per_pe = {str(n): len([t for t, _, _, _ in app["tasks"] if tmap[t] == n]) for n in dem}
    return {"heap_bytes": mem["heap_bytes"], "usable_bytes": usable, "ram_bytes": mem["ram_bytes"],
            "worst_pe": str(worst), "worst_bytes": dem[worst]["bytes"], "free_bytes": usable - dem[worst]["bytes"],
            "fits": dem[worst]["bytes"] <= usable,
            "largest_payload": largest, "payload_fits": largest <= mem["max_payload_bytes"],
            "tasks_fit": all(v + 1 <= mem["max_tasks"] for v in per_pe.values()),
            "pes": {str(n): d for n, d in dem.items()}}


def choose(results, plat):
    """carv.choose on the keys of this module."""
    ok = [r for r in results if r["cpu"]["utilization_at_clock"] <= plat["max_utilization"]
          and r["network_at_clock"]["feasible"] and r["search"]["frequency_hz"] is not None
          and r["search"]["frequency_hz"] <= plat["clock_hz"]]
    return max(ok, key=lambda r: r["cost_factor"])["cost_factor"] if ok else None


def run(cfg, apps, arch, out_dir):
    sc, plat = cfg["scale"], cfg["platform"]
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "candidates")
    os.makedirs(tmp, exist_ok=True)
    mres = mapping(cfg, apps)
    tmap = mres["mapping"]
    ks = sorted(set(sc.get("cost_factor_candidates", [sc["cost_factor"]])) | {sc["cost_factor"]})
    qs = sorted(set(sc.get("payload_divisor_candidates", [sc["payload_divisor"]])) | {sc["payload_divisor"]})
    results = {}
    for k in ks:
        for q in qs:
            results[(k, q)], _ = run_factor(cfg, apps, arch, k, q, tmp, tmap)
    rule = choose([results[(k, sc["payload_divisor"])] for k in ks], plat)
    chosen = results[(sc["cost_factor"], sc["payload_divisor"])]
    app = build(cfg, apps)
    text = csv_text(app, cfg)
    mtext = map_text(tmap)
    for name, t in (("car-full.csv", text), ("car-full.map", mtext)):
        with open(os.path.join(out_dir, name), "w") as f:
            f.write(t)
    repo = os.path.join(apps, cfg["app"]["dir"])
    w_h = router.header_wait()
    m = {
        "header_wait_cycles": w_h, "occupancy": "L0 + %d (m + 1)" % w_h if w_h else "L0",
        "app": {"csv": cfg["app"]["csv"], "map": cfg["app"]["map"],
                "csv_matches_repo": carv._same(os.path.join(repo, cfg["app"]["csv"]), text),
                "map_matches_repo": carv._same(os.path.join(repo, cfg["app"]["map"]), mtext)},
        "selection": {"tasks": [t for t, _, _, _ in app["tasks"]], "flows": len(app["flows"]),
                      "source_periods_s": sorted({float(p) for p in app["source_flow_periods"]}),
                      "feedback": ["-".join(e) for e in app["feedback"]]},
        "mapping": {"criterion": mres["criterion"], "clusters": {c: ts for c, ts in mres["clusters"].items()},
                    "cluster_nodes": mres["cluster_nodes"], "volumes": mres["volumes"],
                    "nodes": {str(n): [t for t, _, _, _ in app["tasks"] if tmap[t] == n]
                              for n in sorted(set(tmap.values()))}},
        "scale": {"ratio": float(app["ratio"]), "period_s": sc["period_s"], "cost_factor": sc["cost_factor"],
                  "payload_divisor": sc["payload_divisor"], "scheduler_cycles": sc["scheduler_cycles"]},
        "rule": {"max_utilization": plat["max_utilization"], "chosen_cost_factor": rule,
                 "config_matches_rule": rule == sc["cost_factor"]},
        "candidates": {f"k{k}_q{q}": _summary(r) for (k, q), r in results.items()},
        "chosen": chosen,
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1, default=carv._json)
    write_csvs(out_dir, m)
    write_values(os.path.join(out_dir, "values.tex"), m)
    return m


def _summary(r):
    s, ck, mn = r["search"], r["at_clock"], r["at_minimum"]
    return {"cost_factor": r["cost_factor"], "payload_divisor": r["payload_divisor"],
            "f_cpu_hz": r["cpu"]["f_cpu_hz"], "f_cpu_phase_hz": r["cpu"]["f_cpu_phase_hz"],
            "utilization_bound_hz": r["cpu"]["utilization_bound_hz"],
            "utilization_at_clock": r["cpu"]["utilization_at_clock"],
            "frequency_hz": s["frequency_hz"], "binding": s["binding"],
            "network_at_f_cpu_feasible": None if s["network_at_f_cpu"] is None else s["network_at_f_cpu"]["feasible"],
            "network_at_clock_feasible": r["network_at_clock"]["feasible"],
            "packets": r["network_at_clock"]["packets"], "skipped": r["network_at_clock"]["skipped"],
            "data_age_max_ms_at_clock": ck["data_age_max"]["ms"] if ck.get("data_age_max") else None,
            "data_age_max_ms_at_minimum": mn["data_age_max"]["ms"] if mn and mn.get("data_age_max") else None,
            "memory_worst_pe": r["memory"]["worst_pe"], "memory_worst_bytes": r["memory"]["worst_bytes"],
            "memory_free_bytes": r["memory"]["free_bytes"], "memory_fits": r["memory"]["fits"]}


def write_csvs(out_dir, m):
    c = m["chosen"]

    def put(name, rows, cols):
        with open(os.path.join(out_dir, name), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(k) for k in cols])

    put("factors.csv", list(m["candidates"].values()), list(next(iter(m["candidates"].values()))))
    put("flows.csv", c["flow_windows"], ["flow", "source", "target", "period_ms", "bytes", "src_pe", "dst_pe",
                                         "on_noc", "packets", "window_min_cycles", "window_max_cycles", "hops",
                                         "net_time_cycles", "slack_min_cycles"])
    rows = []
    for which in ("at_clock", "at_minimum"):
        for a in (c[which] or {}).get("data_age") or []:
            rows.append(dict(a, frequency=which))
    put("chains.csv", rows, ["frequency", "chain", "source", "sink", "length", "max_cycles", "min_cycles", "max_ms",
                             "output_job"])
    ck = c["at_clock"]
    pes = []
    for n, ts in m["mapping"]["nodes"].items():
        p = c["memory"]["pes"][n]
        pes.append({"pe": n, "tasks": " ".join(c["sequences"][n]),
                    "demand_per_hyperperiod": c["cpu"]["demand_per_hyperperiod_cycles"][n],
                    "busy_per_phase_max_at_clock": (ck.get("busy_per_phase_max") or {}).get(n),
                    "heap_bytes": p["bytes"]})
    put("pes.csv", pes, ["pe", "tasks", "demand_per_hyperperiod", "busy_per_phase_max_at_clock", "heap_bytes"])


def write_values(path, m):
    c = m["chosen"]
    lines = ["% generated by python -m rttools.paper.carfull; do not edit"]

    def put(text, *name):
        lines.append(f"\\newcommand{{\\{macro_name('car', 'full', *name)}}}{{{text}}}")

    def mhz(v):
        return "-" if v is None else f"{v / 1e6:.1f}"

    put(str(c["tasks"]), "tasks")
    put(str(c["flows"]), "flows")
    put(f"{c['rates']['phase_ms']:g}", "phase", "ms")
    put(f"{c['rates']['hyperperiod_ms']:g}", "hyperperiod", "ms")
    put(str(c["rates"]["phases_per_hyperperiod"]), "phases")
    put(str(len(c["feedback"])), "feedback", "edges")
    put(", ".join(e.replace("-", "$\\to$") for e in c["feedback"]), "feedback", "list")
    put(str(m["scale"]["cost_factor"]), "cost", "factor")
    put(str(m["scale"]["payload_divisor"]), "payload", "divisor")
    put(m["mapping"]["criterion"].replace("_", "-"), "criterion")
    put(mhz(c["cpu"]["f_cpu_hz"]), "cpu", "mhz")
    put(mhz(c["cpu"]["f_cpu_phase_hz"]), "cpu", "phase", "mhz")
    put(mhz(c["cpu"]["utilization_bound_hz"]), "utilization", "bound", "mhz")
    put(f"{100 * c['cpu']['utilization_at_clock']:.1f}", "utilization", "percent")
    put(mhz(c["search"]["f_noc_hz"]), "noc", "mhz")
    put(mhz(c["search"]["frequency_hz"]), "minimum", "mhz")
    put(c["search"]["binding"] or "-", "binding")
    put(str(c["network_at_clock"]["packets"]), "packets")
    put(str(c["network_at_clock"]["skipped"]), "skipped")
    put(str(c["local_flows"]), "local", "flows")
    ck, mn = c["at_clock"], c["at_minimum"]
    put(str(len(ck.get("data_age") or [])), "chains")
    if ck.get("data_age_max"):
        put(f"{ck['data_age_max']['ms']:.3f}", "age", "max", "ms")
        put(ck["data_age_max"]["chain"].replace("-", "$\\to$"), "age", "max", "chain")
    if mn and mn.get("data_age_max"):
        put(f"{mn['data_age_max']['ms']:.3f}", "age", "max", "minimum", "ms")
    put(f"{c['memory']['worst_bytes']:,}", "memory", "worst", "bytes")
    put(f"{c['memory']['usable_bytes']:,}", "memory", "heap", "bytes")
    put(f"{c['memory']['free_bytes']:,}", "memory", "free", "bytes")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.carfull", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="write apps/car-full/car-full.{csv,map} from apps/shi-2010")
    g.add_argument("--config", required=True)
    g.add_argument("--apps", required=True, help="directory apps/ of the repository")
    g.add_argument("--check", action="store_true", help="compare with the files instead of writing them")
    r = sub.add_parser("run", help="analysis flow on CAR-full")
    r.add_argument("--config", required=True)
    r.add_argument("--apps", required=True)
    r.add_argument("--arch", required=True)
    r.add_argument("--out", required=True)
    a = p.parse_args(argv)
    with open(a.config) as f:
        cfg = json.load(f)
    if a.cmd == "generate":
        app = build(cfg, a.apps)
        texts = {cfg["app"]["csv"]: csv_text(app, cfg), cfg["app"]["map"]: map_text(mapping(cfg, a.apps)["mapping"])}
        status = 0
        for name, text in texts.items():
            out = os.path.join(a.apps, cfg["app"]["dir"], name)
            if a.check:
                same = carv._same(out, text)
                print(out + (": up to date" if same else ": differs from the generator"))
                status |= 0 if same else 1
                continue
            os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
            with open(out, "w") as f:
                f.write(text)
            print("wrote " + out)
        return status
    m = run(cfg, a.apps, a.arch, a.out)
    for key, s in m["candidates"].items():
        print(f"  {key}: f_CPU {carv.mhz_text(s['f_cpu_hz'])} (phase rule {carv.mhz_text(s['f_cpu_phase_hz'])}, "
              f"utilization bound {carv.mhz_text(s['utilization_bound_hz'])}), "
              f"minimum {carv.mhz_text(s['frequency_hz'])} ({s['binding']}); network at the clock "
              f"{'feasible' if s['network_at_clock_feasible'] else 'not feasible'}; largest data age "
              f"{s['data_age_max_ms_at_clock']} ms at the clock; heap of PE {s['memory_worst_pe']} "
              f"{s['memory_worst_bytes']:,} B ({'fits' if s['memory_fits'] else 'does not fit'})")
    c = m["chosen"]
    print(f"  chosen: cost factor {m['scale']['cost_factor']} (rule: {m['rule']['chosen_cost_factor']}), payload "
          f"divisor {m['scale']['payload_divisor']}, {c['network_at_clock']['packets']} packets per hyperperiod")
    print(f"  apps/{cfg['app']['dir']}: csv {'matches' if m['app']['csv_matches_repo'] else 'differs'}, "
          f"map {'matches' if m['app']['map_matches_repo'] else 'differs'}")
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
