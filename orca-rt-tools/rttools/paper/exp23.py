"""Reproduction of the results of Ch. 8 (exp-23) from a simulation log.

    python -m rttools.paper.exp23 analyze <log> --config <config.json> --out <dir>
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

`analyze` reads the ModelSim/Questa transcript (or the extracted events),
takes the time unit from the $printtimescale lines and writes, in real
cycles and milliseconds:

| File | Content |
|---|---|
| metrics.json | Every number below, for `check` and for other scripts |
| tab83.tex, tab83.csv | CPU time per iteration of each cluster, measured and estimated (Tab. 8.3) |
| iterations.tex, iterations.csv | Response time of each iteration and the maximum against the deadline |
| tab82.tex, tab82.csv | Flow characterization (Tab. 8.2): release and deadline of the phase model, plus the measured latency |
| thesis.tex, thesis.csv | Values printed in the thesis next to the values of this run |
| values.tex | LaTeX macros with the numbers, for the text of the article |
| (metrics.json) cpu, response_bound | CPU demand per PE, f_CPU and the response bound R^ of the estimate |
| (metrics.json) per_iteration; packets_per_iteration.csv | Send and arrival of each packet against the phase of its own iteration; with ITER lines, also the response of each iteration to the end of J for it (iterations_markers.csv) and the iterations that a task runs in the run of the previous one |
| fig812.svg, fig812.pdf | Gantt of the first complete hyperperiod |

`check` compares metrics.json with a reference file and exits with 1 when
a value differs (integers exactly; floats within 1e-6 relative).
"""
from __future__ import annotations

import argparse
import bisect
import csv
import json
import math
import os
import sys

from rttools.bench_t import estimate as cpu_estimate
from rttools.modules.instances import release
from rttools.tui.model import export, metrics, parsers
from rttools.tui.model.trace import Trace


# ------------------------------------------------------------ loading

def load(log_path, cfg, unit=None):
    names = cfg["pe_tasks"]
    tr = parsers.load_trace(log_path, "rtl", names, "auto", unit)
    clock = cfg["clock_hz"]
    if tr.unit.clock_hz != clock:
        tr.unit = tr.unit.with_clock(clock)
    if tr.unit.seconds is None:
        raise ValueError("unknown time unit")
    return tr


class Clock:
    """Conversion between raw units of the log, cycles and seconds."""

    def __init__(self, unit, clock_hz):
        self.unit = unit
        self.hz = clock_hz

    def raw(self, seconds):
        return seconds / self.unit.seconds

    def cycles(self, raw):
        return raw * self.unit.seconds * self.hz

    def ms(self, raw):
        # rounded to 1 ps: the products of 1e-10 and 1e-9 differ in the
        # last float digits for the same time
        return round(raw * self.unit.seconds * 1e3, 9)


def exact(x):
    """int when the float is integral (after the unit conversion)."""
    r = round(x)
    return int(r) if abs(x - r) < 1e-6 else x


# ----------------------------------------------------------- analyses

def hyperperiods(tr, cfg, clk):
    """Complete hyperperiod windows [start, end) from first_hyperperiod_s."""
    hp = clk.raw(cfg["release_period_s"] * cfg["iterations_per_hyperperiod"])
    t = clk.raw(cfg["first_hyperperiod_s"])
    out = []
    while t + hp <= tr.t1 + 1e-9:
        out.append((int(round(t)), int(round(t + hp))))
        t += hp
    return out


def cpu_per_iteration(tr, cfg, clk, windows):
    """Tab. 8.3 (measured): non-IDLE time of each PE in each hyperperiod,
    divided by the iterations per hyperperiod, in cycles."""
    n = cfg["iterations_per_hyperperiod"]
    out = {}
    for pe, cluster in cfg["clusters"].items():
        per_hp = [clk.cycles(metrics.lane_stats(tr, pe, a, b).busy) / n for a, b in windows]
        out[cluster] = {
            "per_hyperperiod": [exact(v) for v in per_hp],
            "mean": exact(sum(per_hp) / len(per_hp)) if per_hp else None,
            "equal_in_all_hyperperiods": len(set(round(v, 6) for v in per_hp)) <= 1,
        }
    return out


def cpu_sequence(cfg):
    """Start and finish of each task in the sequence of its PE, in real
    cycles from the start of the phase: ORT/BENCH (rttools/bench_t/
    estimate.py) on the characterized costs of each cluster (thesis
    scale), divided by the scale. The start includes the scheduler cost;
    each cost includes the dispatch of the task."""
    est = cfg["estimate"]
    out = {}
    for cluster, tasks in est["clusters"].items():
        seq = cpu_estimate.sequence([(n, w) for n, w in tasks], est["scheduler_cycles"])
        for name, _ in tasks:
            out[name] = {"cluster": cluster, "start": exact(seq[name]["start"] / est["scale"]),
                         "finish": exact(seq[name]["finish"] / est["scale"])}
    return out


def phase_windows(cfg):
    """Release offset and absolute deadline of the first packet of each
    flow of the config, {flow name: (f^(source), P + s^(target))}, from the
    phase model of the analysis (rttools/modules/instances/release.py) on
    the characterized costs / scale, the scheduler cost / scale and the
    dispatch order of each cluster; cycles from the start of the source
    phase."""
    est = cfg["estimate"]
    scale = est["scale"]
    period = exact(cfg["release_period_s"] * cfg["clock_hz"])
    tasks, mapping, sequences = [], [], {}
    for cluster, ts in est["clusters"].items():
        for name, w in ts:
            tasks.append((name, {"wcet": exact(w / scale)}))
        mapping.append({"node": cluster, "tasks": [n for n, _ in ts]})
        sequences[cluster] = [n for n, _ in ts]
    instance = {
        "tasks": tasks,
        "flows": [(f["source"], f["target"], {"label": f["name"], "period": period}) for f in cfg["flows"]],
        "release": {"model": release.PHASE, "scheduler_cycles": exact(est["scheduler_cycles"] / scale),
                    "sequences": sequences},
    }
    return release.phase_flows(instance, mapping)


