"""Reproduction of the results of Ch. 8 (exp-23) from a simulation log.

    python -m rttools.paper.exp23 analyze <log> --config <config.json> --out <dir>
        [--listing <image.lst> --listing-without <image.lst>]
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
| (metrics.json) sequences | Dispatch order of each cluster: kernel rule on the creation order of the application CSV (config `application`) |
| (metrics.json) instrumentation | With --listing and --listing-without (objdump listings of the image with and without the instrumentation writes, experiments/exp23/build_sw.sh): upper bound of the instrumentation cycles in the measured CPU time per cluster (rttools/paper/instrumentation.py) |
| (metrics.json) phase_conformance | With ITER lines: executions of each task per phase and CPU of each PE per phase against t(V_k), the conformance with the phase model (rttools/paper/phasecheck.py; release rule of the run from the RUN_INFO line `release`, or --release) |
| (metrics.json) per_iteration; packets_per_iteration.csv | Send and arrival of each packet against the phase of its own iteration; with ITER lines, also the response of each iteration to the end of J for it (iterations_markers.csv) and the iterations that a task runs in the run of the previous one |
| fig812.svg, fig812.pdf | Gantt of the first complete hyperperiod |
| network.tex, network.csv, network_packets.csv | Network latency per flow and per packet from the FLIT lines of the packet monitor (only when the log has them) |
| tt_packets.csv, metrics.json "tt" | Packets between PEs of a run with the time-triggered injection (RUN_INFO injection=tt; --arch and --map) against the link schedule of the table of the image (rttools/paper/ttcheck.py) |

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
import bisect
import csv
import json
import math
import os
import sys

from rttools.bench_t import estimate as cpu_estimate
from rttools.paper import instrumentation
from rttools.modules.instances import release
from rttools.modules.io import appparser
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


ISR_RULES = ("no_nesting", "nesting")


def isr_rule(info):
    """Interrupt rule of the image of a run: the RUN_INFO line `isr`
    (simulate.sh: no_nesting, the kernel default, every handler leaves
    interrupts disabled until the return of _isr; nesting with
    ISR_NESTING=1, -DUCX_ISR_NESTING). A RUN_INFO without the line (the
    runs up to r11: A to H, CV, CV2, MA, W1, CF) or no RUN_INFO gives
    nesting, the kernel whose handlers enable interrupts before that
    return (the image of those runs)."""
    rule = (info or {}).get("isr", "nesting")
    if rule not in ISR_RULES:
        raise ValueError(f"RUN_INFO isr={rule!r}: expected one of {', '.join(ISR_RULES)}")
    return rule


CRT0_RULES = ("guard_readback", "guard", "plain")


def crt0_rule(info):
    """crt0.s of the image of a run (_isr and _interrupt_set of
    arch/riscv/hf-riscv-e): the RUN_INFO line `crt0` (simulate.sh, CRT0:
    guard_readback, the default, with the return test of _isr and the read
    back of IRQ_STATUS in _interrupt_set(0); guard, the return test only;
    plain, neither). A RUN_INFO without the line is of a run up to tag
    r11-rc4: guard for car_full of r11-rc4 (run CF3, return test in the
    build rule of car_full), plain otherwise (the runs up to r11 and TG, TH,
    TCV, TMA, W2, CF2 of r11-rc3); no RUN_INFO gives plain."""
    info = info or {}
    if "crt0" in info:
        rule = info["crt0"]
        if rule not in CRT0_RULES:
            raise ValueError(f"RUN_INFO crt0={rule!r}: expected one of {', '.join(CRT0_RULES)}")
        return rule
    if info.get("repo_tag") == "r11-rc4" and info.get("app") == "car_full":
        return "guard"
    return "plain"


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
    # ITER lines (iteration markers) are printed at rising edges too
    meta["iterations"] = [dict(m, time=edge(m["time"])) for m in tr.meta.get("iterations") or []]
    meta["edges_snapped"] = True
    return Trace(tr.name, tr.unit, list(tr.lanes), slices, marks, meta)


# ------------------------------------------------------------ loading

def load_config(path):
    """config.json of the experiment, with `application` (the CSV of the
    application, relative to the directory of the config) as an absolute
    path."""
    with open(path) as f:
        cfg = json.load(f)
    if cfg.get("application"):
        cfg["application"] = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(path)),
                                                           cfg["application"]))
    return cfg


def creation_order(cfg):
    """{cluster: [task, ...]}: creation order of the tasks of each cluster,
    from the creation rows of the application CSV (config `application`,
    #parameters; a row belongs to the cluster with the same tasks). The
    CSV is the source of the order: the log table pe_tasks (id 0 = IDLE,
    then the creation order) must follow it, otherwise the task ids of the
    log decode to other tasks; ValueError when it does not."""
    app = cfg.get("application")
    if not app:
        raise ValueError("config has no application (CSV with the creation rows)")
    if not os.path.isabs(app):
        raise ValueError("application path is relative (" + app + "); load the config with load_config")
    rows = appparser.readParameters(app).get("creation") or {}
    out = {}
    for cluster, tasks in cfg["estimate"]["clusters"].items():
        names = [n for n, _ in tasks]
        row = release.matching_sequence(cluster, names, rows, "creation order")
        if row is None:
            raise ValueError(f"no creation row of {os.path.basename(app)} holds the tasks of cluster {cluster}")
        out[cluster] = row
    for pe, cluster in cfg["clusters"].items():
        if cfg["pe_tasks"][pe] != ["IDLE"] + out[cluster]:
            raise ValueError(f"pe_tasks of PE {pe} ({', '.join(cfg['pe_tasks'][pe])}) differs from IDLE and the "
                             f"creation order of cluster {cluster} ({', '.join(out[cluster])})")
    return out


def task_pe(cfg):
    """task -> cluster of the PE that runs it."""
    return {n: c for c, ts in cfg["estimate"]["clusters"].items() for n, _ in ts}


def dispatch_sequences(cfg):
    """{cluster: [task, ...]}: dispatch order of each cluster in one phase,
    the kernel rule (rttools/bench_t/estimate.py, dispatch_order) on the
    creation order (creation_order) with the phase index of the task graph
    of the config."""
    edges = [tuple(e) for e in cfg["task_graph"]["edges"]]
    phi = cpu_estimate.phases(edges, task_pe(cfg))
    return {c: cpu_estimate.dispatch_order(ts, edges, phi) for c, ts in creation_order(cfg).items()}


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
    clock["isr"] = isr_rule(info)
    clock["crt0"] = crt0_rule(info)
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
    scale) in the dispatch order of dispatch_sequences, divided by the
    scale. The start includes the scheduler cost; each cost includes the
    dispatch of the task."""
    est = cfg["estimate"]
    order = dispatch_sequences(cfg)
    out = {}
    for cluster, tasks in est["clusters"].items():
        cost = dict((n, w) for n, w in tasks)
        tasks = [(n, cost[n]) for n in order[cluster]]
        seq = cpu_estimate.sequence(tasks, est["scheduler_cycles"])
        for name, _ in tasks:
            out[name] = {"cluster": cluster, "start": exact(seq[name]["start"] / est["scale"]),
                         "finish": exact(seq[name]["finish"] / est["scale"])}
    return out


def phase_windows(cfg):
    """Release offset and absolute deadline of the first packet of each
    flow of the config, {flow name: (f^(source), P + s^(target))}, from the
    phase model of the analysis (rttools/modules/instances/release.py) on
    the characterized costs / scale, the scheduler cost / scale, the edges
    of the task graph and the creation order of each cluster (the model
    derives the dispatch order by the kernel rule, as for the CSV); cycles
    from the start of the source phase."""
    est = cfg["estimate"]
    scale = est["scale"]
    period = exact(cfg["release_period_s"] * cfg["clock_hz"])
    tasks, mapping = [], []
    for cluster, ts in est["clusters"].items():
        for name, w in ts:
            tasks.append((name, {"wcet": exact(w / scale)}))
        mapping.append({"node": cluster, "tasks": [n for n, _ in ts]})
    names = {(f["source"], f["target"]): f["name"] for f in cfg["flows"]}
    flows = [(u, v, {"label": names.get((u, v), f"{u}->{v}"), "period": period})
             for u, v in (tuple(e) for e in cfg["task_graph"]["edges"])]
    instance = {
        "tasks": tasks,
        "flows": flows,
        "release": {"model": release.PHASE, "scheduler_cycles": exact(est["scheduler_cycles"] / scale),
                    "sequences": None, "creation": creation_order(cfg)},
    }
    win = release.phase_flows(instance, mapping)
    return {f["name"]: win[f["name"]] for f in cfg["flows"]}


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
    per edge between PEs, config task_graph; on the same PE, one phase
    when the target runs before the source in the dispatch order) and the
    finish of the last task of the iteration in its sequence; P = phase in
    cycles. With the dispatch order J, G of GJ, J of iteration k runs first
    in phase 3 and G of iteration k ran in phase 1 (phi(J) = 3 comes from
    I and H), so f^(J) = c^(J)."""
    seq = cpu_sequence(cfg)
    pe_of = {t: v["cluster"] for t, v in seq.items()}
    order = release.sequence_positions(dispatch_sequences(cfg))
    phi = cpu_estimate.phases([tuple(e) for e in cfg["task_graph"]["edges"]], pe_of, order)
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
    ins = m.get("instrumentation")
    if ins:
        for kind, e in ins["events"].items():
            put(macro_name("instrumentation", kind, "instructions"), str(e["instructions"]))
            put(macro_name("instrumentation", kind, "cycles"), str(e["cycles"]))
        for cluster, c in ins["clusters"].items():
            put(macro_name(cluster, "instrumentation", "cycles"), fmt_int(round(c["max_cycles"], 1)))
            put(macro_name(cluster, "instrumentation", "percent"), f"{c['max_percent']:.2f}")
        put(macro_name("instrumentation", "max", "percent"), f"{ins['max_percent']:.2f}")
        put(macro_name("instrumentation", "max", "cluster"), ins["max_cluster"])
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
    order of manycore_pe.sv (the config uses the Y-X order of the stored
    log A)."""
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


