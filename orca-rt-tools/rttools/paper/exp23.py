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
| fig812.svg, fig812.pdf | Gantt of the first complete hyperperiod |

`check` compares metrics.json with a reference file and exits with 1 when
a value differs (integers exactly; floats within 1e-6 relative).

Clock of the run: `analyze` reads it from the RUN_INFO of the simulation
(experiments/exp23/simulate.sh: f_clk_hz, clock_half_period_fs,
release_cycles), next to the log (<dir>/<name>.RUN_INFO or <dir>/RUN_INFO)
or given by --run-info; without these keys, from config clock_hz. F_CLK is
the clock of the platform: the release period, the tick and the model
count cycles of F_CLK, and platform time = cycles / F_CLK. The simulator
clock has the half period of RUN_INFO (1e15 / (2 half) Hz, at or above
F_CLK); the log converts to cycles with that period, and the rising edges
are restored from $time when the period is not a whole number of log
units (see snap_to_edges).

    python -m rttools.paper.exp23 clock <frequency metrics.json> --config <config.json>

prints the clock of a run at the minimum frequency of the flow (see
flow_clock).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

from rttools.bench_t import estimate as cpu_estimate
from rttools.modules.instances import release
from rttools.tui.model import export, metrics, parsers
from rttools.tui.model.trace import Trace


# ------------------------------------------------------------ clock

# keys of RUN_INFO (simulate.sh) that give the clock of the run
RUN_INFO_CLOCK = ("f_clk_hz", "clock_half_period_fs")
# TIMER1 of the platform counts steps of this many cycles (hal.c,
# peripherals_minimal.vhd): the release period in cycles is a multiple
TICK_STEP_CYCLES = 16
# precision of the timescale of manycore_top.sv and manycore_pe.sv (1 fs)
TIMESCALE_PRECISION_FS = 1


def run_info_path(log_path):
    """RUN_INFO of a log: <dir>/<name>.RUN_INFO (logs/F.events.txt ->
    logs/F.RUN_INFO), else <dir>/RUN_INFO (output directory of
    simulate.sh); None when neither exists."""
    d, base = os.path.split(os.path.abspath(log_path))
    for cand in (os.path.join(d, base.split(".")[0] + ".RUN_INFO"), os.path.join(d, "RUN_INFO")):
        if os.path.isfile(cand):
            return cand
    return None


def read_run_info(path):
    """key=value tokens of a RUN_INFO file (several per line allowed)."""
    out = {}
    with open(path) as f:
        for line in f:
            for tok in line.split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    out.setdefault(k, v)
    return out