def estimates(cfg):
    """Tab. 8.3 (estimated): CPU demand c^(V_k) of each cluster, the sum of
    the characterized costs of its tasks / scale."""
    est = cfg["estimate"]
    return {c: exact(cpu_estimate.demand([(n, w) for n, w in tasks]) / est["scale"])
            for c, tasks in est["clusters"].items()}


def cpu_check(cfg, estimated):
    """CPU test, computed once (it does not depend on the candidate
    frequency of the link schedule): f_CPU = max_k c^(V_k) / T, and the
    demand of each PE in percent of the phase at the clock of the run."""
    period = exact(cfg["release_period_s"] * cfg["clock_hz"])
    f_cpu = cpu_estimate.cpu_frequency(estimated, cfg["release_period_s"])
    return {"demand_cycles": dict(estimated), "phase_cycles": period,
            "phase_percent": {c: 100 * v / period for c, v in estimated.items()},
            "f_cpu_hz": exact(f_cpu), "meets_phase": f_cpu <= cfg["clock_hz"]}


def response_bound(cfg):
    """R^ = phi(v_out) P + f^(v_out): phase index of each task (one phase
    per edge between PEs, config task_graph) and the finish of the last
    task of the iteration in its sequence; P = phase in cycles."""
    seq = cpu_sequence(cfg)
    pe_of = {t: v["cluster"] for t, v in seq.items()}
    phi = cpu_estimate.phases([tuple(e) for e in cfg["task_graph"]["edges"]], pe_of)
    period = exact(cfg["release_period_s"] * cfg["clock_hz"])
    bound, task = cpu_estimate.response_bound(phi, {t: v["finish"] for t, v in seq.items()}, period)
    ms = round(bound / cfg["clock_hz"] * 1e3, 9)
    deadline_ms = cfg["response_deadline_s"] * 1e3
    return {"cycles": bound, "ms": ms, "task": task, "phase": phi[task], "phases": phi,
            "deadline_ms": deadline_ms, "deadline_percent": 100 * ms / deadline_ms}


def tab83(measured, estimated, cfg):
    period_cycles = cfg["release_period_s"] * cfg["clock_hz"]
    rows = []
    for cluster in cfg["estimate"]["clusters"]:
        m = measured[cluster]["mean"]
        e = estimated[cluster]
        rows.append({"cluster": cluster, "measured": m, "estimated": e,
                     "difference": exact(e - m), "difference_percent": 100 * (e - m) / m,
                     "utilization_percent": 100 * m / period_cycles})
    mean = sum(r["difference_percent"] for r in rows) / len(rows)
    return rows, mean


def release_times(tr, cfg, clk):
    """Releases of the source task in raw units: the TRIGGER lines; without
    TRIGGER lines, each multiple of the release period from warmup."""
    releases = [m.time for m in tr.lane_marks("TRIGGER")]
    if not releases:
        p = clk.raw(cfg["release_period_s"])
        t = clk.raw(cfg["warmup_s"])
        while t <= tr.t1:
            releases.append(t)
            t += p
    return releases


def iteration_releases(tr, cfg, clk):
    """(release, start) of each iteration: the release is the TRIGGER line
    (without TRIGGER lines, each multiple of the release period from
    warmup) and the start is the first dispatch of the source task at or
    after it."""
    src = cfg["source"]
    a_starts = [s.start for s in tr.lane_slices(src["pe"]) if s.label == src["task"]]
    releases = release_times(tr, cfg, clk)
    out = []
    for r in releases:
        nxt = next((a for a in a_starts if a >= r), None)
        if nxt is not None and (not out or nxt > out[-1][1]):
            out.append((r, nxt))
    return out


def release_to_dispatch(tr, cfg, clk):
    """Cycles from each release to the first dispatch of the source task,
    over every release of the log (also the releases whose iteration does
    not complete before the end of the log): {"releases", "min_cycles",
    "max_cycles"}."""
    d = [exact(clk.cycles(s - r)) for r, s in iteration_releases(tr, cfg, clk)]
    return {"releases": len(d), "min_cycles": min(d) if d else None, "max_cycles": max(d) if d else None}


def iteration_starts(tr, cfg, clk):
    """Start of each iteration: first dispatch of the source task at or
    after each release (TRIGGER line); without TRIGGER lines, the first
    dispatch after each multiple of the release period from warmup."""
    return [s for _, s in iteration_releases(tr, cfg, clk)]


# join rule of J (config join.rule, option --join)
JOIN_PER_PRODUCER = "per_producer"
JOIN_ANY3 = "any3"
JOIN_RULES = (JOIN_PER_PRODUCER, JOIN_ANY3)


def join_rule(cfg, override=None):
    """Join rule of J: `override` (option --join), else config join.rule,
    else per_producer (the application of this tree)."""
    rule = override or cfg["join"].get("rule", JOIN_PER_PRODUCER)
    if rule not in JOIN_RULES:
        raise ValueError("unknown join rule " + repr(rule) + "; options: " + ", ".join(JOIN_RULES))
    return rule