# ---------------------------------------------------- flit times (monitor)

FLIT_INT_KEYS = ("t", "tag", "size", "head", "last", "block", "stall", "gap")


def parse_flit_lines(lines):
    """FLIT lines of the packet monitor (rtl/pe_checker.sv), optionally
    prefixed by `#`:

        FLIT TX t=<ns> src=<x-y> dst=<x-y> tag=<n> size=<p> head=<c> last=<c> block=<n> gap=<n>
        FLIT RX t=<ns> src=<x-y> dst=<x-y> tag=<n> size=<p> head=<c> last=<c> stall=<n> gap=<n>

    Returns (tx, rx): lists of dicts with the fields of each line (labels
    as printed, cycles as int)."""
    tx, rx = [], []
    for raw in lines:
        if "FLIT" not in raw:
            continue
        s = parsers._strip(raw)
        parts = s.split()
        if len(parts) < 3 or parts[0] != "FLIT" or parts[1] not in ("TX", "RX"):
            continue
        d = {"side": parts[1]}
        for kv in parts[2:]:
            k, _, v = kv.partition("=")
            d[k] = int(v) if k in FLIT_INT_KEYS else v
        (tx if parts[1] == "TX" else rx).append(d)
    return tx, rx


def _hops(a, b):
    (ax, ay), (bx, by) = (tuple(int(v) for v in n.split("-")) for n in (a, b))
    return abs(ax - bx) + abs(ay - by)


