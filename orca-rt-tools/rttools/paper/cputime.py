"""CPU time of each PE in the RTL runs, with the kernel work that runs while
the idle task holds the CPU.

The analyses of exp23 and rtlapp measure the CPU time of a PE as the time in
which a task other than the idle task holds the CPU (the slices between two
`scheduled` markers). Three kinds of kernel work run without a marker of
their own and fall in the slice of the task that holds the CPU: the tick
handler with the scheduler (from the TIMER line of the tick to the next
`scheduled` marker), the compare handler that injects a packet (TIMER line
off the tick), and the two receive handlers of a packet (FLIT RX at the head
flit and FLIT END after the last flit). When the idle task holds the CPU,
this work is missing from the busy time. The log marks when each handler
starts but not when it returns, so this module gives t_RTL as an interval:

    t_RTL,meas = busy + sum of the measured tick-to-dispatch times that start
                 in an idle slice
    t_RTL      = t_RTL,meas + n_inject * c_inject + n_size * c_size
                 + n_end * c_end + n_release * c_release

where n_inject counts the compare interrupts that fire in an idle slice,
n_size and n_end count the head flits and the ends of reception that fall in
an idle slice (each event charged once, with its own handler), and c_inject,
c_size and c_end are the static WCETs of the handlers in the image of the run
(experiments/wcet costs/tt <image>.handlers.json, key inject; rx_isr of the
config: irq2_handler and irq3_handler). n_release counts the release
interrupts that the PE acknowledges in an idle slice (TRIGGER-PE lines; PE
0-0 logs its acknowledgment as "TRIGGER: workflow iteration"), and c_release
is the static WCET of the release handler (release_isr of the config: the
term release of the kernel of experiments/wcet reference_r11g.json).
t_RTL,meas is the measured part (a lower bound of the CPU time) and t_RTL adds
the static bounds of the handlers that run in idle slices (an upper bound).

Windows: n = phi(v_last) + 1 consecutive releases from r_{phi(v_last)}
(0-indexed TRIGGER lines), the first window in which every phase holds a job
of every task (rtlapp.cpu_windows; exp23 took its windows from
first_hyperperiod_s). Each window value is the CPU time in the window divided
by n; each phase value is the CPU time of one phase [r_k, r_{k+1}), k >= n - 1.

    python -m rttools.paper.cputime analyze --config experiments/cputime/config.json --out build/cputime
    python -m rttools.paper.cputime check build/cputime/metrics.json experiments/cputime/reference.json
"""
import argparse
import json
import os
import re
import sys
from bisect import bisect_right

from rttools.paper import exp23, rtlapp
from rttools.tui.model import metrics as tmetrics
from rttools.tui.model import parsers

RE_TIMER = re.compile(r"^TIMER t=(\d+) pe=(\d+-\d+) cyc=(\d+)")
RE_FLIT = re.compile(r"^FLIT (RX|END) t=(\d+) src=(\S+) dst=(\S+) tag=(\d+)")
RE_ACK = re.compile(r"^TRIGGER-PE (\d+-\d+): release acknowledged at (\d+)")
RE_ACK0 = re.compile(r"^TRIGGER: workflow iteration at (\d+)")    # acknowledgment of PE 0-0


def num(x):
    return exp23.exact(x)