def join_arrivals(tr, cfg, first, rule):
    """Instant at which J has the packets of iteration k (k = 1, 2, ...),
    for receives at the PE of J from `first` on.

    per_producer (weird_a.c after 379f388): J runs iteration k after the
    k-th packet of each producer; each producer sends one packet per
    iteration with its own tag (j.tags), so iteration k is complete at the
    latest of the k-th `<- TAG` of each tag.
    any3 (weird_a.c before 379f388, logs A to E): J consumes any
    `packets_per_iteration` packets, so iteration k is complete with the
    (k * packets_per_iteration)-th packet of any of the tags."""
    j = cfg["join"]
    marks = [m for m in tr.lane_marks(j["pe"]) if m.kind == "recv" and m.time >= first]
    if rule == JOIN_ANY3:
        arrivals = sorted(m.time for m in marks if m.label.split()[-1] in j["tags"])
        n = j["packets_per_iteration"]
        return [arrivals[k * n - 1] for k in range(1, len(arrivals) // n + 1)]
    per_tag = [sorted(m.time for m in marks if m.label.split()[-1] == tag) for tag in j["tags"]]
    return [max(ts[k] for ts in per_tag) for k in range(min(len(ts) for ts in per_tag))]


def closed_runs(tr, lane, task):
    """(start, end) of the slices of `task` on `lane` that a `scheduled`
    event closes. The parser ends the last slice of each lane at the end of
    the log (no event closes it), so only that slice leaves; a slice closed
    by an event at the last instant of the log counts."""
    slices = tr.lane_slices(lane)
    if not slices:
        return []
    open_slice = max(slices, key=lambda s: (s.start, s.end))
    return [(s.start, s.end) for s in slices if s.label == task and s is not open_slice]


def responses(tr, cfg, clk, rule=None):
    """Response time of each iteration: from the start of iteration k
    (iteration_starts) to the exit of J from the CPU after the instant at
    which J has the packets of iteration k (join_arrivals with the join
    rule of join_rule)."""
    j = cfg["join"]
    rule = join_rule(cfg, rule)
    rel_starts = iteration_releases(tr, cfg, clk)
    if not rel_starts:
        return []
    starts = [s for _, s in rel_starts]
    first = starts[0]
    complete = join_arrivals(tr, cfg, first, rule)
    runs = closed_runs(tr, j["pe"], j["task"])
    hp = clk.raw(cfg["release_period_s"] * cfg["iterations_per_hyperperiod"])
    anchor = clk.raw(cfg["first_hyperperiod_s"])
    out = []
    for k, s in enumerate(starts, start=1):
        if k > len(complete):
            break
        a = complete[k - 1]
        end = next((e for (b, e) in runs if e > a), None)
        if end is None:
            break
        offset = (s - anchor) % hp
        r = rel_starts[k - 1][0]
        out.append({"iteration": k, "release": r, "start": s, "last_packet": a, "end": end,
                    "response_raw": end - s, "response_cycles": exact(clk.cycles(end - s)),
                    "response_ms": clk.ms(end - s),
                    "release_to_dispatch_cycles": exact(clk.cycles(s - r)),
                    "response_from_release_cycles": exact(clk.cycles(end - r)),
                    "response_from_release_ms": clk.ms(end - r),
                    "release_offset_ms": round(clk.ms(offset - (offset % clk.raw(cfg["release_period_s"]))), 6)})
    return out


# ---------------------------------------------------- iteration markers

ITER_MARKERS = "markers"   # iteration of a packet from the ITER lines of its source task
ITER_FIFO = "fifo"         # iteration k = k-th packet of the flow (log without ITER lines)


def iteration_marks(tr):
    """Begin and end of the work of each iteration of each task, from the
    ITER lines (weird_a.c ITER_BEGIN/ITER_END, register 0x2000003C of
    manycore_pe.sv): {task: {k: {"lane", "begin", "end"}}}, raw units; {}
    for a log without markers (runs A to F). A repeated marker raises
    ValueError."""
    out = {}
    for m in tr.meta.get("iterations") or []:
        it = out.setdefault(m["task"], {}).setdefault(
            m["iteration"], {"lane": m["lane"], "begin": None, "end": None})
        if it[m["edge"]] is not None:
            raise ValueError(f"repeated ITER {m['edge']} {m['task']} {m['iteration']} at {m['time']}")
        it[m["edge"]] = m["time"]
    return out


def marker_iterations(tr, cfg, clk, marks):
    """Iterations of the markers: release r_j of iteration j = last
    release at or before the begin marker of the source task for j; start
    = first dispatch of the source task at or after r_j (as
    iteration_releases); end = end marker of J for j. The response of
    iteration j goes from r_j (and from the start) to the end of J for j,
    also when one run of J serves j and j + 1. run_end = exit of J from
    the CPU after the end marker (the end of the response of `responses`);
    pair_excess_cycles = run_end - end. One row per begin marker of the
    source task that follows a release; end and the responses are None
    while J has no end marker for the iteration (end of the log)."""
    src, j = cfg["source"]["task"], cfg["join"]["task"]
    rel = sorted(release_times(tr, cfg, clk))
    start_of = dict(iteration_releases(tr, cfg, clk))
    runs = closed_runs(tr, cfg["join"]["pe"], j)
    out = []
    for k in sorted(marks.get(src, {})):
        b = marks[src][k]["begin"]
        e = marks.get(j, {}).get(k, {}).get("end")
        i = bisect.bisect_right(rel, b) - 1 if b is not None else -1
        if i < 0:
            continue
        r = rel[i]
        s = start_of.get(r)
        done = e is not None
        run_end = next((re_ for (rb, re_) in runs if rb <= e <= re_), None) if done else None
        out.append({"iteration": k, "release": r, "start": s, "end": e, "run_end": run_end,
                    "response_from_release_cycles": exact(clk.cycles(e - r)) if done else None,
                    "response_from_release_ms": clk.ms(e - r) if done else None,
                    "response_cycles": exact(clk.cycles(e - s)) if done and s is not None else None,
                    "response_ms": clk.ms(e - s) if done and s is not None else None,
                    "pair_excess_cycles": exact(clk.cycles(run_end - e)) if run_end is not None else None})
    return out


def same_run_iterations(tr, cfg, marks):
    """For each task with markers: iterations, and iterations k whose begin
    falls in the CPU slice (run) of the end of k - 1, i.e. one run serves
    k - 1 and k (weird_a.c, recv_and_print consumes every queued packet)."""
    lanes = {t: pe for pe, ts in cfg["pe_tasks"].items() for t in ts}
    out = {}
    for task, its in sorted(marks.items()):
        lane = lanes.get(task) or next(iter(its.values()))["lane"]
        same = []
        for k in sorted(its):
            prev = its.get(k - 1)
            if prev is None or prev["end"] is None or its[k]["begin"] is None:
                continue
            a, b = tr.slice_at(lane, prev["end"]), tr.slice_at(lane, its[k]["begin"])
            if a is not None and a is b:
                same.append(k)
        out[task] = {"iterations": len(its), "same_run_as_previous": len(same), "iterations_same_run": same}
    return out


def _range(v):
    return {"min": min(v), "max": max(v)} if v else {"min": None, "max": None}


def _packet_summary(rows, r0):
    send = [p["send_cycles"] for p in rows]
    arr = [p["arrival_cycles"] for p in rows if p["arrival_cycles"] is not None]
    slack = [p["slack_cycles"] for p in rows if p["slack_cycles"] is not None]
    return {"packets": len(rows), "send": _range(send), "arrival": _range(arr),
            "sent_after_release": sum(1 for v in send if v > r0),
            "min_slack_cycles": min(slack) if slack else None}


def packet_iterations(tr, cfg, clk, marks=None, releases=None):
    """Send and arrival of each packet of each flow of the config against
    the phase of its own iteration k: cycles from r_k + phi(source) T, with
    r_k the release of iteration k, phi the phase index of the source
    (response_bound) and T the release period; compared with the release
    offset and the deadline of the phase model (phase_windows).

    The iteration of a packet: with ITER lines (`marks`), the iteration of
    the begin/end interval of the source task that contains the send;
    without them, k = position of the packet in the flow (FIFO, one packet
    per iteration from the first release). The arrival is the receive of
    the same position in the flow (FIFO per flow). `releases` maps
    iteration -> release (marker_iterations); default: the k-th release
    of iteration_releases."""
    period = exact(cfg["release_period_s"] * cfg["clock_hz"])
    phi = response_bound(cfg)["phases"]
    win = phase_windows(cfg)
    if releases is None:
        releases = {k: r for k, (r, _) in enumerate(iteration_releases(tr, cfg, clk), start=1)}
    mode = ITER_MARKERS if marks else ITER_FIFO
    flows = []
    for f in cfg["flows"]:
        tag = "TAG " + f["tag"]
        sends = sorted(m.time for m in tr.lane_marks(f["src_pe"]) if m.kind == "send" and m.label == tag)
        recvs = sorted(m.time for m in tr.lane_marks(f["dst_pe"]) if m.kind == "recv" and m.label == tag)
        spans = sorted((v["begin"], v["end"], k) for k, v in (marks or {}).get(f["source"], {}).items()
                       if v["begin"] is not None and v["end"] is not None)
        begins = [b for b, _, _ in spans]
        r0, d0 = win[f["name"]]
        shift = phi[f["source"]] * period
        rows, unassigned, mismatch = [], 0, 0
        for pos, t in enumerate(sends, start=1):
            if mode == ITER_MARKERS:
                i = bisect.bisect_right(begins, t) - 1
                k = spans[i][2] if i >= 0 and t <= spans[i][1] else None
                if k is None:
                    unassigned += 1
                    continue
                mismatch += k != pos
            else:
                k = pos
            r = releases.get(k)
            if r is None:
                continue
            a = recvs[pos - 1] if pos <= len(recvs) else None
            sc = exact(clk.cycles(t - r) - shift)
            ac = exact(clk.cycles(a - r) - shift) if a is not None else None
            rows.append({"flow": f["name"], "iteration": k, "parity": "odd" if k % 2 else "even",
                         "send_cycles": sc, "arrival_cycles": ac,
                         "after_release": sc > r0, "slack_cycles": exact(d0 - ac) if ac is not None else None})
        summary = _packet_summary(rows, r0)
        summary.update({"flow": f["name"], "source": f["source"], "target": f["target"],
                        "min_release": r0, "deadline": d0, "phase": phi[f["source"]],
                        "unassigned": unassigned, "fifo_mismatch": mismatch if mode == ITER_MARKERS else None,
                        "by_parity": {p: _packet_summary([x for x in rows if x["parity"] == p], r0)
                                      for p in ("odd", "even")},
                        "rows": rows})
        flows.append(summary)
    return {"source": mode, "flows": flows}


def per_iteration(tr, cfg, clk):
    """metrics.json per_iteration: packets against their own iteration
    (markers or FIFO); with markers, also the response of each iteration
    and the iterations served in the run of the previous one."""
    marks = iteration_marks(tr)
    out = {"markers": len(tr.meta.get("iterations") or []), "responses": None, "tasks": None}
    releases = None
    if marks:
        rows = marker_iterations(tr, cfg, clk, marks)
        rel = [r["release"] for r in rows]
        releases = {r["iteration"]: r["release"] for r in rows}
        its = [r for r in rows if r["end"] is not None]
        resp = [r["response_from_release_cycles"] for r in its]
        excess = [r["pair_excess_cycles"] for r in its if r["pair_excess_cycles"] is not None]
        out["responses"] = {
            "all": [{k: r[k] for k in ("iteration", "response_from_release_cycles", "response_from_release_ms",
                                       "response_cycles", "response_ms", "pair_excess_cycles")} for r in its],
            "complete": len(its),
            "releases_unique": len(set(rel)) == len(rel),
            "max_from_release_cycles": max(resp) if resp else None,
            "max_from_release_ms": max(r["response_from_release_ms"] for r in its) if its else None,
            "max_cycles": max((r["response_cycles"] for r in its if r["response_cycles"] is not None), default=None),
            "max_ms": max((r["response_ms"] for r in its if r["response_ms"] is not None), default=None),
            "max_pair_excess_cycles": max(excess) if excess else None,
            "deadline_ms": cfg["response_deadline_s"] * 1e3,
        }
        out["tasks"] = same_run_iterations(tr, cfg, marks)
    out.update(packet_iterations(tr, cfg, clk, marks, releases))
    return out


def packet_pairs(tr, cfg):
    """Pairs of `->`/`<-` lines (parsers.pair_packets pairs by tag in FIFO
    order) whose sender and receiver PEs differ and do not form a flow of
    the config: a receive paired with a send of another flow of the same
    tag (tag 1230: A->C and G->J). 0 when the pairing is consistent."""
    flows = {(f["tag"], f["src_pe"], f["dst_pe"]) for f in cfg["flows"]}
    tags = {f["tag"] for f in cfg["flows"]}
    bad = [p for p in tr.meta.get("packets") or []
           if p["tag"] in tags and p["src"] is not None and p["dst"] is not None
           and p["src"] != p["dst"] and (p["tag"], p["src"], p["dst"]) not in flows]
    return {"unexpected": len(bad)}


def per_position(resp):
    """Maximum and minimum response for each release offset in the
    hyperperiod (the pattern repeats every hyperperiod)."""
    by = {}
    for r in resp:
        by.setdefault(r["release_offset_ms"], []).append(r["response_ms"])
    return [{"release_offset_ms": k, "count": len(v), "min_ms": min(v), "max_ms": max(v)}
            for k, v in sorted(by.items())]


def tab82(cfg, tr, clk):
    """Flow characterization (phase model, cycles from the start of the
    phase in which the source sends). Minimum release = finish of the
    source task in its sequence; deadline = start of the target task in
    the next phase (phase + start in its sequence). Volume = packet size
    of weird_a.c (the tag). The measured latency comes from the log
    (send -> receive)."""
    sched = cpu_sequence(cfg)
    period = exact(cfg["release_period_s"] * cfg["clock_hz"])
    packets = tr.meta.get("packets") or []
    rows = []
    for f in cfg["flows"]:
        lat = [p["latency"] for p in packets
               if p["tag"] == f["tag"] and p["src"] == f["src_pe"] and p["dst"] == f["dst_pe"]
               and p["latency"] is not None]
        rows.append({
            "flow": f["name"], "source": f["source"], "target": f["target"],
            "min_release": sched[f["source"]]["finish"],
            "deadline": period + sched[f["target"]]["start"],
            "volume_bytes": int(f["tag"]), "period": period,
            "latency_min_cycles": exact(clk.cycles(min(lat))) if lat else None,
            "latency_max_cycles": exact(clk.cycles(max(lat))) if lat else None,
            "packets": len(lat),
        })
    return rows


# ------------------------------------------------------------ outputs

def cycles_text(v):
    """Cycles for the terminal: thousands separator; one decimal when the
    value is not integral (mean of half cycles)."""
    if isinstance(v, float) and not float(v).is_integer():
        return f"{v:,.1f}"
    return f"{int(round(v)):,}"


def fmt_int(v):
    if v is None:
        return "-"
    if isinstance(v, float) and not float(v).is_integer():
        return f"{v:,.1f}".replace(",", "\\,")
    return f"{int(round(v)):,}".replace(",", "\\,")


def write_table(path_base, header, rows, align, caption, label):
    with open(path_base + ".csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([h for h, _ in header])
        for r in rows:
            w.writerow([r[k] for _, k in header])
    with open(path_base + ".tex", "w") as f:
        f.write("% generated by python -m rttools.paper.exp23; do not edit\n")
        f.write("\\begin{table}[t]\n\\centering\n")
        f.write(f"\\caption{{{caption}}}\n\\label{{{label}}}\n")
        f.write(f"\\begin{{tabular}}{{{align}}}\n\\toprule\n")
        f.write(" & ".join(h for h, _ in header) + " \\\\\n\\midrule\n")
        for r in rows:
            cells = []
            for _, k in header:
                v = r[k]
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    cells.append(f"{v:+.2f}\\%" if k.endswith("percent_signed") else
                                 f"{v:.2f}\\%" if k.endswith("percent") else
                                 f"{v:.4f}" if k.endswith("_ms") else fmt_int(v))
                else:
                    cells.append("-" if v is None else str(v))
            f.write(" & ".join(cells) + " \\\\\n")
        f.write("\\bottomrule\n\\end{tabular}\n\\end{table}\n")


def macro_name(*parts):
    """LaTeX macro name from parts (letters only)."""
    digits = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four", "5": "Five",
              "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}
    out = "Exp"
    for p in parts:
        p = "".join(digits.get(ch, ch) for ch in str(p))
        out += "".join(ch for ch in p.title() if ch.isalpha())
    return out


def write_values(path, m):
    lines = ["% generated by python -m rttools.paper.exp23; do not edit"]

    def put(name, text):
        lines.append(f"\\newcommand{{\\{name}}}{{{text}}}")

    for r in m["tab83"]["rows"]:
        put(macro_name(r["cluster"], "measured"), fmt_int(r["measured"]))
        put(macro_name(r["cluster"], "estimated"), fmt_int(r["estimated"]))
        put(macro_name(r["cluster"], "difference"), f"{r['difference_percent']:.2f}")
    put(macro_name("mean", "overestimation"), f"{m['tab83']['mean_difference_percent']:.2f}")
    put(macro_name("max", "response", "ms"), f"{m['iterations']['max_ms']:.3f}")
    put(macro_name("max", "response", "deadline", "percent"), f"{m['iterations']['max_deadline_percent']:.0f}")
    it = m["iterations"]
    if it.get("max_cycles") is not None:
        put(macro_name("max", "response", "cycles"), fmt_int(it["max_cycles"]))
        put(macro_name("release", "to", "dispatch", "min", "cycles"), fmt_int(it["release_to_dispatch"]["min_cycles"]))
        put(macro_name("release", "to", "dispatch", "max", "cycles"), fmt_int(it["release_to_dispatch"]["max_cycles"]))
        allr = it["release_to_dispatch_all_releases"]
        put(macro_name("release", "to", "dispatch", "all", "min", "cycles"), fmt_int(allr["min_cycles"]))
        put(macro_name("release", "to", "dispatch", "all", "max", "cycles"), fmt_int(allr["max_cycles"]))
        put(macro_name("response", "from", "release", "max", "cycles"),
            fmt_int(it["response_from_release_max"]["cycles"]))
        put(macro_name("response", "from", "release", "max", "ms"), f"{it['response_from_release_max']['ms']:.3f}")
        put(macro_name("complete", "iterations"), str(it["complete"]))
    pr = (m.get("per_iteration") or {}).get("responses")
    if pr and pr["max_from_release_cycles"] is not None:
        # logs with ITER lines: response of each iteration to the end of J for it
        put(macro_name("marker", "response", "from", "release", "max", "cycles"),
            fmt_int(pr["max_from_release_cycles"]))
        put(macro_name("marker", "response", "from", "release", "max", "ms"), f"{pr['max_from_release_ms']:.3f}")
        put(macro_name("marker", "response", "max", "ms"), f"{pr['max_ms']:.3f}")
        if pr["max_pair_excess_cycles"] is not None:
            put(macro_name("marker", "pair", "excess", "max", "cycles"), fmt_int(pr["max_pair_excess_cycles"]))
    put(macro_name("release", "period", "ms"), f"{m['parameters']['release_period_ms']:g}")
    put(macro_name("hyperperiod", "ms"), f"{m['parameters']['hyperperiod_ms']:g}")
    put(macro_name("cpu", "frequency", "mhz"), f"{m['cpu']['f_cpu_hz'] / 1e6:.1f}")
    put(macro_name("response", "bound", "cycles"), fmt_int(m["response_bound"]["cycles"]))
    put(macro_name("response", "bound", "ms"), f"{m['response_bound']['ms']:.3f}")
    put(macro_name("response", "bound", "deadline", "percent"), f"{m['response_bound']['deadline_percent']:.0f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def write_per_iteration(out_dir, pi):
    """packets_per_iteration.csv (every log) and iterations_markers.csv
    (logs with ITER lines)."""
    with open(os.path.join(out_dir, "packets_per_iteration.csv"), "w", newline="") as f:
        w = csv.writer(f)
        keys = ("flow", "iteration", "parity", "send_cycles", "arrival_cycles", "after_release", "slack_cycles")
        w.writerow(keys + ("iteration_source",))
        for fl in pi["flows"]:
            for r in fl["rows"]:
                w.writerow([r[k] for k in keys] + [pi["source"]])
    if pi["responses"] is not None:
        with open(os.path.join(out_dir, "iterations_markers.csv"), "w", newline="") as f:
            w = csv.writer(f)
            keys = ("iteration", "response_from_release_cycles", "response_from_release_ms",
                    "response_cycles", "response_ms", "pair_excess_cycles")
            w.writerow(keys)
            for r in pi["responses"]["all"]:
                w.writerow([r[k] for k in keys])


def write_figure(tr, cfg, out_dir, window):
    """Gantt of one hyperperiod; lanes named `PE x-y (cluster)` in the X-Y
    order of the fixed RTL (the config uses the order of the original
    log)."""
    from rttools.tui.model.trace import Mark, Slice
    a, b = window
    lanes = [l for l in tr.lanes if l in cfg["clusters"]]

    def name(pe):
        x, y = pe.split("-")
        return f"PE {y}-{x} ({cfg['clusters'][pe]})"

    sub = Trace(tr.name, tr.unit, [name(l) for l in lanes],
                [Slice(name(s.lane), s.start, s.end, s.label, s.kind) for s in tr.slices if s.lane in lanes],
                [Mark(name(m.lane), m.time, m.kind, m.label) for m in tr.marks if m.lane in lanes], tr.meta)
    export.write_svg(sub, os.path.join(out_dir, "fig812.svg"), a, b, "ms",
                     title="Application E, first complete hyperperiod")
    try:
        export.write_png(sub, os.path.join(out_dir, "fig812.pdf"), a, b, "ms", title="", width_in=7.2)
    except ImportError:
        pass


def monitor_summary(log_path):
    """Totals of the CHKSUM lines of the packet monitor (rtl/pe_checker.sv);
    None when the log has none."""
    import re
    keys = ("send_err", "send_incomplete", "recv_err", "recv_spurious", "recv_missing")
    tot = {k: 0 for k in keys}
    tot.update(send_pkts=0, recv_pkts=0)
    n = 0
    with open(log_path, errors="replace") as f:
        for line in f:
            if "CHKSUM" not in line:
                continue
            n += 1
            for k, v in re.findall(r"(\w+)=(\d+)", line):
                if k in tot:
                    tot[k] += int(v)
    if n == 0:
        return None
    tot["nodes"] = n
    tot["errors"] = sum(tot[k] for k in keys)
    return tot


# ----------------------------------------------------------- commands

def analyze(log_path, cfg, out_dir, unit=None, join=None):
    tr = load(log_path, cfg, unit)
    clk = Clock(tr.unit, cfg["clock_hz"])
    windows = hyperperiods(tr, cfg, clk)
    if not windows:
        raise ValueError("the log has no complete hyperperiod after first_hyperperiod_s")
    measured = cpu_per_iteration(tr, cfg, clk, windows)
    est = estimates(cfg)
    rows83, mean83 = tab83(measured, est, cfg)
    rule = join_rule(cfg, join)
    resp = responses(tr, cfg, clk, rule)
    deadline_ms = cfg["response_deadline_s"] * 1e3
    max_ms = max(r["response_ms"] for r in resp) if resp else None
    rows82 = tab82(cfg, tr, clk)
    m = {
        "log": os.path.basename(log_path),
        "unit": {"name": tr.unit.name, "seconds": tr.unit.seconds, "detected": tr.meta["timescale_detected"],
                 "swap_xy": bool(tr.meta["swap_xy"])},
        "parameters": {
            "clock_hz": cfg["clock_hz"],
            "release_period_ms": cfg["release_period_s"] * 1e3,
            "hyperperiod_ms": cfg["release_period_s"] * cfg["iterations_per_hyperperiod"] * 1e3,
            "release_period_cycles": exact(cfg["release_period_s"] * cfg["clock_hz"]),
            "hyperperiods": len(windows),
            "first_hyperperiod_raw": windows[0],
        },
        "tab83": {"rows": rows83, "mean_difference_percent": mean83, "per_cluster": measured},
        "cpu": cpu_check(cfg, est),
        "response_bound": response_bound(cfg),
        "iterations": {"all": [{k: r[k] for k in ("iteration", "response_cycles", "response_ms", "release_offset_ms",
                                                  "release_to_dispatch_cycles", "response_from_release_cycles")}
                               for r in resp],
                       "per_release_offset": per_position(resp),
                       "complete": len(resp),
                       "max_ms": max_ms,
                       "max_cycles": max(r["response_cycles"] for r in resp) if resp else None,
                       "release_to_dispatch": {
                           "min_cycles": min(r["release_to_dispatch_cycles"] for r in resp) if resp else None,
                           "max_cycles": max(r["release_to_dispatch_cycles"] for r in resp) if resp else None},
                       "release_to_dispatch_all_releases": release_to_dispatch(tr, cfg, clk),
                       "response_from_release_max": {
                           "cycles": max(r["response_from_release_cycles"] for r in resp) if resp else None,
                           "ms": max(r["response_from_release_ms"] for r in resp) if resp else None},
                       "deadline_ms": deadline_ms,
                       "max_deadline_percent": 100 * max_ms / deadline_ms if max_ms else None},
        "tab82": rows82,
        "join_rule": rule,
        "packet_pairs": packet_pairs(tr, cfg),
        "monitor": monitor_summary(log_path),
        "per_iteration": per_iteration(tr, cfg, clk),
    }
    th = cfg.get("thesis", {})
    thesis_rows = []
    for c in cfg["estimate"]["clusters"]:
        r = next(x for x in rows83 if x["cluster"] == c)
        if c in th.get("tab83_measured_cycles", {}):
            thesis_rows.append({"item": f"Tab. 8.3 {c} measured (cycles)",
                                "thesis": th["tab83_measured_cycles"][c], "this_run": r["measured"]})
        if c in th.get("tab83_estimated_cycles", {}):
            thesis_rows.append({"item": f"Tab. 8.3 {c} estimated (cycles)",
                                "thesis": th["tab83_estimated_cycles"][c], "this_run": r["estimated"]})
    if "tab83_mean_overestimation_percent" in th:
        thesis_rows.append({"item": "Mean overestimation (%)", "thesis": th["tab83_mean_overestimation_percent"],
                            "this_run": round(mean83, 3)})
    if "release_period_ms" in th:
        thesis_rows.append({"item": "Release period of A (ms)", "thesis": th["release_period_ms"],
                            "this_run": m["parameters"]["release_period_ms"]})
    if "hyperperiod_ms" in th:
        thesis_rows.append({"item": "Hyperperiod and deadline (ms)", "thesis": th["hyperperiod_ms"],
                            "this_run": m["parameters"]["hyperperiod_ms"]})
    for i, v in enumerate(th.get("iterations_ms", []), start=1):
        pos = m["iterations"]["per_release_offset"]
        thesis_rows.append({"item": f"Iteration {i} response (ms)", "thesis": v,
                            "this_run": round(pos[i - 1]["max_ms"], 4) if i - 1 < len(pos) else None})
    m["thesis_comparison"] = thesis_rows

    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
    write_table(os.path.join(out_dir, "tab83"),
                [("Cluster", "cluster"), ("Measured", "measured"), ("Estimated", "estimated"),
                 ("Difference", "difference"), ("Difference (\\%)", "difference_percent"),
                 ("Utilization (\\%)", "utilization_percent")],
                rows83, "lrrrrr",
                f"CPU time per iteration (cycles at 500 MHz). Mean overestimation {mean83:.2f}\\%.",
                "tab:exp23-cpu")
    write_table(os.path.join(out_dir, "iterations"),
                [("Release offset (ms)", "release_offset_ms"), ("Iterations", "count"),
                 ("Min (ms)", "min_ms"), ("Max (ms)", "max_ms")],
                m["iterations"]["per_release_offset"], "rrrr",
                f"Response time per release in the hyperperiod; deadline {deadline_ms:g} ms.",
                "tab:exp23-response")
    write_table(os.path.join(out_dir, "tab82"),
                [("Flow", "flow"), ("Source", "source"), ("Target", "target"),
                 ("Min. release", "min_release"), ("Deadline", "deadline"), ("Volume (B)", "volume_bytes"),
                 ("Latency min", "latency_min_cycles"), ("Latency max", "latency_max_cycles")],
                rows82, "lllrrrrr",
                "Flows (cycles from the start of the phase in which the source sends; "
                "the deadline falls in the next phase, phase = "
                f"{fmt_int(m['parameters']['release_period_cycles'])} cycles).",
                "tab:exp23-flows")
    write_table(os.path.join(out_dir, "thesis"),
                [("Item", "item"), ("Thesis", "thesis"), ("This run", "this_run")],
                thesis_rows, "lrr", "Values of the thesis and of this run.", "tab:exp23-thesis")
    write_per_iteration(out_dir, m["per_iteration"])
    write_values(os.path.join(out_dir, "values.tex"), m)
    write_figure(tr, cfg, out_dir, windows[0])
    return m


def flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flatten(v, f"{prefix}{k}."))
    elif isinstance(d, list):
        for i, v in enumerate(d):
            out.update(flatten(v, f"{prefix}{i}."))
    else:
        out[prefix[:-1]] = d
    return out


def check(metrics_path, reference_path):
    """Returns the list of differences between metrics and reference (only
    the keys of the reference are compared)."""
    with open(metrics_path) as f:
        got = flatten(json.load(f))
    with open(reference_path) as f:
        ref = flatten(json.load(f))
    diffs = []
    for k, v in ref.items():
        if k.startswith("_"):
            continue
        g = got.get(k, "<missing>")
        if isinstance(v, float) or isinstance(g, float):
            ok = isinstance(g, (int, float)) and math.isclose(g, v, rel_tol=1e-6, abs_tol=1e-9)
        else:
            ok = g == v
        if not ok:
            diffs.append(f"{k}: expected {v!r}, got {g!r}")
    return diffs


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.exp23", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("log")
    a.add_argument("--config", required=True)
    a.add_argument("--out", required=True)
    a.add_argument("--unit", choices=["100ps", "1ns"], default=None,
                   help="raw unit when the log has no $printtimescale line")
    a.add_argument("--join", choices=JOIN_RULES, default=None,
                   help="join rule of J (default: config join.rule; any3 for the logs A to E of the "
                        "application before 379f388)")
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    args = p.parse_args(argv)
    if args.cmd == "analyze":
        with open(args.config) as f:
            cfg = json.load(f)
        unit = None
        if args.unit:
            from rttools.tui.model.timeunit import RTL_PRESETS
            unit = RTL_PRESETS[args.unit]
        m = analyze(args.log, cfg, args.out, unit, args.join)
        print(f"{m['log']}: unit {m['unit']['name']} (detected {m['unit']['detected']}), "
              f"{m['parameters']['hyperperiods']} hyperperiods, join rule {m['join_rule']}")
        for r in m["tab83"]["rows"]:
            print(f"  {r['cluster']:5s} measured {cycles_text(r['measured']):>10} "
                  f"estimated {cycles_text(r['estimated']):>10} "
                  f"{r['difference_percent']:+7.2f}%")
        print(f"  mean overestimation {m['tab83']['mean_difference_percent']:.2f}%; "
              f"max response {m['iterations']['max_ms']:.3f} ms of {m['iterations']['deadline_ms']:g} ms")
        print(f"  f_CPU {m['cpu']['f_cpu_hz'] / 1e6:.1f} MHz; response bound {m['response_bound']['ms']:.3f} ms "
              f"(task {m['response_bound']['task']}, phase {m['response_bound']['phase']})")
        pi = m["per_iteration"]
        late = ", ".join(f"{fl['flow']} {fl['sent_after_release']}/{fl['packets']}" for fl in pi["flows"])
        print(f"  per iteration ({pi['source']}, {pi['markers']} ITER lines): sent after the release {late}")
        if pi["responses"] is not None:
            pr = pi["responses"]
            print(f"  response to the end of J per iteration: max {pr['max_from_release_ms']:.3f} ms from the "
                  f"release, {pr['max_ms']:.3f} ms from the start ({pr['complete']} iterations)")
        mon = m["monitor"]
        print("  packet monitor: " + ("no CHKSUM lines" if mon is None else
                                       f"{mon['errors']} errors in {mon['send_pkts']} sent and "
                                       f"{mon['recv_pkts']} received packets ({mon['nodes']} PEs)"))
        print("wrote " + args.out)
        return 0
    diffs = check(args.metrics, args.reference)
    for d in diffs:
        print(d)
    print("match" if not diffs else f"{len(diffs)} differences")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