def _span(values):
    return (min(values), max(values)) if values else (None, None)


def network_latency(tx, rx, cfg, swap_xy=False, software=None):
    """Network latency of each packet from the FLIT lines, against the
    zero-load latency of the Hermes (experiments/zll).

    A TX line (source) and an RX line (destination) form a packet when they
    have the same source, destination and size flit; the k-th TX of a key
    pairs with its k-th RX (XY routing and wormhole switching keep the order
    of the packets of one source and destination). Per packet, in cycles:

    | Quantity | Definition |
    |---|---|
    | latency | RX.last - TX.head (header accepted at the LOCAL port of the source router to the last flit taken from the LOCAL port of the destination router) |
    | L0 | 6 (m + 1) + p + 1 (rttools.modules.routing.router.occupancy), m = XY hops, p = size flit |
    | header | RX.head - TX.head (header on the LOCAL output of the destination); 6 (m + 1) without contention |
    | stall, gap | RX window: edges with the flit on data_o and no credit of the DDMA, edges without a flit |

    Counting the edges of the RX window gives latency = header + p + 1 +
    stall + gap, so latency - L0 = (header - 6 (m + 1)) + stall + gap;
    `identity_errors` counts the packets where the printed numbers break
    it. A flow of the config takes the packets with its source PE,
    destination PE and p = getPacketFlits(tag); `tag_mismatch` counts its
    packets whose decoded tag differs from the tag of the flow.

    `software`: {flow name: [software latency in cycles, in send order]}
    (`->`/`<-` TAG marks of noc.c); when the counts agree, `driver` gives
    software minus network latency per packet.

    Labels: swap_xy (of the trace) swaps X and Y of the monitor labels, as
    for the `scheduled` and TAG lines. Returns None without FLIT lines."""
    if not tx and not rx:
        return None
    from rttools.modules.routing import router as hermes
    sw = parsers.swap_node if swap_xy else (lambda n: n)
    queues = {}
    for t in sorted(tx, key=lambda d: d["head"]):
        queues.setdefault((sw(t["src"]), sw(t["dst"]), t["size"]), []).append(t)
    packets, unpaired_rx = [], 0
    for r in sorted(rx, key=lambda d: d["last"]):
        q = queues.get((sw(r["src"]), sw(r["dst"]), r["size"]))
        if not q:
            unpaired_rx += 1
            continue
        t = q.pop(0)
        src, dst, p = sw(t["src"]), sw(t["dst"]), t["size"]
        m = _hops(src, dst)
        hop = hermes.getRoutingTime() * (m + 1)
        lat = r["last"] - t["head"]
        head = r["head"] - t["head"]
        packets.append({
            "src": src, "dst": dst, "tag_tx": t.get("tag"), "tag_rx": r.get("tag"), "size": p, "hops": m,
            "tx_t": t.get("t"), "rx_t": r.get("t"), "tx_head": t["head"], "tx_last": t["last"],
            "rx_head": r["head"], "rx_last": r["last"],
            "latency": lat, "L0": hop + p + 1, "latency_minus_L0": lat - (hop + p + 1),
            "header": head, "header_model": hop, "header_minus_model": head - hop,
            "stall": r.get("stall"), "gap": r.get("gap"), "tx_block": t.get("block"), "tx_gap": t.get("gap"),
            "identity_ok": (r["last"] - r["head"] == p + 1 + r.get("stall", 0) + r.get("gap", 0)
                            and t["last"] - t["head"] == p + 1 + t.get("block", 0) + t.get("gap", 0)),
            "flow": None,
        })
    unpaired_tx = sum(len(q) for q in queues.values())
    flows = []
    for f in cfg["flows"]:
        p = hermes.getPacketFlits(int(f["tag"]))
        pk = [x for x in packets if (x["src"], x["dst"], x["size"]) == (f["src_pe"], f["dst_pe"], p)]
        for x in pk:
            x["flow"] = f["name"]
        m = _hops(f["src_pe"], f["dst_pe"])
        hop = hermes.getRoutingTime() * (m + 1)
        row = {"flow": f["name"], "source": f["source"], "target": f["target"], "tag": f["tag"],
               "hops": m, "flits": p, "L0": hop + p + 1, "header_model": hop, "packets": len(pk),
               "tag_mismatch": sum(1 for x in pk if str(x["tag_tx"]) != f["tag"] or str(x["tag_rx"]) != f["tag"]),
               "at_L0": sum(1 for x in pk if x["latency_minus_L0"] == 0),
               "header_at_model": sum(1 for x in pk if x["header_minus_model"] == 0)}
        for k in ("latency", "latency_minus_L0", "header_minus_model", "stall", "gap", "tx_block", "tx_gap"):
            row[k + "_min"], row[k + "_max"] = _span([x[k] for x in pk if x[k] is not None])
        drv = None
        if software is not None and f["name"] in software and len(software[f["name"]]) == len(pk) and pk:
            net = [x["latency"] for x in sorted(pk, key=lambda x: x["tx_head"])]
            drv = [exact(s - n) for s, n in zip(software[f["name"]], net)]
        row["driver_min"], row["driver_max"] = _span(drv or [])
        flows.append(row)
    return {
        "model": "L0 = 6 (m + 1) + p + 1; header 6 (m + 1)",
        "tx": len(tx), "rx": len(rx), "packets": len(packets),
        "unpaired_tx": unpaired_tx, "unpaired_rx": unpaired_rx,
        "outside_flows": sum(1 for x in packets if x["flow"] is None),
        "identity_errors": sum(1 for x in packets if not x["identity_ok"]),
        "flows": flows,
        "per_packet": packets,
    }