def kernel_events(log_path, swap, period_cycles):
    """{lane: {"tick": [t], "compare": [t], "packets": [(t_head, t_end)]}} in
    raw units of the log. A TIMER line is a tick when its cycle count has the
    residue modulo period_cycles of most TIMER lines of the log (the ticks of
    all PEs share one residue; a compare line falls off it)."""
    timers = []
    acks = {}
    rx = {}
    packets = {}
    with open(log_path, errors="replace") as fh:
        for raw in fh:
            s = raw.lstrip("# ").strip()
            m = RE_TIMER.match(s)
            if m:
                pe = parsers.swap_node(m.group(2)) if swap else m.group(2)
                timers.append((int(m.group(1)), pe, int(m.group(3))))
                continue
            m = RE_ACK.match(s)
            if m:
                pe = parsers.swap_node(m.group(1)) if swap else m.group(1)
                acks.setdefault(pe, []).append(int(m.group(2)))
                continue
            m = RE_ACK0.match(s)
            if m:
                acks.setdefault("0-0", []).append(int(m.group(1)))
                continue
            m = RE_FLIT.match(s)
            if m:
                kind, t, dst, tag = m.group(1), int(m.group(2)), m.group(4), m.group(5)
                dst = parsers.swap_node(dst) if swap else dst
                key = (dst, m.group(3), tag)
                if kind == "RX":
                    rx.setdefault(key, []).append(t)
                else:
                    heads = rx.get(key) or []
                    head = heads.pop(0) if heads else t
                    packets.setdefault(dst, []).append((head, t))
    res = {}
    for _, _, cyc in timers:
        res[cyc % period_cycles] = res.get(cyc % period_cycles, 0) + 1
    tick_res = max(res, key=res.get) if res else None
    ev = {}
    for t, pe, cyc in timers:
        kind = "tick" if cyc % period_cycles == tick_res else "compare"
        ev.setdefault(pe, {"tick": [], "compare": [], "packets": []})[kind].append(t)
    for pe, lst in packets.items():
        ev.setdefault(pe, {"tick": [], "compare": [], "packets": []})["packets"] = lst
    for pe, lst in acks.items():
        ev.setdefault(pe, {"tick": [], "compare": [], "packets": []})["release"] = lst
    return ev


def _idle(tr, lane, t):
    s = tr.slice_at(lane, t)
    return s is not None and tr.is_idle(s)


def _next_start(starts, t):
    i = bisect_right(starts, t)
    return starts[i] if i < len(starts) else None


def charge(tr, clk, lane, ev, a, b, costs):
    """Kernel work of `lane` in [a, b) that the idle task holds, in cycles."""
    e = ev.get(lane, {"tick": [], "compare": [], "packets": []})
    starts = [s.start for s in tr.lane_slices(lane)]
    tick = 0.0
    n_tick = 0
    for t in e["tick"]:
        if a <= t < b and _idle(tr, lane, t):
            nxt = _next_start(starts, t)
            if nxt is not None:
                tick += clk.cycles(min(nxt, b) - t)
                n_tick += 1
    n_inj = sum(1 for t in e["compare"] if a <= t < b and _idle(tr, lane, t))
    n_size = sum(1 for head, _ in e["packets"] if a <= head < b and _idle(tr, lane, head))
    n_end = sum(1 for _, end in e["packets"] if a <= end < b and _idle(tr, lane, end))
    n_rel = sum(1 for t in e.get("release", []) if a <= t < b and _idle(tr, lane, t))
    handlers = (n_inj * costs["inject"] + n_size * costs["rx_size"] + n_end * costs["rx_end"]
                + n_rel * costs["release"])
    return {"cycles": tick + handlers, "tick_cycles": tick, "handler_cycles": handlers, "ticks": n_tick,
            "injections": n_inj, "size_flits": n_size, "ends": n_end, "releases": n_rel}


def windows(releases, n, t1, p_raw):
    """[(a, b)] of n releases from r_{n-1}, and the phases [r_k, r_{k+1}),
    k >= n - 1, inside the log."""
    wins = []
    s = n - 1
    while s < len(releases):
        a = releases[s]
        b = releases[s + n] if s + n < len(releases) else a + n * p_raw
        if b > t1:
            break
        wins.append((a, b))
        s += n
    phases = []
    for k in range(n - 1, len(releases)):
        a = releases[k]
        b = releases[k + 1] if k + 1 < len(releases) else a + p_raw
        if b <= t1:
            phases.append((a, b))
    return wins, phases