def half_period_fs(f_clk_hz, precision_fs=TIMESCALE_PRECISION_FS):
    """Half period of the simulator clock for F_CLK: the largest multiple
    of the timescale precision at or below 1e15 / (2 F_CLK) fs, so the
    clock runs at or above F_CLK (simulate.sh, CLOCK_HALF_PERIOD_FS)."""
    return (10 ** 15 // (2 * int(f_clk_hz) * precision_fs)) * precision_fs


def simulation_clock(cfg, info=None):
    """Clock of a run: {"clock_hz": F_CLK (cycles per second of platform
    time), "cycle_hz": frequency of the simulator clock (1e15 / (2 half)),
    "half_period_fs", "source": "RUN_INFO" or "config"}. RUN_INFO wins
    over config clock_hz; its release_cycles must equal
    release_period_s F_CLK of the config."""
    if info and all(k in info for k in RUN_INFO_CLOCK):
        f = int(info["f_clk_hz"])
        half = int(info["clock_half_period_fs"])
        if "release_cycles" in info:
            want = exact(cfg["release_period_s"] * f)
            if int(info["release_cycles"]) != want:
                raise ValueError(f"RUN_INFO release_cycles={info['release_cycles']} differs from "
                                 f"release_period_s * f_clk_hz = {want} of the config")
        source = "RUN_INFO"
    else:
        f = cfg["clock_hz"]
        half = None
        source = "config"
    if half is None or 2 * half * f == 10 ** 15:
        cycle_hz = f
    else:
        cycle_hz = 10 ** 15 / (2 * half)
    if cycle_hz < f:
        raise ValueError(f"simulator clock {cycle_hz} Hz below F_CLK {f} Hz")
    return {"clock_hz": f, "cycle_hz": cycle_hz, "half_period_fs": half, "source": source}


def flow_clock(f_min_hz, period_s, precision_fs=TIMESCALE_PRECISION_FS, step_cycles=TICK_STEP_CYCLES):
    """Clock of a run at the minimum frequency f_min of the flow: F_CLK is
    the first frequency at or above f_min whose release period T F_CLK is a
    whole number of TIMER1 steps (multiple of step_cycles / T Hz, 32 kHz
    for T = 0.5 ms), so the tick (F_CLK / F_TIMER cycles, hal.c) and the
    release generator (T F_CLK cycles, manycore_pe.sv) count the same
    period; the simulator clock has the half period of half_period_fs, at
    or above F_CLK."""
    grid = step_cycles / period_s
    if abs(grid - round(grid)) > 1e-6:
        raise ValueError(f"{step_cycles} / T = {grid} Hz is not an integer")
    grid = int(round(grid))
    f_clk = -(-int(math.ceil(f_min_hz - 1e-6)) // grid) * grid
    half = half_period_fs(f_clk, precision_fs)
    return {"f_min_hz": f_min_hz, "f_clk_hz": f_clk, "grid_hz": grid, "half_period_fs": half,
            "period_fs": 2 * half, "clock_hz_exact": 10 ** 15 / (2 * half),
            "release_cycles": exact(period_s * f_clk), "tick_steps": exact(period_s * f_clk / step_cycles)}


def clock_of_frequency_run(freq_metrics, cfg, map_name=None):
    """flow_clock of the minimum frequency of a mapping in the metrics.json
    of rttools.paper.frequency (default: the first .map file, the mapping
    of the RTL), with T = config release_period_s."""
    with open(freq_metrics) as f:
        m = json.load(f)
    runs = m["runs"]
    if map_name is None:
        map_name = next(k for k in runs if k.endswith(".map"))
    f_min = runs[map_name]["frequency_hz"]
    if f_min is None:
        raise ValueError(f"{map_name}: the flow returned no frequency")
    out = flow_clock(f_min, cfg["release_period_s"])
    out["map"] = map_name
    return out


def snap_to_edges(tr, half_fs):
    """Trace with each time moved to the rising edge of the simulator
    clock that it rounds: manycore_pe.sv prints $time (integer, unit of the
    log) at rising edges, and edge n occurs at (2 n + 1) half fs. With a
    period that is not a whole number of units (435.2 MHz: 2.297794 ns),
    the printed value differs from the edge by up to half a unit; the edge
    is the nearest one while the period exceeds one unit. The cycles
    between two events are then whole numbers."""
    unit_fs = round(tr.unit.seconds * 1e15)
    period_fs = 2 * half_fs
    if period_fs <= unit_fs:
        raise ValueError(f"clock period of {period_fs} fs not above the log unit of {unit_fs} fs")

    cache = {}

    def edge(t):
        if t in cache:
            return cache[t]
        t_fs = t * unit_fs
        n = round((t_fs - half_fs) / period_fs)
        e_fs = (2 * n + 1) * half_fs
        if abs(e_fs - t_fs) > unit_fs / 2 + 1e-6:
            raise ValueError(f"time {t} is not within half a unit of a rising edge")
        cache[t] = e_fs / unit_fs
        return cache[t]

    from dataclasses import replace
    slices = [replace(s, start=edge(s.start), end=edge(s.end)) for s in tr.slices]
    marks = [replace(m, time=edge(m.time)) for m in tr.marks]
    meta = dict(tr.meta)
    pk = []
    for p in tr.meta.get("packets") or []:
        q = dict(p)
        for k in ("send", "recv"):
            if q[k] is not None:
                q[k] = edge(q[k])
        q["latency"] = None if q["send"] is None or q["recv"] is None else q["recv"] - q["send"]
        pk.append(q)
    meta["packets"] = pk
    meta["edges_snapped"] = True
    return Trace(tr.name, tr.unit, list(tr.lanes), slices, marks, meta)


# ------------------------------------------------------------ loading

def load(log_path, cfg, unit=None, clock=None):
    """Trace of the log; `clock` (simulation_clock) gives the simulator
    clock, else config clock_hz."""
    names = cfg["pe_tasks"]
    tr = parsers.load_trace(log_path, "rtl", names, "auto", unit)
    hz = clock["cycle_hz"] if clock else cfg["clock_hz"]
    if tr.unit.clock_hz != hz:
        tr.unit = tr.unit.with_clock(hz)
    if tr.unit.seconds is None:
        raise ValueError("unknown time unit")
    tr.meta["edges_snapped"] = False
    if clock and clock["half_period_fs"] is not None:
        unit_fs = round(tr.unit.seconds * 1e15)
        if (2 * clock["half_period_fs"]) % unit_fs:
            tr = snap_to_edges(tr, clock["half_period_fs"])
    return tr


def load_run(log_path, cfg, unit=None, run_info="auto"):
    """(trace, config of the run, Clock, clock dict) of a log: the clock
    comes from run_info (path; "auto" = run_info_path(log_path); None =
    config only); the config of the run carries clock_hz = F_CLK."""
    path = run_info_path(log_path) if run_info == "auto" else run_info
    info = read_run_info(path) if path else None
    clock = simulation_clock(cfg, info)
    clock["run_info"] = os.path.basename(path) if path else None
    run_cfg = dict(cfg, clock_hz=clock["clock_hz"])
    tr = load(log_path, run_cfg, unit, clock)
    clock["edges_snapped"] = tr.meta["edges_snapped"]
    return tr, run_cfg, Clock(tr.unit, clock["clock_hz"], clock["cycle_hz"]), clock


class Clock:
    """Conversion between raw units of the log, cycles and seconds.

    clock_hz: F_CLK, cycles per second of platform time (config, RUN_INFO).
    cycle_hz: frequency of the simulator clock (default clock_hz), for the
    conversion of the log to cycles. Platform seconds = cycles / clock_hz."""

    def __init__(self, unit, clock_hz, cycle_hz=None):
        self.unit = unit
        self.hz = clock_hz
        self.cycle_hz = clock_hz if cycle_hz is None else cycle_hz
        # platform seconds per second of the simulator (1.0 at F_CLK)
        self.scale = self.cycle_hz / self.hz

    def raw(self, seconds):
        """Raw units of `seconds` of platform time."""
        return seconds / self.scale / self.unit.seconds

    def cycles(self, raw):
        return raw * self.unit.seconds * self.cycle_hz

    def seconds(self, raw):
        """Platform time of `raw` units."""
        return raw * self.unit.seconds * self.scale

    def ms(self, raw):
        # rounded to 1 ps: the products of 1e-10 and 1e-9 differ in the
        # last float digits for the same time
        return round(raw * self.unit.seconds * self.scale * 1e3, 9)


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
        # bounds at cycle boundaries; a clock period that is not a whole
        # number of units gives non-integral bounds (exact keeps them)
        out.append((exact(t), exact(t + hp)))
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


def iteration_releases(tr, cfg, clk):
    """(release, start) of each iteration: the release is the TRIGGER line
    (without TRIGGER lines, each multiple of the release period from
    warmup) and the start is the first dispatch of the source task at or
    after it."""
    src = cfg["source"]
    a_starts = [s.start for s in tr.lane_slices(src["pe"]) if s.label == src["task"]]
    releases = [m.time for m in tr.lane_marks("TRIGGER")]
    if not releases:
        p = clk.raw(cfg["release_period_s"])
        t = clk.raw(cfg["warmup_s"])
        while t <= tr.t1:
            releases.append(t)
            t += p
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
    put(macro_name("release", "period", "ms"), f"{m['parameters']['release_period_ms']:g}")
    put(macro_name("hyperperiod", "ms"), f"{m['parameters']['hyperperiod_ms']:g}")
    put(macro_name("cpu", "frequency", "mhz"), f"{m['cpu']['f_cpu_hz'] / 1e6:.1f}")
    put(macro_name("response", "bound", "cycles"), fmt_int(m["response_bound"]["cycles"]))
    put(macro_name("response", "bound", "ms"), f"{m['response_bound']['ms']:.3f}")
    put(macro_name("response", "bound", "deadline", "percent"), f"{m['response_bound']['deadline_percent']:.0f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


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

def mhz_text(hz):
    """F_CLK in MHz for captions: 500, 435.2, 434.912."""
    return f"{hz / 1e6:.6f}".rstrip("0").rstrip(".")


def analyze(log_path, cfg, out_dir, unit=None, join=None, run_info="auto"):
    """Every output of the module for one log; run_info: RUN_INFO path,
    "auto" (next to the log) or None (config clock_hz)."""
    tr, cfg, clk, clock = load_run(log_path, cfg, unit, run_info)
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
        "clock": clock,
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
                f"CPU time per iteration (cycles at {mhz_text(cfg['clock_hz'])} MHz). "
                f"Mean overestimation {mean83:.2f}\\%.",
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
    a.add_argument("--run-info", default="auto",
                   help="RUN_INFO of the simulation (clock of the run); default: next to the log; "
                        "`none`: config clock_hz")
    k = sub.add_parser("clock", help="clock of a run at the minimum frequency of the flow")
    k.add_argument("frequency", help="metrics.json of rttools.paper.frequency run")
    k.add_argument("--config", required=True)
    k.add_argument("--map", default=None, help="mapping of the frequency run (default: the first .map file)")
    k.add_argument("--field", default=None, help="print only this field (for example f_clk_hz)")
    k.add_argument("--out", default=None, help="write the clock as JSON")
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
        run_info = None if args.run_info == "none" else args.run_info
        m = analyze(args.log, cfg, args.out, unit, args.join, run_info)
        ck = m["clock"]
        print(f"{m['log']}: unit {m['unit']['name']} (detected {m['unit']['detected']}), "
              f"{m['parameters']['hyperperiods']} hyperperiods, join rule {m['join_rule']}")
        print(f"  clock F_CLK {mhz_text(ck['clock_hz'])} MHz from {ck['source']}"
              + ("" if ck["half_period_fs"] is None else
                 f" (half period {ck['half_period_fs']} fs, simulator {ck['cycle_hz']:.3f} Hz"
                 f"{', edges restored' if ck['edges_snapped'] else ''})"))
        for r in m["tab83"]["rows"]:
            print(f"  {r['cluster']:5s} measured {cycles_text(r['measured']):>10} "
                  f"estimated {cycles_text(r['estimated']):>10} "
                  f"{r['difference_percent']:+7.2f}%")
        print(f"  mean overestimation {m['tab83']['mean_difference_percent']:.2f}%; "
              f"max response {m['iterations']['max_ms']:.3f} ms of {m['iterations']['deadline_ms']:g} ms")
        print(f"  f_CPU {m['cpu']['f_cpu_hz'] / 1e6:.1f} MHz; response bound {m['response_bound']['ms']:.3f} ms "
              f"(task {m['response_bound']['task']}, phase {m['response_bound']['phase']})")
        mon = m["monitor"]
        print("  packet monitor: " + ("no CHKSUM lines" if mon is None else
                                       f"{mon['errors']} errors in {mon['send_pkts']} sent and "
                                       f"{mon['recv_pkts']} received packets ({mon['nodes']} PEs)"))
        print("wrote " + args.out)
        return 0
    if args.cmd == "clock":
        with open(args.config) as f:
            cfg = json.load(f)
        ck = clock_of_frequency_run(args.frequency, cfg, args.map)
        if args.out:
            with open(args.out, "w") as f:
                json.dump(ck, f, indent=1)
        if args.field:
            print(ck[args.field])
        else:
            print(f"minimum frequency {ck['f_min_hz']:.0f} Hz ({ck['map']}) -> F_CLK {ck['f_clk_hz']} Hz "
                  f"(multiple of {ck['grid_hz']} Hz), half period {ck['half_period_fs']} fs, "
                  f"period {ck['period_fs']} fs, clock {ck['clock_hz_exact']:.3f} Hz, "
                  f"release {ck['release_cycles']} cycles = {ck['tick_steps']} TIMER1 steps")
        return 0
    diffs = check(args.metrics, args.reference)
    for d in diffs:
        print(d)
    print("match" if not diffs else f"{len(diffs)} differences")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