def software_latencies(tr, cfg, clk):
    """Software latency (`->` to `<-` TAG marks, noc.c) of each packet of
    each flow in cycles, in send order (the pairing of figures.flows)."""
    out = {}
    for f in cfg["flows"]:
        tag = "TAG " + f["tag"]
        sends = sorted(mk.time for mk in tr.lane_marks(f["src_pe"]) if mk.kind == "send" and mk.label == tag)
        recvs = sorted(mk.time for mk in tr.lane_marks(f["dst_pe"]) if mk.kind == "recv" and mk.label == tag)
        out[f["name"]] = [clk.cycles(b - a) for a, b in zip(sends, recvs)]
    return out


def flit_times(log_path, tr, cfg, clk):
    with open(log_path, errors="replace") as f:
        tx, rx = parse_flit_lines(f)
    return network_latency(tx, rx, cfg, bool(tr.meta.get("swap_xy")), software_latencies(tr, cfg, clk))


# ----------------------------------------------------------- commands

def mhz_text(hz):
    """F_CLK in MHz for captions: 500, 435.2, 434.912."""
    return f"{hz / 1e6:.6f}".rstrip("0").rstrip(".")


def tt_check(log_path, tr, cfg, clk, per_packet, arch_path, map_path):
    """Packets between PEs of a run with the time-triggered injection
    (weird_a.c with the table weird_a_tt.h) against the link schedule at
    the clock of the run (rttools.paper.ttcheck): the n-th packet of a flow
    (n from 0, order of TX.head) comes from the job of its source in phase
    n + n(source)."""
    from rttools.paper import ttcheck
    from rttools.tui.model import parsers as tparsers
    from rttools.ucxgen.model import read_csv
    _, csv_flows, _ = read_csv(cfg["application"])
    label = {(f["source"], f["target"]): "f" + str(f["id"]) for f in csv_flows}
    flows = {f["name"]: f for f in cfg["flows"]}
    phi = response_bound(cfg)["phases"]
    pk = []
    for x in sorted(per_packet, key=lambda x: x["tx_head"]):
        f = flows.get(x["flow"])
        if f is None:
            continue
        pk.append(dict(x, tag=x["tag_tx"], flow_label=label[(f["source"], f["target"])]))
    count = {}
    for p in pk:
        p["n"] = count.get(p["flow"], 0)
        count[p["flow"]] = p["n"] + 1
    table = ttcheck.schedule_rows(cfg["application"], map_path, arch_path, cfg["clock_hz"])

    def phase_of(p, row, h):
        return h + phi[flows[p["flow"]]["source"]]
    return ttcheck.analyze_run(log_path, clk, release_times(tr, cfg, clk), table, pk, phase_of,
                               relabel=tparsers.swap_node if tr.meta.get("swap_xy") else None)