def load(run, base):
    """(trace, Clock, lanes {lane: name}, estimates {lane: cycles}, n, period
    in cycles) of one run of the config."""
    p = lambda k: os.path.join(base, run[k])
    ref = json.load(open(p("reference")))
    if run["kind"] == "exp23":
        cfg0 = exp23.load_config(p("exp23_config"))
        tr, cfg, clk, clock = exp23.load_run(p("log"), cfg0)
        rows = {r["cluster"]: r["estimated"] for r in ref["tab83"]["rows"]}
        lanes = dict(cfg["clusters"])
        est = {lane: rows[name] for lane, name in lanes.items()}
        n = cfg["iterations_per_hyperperiod"]
        period_cycles = ref["parameters"]["release_period_cycles"]
    else:
        app = rtlapp.load_app(p("manifest"), p("csv"), p("map"), run.get("app"))
        tr, clk, clock = rtlapp.load_log(p("log"), app)
        win = ref["cpu_windows"] if "cpu_windows" in ref else ref["rtlapp"]["cpu_windows"]
        est = {lane: q["estimated"] for lane, q in win["pes"].items()}
        lanes = {lane: "+".join(q["tasks"]) for lane, q in win["pes"].items()}
        n = win["releases_per_window"]
        period_cycles = run["period_cycles"]
    return tr, clk, lanes, est, n, period_cycles


def analyze_run(run, base):
    tr, clk, lanes, est, n, period_cycles = load(run, base)
    costs = json.load(open(os.path.join(base, run["handlers"])))
    costs = {"inject": costs["inject"], "rx_size": run["rx_isr"][0], "rx_end": run["rx_isr"][1],
             "release": run["release_isr"]}
    static = run.get("static") or {}
    releases = sorted(m.time for m in tr.lane_marks("TRIGGER"))
    p_raw = releases[1] - releases[0]
    wins, phases = windows(releases, n, tr.t1, p_raw)
    ev = kernel_events(os.path.join(base, run["log"]), bool(tr.meta.get("swap_xy")), period_cycles)
    out = {}
    for lane, name in lanes.items():
        per, meas, busy_per, ch = [], [], [], []
        for a, b in wins:
            busy = clk.cycles(tmetrics.lane_stats(tr, lane, a, b).busy)
            c = charge(tr, clk, lane, ev, a, b, costs)
            per.append((busy + c["cycles"]) / n)
            meas.append((busy + c["tick_cycles"]) / n)
            busy_per.append(busy / n)
            ch.append(c)
        ph = []
        for a, b in phases:
            busy = clk.cycles(tmetrics.lane_stats(tr, lane, a, b).busy)
            ph.append(busy + charge(tr, clk, lane, ev, a, b, costs)["cycles"])
        mean = sum(per) / len(per)
        mean_meas = sum(meas) / len(meas)
        row = {
            "name": name,
            "estimated": est[lane],
            "per_window": [num(v) for v in per],
            "mean": num(mean),
            "window_max": num(max(per)),
            "phase_max": num(max(ph)),
            "busy_mean": num(sum(busy_per) / len(busy_per)),
            "measured_mean": num(mean_meas),
            "static_handlers_per_iteration": num(sum(c["handler_cycles"] for c in ch) / len(ch) / n),
            "idle_kernel_per_iteration": num(sum(c["cycles"] for c in ch) / len(ch) / n),
            "idle_injections": sum(c["injections"] for c in ch),
            "idle_size_flits": sum(c["size_flits"] for c in ch),
            "idle_ends": sum(c["ends"] for c in ch),
            "idle_ticks": sum(c["ticks"] for c in ch),
            "idle_releases": sum(c["releases"] for c in ch),
            "over_mean_percent": 100 * (est[lane] - mean) / mean,
            "over_measured_percent": 100 * (est[lane] - mean_meas) / mean_meas,
            "handler_share_percent": 100 * (mean - mean_meas) / mean,
            "over_window_max_percent": 100 * (est[lane] - max(per)) / max(per),
            "phase_max_below_estimate": max(ph) <= est[lane],
        }
        key = static.get("key", "name")
        sref = static.get("values", {}).get(name if key == "name" else lane)
        if sref is not None:
            row["static"] = sref
            row["static_over_mean_percent"] = 100 * (sref - mean) / mean
            row["static_over_measured_percent"] = 100 * (sref - mean_meas) / mean_meas
        out[lane] = row

    def stats(k):
        v = [r[k] for r in out.values() if k in r]
        return {"min": min(v), "max": max(v), "mean": sum(v) / len(v)} if v else None
    return {
        "releases_per_window": n,
        "windows": [{"start_ms": clk.ms(a), "end_ms": clk.ms(b)} for a, b in wins],
        "phases": len(phases),
        "handler_costs": costs,
        "pes": out,
        "over_mean_percent": stats("over_mean_percent"),
        "over_measured_percent": stats("over_measured_percent"),
        "handler_share_percent": stats("handler_share_percent"),
        "static_over_measured_percent": stats("static_over_measured_percent"),
        "over_window_max_percent": stats("over_window_max_percent"),
        "static_over_mean_percent": stats("static_over_mean_percent"),
        "every_phase_below_estimate": all(r["phase_max_below_estimate"] for r in out.values()),
    }


