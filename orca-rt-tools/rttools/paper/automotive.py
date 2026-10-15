"""Engine-control workload from the application characteristics of Kramer,
Ziegenbein and Hamann, "Real World Automotive Benchmarks For Free" (WATERS
2015), and the analysis flow of the paper with the general phase model
(rttools/bench_t/multirate.py), without RTL.

    python -m rttools.paper.automotive run --config experiments/automotive/config.json --out <dir>
    python -m rttools.paper.automotive check <dir>/metrics.json experiments/automotive/reference.json

Generation (`generate`, seeded, tables of the config, which copy Tables I and
III to VII of the paper):

| Element | Rule |
|---|---|
| Cause-effect chains | `chains` chains; the number of activation patterns (periods) of a chain from Table VI, the runnables per pattern from Table VII; the periods of the time-synchronous patterns of Table III (angle-synchronous and interrupt-driven runnables left out), drawn by their shares; consecutive patterns of a chain have periods that divide one another (the flow period must be a multiple of the period of its source, Section 6.6), and no period repeats in a chain |
| Tasks | the runnables of one activation pattern of a chain form one task (Section II.A of the paper: runnables with the same activation pattern are mapped to the same task), which runs them in their chain order in one job |
| Execution times | ACET of each runnable from a Weibull distribution (shape `weibull_shape`) truncated to [min, max] of Table IV, with the scale that gives the average of Table IV; BCET = ACET x U(fmin, fmax) and WCET = ACET x U(fmin, fmax) of Table V |
| Cost | c(v) = round(WCET(v) x `cycles_per_us`) + `scheduler_cycles`, WCET(v) the sum of the WCETs of the runnables of task v (the time scale of the microcontroller of the characteristics, plus the dispatch of the job); BCET(v) the sum of their BCETs |
| Edges | consecutive tasks of a chain, and one edge from the last task of an earlier chain with a harmonic period to the first task of each other chain (inter-task communication), so the graph is acyclic; payload of each edge: a label size from Table I |
| End-to-end constraint | the sum of the periods of the activation patterns of the chain (Section IV.E of the paper) |
| Mapping | steps 1 and 2 of the flow (spiral.map_application: ORT/GCM with the four criteria, smallest M2, Spiral Mapping) on the `width` x `height` mesh |

The run: f_CPU of the CPU test of the general model, the minimum frequency of
the flow (search.minimum_frequency), the data age bound DA of every chain at
that frequency against its end-to-end constraint, and the execution-time
variation: `trials` simulations of each PE with the tick table of the flow
(rttools.bench.ucx, owners), each job of v with a work drawn in [BCET, WCET]
of v, against F_j(v) of the model.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import random
import sys
import time
from fractions import Fraction

from rttools.bench import ucx
from rttools.bench_t import multirate
from rttools.modules.frequency import search
from rttools.modules.io import appparser, nocparser
from rttools.modules.mapping import mapfile, spiral
from rttools.paper import cputime
from rttools.paper.frequency import search_config
from rttools.tui.model import network as tnet


def _pick(rnd, shares):
    """Key of `shares` ({key: share}) drawn by its share."""
    keys = list(shares)
    x = rnd.random() * sum(shares[k] for k in keys)
    for k in keys:
        x -= shares[k]
        if x < 0:
            return k
    return keys[-1]


def _truncated_weibull_mean(shape, scale, lo, hi, n=400):
    """Mean of a Weibull(shape, scale) truncated to [lo, hi] (numeric)."""
    def cdf(x):
        return 1 - math.exp(-((x / scale) ** shape))
    a, b = cdf(lo), cdf(hi)
    if b - a <= 0:
        return (lo + hi) / 2
    # inverse-CDF sampling on a uniform grid of the truncated mass
    s = 0.0
    for i in range(n):
        u = a + (b - a) * (i + 0.5) / n
        s += scale * (-math.log(1 - u)) ** (1 / shape)
    return s / n


def _scale_for_mean(shape, lo, avg, hi):
    """Scale of the truncated Weibull with mean `avg` (bisection)."""
    a, b = lo / 100, hi * 100
    for _ in range(200):
        m = math.sqrt(a * b)
        if _truncated_weibull_mean(shape, m, lo, hi) < avg:
            a = m
        else:
            b = m
    return math.sqrt(a * b)


def _acet(rnd, shape, scale, lo, hi):
    def cdf(x):
        return 1 - math.exp(-((x / scale) ** shape))
    a, b = cdf(lo), cdf(hi)
    u = a + (b - a) * rnd.random()
    return min(hi, max(lo, scale * (-math.log(1 - u)) ** (1 / shape)))


def _harmonic(a, b):
    a, b = Fraction(a), Fraction(b)
    big, small = max(a, b), min(a, b)
    return (big / small).denominator == 1


def generate(cfg):
    """{"tasks": [(name, period s, cost, bcet_us, wcet_us, acet_us)], "flows":
    [(u, v, period s, bytes)], "chains": [{"tasks", "periods_ms", "constraint_ms"}]}."""
    rnd = random.Random(cfg["seed"])
    per = {str(k): v for k, v in cfg["period_shares"].items()}
    shape = cfg["weibull_shape"]
    acet = {p: cfg["acet_us"][p] for p in per}
    scale = {p: _scale_for_mean(shape, a["min"], a["avg"], a["max"]) for p, a in acet.items()}
    tasks, flows, chains = [], [], []
    period_of = {}

    def runnable(p):
        a = acet[p]
        ac = _acet(rnd, shape, scale[p], a["min"], a["max"])
        fb, fw = cfg["factors"][p]["best"], cfg["factors"][p]["worst"]
        return ac, ac * rnd.uniform(fb[0], fb[1]), ac * rnd.uniform(fw[0], fw[1])

    def new_task(p, n):
        """Task of n runnables of period p ms (one segment of a chain):
        the runnables run in one job in their chain order."""
        rs = [runnable(p) for _ in range(n)]
        name = f"T{len(tasks) + 1}"
        bc, wc, ac = sum(r[1] for r in rs), sum(r[2] for r in rs), sum(r[0] for r in rs)
        cost = max(1, round(wc * cfg["cycles_per_us"])) + cfg["scheduler_cycles"]
        tasks.append((name, Fraction(p) / 1000, cost, bc, wc, ac))
        period_of[name] = Fraction(p) / 1000
        runnables.append(n)
        return name

    def label_bytes():
        k = _pick(rnd, cfg["label_size_shares"])
        lo, hi = (int(x) for x in k.split("-")) if "-" in k else (int(k), int(k))
        return rnd.randint(lo, hi)

    def flow(u, v):
        T = max(period_of[u], period_of[v])
        flows.append((u, v, T, label_bytes()))

    runnables = []
    for c in range(cfg["chains"]):
        n_pat = int(_pick(rnd, cfg["patterns_per_chain_shares"]))
        pats = []
        for _ in range(100):
            pats = [_pick(rnd, per)]
            ok = True
            while len(pats) < n_pat:
                cand = [p for p in per if p not in pats and _harmonic(int(p), int(pats[-1]))]
                if not cand:
                    ok = False
                    break
                pats.append(_pick(rnd, {p: per[p] for p in cand}))
            if ok:
                break
        names = [new_task(p, int(_pick(rnd, cfg["runnables_per_pattern_shares"]))) for p in pats]
        for u, v in zip(names, names[1:]):
            flow(u, v)
        if chains:
            cand = [ch for ch in chains if _harmonic(int(period_of[ch["tasks"][-1]] * 1000), int(pats[0]))]
            if cand:
                src = rnd.choice(cand)["tasks"][-1]
                flow(src, names[0])
        chains.append({"tasks": names, "periods_ms": [int(p) for p in pats],
                       "constraint_ms": sum(int(p) for p in pats)})
    return {"tasks": tasks, "flows": flows, "chains": chains, "runnables": sum(runnables)}


def dec(x):
    s = f"{float(x):.6f}".rstrip("0").rstrip(".")
    return s


def csv_text(app, cfg, task_node=None):
    buf = io.StringIO()
    buf.write("# Engine-control workload from the characteristics of Kramer et al. (WATERS 2015); generated by "
              "python -m rttools.paper.automotive (seed %d); do not edit\n" % cfg["seed"])
    buf.write("#tasks,,,,,\nTask,Period,Capacity,Deadline,Acronym,Description\n")
    for i, (t, T, c, *_rest) in enumerate(app["tasks"], 1):
        buf.write(f"{i},{dec(T)},{c},{dec(T)},{t},Runnable {t}\n")
    buf.write("#flows,,,,,\nFlow,Period,Data,Deadline,Source,Target\n")
    for i, (a, b, T, d) in enumerate(app["flows"], 1):
        buf.write(f"{i},{dec(T)},{d},{dec(T)},{a},{b}\n")
    buf.write("#parameters,,,,,\nParameter,Value,,,,\nrelease_model,phase,,,,\n")
    buf.write(f"scheduler_cycles,{cfg['scheduler_cycles']},,,,\n")
    if task_node:
        # creation order on each PE: the order of generation (data-flow order of the chains)
        by_node = {}
        for t, *_ in app["tasks"]:
            by_node.setdefault(task_node[t], []).append(t)
        for n in sorted(by_node):
            buf.write("creation," + str(n) + "," + ",".join(by_node[n]) + "\n")
    return buf.getvalue()


def mapping(app, cfg):
    tasks = [(t, c) for t, _, c, *_ in app["tasks"]]
    edges = [(a, b, d) for a, b, _, d in app["flows"]]
    return spiral.map_application(tasks, edges, cfg["width"], cfg["height"])


def variation(spec, sched, app, cfg):
    """Simulations of each PE with the tick table of the flow and random
    work in [BCET, WCET] of each runnable: jobs that end after F_j(v)."""
    rnd = random.Random(cfg["seed"] + 1)
    cyc = cfg["cycles_per_us"]
    bw = {t: (bc, wc) for t, _, _, bc, wc, _ in app["tasks"]}
    own = sched.tick_owners()
    loop = sched.h0 * spec.hyper_ticks
    jobs = late = 0
    for node, ts in spec.orders.items():
        o = own[node]

        def owner_of(t, o=o):
            return o[t] if t < len(o) else o[loop + (t - loop) % (len(o) - loop)]
        for _ in range(cfg["trials"]):
            tasks = []
            for t in ts:
                lo, hi = bw[t]
                work = min(spec.cost[t], max(1, round(rnd.uniform(lo, hi) * cyc)) + spec.sigma)
                tasks.append({"name": t, "cost": work, "period": spec.ticks[t], "offset": spec.offsets[t]})
            run = ucx.simulate(tasks, sched.P, 3 * spec.hyper_ticks, spec.sigma, tail=3 * spec.hyper_ticks,
                               owner_of=owner_of)
            for t, js in run["jobs"].items():
                for j, mj in zip(js, sched.sims[node]["jobs"][t]):
                    if j.finish is not None and mj.finish is not None:
                        jobs += 1
                        late += j.finish > mj.finish
    return {"trials_per_pe": cfg["trials"], "jobs": jobs, "late": late}


def run(cfg_path, out_dir):
    base = os.path.dirname(os.path.abspath(cfg_path))
    cfg = json.load(open(cfg_path))
    app = generate(cfg)
    mres = mapping(app, cfg)
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "automotive.csv")
    with open(csv_path, "w") as fh:
        fh.write(csv_text(app, cfg, mres["mapping"]))
    with tnet.quiet():
        g, name = appparser.loadFromFile(csv_path)
        noc = nocparser.loadFromFile(os.path.join(base, cfg["arch"]))
    entries = mapfile.from_dict(mres["mapping"])
    r = multirate.graph_rates(g)
    spec = multirate.spec_from_graph(g, entries, r, noc)
    with tnet.quiet():
        freq = search.minimum_frequency(g, noc, entries, name, search_config(cfg["f0_hz"]))
    fmin = freq["frequency_hz"]
    out = {"_doc": "rttools.paper.automotive run --config " + os.path.basename(cfg_path),
           "runnables": app["runnables"], "tasks": len(app["tasks"]), "edges": len(app["flows"]),
           "chains": len(app["chains"]),
           "periods_ms": sorted({int(T * 1000) for _, T, *_ in app["tasks"]}),
           "wcet_us": {"min": min(w for *_, w, _ in app["tasks"]), "max": max(w for *_, w, _ in app["tasks"])},
           "criterion": mres["criterion"], "f_cpu_hz": freq["f_cpu_hz"], "minimum_hz": fmin,
           "edges_on_noc": sum(1 for a, b, _, _ in app["flows"] if mres["mapping"][a] != mres["mapping"][b])}
    if fmin is not None:
        P = math.floor(spec.phase_s * Fraction(fmin))
        sched = multirate.schedule(spec, P)
        ages = multirate.data_age(spec, sched, [c["tasks"] for c in app["chains"]])
        rows = []
        for c, a in zip(app["chains"], ages):
            ms = a["max_cycles"] / fmin * 1e3
            rows.append({"chain": "-".join(c["tasks"]), "periods_ms": c["periods_ms"],
                         "constraint_ms": c["constraint_ms"], "data_age_ms": ms, "within": ms <= c["constraint_ms"]})
        out["chains_within_constraint"] = sum(r_["within"] for r_ in rows)
        out["data_age_over_constraint_max"] = max(r_["data_age_ms"] / r_["constraint_ms"] for r_ in rows)
        out["chain_rows"] = rows
        out["variation"] = variation(spec, sched, app, cfg)
        from rttools.modules.instances import instantiator
        from rttools.modules.unwrapper import flowUnwrapper
        with tnet.quiet():
            packets, _, _ = flowUnwrapper.unwrap(instantiator.createInstance(g, noc, fmin), noc, entries)
        out["packets_per_hyperperiod"] = len(packets)
        out["hyperperiod_ms"] = int(spec.phase_s * spec.hyper_ticks * 1000)
    with open(os.path.join(out_dir, "metrics.json"), "w") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rttools.paper.automotive")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    args = ap.parse_args(argv)
    if args.cmd == "run":
        m = run(args.config, args.out)
        print({k: v for k, v in m.items() if k != "chain_rows"})
        return 0
    return 0 if cputime.check(args.metrics, args.reference) else 1


if __name__ == "__main__":
    sys.exit(main())