def phase_conformance(tr, cfg, clk, rule):
    """Executions per phase of each task (ITER begin markers) and CPU per
    phase of each PE against t(V_k) (estimates), with n(v) of
    response_bound (rttools/paper/phasecheck.py); None without ITER lines."""
    from rttools.paper import phasecheck
    marks = iteration_marks(tr)
    if not marks:
        return None
    phi = response_bound(cfg)["phases"]
    est = estimates(cfg)
    pe_of = {t: pe for pe, ts in cfg["pe_tasks"].items() for t in ts if t != "IDLE"}
    begins = {t: {k: it["begin"] for k, it in its.items()} for t, its in marks.items() if t in pe_of}
    return phasecheck.conformance(
        tr, clk, release_times(tr, cfg, clk), begins, lambda v, j: j - 1 + phi[v], pe_of,
        lambda pe, p: est[cfg["clusters"][pe]], rule)


def analyze(log_path, cfg, out_dir, unit=None, join=None, run_info="auto", listing=None, listing_without=None,
            release_rule=None, arch=None, mapping=None):
    """Every output of the module for one log; run_info: RUN_INFO path,
    "auto" (next to the log) or None (config clock_hz); listing and
    listing_without: objdump listings of the image with and without the
    instrumentation writes (bound of their cycles; None: no bound);
    release_rule: release rule of the run for phase_conformance ("tick",
    "data"; None: the RUN_INFO line `release`, "data" without it); arch
    and mapping (.gml and .map of E): the check of the time-triggered
    injection of a run with injection=tt in its RUN_INFO (tt_check)."""
    from rttools.paper import phasecheck, ttcheck
    tr, cfg, clk, clock = load_run(log_path, cfg, unit, run_info)
    info_path = run_info_path(log_path) if run_info == "auto" else run_info
    info = read_run_info(info_path) if info_path else {}
    rel_rule = phasecheck.release_rule(info, release_rule)
    injection = ttcheck.injection_rule(info)
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
    net = flit_times(log_path, tr, cfg, clk)
    per_packet = net.pop("per_packet") if net else []
    tt = None
    if injection == "tt" and net is not None and arch and mapping:
        tt = tt_check(log_path, tr, cfg, clk, per_packet, arch, mapping)
    tt_packets = tt.pop("per_packet") if tt else []
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
        "sequences": dispatch_sequences(cfg),
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
        "network": net,
        "phase_conformance": phase_conformance(tr, cfg, clk, rel_rule),
        "injection": injection,
        "tt": tt,
    }
    if listing or listing_without:
        if not (listing and listing_without):
            raise ValueError("the instrumentation bound needs --listing and --listing-without")
        m["instrumentation"] = instrumentation.analyze(tr, cfg, windows, measured, listing, listing_without)
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
    write_per_iteration(out_dir, m["per_iteration"])
    if tt_packets:
        with open(os.path.join(out_dir, "tt_packets.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(tt_packets[0]))
            for x in tt_packets:
                w.writerow(list(x.values()))
    if net:
        cols = list(per_packet[0].keys()) if per_packet else []
        with open(os.path.join(out_dir, "network_packets.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for x in per_packet:
                w.writerow([x[c] for c in cols])
        write_table(os.path.join(out_dir, "network"),
                    [("Flow", "flow"), ("m", "hops"), ("p", "flits"), ("$L_0$", "L0"),
                     ("Packets", "packets"), ("Latency min", "latency_min"), ("Latency max", "latency_max"),
                     ("Header $-$ 6(m+1) max", "header_minus_model_max"),
                     ("Stall min", "stall_min"), ("Stall max", "stall_max"), ("Gap max", "gap_max")],
                    net["flows"], "lrrrrrrrrrr",
                    "Network latency per packet (packet monitor): header accepted at the LOCAL port of the "
                    "source router to the last flit taken at the LOCAL port of the destination router, "
                    "cycles; latency $-$ $L_0$ = (header $-$ 6(m+1)) + stall + gap.",
                    "tab:exp23-network")
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
    a.add_argument("--release", choices=["auto", "tick", "data"], default="auto",
                   help="release rule of the run for phase_conformance (default: the line `release` of the "
                        "RUN_INFO; data without it, the runs before the release by tick)")
    k = sub.add_parser("clock", help="clock of a run at the minimum frequency of the flow")
    k.add_argument("frequency", help="metrics.json of rttools.paper.frequency run")
    k.add_argument("--config", required=True)
    k.add_argument("--map", default=None, help="mapping of the frequency run (default: the first .map file)")
    k.add_argument("--field", default=None, help="print only this field (for example f_clk_hz)")
    k.add_argument("--out", default=None, help="write the clock as JSON")
    a.add_argument("--listing", default=None,
                   help="objdump listing of the simulated image (build_sw.sh, image.lst)")
    a.add_argument("--listing-without", default=None,
                   help="objdump listing of the image built with -DUCX_NO_INSTRUMENTATION")
    a.add_argument("--arch", default=None,
                   help="architecture (.gml) of E: with --map, the check of the time-triggered injection of a run "
                        "with injection=tt in its RUN_INFO (rttools.paper.ttcheck)")
    a.add_argument("--map", default=None, help="mapping (.map) of E for the check of the time-triggered injection")
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    args = p.parse_args(argv)
    if args.cmd == "analyze":
        cfg = load_config(args.config)
        unit = None
        if args.unit:
            from rttools.tui.model.timeunit import RTL_PRESETS
            unit = RTL_PRESETS[args.unit]
        run_info = None if args.run_info == "none" else args.run_info
        m = analyze(args.log, cfg, args.out, unit, args.join, run_info, args.listing, args.listing_without,
                    args.release, args.arch, args.map)
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
        ins = m.get("instrumentation")
        if ins:
            ev = ", ".join(f"{k} {e['instructions']} instructions {e['cycles']} cycles" for k, e in ins["events"].items())
            print(f"  instrumentation per event: {ev}")
            for c, v in ins["clusters"].items():
                print(f"  {c:5s} instrumentation at most {cycles_text(round(v['max_cycles'], 1)):>6} cycles "
                      f"per iteration = {v['max_percent']:.2f}% of the measured CPU time")
        pc = m["phase_conformance"]
        if pc is not None:
            from rttools.paper import phasecheck
            print("  phase conformance: " + phasecheck.summary(pc)[0][2:])
        if m["injection"] == "tt":
            from rttools.paper import ttcheck
            for line in ttcheck.summary_lines(m["tt"]):
                print("  " + line.lstrip())
        net = m["network"]
        if net is None:
            print("  flit times: no FLIT lines")
        else:
            print(f"  flit times: {net['packets']} packets ({net['unpaired_tx']} TX and {net['unpaired_rx']} RX "
                  f"unpaired, {net['outside_flows']} outside the flows, {net['identity_errors']} identity errors)")
            for r in net["flows"]:
                print(f"  {r['flow']} m {r['hops']} p {r['flits']} L0 {r['L0']}: {r['packets']} packets, "
                      f"latency {r['latency_min']}-{r['latency_max']} ({r['at_L0']} at L0), "
                      f"header-6(m+1) {r['header_minus_model_min']}-{r['header_minus_model_max']}, "
                      f"stall {r['stall_min']}-{r['stall_max']}, gap {r['gap_min']}-{r['gap_max']}, "
                      f"driver {r['driver_min']}-{r['driver_max']}, tag mismatch {r['tag_mismatch']}")
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