def static_values(path, app):
    """Static t(V_k) of each group of `app` in a reference of experiments/wcet
    (apps.<app>.groups.<key>.static)."""
    d = json.load(open(path))
    return {k: g["static"] for k, g in d["apps"][app]["groups"].items()}


def analyze(config_path, out_dir):
    base = os.path.dirname(os.path.abspath(config_path))
    cfg = json.load(open(config_path))
    res = {"_doc": "rttools.paper.cputime analyze --config " + os.path.basename(config_path), "runs": {}}
    for rid, run in cfg["runs"].items():
        run = dict(run)
        if "static_of" in run:
            so = run["static_of"]
            run["static"] = {"key": so.get("key", "name"),
                             "values": static_values(os.path.join(base, so["reference"]), so["app"])}
        res["runs"][rid] = analyze_run(run, base)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as fh:
        json.dump(res, fh, indent=1, sort_keys=True)
    return res


def _close(a, b, rel=1e-9):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], rel) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y, rel) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= rel * max(1.0, abs(a), abs(b))
    return a == b


def check(metrics_path, ref_path):
    a = json.load(open(metrics_path))
    b = json.load(open(ref_path))
    a.pop("_doc", None)
    b.pop("_doc", None)
    ok = _close(a, b)
    print("match" if ok else "MISMATCH")
    return ok


def summary(res):
    for rid, r in res["runs"].items():
        o, m = r["over_mean_percent"], r["over_measured_percent"]
        print(f"{rid}: windows {len(r['windows'])} of {r['releases_per_window']} releases; over t_RTL "
              f"{o['min']:.2f} to {o['max']:.2f} % (mean {o['mean']:.2f} %), over t_RTL,meas {m['min']:.2f} to "
              f"{m['max']:.2f} % (mean {m['mean']:.2f} %); every phase below t(V_k): {r['every_phase_below_estimate']}")
        for lane, q in r["pes"].items():
            print(f"   {lane} {q['name']:>12}: t(V_k) {q['estimated']}, t_RTL [{q['measured_mean']:.1f}, {q['mean']:.1f}] (busy {q['busy_mean']:.1f},"
                  f" idle kernel {q['idle_kernel_per_iteration']:.1f}; inj {q['idle_injections']}, size {q['idle_size_flits']}, end {q['idle_ends']}),"
                  f" window max {q['window_max']:.1f}, phase max {q['phase_max']:.1f}, over {q['over_mean_percent']:.2f} %"
                  + (f", static {q['static']} ({q['static_over_mean_percent']:.2f} %)" if "static" in q else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="rttools.paper.cputime")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--config", required=True)
    a.add_argument("--out", required=True)
    c = sub.add_parser("check")
    c.add_argument("metrics")
    c.add_argument("reference")
    args = ap.parse_args(argv)
    if args.cmd == "analyze":
        summary(analyze(args.config, args.out))
        return 0
    return 0 if check(args.metrics, args.reference) else 1


if __name__ == "__main__":
    sys.exit(main())
