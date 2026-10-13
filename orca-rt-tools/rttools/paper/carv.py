"""CAR-V: the vision subgraph of CAR (Shi et al. 2010) on the time scale of
application E, and the analysis flow of the paper on it (no RTL).

    python -m rttools.paper.carv generate --config <config.json> --apps <apps dir> [--out <csv>] [--check]
    python -m rttools.paper.carv run --config <config.json> --apps <apps dir> --arch <arch.gml> --out <dir>
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

Selection rule (`select`): the flows of apps/shi-2010/SHI2010.csv with the
shortest period of CAR (0.04 s) and the tasks at their ends. The result is
a graph with one period, so the phase model of the paper applies (CAR as a
whole has four periods and the cycles NAVC-OBDB-NAVC and OBDB-OBMG-OBDB).

Scale rule (`scale`), parameters in the config:

| Quantity | CAR | CAR-V |
|---|---|---|
| Period | T_src = 0.04 s | T = period_s (0.5 ms, the period of application E) |
| Task cost | w(v) cycles per hyperperiod H = 1 s on the 1 MHz basis of shi-2010.txt | c^(v) = k round(w(v) T_src / H) + sigma: the cycles of one job on the basis times the cost factor k, plus one scheduler event sigma (11,000 cycles, as synthetic-app-e.csv) |
| Payload | d bytes per packet (SHI2010.csv) | floor(d / q), q = payload divisor |
| Task deadline | none (Shi et al. give one deadline per flow) | end-to-end deadline D = (L + 1) T, L = number of edges of the longest path |

D: the phase index n(v) of a task counts the edges between PEs on its
longest input path, so n(v) <= L for every mapping, and the phase model
finishes the last task in phase n(v_last) <= L; (L + 1) T covers every
mapping. Application E follows the same rule with its mapping
(n(v_last) = 3, D = 4 T = 2 ms).

The flow (`run`) runs, for each candidate cost factor of the config, the
steps of the CLI (rttools/__main__.py, input `spiral`): ORT/GCM on N =
mesh nodes with the four criteria and the smallest M2 (population standard
deviation of the cluster costs, spiral.cluster_application), the Spiral
Mapping, f_CPU (release.cpu_bound), the frequency search (f*, the network
check at f_CPU and the minimum, search.minimum_frequency), the network
check at the platform clock, the phase index and R_bound
(bench_t/estimate.py), the release window of each flow and the number of
packets on the NoC. The chosen factor is the largest candidate whose CPU
utilization at the platform clock, f_CPU / clock, stays at or below
max_utilization and whose network is feasible at the clock.

Memory (`memory`): heap bytes per PE of a UCX-OS port in the pattern of
weird_a.c (pkt-sim/software/ucx-os/app/weird_a.c), against the heap of the
weird_a.c image (`make weird_a` with ARCH=riscv/hf-riscv-e, image.map
_heap_size):

| Item | Bytes | Source |
|---|---|---|
| Each task and the idle task | tcb_s (112) + rt_s (12) + stack (2,048), each with a block header (8) | kernel/ucx.c:24-52; include/kernel/kernel.h:13-33; arch/riscv/hf-riscv-e/hal.h:416; include/lib/malloc.h:3-6 |
| Each application task | queue_s (24) + 8 slot pointers (32), each with a block header | lib/noc.c:165 (ucx_noc_comm_create); lib/queue.c:37-44; include/lib/noc.h:5 |
| Each outgoing flow | persistent packet: header (12) + payload rounded to 4, block header | lib/noc.c:307 (ucx_noc_create_packet); weird_a.c create_pkt |
| Each incoming flow from another PE | receive_buffers copies of header + payload, block header (irq2_handler allocates the packet; the target frees it after ucx_noc_receive) | lib/noc.c:55; weird_a.c recv_and_print |

A packet between tasks of one PE shares the buffer of the sender
(ucx_noc_send enqueues the pointer, lib/noc.c:357-377; weird_a.c frees
only packets from other nodes). receive_buffers = 2 covers the next
packet of a flow arriving before the target consumes the previous one.
The check also requires payload <= 65,535 bytes (uint16 payload_size,
include/lib/noc.h:23), tasks per PE plus idle <= MAX_TASKS (16,
include/lib/noc.h:2) and receive_buffers times the inputs of a task <=
MAX_PKT_QUEUE_SLOTS (8).

Outputs of `run`: metrics.json, clustering.csv, factors.csv, flows.csv,
pes.csv and values.tex (LaTeX macros \\ExpCarv...).
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from fractions import Fraction

from rttools import __main__ as cli
from rttools.bench_t import estimate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.io import appparser, nocparser
from rttools.modules.mapping import mapfile, spiral
from rttools.modules.unwrapper import flowUnwrapper
from rttools.paper.exp23 import macro_name
from rttools.paper.frequency import search_config
from rttools.tui.model import network


# ------------------------------------------------------------ CAR input

def read_wcet(path):
    """{task: w(v)} and the task order of shi-2010.txt (cycles per
    hyperperiod on the 1 MHz basis)."""
    out, order, mode = {}, [], 0
    with open(path) as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            if s.startswith("# nodes"):
                mode = 1
                continue
            if s.startswith("# edges"):
                mode = 2
                continue
            if mode == 1:
                name, w = s.split()[:2]
                out[name] = int(w)
                order.append(name)
    return out, order


def read_flows(path):
    """Flows of SHI2010.csv in file order: {"src", "dst", "period" (s, as
    the text of the file), "data" (bytes), "deadline" (s)}."""
    flows, mode = [], 0
    with open(path, newline="") as f:
        for row in csv.reader(f):
            if not row:
                continue
            if row[0] == "#flows":
                mode = 1
                continue
            if row[0].startswith("#"):
                mode = 0
                continue
            if mode == 1:
                mode = 2
                continue
            if mode == 2:
                flows.append({"src": row[4], "dst": row[5], "period": Fraction(row[1]),
                              "data": int(row[2]), "deadline": Fraction(row[3])})
    return flows


def select(flows, order, period=None):
    """Selection rule: the flows with `period` (default: the shortest
    period of the input) and the tasks at their ends, in the task order of
    shi-2010.txt; the flows keep the order of SHI2010.csv. Returns
    (period, tasks, flows)."""
    if period is None:
        period = min(f["period"] for f in flows)
    period = Fraction(str(period))
    sel = [f for f in flows if f["period"] == period]
    if not sel:
        raise ValueError(f"no flow with period {period} s")
    ends = {f["src"] for f in sel} | {f["dst"] for f in sel}
    missing = sorted(ends - set(order))
    if missing:
        raise ValueError("tasks without WCET: " + ", ".join(missing))
    return period, [t for t in order if t in ends], sel


def longest_path(tasks, edges):
    """Number of edges of the longest path of an acyclic graph; ValueError
    on a cycle."""
    succ = {t: [] for t in tasks}
    indeg = {t: 0 for t in tasks}
    for a, b in edges:
        succ[a].append(b)
        indeg[b] += 1
    depth = {t: 0 for t in tasks}
    ready = [t for t in tasks if indeg[t] == 0]
    seen = 0
    while ready:
        t = ready.pop(0)
        seen += 1
        for v in succ[t]:
            depth[v] = max(depth[v], depth[t] + 1)
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
    if seen != len(tasks):
        raise ValueError("the selected graph has a cycle")
    return max(depth.values())


def job_cycles(w, source_period, hyperperiod):
    """Cycles of one job on the basis: round(w T_src / H), exact."""
    return round(Fraction(w) * Fraction(str(source_period)) / Fraction(str(hyperperiod)))


def scale(wcet, tasks, flows, source_period, sc, cost_factor=None, payload_divisor=None):
    """Scale rule. `sc`: config "scale" (period_s, cost_factor,
    payload_divisor, scheduler_cycles, hyperperiod_s). Returns the
    application {"period_s", "deadline_s", "longest_path", "tasks": [(name,
    cost)], "flows": [(src, dst, bytes)], "scheduler_cycles", ...}."""
    k = sc["cost_factor"] if cost_factor is None else cost_factor
    q = sc["payload_divisor"] if payload_divisor is None else payload_divisor
    if int(k) != k or k < 1 or int(q) != q or q < 1:
        raise ValueError("cost factor and payload divisor must be positive integers")
    sigma = int(sc["scheduler_cycles"])
    period = Fraction(str(sc["period_s"]))
    edges = [(f["src"], f["dst"]) for f in flows]
    L = longest_path(tasks, edges)
    out_tasks = [(t, int(k) * job_cycles(wcet[t], source_period, sc["hyperperiod_s"]) + sigma) for t in tasks]
    out_flows = [(f["src"], f["dst"], f["data"] // int(q)) for f in flows]
    return {"period_s": period, "deadline_s": (L + 1) * period, "longest_path": L, "cost_factor": int(k),
            "payload_divisor": int(q), "scheduler_cycles": sigma, "source_period_s": Fraction(source_period),
            "tasks": out_tasks, "flows": out_flows}


def build(cfg, apps, cost_factor=None, payload_divisor=None):
    src = cfg["source"]
    wcet, order = read_wcet(os.path.join(apps, src["graph"]))
    flows = read_flows(os.path.join(apps, src["flows"]))
    period, tasks, sel = select(flows, order, src.get("period_s"))
    return scale(wcet, tasks, sel, period, cfg["scale"], cost_factor, payload_divisor)


def dec(x):
    """Decimal text of a Fraction with a finite expansion (0.0005)."""
    x = Fraction(x)
    s = f"{float(x):.12f}".rstrip("0").rstrip(".")
    if Fraction(s) != x:
        raise ValueError(f"{x} has no short decimal form")
    return s


def csv_text(app, cfg):
    """CSV in the format of apps/synthetic-app-e/synthetic-app-e.csv."""
    T, D = dec(app["period_s"]), dec(app["deadline_s"])
    buf = io.StringIO()
    buf.write("# CAR-V: vision subgraph of CAR (apps/shi-2010) on the time scale of application E; "
              "generated by python -m rttools.paper.carv generate (config experiments/car-v/config.json); "
              "do not edit\n")
    buf.write(f"# Selection: the {len(app['flows'])} flows of SHI2010.csv with period "
              f"{dec(app['source_period_s'])} s (the shortest period of CAR) and their {len(app['tasks'])} tasks\n")
    buf.write(f"# Task rows: Period = release period T (s); Capacity = c^(v) = {app['cost_factor']} "
              f"round(w(v) {dec(app['source_period_s'])} / {dec(Fraction(str(cfg['scale']['hyperperiod_s'])))}) + "
              f"{app['scheduler_cycles']} cycles (w(v) of shi-2010.txt); Deadline = end-to-end deadline "
              f"D = (L + 1) T, L = {app['longest_path']} edges of the longest path (s)\n")
    buf.write(f"# Flow rows: Period = T (s); Data = floor(bytes of SHI2010.csv / {app['payload_divisor']}); "
              "Deadline = T (s), not used by the phase model\n")
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["#tasks", "", "", "", "", ""])
    w.writerow(["Task", "Period", "Capacity", "Deadline", "Acronym", "Description"])
    for i, (t, c) in enumerate(app["tasks"], 1):
        w.writerow([i, T, c, D, t, "Task " + t])
    w.writerow(["#flows", "", "", "", "", ""])
    w.writerow(["Flow", "Period", "Data", "Deadline", "Source", "Target"])
    for i, (a, b, d) in enumerate(app["flows"], 1):
        w.writerow([i, T, d, T, a, b])
    w.writerow(["#parameters", "", "", "", "", ""])
    w.writerow(["Parameter", "Value", "", "", "", ""])
    w.writerow(["release_model", "phase", "", "", "", ""])
    w.writerow(["scheduler_cycles", app["scheduler_cycles"], "", "", "", ""])
    return buf.getvalue()


# ------------------------------------------------------------ memory

def memory(app, mapping, mem):
    """Heap bytes per PE (model of the module docstring). `mapping`:
    {task: node}; `mem`: config "memory". Returns {"pes": {node: {...}},
    "worst_pe", "worst_bytes", "heap_bytes", "fits", "largest_payload",
    "payload_fits", "tasks_fit", "queue_fits"}."""
    blk = mem["block_header_bytes"]
    task_bytes = sum(b + blk for b in (mem["tcb_bytes"], mem["rt_bytes"], mem["stack_bytes"]))
    comm_bytes = mem["queue_bytes"] + blk + 4 * mem["queue_slots"] + blk

    def pkt(d):
        return mem["packet_header_bytes"] + (d + 3) // 4 * 4 + blk

    pes = {}
    for node in sorted(set(mapping.values())):
        ts = [t for t, _ in app["tasks"] if mapping[t] == node]
        out_f = [(a, b, d) for a, b, d in app["flows"] if a in ts]
        in_f = [(a, b, d) for a, b, d in app["flows"] if b in ts and mapping[a] != node]
        parts = {"tasks": (len(ts) + 1) * task_bytes, "comm": len(ts) * comm_bytes,
                 "send": sum(pkt(d) for _, _, d in out_f),
                 "receive": mem["receive_buffers"] * sum(pkt(d) for _, _, d in in_f)}
        slots = max([sum(1 for a, b, _ in app["flows"] if b == t) * mem["receive_buffers"] for t in ts] or [0])
        pes[str(node)] = dict(parts, tasks_list=ts, total=sum(parts.values()),
                              free=mem["heap_bytes"] - sum(parts.values()), queue_slots_used=slots)
    worst = max(pes, key=lambda n: (pes[n]["total"], -int(n)))
    largest = max(d for _, _, d in app["flows"])
    return {"pes": pes, "worst_pe": worst, "worst_bytes": pes[worst]["total"], "heap_bytes": mem["heap_bytes"],
            "fits": all(p["total"] <= mem["heap_bytes"] for p in pes.values()),
            "largest_payload": largest, "payload_fits": largest <= mem["max_payload_bytes"],
            "tasks_fit": all(len(p["tasks_list"]) + 1 <= mem["max_tasks"] for p in pes.values()),
            "queue_fits": all(p["queue_slots_used"] <= mem["queue_slots"] for p in pes.values())}


# ------------------------------------------------------------ flow

def clustering_rows(tasks, edges, n, criteria):
    """Rows of step 1 (ORT/GCM, four criteria): M2, inter-cluster edges,
    NoC volume, largest cluster cost; chosen = smallest M2."""
    chosen, clusters, rows = spiral.cluster_application(tasks, edges, n, criteria)
    total = sum(w for _, _, w in edges)
    out = []
    for r in rows:
        owner = {t: c for c, ts in r["clusters"].items() for t in ts}
        inter = [(a, b, w) for a, b, w in edges if owner[a] != owner[b]]
        vol = sum(w for _, _, w in inter)
        out.append({"criterion": r["criterion"], "M2": r["sigma"], "clusters": len(r["clusters"]),
                    "inter_edges": len(inter), "noc_volume": vol, "noc_volume_percent": 100 * vol / total,
                    "largest_cost": max(r["wcet"]), "smallest_cost": min(r["wcet"]),
                    "chosen": r["criterion"] == chosen,
                    "groups": [":".join(ts) for ts in r["clusters"].values()]})
    return chosen, clusters, out


def run_factor(cfg, apps, arch, k, q, tmp):
    """The analysis flow on CAR-V with cost factor k and payload divisor q."""
    app = build(cfg, apps, k, q)
    path = os.path.join(tmp, f"car-v-k{k}-q{q}.csv")
    with open(path, "w") as f:
        f.write(csv_text(app, cfg))
    with network.quiet():
        g, appname = appparser.loadFromFile(path)
        noc = nocparser.loadFromFile(arch)
    width, height = cli.mesh_size(noc)
    tasks, edges = spiral.from_networkx(g)
    plat = cfg["platform"]
    chosen, clusters, rows = clustering_rows(tasks, edges, width * height, spiral.CRITERIA)
    res = spiral.map_application(tasks, edges, width, height)
    entries = mapfile.from_dict(res["mapping"])
    scfg = search_config(plat["f0_hz"])
    with network.quiet():
        freq = search.minimum_frequency(g, noc, entries, appname, scfg)
        at_clock = search.network_check(g, noc, entries, appname, plat["clock_hz"], scfg)
    cpu = freq["cpu"]
    T = app["period_s"]
    clock = plat["clock_hz"]
    period_cycles = int(T * clock)

    # phase index, sequence of each PE, R_bound
    inst = instantiator.createInstance(g, noc, clock)
    win = release.task_windows(inst, entries)
    pe_of = {t: win[t]["node"] for t in win}
    phi = estimate.phases([(a, b) for a, b, _ in edges], pe_of)
    rb, vlast = estimate.response_bound(phi, {t: win[t]["finish"] for t in win}, period_cycles)
    fmin = freq["frequency_hz"]
    rb_min = None
    if fmin:
        rb_min = phi[vlast] * T * fmin + win[vlast]["finish"]

    # release window of each flow (phase model) and network time of its
    # packet at the clock (flowUnwrapper: XY route, occupancy)
    pf = release.phase_flows(inst, entries)
    with network.quiet():
        packets, _, _ = flowUnwrapper.unwrap(inst, noc, entries)
    net = {p["flow"]: p for p in packets}
    by_label = {d["label"]: (s, t) for s, t, d in inst["flows"]}
    flows = []
    for i, (a, b, d) in enumerate(app["flows"], 1):
        label = f"f{i}"
        if by_label[label] != (a, b):
            raise RuntimeError(f"flow {label} of the instance is {by_label[label]}, expected {(a, b)}")
        off, end = pf[label]
        p = net.get(label)
        flows.append({"flow": label, "source": a, "target": b, "bytes": d,
                      "src_pe": pe_of[a], "dst_pe": pe_of[b], "on_noc": pe_of[a] != pe_of[b],
                      "offset_cycles": off, "end_cycles": end, "window_cycles": end - off,
                      "hops": None if p is None else len(p["path"]),
                      "net_time_cycles": None if p is None else p["net_time"],
                      "slack_cycles": None if p is None else end - off - p["net_time"]})
    demand = {str(n): v for n, v in cpu["demand"].items()}
    f_cpu = freq["f_cpu_hz"]
    D_cycles = app["deadline_s"] * clock
    out = {
        "cost_factor": k, "payload_divisor": q,
        "period_s": float(T), "deadline_s": float(app["deadline_s"]), "longest_path": app["longest_path"],
        "tasks": len(app["tasks"]), "flows": len(app["flows"]),
        "costs": {t: c for t, c in app["tasks"]}, "largest_cost": max(c for _, c in app["tasks"]),
        "clustering": {"chosen": chosen, "rows": rows},
        "mapping": {str(e["node"]): list(e["tasks"]) for e in entries},
        "cluster_nodes": {c: res["cluster_nodes"][c] for c in res["clusters"]},
        "cpu": {"demand_cycles": demand, "phase_cycles": period_cycles,
                "phase_percent": {n: 100 * v / period_cycles for n, v in demand.items()},
                "f_cpu_hz": f_cpu, "utilization_at_clock": f_cpu / clock},
        "search": {"f_star_hz": freq["f_star_hz"],
                   "f_star_lower_hz": freq["network"]["lower"] if freq["network"] else None,
                   "attempts": len(freq["network"]["attempts"]) if freq["network"] else None,
                   "final_check": freq["final_check"], "frequency_hz": fmin,
                   "binding": None if fmin is None else
                   ("cpu" if f_cpu is not None and fmin == f_cpu and f_cpu > freq["f_star_hz"] else "network")},
        "network_at_clock": at_clock,
        "phases": phi, "phase_max": max(phi.values()),
        "response_bound": {"v_last": vlast, "phase": phi[vlast], "finish_cycles": win[vlast]["finish"],
                           "cycles_at_clock": rb, "ms_at_clock": rb / clock * 1e3,
                           "s_at_minimum": None if rb_min is None else float(rb_min / fmin),
                           "deadline_ms": float(app["deadline_s"]) * 1e3,
                           "deadline_percent": float(100 * rb / D_cycles),
                           "deadline_equals_phase_rule": app["deadline_s"] == (phi[vlast] + 1) * T},
        "sequences": {str(n): [t for t in ts] for n, ts in
                      release.pe_sequences([t for t, _ in app["tasks"]], [(a, b) for a, b, _ in edges],
                                           entries).items()},
        "windows": {t: {"start": win[t]["start"], "finish": win[t]["finish"], "node": win[t]["node"]}
                    for t in win},
        "flow_windows": flows,
        "packets_per_period": sum(1 for f in flows if f["on_noc"]),
        "local_flows": sum(1 for f in flows if not f["on_noc"]),
        "memory": memory(app, {t: int(n) for t, n in res["mapping"].items()}, cfg["memory"]),
        "tick_cycles": cfg["platform"]["tick_cycles"],
        "largest_cost_below_tick": max(c for _, c in app["tasks"]) < cfg["platform"]["tick_cycles"],
    }
    return out, app


def choose(results, plat):
    """Largest cost factor with f_CPU / clock <= max_utilization and a
    feasible network at the clock."""
    ok = [r for r in results if r["cpu"]["utilization_at_clock"] <= plat["max_utilization"]
          and r["network_at_clock"]["feasible"] and r["search"]["frequency_hz"] is not None
          and r["search"]["frequency_hz"] <= plat["clock_hz"]]
    if not ok:
        return None
    return max(ok, key=lambda r: r["cost_factor"])["cost_factor"]


def run(cfg, apps, arch, out_dir):
    """Generation check, every candidate (cost factor x payload divisor)
    and the outputs of the chosen one."""
    sc, plat = cfg["scale"], cfg["platform"]
    os.makedirs(out_dir, exist_ok=True)
    tmp = os.path.join(out_dir, "candidates")
    os.makedirs(tmp, exist_ok=True)
    ks = sorted(set(sc.get("cost_factor_candidates", [sc["cost_factor"]])) | {sc["cost_factor"]})
    qs = sorted(set(sc.get("payload_divisor_candidates", [sc["payload_divisor"]])) | {sc["payload_divisor"]})
    results = {}
    for k in ks:
        for q in qs:
            results[(k, q)], _ = run_factor(cfg, apps, arch, k, q, tmp)
    rule = choose([results[(k, sc["payload_divisor"])] for k in ks], plat)
    chosen = results[(sc["cost_factor"], sc["payload_divisor"])]
    app = build(cfg, apps)
    text = csv_text(app, cfg)
    with open(os.path.join(out_dir, "car-v.csv"), "w") as f:
        f.write(text)
    tmap = {t: int(n) for n, ts in chosen["mapping"].items() for t in ts}
    map_text = mapfile.to_text(mapfile.from_dict(tmap))
    with open(os.path.join(out_dir, "car-v.map"), "w") as f:
        f.write(map_text)
    repo = os.path.join(apps, cfg["app"]["dir"])
    m = {
        "app": {"csv": cfg["app"]["csv"], "map": cfg["app"]["map"],
                "csv_matches_repo": _same(os.path.join(repo, cfg["app"]["csv"]), text),
                "map_matches_repo": _same(os.path.join(repo, cfg["app"]["map"]), map_text)},
        "selection": {"source_period_s": float(app["source_period_s"]), "tasks": [t for t, _ in app["tasks"]],
                      "flows": len(app["flows"]), "longest_path": app["longest_path"]},
        "scale": {"period_s": float(app["period_s"]), "deadline_s": float(app["deadline_s"]),
                  "cost_factor": sc["cost_factor"], "payload_divisor": sc["payload_divisor"],
                  "scheduler_cycles": sc["scheduler_cycles"],
                  "utilization_preserving_factor": float(Fraction(plat["clock_hz"]) * app["period_s"]
                                                         / (Fraction(sc["base_hz"]) * app["source_period_s"]))},
        "rule": {"max_utilization": plat["max_utilization"], "chosen_cost_factor": rule,
                 "config_matches_rule": rule == sc["cost_factor"]},
        "candidates": {f"k{k}_q{q}": _summary(r) for (k, q), r in results.items()},
        "chosen": chosen,
    }
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1, default=_json)
    write_csvs(out_dir, m)
    write_values(os.path.join(out_dir, "values.tex"), m)
    return m


def _same(path, text):
    if not os.path.exists(path):
        return False
    with open(path) as f:
        return f.read() == text


def _json(x):
    if isinstance(x, Fraction):
        return float(x)
    raise TypeError(type(x).__name__)


def _summary(r):
    s = r["search"]
    return {"cost_factor": r["cost_factor"], "payload_divisor": r["payload_divisor"],
            "largest_cost": r["largest_cost"], "criterion": r["clustering"]["chosen"],
            "f_cpu_hz": r["cpu"]["f_cpu_hz"], "utilization_at_clock": r["cpu"]["utilization_at_clock"],
            "f_star_hz": s["f_star_hz"], "frequency_hz": s["frequency_hz"], "binding": s["binding"],
            "network_at_clock_feasible": r["network_at_clock"]["feasible"],
            "packets": r["network_at_clock"]["packets"], "skipped": r["network_at_clock"]["skipped"],
            "response_bound_ms": r["response_bound"]["ms_at_clock"],
            "deadline_percent": r["response_bound"]["deadline_percent"],
            "memory_worst_pe": r["memory"]["worst_pe"], "memory_worst_bytes": r["memory"]["worst_bytes"],
            "memory_free_bytes": r["memory"]["heap_bytes"] - r["memory"]["worst_bytes"],
            "memory_fits": r["memory"]["fits"], "largest_cost_below_tick": r["largest_cost_below_tick"]}


def write_csvs(out_dir, m):
    c = m["chosen"]
    with open(os.path.join(out_dir, "clustering.csv"), "w", newline="") as f:
        w = csv.writer(f)
        cols = ["criterion", "M2", "clusters", "inter_edges", "noc_volume", "noc_volume_percent", "largest_cost",
                "smallest_cost", "chosen"]
        w.writerow(cols)
        for r in c["clustering"]["rows"]:
            w.writerow([r[k] for k in cols])
    with open(os.path.join(out_dir, "factors.csv"), "w", newline="") as f:
        w = csv.writer(f)
        cols = list(next(iter(m["candidates"].values())))
        w.writerow(cols)
        for r in m["candidates"].values():
            w.writerow([r[k] for k in cols])
    with open(os.path.join(out_dir, "flows.csv"), "w", newline="") as f:
        w = csv.writer(f)
        cols = ["flow", "source", "target", "bytes", "src_pe", "dst_pe", "on_noc", "offset_cycles", "end_cycles",
                "window_cycles", "hops", "net_time_cycles", "slack_cycles"]
        w.writerow(cols)
        for r in c["flow_windows"]:
            w.writerow([r[k] for k in cols])
    with open(os.path.join(out_dir, "pes.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pe", "tasks", "demand_cycles", "phase_percent", "heap_tasks", "heap_comm", "heap_send",
                    "heap_receive", "heap_total", "heap_free"])
        for n in sorted(c["mapping"], key=int):
            p = c["memory"]["pes"][n]
            w.writerow([n, " ".join(c["sequences"][n]), c["cpu"]["demand_cycles"][n],
                        f"{c['cpu']['phase_percent'][n]:.1f}", p["tasks"], p["comm"], p["send"], p["receive"],
                        p["total"], p["free"]])


NUMBER_WORDS = {2: "two", 4: "four", 6: "six", 7: "seven", 8: "eight", 16: "sixteen", 32: "thirtytwo"}


def write_values(path, m):
    c = m["chosen"]
    lines = ["% generated by python -m rttools.paper.carv; do not edit"]

    def put(text, *name):
        lines.append(f"\\newcommand{{\\{macro_name('carv', *name)}}}{{{text}}}")

    def mhz(v):
        return "-" if v is None else f"{v / 1e6:.1f}"

    put(str(c["tasks"]), "tasks")
    put(str(c["flows"]), "flows")
    put(f"{m['selection']['source_period_s'] * 1e3:g}", "source", "period", "ms")
    put(f"{c['period_s'] * 1e3:g}", "period", "ms")
    put(f"{c['deadline_s'] * 1e3:g}", "deadline", "ms")
    put(str(c["longest_path"]), "longest", "path")
    put(str(m["scale"]["cost_factor"]), "cost", "factor")
    put(f"{m['scale']['utilization_preserving_factor']:g}", "utilization", "preserving", "factor")
    put(str(m["scale"]["payload_divisor"]), "payload", "divisor")
    put(f"{m['scale']['scheduler_cycles']:,}", "scheduler", "cycles")
    put(f"{c['largest_cost']:,}", "largest", "cost")
    put(c["clustering"]["chosen"].replace("_", "-"), "criterion")
    put(f"{min(r['M2'] for r in c['clustering']['rows']):,.0f}", "criterion", "m2")
    put(mhz(c["cpu"]["f_cpu_hz"]), "cpu", "mhz")
    put(f"{100 * c['cpu']['utilization_at_clock']:.1f}", "utilization", "percent")
    put(mhz(c["search"]["f_star_hz"]), "network", "mhz")
    put(mhz(c["search"]["frequency_hz"]), "minimum", "mhz")
    put(c["search"]["binding"] or "-", "binding")
    put(str(c["network_at_clock"]["packets"]), "packets")
    put(str(c["network_at_clock"]["skipped"]), "skipped")
    put(str(c["local_flows"]), "local", "flows")
    put(str(c["response_bound"]["phase"]), "phase", "max")
    put(c["response_bound"]["v_last"], "v", "last")
    put(f"{c['response_bound']['ms_at_clock']:.3f}", "response", "bound", "ms")
    put(f"{c['response_bound']['deadline_percent']:.1f}", "response", "bound", "deadline", "percent")
    put(f"{c['memory']['worst_bytes']:,}", "memory", "worst", "bytes")
    put(f"{c['memory']['heap_bytes']:,}", "memory", "heap", "bytes")
    put(f"{c['memory']['heap_bytes'] - c['memory']['worst_bytes']:,}", "memory", "free", "bytes")
    for key, r in m["candidates"].items():
        k, q = r["cost_factor"], r["payload_divisor"]
        kw, qw = NUMBER_WORDS.get(k, str(k)), NUMBER_WORDS.get(q, str(q))
        put(mhz(r["f_cpu_hz"]), "factor", kw, "divisor", qw, "cpu", "mhz")
        put(f"{100 * r['utilization_at_clock']:.1f}", "factor", kw, "divisor", qw, "utilization", "percent")
        put(f"{r['memory_worst_bytes']:,}", "factor", kw, "divisor", qw, "memory", "bytes")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.carv", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="write apps/car-v/car-v.csv from apps/shi-2010")
    g.add_argument("--config", required=True)
    g.add_argument("--apps", required=True, help="directory apps/ of the repository")
    g.add_argument("--out", default=None, help="CSV path (default: <apps>/<app dir>/<csv> of the config)")
    g.add_argument("--check", action="store_true", help="compare with the file instead of writing it")
    r = sub.add_parser("run", help="analysis flow on CAR-V")
    r.add_argument("--config", required=True)
    r.add_argument("--apps", required=True)
    r.add_argument("--arch", required=True)
    r.add_argument("--out", required=True)
    a = p.parse_args(argv)
    with open(a.config) as f:
        cfg = json.load(f)
    if a.cmd == "generate":
        app = build(cfg, a.apps)
        text = csv_text(app, cfg)
        out = a.out or os.path.join(a.apps, cfg["app"]["dir"], cfg["app"]["csv"])
        if a.check:
            same = _same(out, text)
            print(out + (": up to date" if same else ": differs from the generator"))
            return 0 if same else 1
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w") as f:
            f.write(text)
        print(f"wrote {out} ({len(app['tasks'])} tasks, {len(app['flows'])} flows, T = {dec(app['period_s'])} s, "
              f"D = {dec(app['deadline_s'])} s, cost factor {app['cost_factor']}, "
              f"payload divisor {app['payload_divisor']})")
        return 0
    m = run(cfg, a.apps, a.arch, a.out)
    for key, s in m["candidates"].items():
        print(f"  {key}: f_CPU {mhz_text(s['f_cpu_hz'])} ({100 * s['utilization_at_clock']:.1f}% of the clock), "
              f"f* {mhz_text(s['f_star_hz'])}, minimum {mhz_text(s['frequency_hz'])} ({s['binding']}); "
              f"R_bound {s['response_bound_ms']:.3f} ms ({s['deadline_percent']:.1f}% of D); "
              f"heap of PE {s['memory_worst_pe']} {s['memory_worst_bytes']:,} B "
              f"({'fits' if s['memory_fits'] else 'does not fit'})")
    c = m["chosen"]
    print(f"  chosen: cost factor {m['scale']['cost_factor']} (rule: {m['rule']['chosen_cost_factor']}), "
          f"payload divisor {m['scale']['payload_divisor']}, criterion {c['clustering']['chosen']}, "
          f"{c['network_at_clock']['packets']} packets on the NoC, {c['local_flows']} local flows")
    print(f"  apps/{cfg['app']['dir']}: csv {'matches' if m['app']['csv_matches_repo'] else 'differs'}, "
          f"map {'matches' if m['app']['map_matches_repo'] else 'differs'}")
    print("wrote " + a.out)
    return 0


def mhz_text(v):
    return "none" if v is None else f"{v / 1e6:.3f} MHz"


if __name__ == "__main__":
    sys.exit(main())
