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
| tab82.tex, tab82.csv | Flow characterization (Tab. 8.2), derived from the estimates, plus the measured latency |
| thesis.tex, thesis.csv | Values printed in the thesis next to the values of this run |
| values.tex | LaTeX macros with the numbers, for the text of the article |
| (metrics.json) cpu, response_bound | CPU demand per PE, f_CPU and the response bound R^ of the estimate |
| fig812.svg, fig812.pdf | Gantt of the first complete hyperperiod |

`check` compares metrics.json with a reference file and exits with 1 when
a value differs (integers exactly; floats within 1e-6 relative).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys

from rttools.bench_t import estimate as cpu_estimate
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


def iteration_starts(tr, cfg, clk):
    """Start of each iteration: first dispatch of the source task at or
    after each release (TRIGGER line); without TRIGGER lines, the first
    dispatch after each multiple of the release period from warmup."""
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
        if nxt is not None and (not out or nxt > out[-1]):
            out.append(nxt)
    return out


def responses(tr, cfg, clk):
    """Response time of each iteration with the criterion of the code:
    J joins any `packets_per_iteration` packets (weird_a.c), so iteration k
    is complete with the (k * packets_per_iteration)-th packet that reaches
    J; it ends when J leaves the CPU after that packet arrived."""
    j = cfg["join"]
    starts = iteration_starts(tr, cfg, clk)
    if not starts:
        return []
    first = starts[0]
    arrivals = sorted(m.time for m in tr.lane_marks(j["pe"])
                      if m.kind == "recv" and m.label.split()[-1] in j["tags"] and m.time >= first)
    runs = [(s.start, s.end) for s in tr.lane_slices(j["pe"]) if s.label == j["task"]]
    hp = clk.raw(cfg["release_period_s"] * cfg["iterations_per_hyperperiod"])
    anchor = clk.raw(cfg["first_hyperperiod_s"])
    out = []
    for k, s in enumerate(starts, start=1):
        idx = k * j["packets_per_iteration"] - 1
        if idx >= len(arrivals):
            break
        a = arrivals[idx]
        end = next((e for (b, e) in runs if e > a and e < tr.t1), None)
        if end is None:
            break
        offset = (s - anchor) % hp
        out.append({"iteration": k, "start": s, "last_packet": a, "end": end,
                    "response_raw": end - s, "response_cycles": exact(clk.cycles(end - s)),
                    "response_ms": clk.ms(end - s),
                    "release_offset_ms": round(clk.ms(offset - (offset % clk.raw(cfg["release_period_s"]))), 6)})
    return out


def per_position(resp):
    """Maximum and minimum response for each release offset in the
    hyperperiod (the pattern repeats every hyperperiod)."""
    by = {}
    for r in resp:
        by.setdefault(r["release_offset_ms"], []).append(r["response_ms"])
    return [{"release_offset_ms": k, "count": len(v), "min_ms": min(v), "max_ms": max(v)}
            for k, v in sorted(by.items())]


def tab82(cfg, tr, clk):
    """Flow characterization. Minimum release = finish of the source task
    in its sequence; deadline = start of the target task in its sequence.
    Volume = packet size
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
            "deadline": sched[f["target"]]["start"],
            "volume_bytes": int(f["tag"]), "period": period,
            "latency_min_cycles": exact(clk.cycles(min(lat))) if lat else None,
            "latency_max_cycles": exact(clk.cycles(max(lat))) if lat else None,
            "packets": len(lat),
        })
    return rows


# ------------------------------------------------------------ outputs

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

def analyze(log_path, cfg, out_dir, unit=None):
    tr = load(log_path, cfg, unit)
    clk = Clock(tr.unit, cfg["clock_hz"])
    windows = hyperperiods(tr, cfg, clk)
    if not windows:
        raise ValueError("the log has no complete hyperperiod after first_hyperperiod_s")
    measured = cpu_per_iteration(tr, cfg, clk, windows)
    est = estimates(cfg)
    rows83, mean83 = tab83(measured, est, cfg)
    resp = responses(tr, cfg, clk)
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
        "iterations": {"all": [{k: r[k] for k in ("iteration", "response_cycles", "response_ms", "release_offset_ms")}
                               for r in resp],
                       "per_release_offset": per_position(resp),
                       "max_ms": max_ms, "deadline_ms": deadline_ms,
                       "max_deadline_percent": 100 * max_ms / deadline_ms if max_ms else None},
        "tab82": rows82,
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
                "Flows (cycles; release and deadline add phase $\\times$ pv, "
                f"pv = {fmt_int(m['parameters']['release_period_cycles'])} cycles).",
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
        m = analyze(args.log, cfg, args.out, unit)
        print(f"{m['log']}: unit {m['unit']['name']} (detected {m['unit']['detected']}), "
              f"{m['parameters']['hyperperiods']} hyperperiods")
        for r in m["tab83"]["rows"]:
            print(f"  {r['cluster']:5s} measured {r['measured']:>10,} estimated {r['estimated']:>10,} "
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
    diffs = check(args.metrics, args.reference)
    for d in diffs:
        print(d)
    print("match" if not diffs else f"{len(diffs)} differences")
    return 0 if not diffs else 1


if __name__ == "__main__":
    sys.exit(main())
