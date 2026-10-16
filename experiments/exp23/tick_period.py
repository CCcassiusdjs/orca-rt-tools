#!/usr/bin/env python3
"""Tick period of the UCX-OS (hf-riscv-e) against the release period of A.

    tick_period.py code [--repo ROOT] [--f-clk HZ] [--json]
    tick_period.py log EVENTS [--repo ROOT] [--json]

`code` reads the sources that set the two periods and checks that the
tick lasts exactly the release period T, in cycles (T * F_CLK):

| Source | Value |
|---|---|
| arch/riscv/hf-riscv-e/arch.mak | F_CLK, F_TICK (defaults of the build) |
| arch/riscv/hf-riscv-e/hal.c, hal.h | TIMER1PRE (prescaler code), TIMER1CTC expression |
| hw/peripherals/peripherals_minimal.vhd | prescaler bit per code; counter from 0 to TIMER1CTC inclusive |
| manycore_modelsim/manycore_pe.sv | RELEASE_CYCLES (release period), WARMUP_CYCLES (first release), defaults |
| manycore_modelsim/manycore_top.sv | CLOCK_HALF_PERIOD_FS (half period of the clock, fs), default |
| experiments/exp23/config.json | clock_hz, release_period_s |

tick (cycles) = prescaler * (TIMER1CTC + 1), with TIMER1CTC evaluated as
C integer arithmetic on F_CPU = F_CLK and F_TIMER = F_TICK. --f-clk HZ
checks the build and the testbench parameters that simulate.sh derives for
F_CLK = HZ (F_TICK = 1 / T, RELEASE_CYCLES = T HZ, half period
floor(1e15 / (2 HZ)) fs), for example the clock of make paper-flow.

`log` reads a simulation log (events.txt of simulate.sh) and reports,
per release of A: release_to_dispatch (TRIGGER line, the acknowledgement
of IRQ 4, to the first dispatch of A; the metric of metrics.json),
request_to_dispatch (release request of the testbench, the start of cycle
WARMUP_CYCLES + k RELEASE_CYCLES: the cycle of "next release will be at"
minus RELEASE_CYCLES, to the same dispatch) and the spacing of the
dispatches of A. The log passes when every spacing equals the tick of the
code at the clock of the run (f_clk_hz of the RUN_INFO next to the log, as
--f-clk of `code`; the defaults of the code when RUN_INFO has no clock)
and request_to_dispatch takes one value; release_to_dispatch then
varies only by the acknowledgement latency of IRQ 4.

Exit status: 0 when every check passes, 1 otherwise, 2 when a source
does not have the expected form.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_REPO = os.path.dirname(os.path.dirname(HERE))

ARCH = "pkt-sim/software/ucx-os/arch/riscv/hf-riscv-e"
PATHS = {
    "arch_mak": ARCH + "/arch.mak",
    "hal_c": ARCH + "/hal.c",
    "hal_h": ARCH + "/hal.h",
    "periph": "pkt-sim/hw/peripherals/peripherals_minimal.vhd",
    "pe_sv": "pkt-sim/manycore_modelsim/manycore_pe.sv",
    "top_sv": "pkt-sim/manycore_modelsim/manycore_top.sv",
    "config": "experiments/exp23/config.json",
}


class SourceError(Exception):
    pass


def read(repo, key):
    with open(os.path.join(repo, PATHS[key])) as f:
        return f.read()


def strip_comments(text, line_comment):
    return "\n".join(l.split(line_comment, 1)[0] for l in text.splitlines())


def last_int(pattern, text, what):
    m = re.findall(pattern, text, re.M)
    if not m:
        raise SourceError("no " + what)
    return int(m[-1].replace("_", ""))


def c_int_eval(expr, names):
    """Value of a C integer expression of + - * / % and names (positive
    operands: C division truncates like Python floor division)."""
    ops = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
           ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a // b,
           ast.Mod: lambda a, b: a % b}

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            a, b = ev(n.left), ev(n.right)
            if a < 0 or b <= 0 and type(n.op) in (ast.Div, ast.Mod):
                raise SourceError("TIMER1CTC: operand outside the positive integers")
            return ops[type(n.op)](a, b)
        if isinstance(n, ast.Constant) and isinstance(n.value, int):
            return n.value
        if isinstance(n, ast.Name) and n.id in names:
            return names[n.id]
        raise SourceError("TIMER1CTC: unsupported expression " + repr(expr))

    return ev(ast.parse(expr, mode="eval"))


def code_values(repo, f_clk_run=None):
    """Values of the sources (see the module docstring); f_clk_run: the
    clock of a run of simulate.sh (F_CLK, F_TICK = 1 / T and the testbench
    parameters derived from it) in place of the defaults."""
    mak = strip_comments(read(repo, "arch_mak"), "#")
    f_clk = last_int(r"^\s*F_CLK\s*\??=\s*(\d+)\s*$", mak, "F_CLK in arch.mak")
    f_tick = last_int(r"^\s*F_TICK\s*\??=\s*(\d+)\s*$", mak, "F_TICK in arch.mak")
    with open(os.path.join(repo, PATHS["config"])) as f:
        cfg = json.load(f)
    if f_clk_run is not None:
        f_clk = int(f_clk_run)
        f_tick = round(1 / cfg["release_period_s"])

    hal = strip_comments(read(repo, "hal_c"), "//")
    hal = re.sub(r"/\*.*?\*/", "", hal, flags=re.S)
    m = re.search(r"\bTIMER1PRE\s*=\s*(\w+)\s*;", hal)
    if not m:
        raise SourceError("no TIMER1PRE assignment in hal.c")
    pre_name = m.group(1)
    hal_h = read(repo, "hal_h")
    m2 = re.search(r"#define\s+" + re.escape(pre_name) + r"\s+(0x[0-9a-fA-F]+|\d+)", hal_h)
    if not m2:
        raise SourceError("no #define " + pre_name + " in hal.h")
    pre_code = int(m2.group(1), 0)
    m = re.search(r"\bTIMER1CTC\s*=\s*([^;]+);", hal)
    if not m:
        raise SourceError("no TIMER1CTC assignment in hal.c")
    ctc_expr = " ".join(m.group(1).split())
    ctc = c_int_eval(ctc_expr, {"F_CPU": f_clk, "F_TIMER": f_tick})

    vhd = strip_comments(read(repo, "periph"), "--")
    bits = {int(c, 2): int(b) for c, b in
            re.findall(r'when\s+"([01]{3})"\s*=>\s*tmr1_dly\s*<=\s*timer0\((\d+)\)', vhd)}
    if pre_code not in bits:
        raise SourceError(f"no prescaler case {pre_code:03b} in peripherals_minimal.vhd")
    # tmr1_pulse = tmr1_dly /= tmr1_dly2: one pulse per change of timer0(bit),
    # that is, one pulse per 2**bit cycles
    if not re.search(r"tmr1_pulse\s*<=\s*'1'\s+when\s+tmr1_dly\s*/=\s*tmr1_dly2", vhd):
        raise SourceError("TIMER1 pulse of peripherals_minimal.vhd not recognized")
    prescaler = 2 ** bits[pre_code]
    # counter: increments while timer1 /= timer1_ctc, toggles the CTC
    # interrupt and restarts at 0 on equality: TIMER1CTC + 1 steps per tick
    inclusive = re.search(
        r"if\s*\(?\s*timer1\s*/=\s*timer1_ctc\s*\)?\s*then.*?timer1\s*<=\s*timer1\s*\+\s*1\s*;"
        r".*?else\s*int_timer1_ctc\s*<=\s*not\s+int_timer1_ctc\s*;\s*timer1\s*<=\s*\(others\s*=>\s*'0'\)",
        vhd, re.S)
    if not inclusive:
        raise SourceError("TIMER1 counter of peripherals_minimal.vhd not recognized")
    steps = ctc + 1

    pe = strip_comments(read(repo, "pe_sv"), "//")
    if not re.search(r"`timescale\s+1ns/", read(repo, "pe_sv")):
        raise SourceError("manycore_pe.sv: time unit is not 1 ns")
    release_cycles = last_int(r"longint\s+RELEASE_CYCLES\s*=\s*([\d_]+)", pe, "RELEASE_CYCLES")
    warmup_cycles = last_int(r"longint\s+WARMUP_CYCLES\s*=\s*([\d_]+)", pe, "WARMUP_CYCLES")

    top_raw = read(repo, "top_sv")
    top = strip_comments(top_raw, "//")
    if not re.search(r"`timescale\s+1ns/", top_raw):
        raise SourceError("manycore_top.sv: time unit is not 1 ns")
    half_fs = last_int(r"longint\s+CLOCK_HALF_PERIOD_FS\s*=\s*([\d_]+)", top, "CLOCK_HALF_PERIOD_FS")

    if f_clk_run is not None:
        # parameters of simulate.sh for this clock (vsim -g)
        release_cycles = round(cfg["release_period_s"] * f_clk)
        warmup_cycles = round(cfg["warmup_s"] * f_clk)
        half_fs = 10 ** 15 // (2 * f_clk)

    return {
        "f_clk_hz": f_clk, "f_tick_hz": f_tick, "run_clock": f_clk_run is not None,
        "timer1pre": pre_name, "timer1pre_code": pre_code, "prescaler_cycles": prescaler,
        "timer1ctc_expr": ctc_expr, "timer1ctc": ctc, "steps_per_tick": steps,
        "tick_cycles": prescaler * steps,
        "release_cycles": release_cycles, "first_release_cycles": warmup_cycles,
        "clock_half_period_fs": half_fs, "clock_hz": 10 ** 15 / (2 * half_fs),
        "config_clock_hz": cfg["clock_hz"], "config_release_period_s": cfg["release_period_s"],
    }


def code_checks(v):
    """(name, value, expected, ok) rows."""
    f = v["f_clk_hz"]
    release_cycles = v["release_cycles"]
    t_cycles = v["config_release_period_s"] * f
    rows = [
        ("F_CLK of the run (Hz)", f, f, True) if v["run_clock"] else
        ("F_CLK = config clock_hz (Hz)", f, v["config_clock_hz"], f == v["config_clock_hz"]),
        # the clock runs at or above F_CLK, within one fs of the half period
        ("clock 1e15 / (2 CLOCK_HALF_PERIOD_FS) >= F_CLK (Hz)", round(v["clock_hz"], 3), f,
         v["clock_hz"] >= f and 10 ** 15 / (2 * (v["clock_half_period_fs"] + 1)) < f),
        ("TIMER1CTC fits 16 bits", v["timer1ctc"], "0..65535", 0 <= v["timer1ctc"] <= 0xFFFF),
        ("RELEASE_CYCLES = config T (cycles)", release_cycles, t_cycles, abs(release_cycles - t_cycles) < 1e-6),
        ("F_TICK = 1 / T (Hz)", v["f_tick_hz"], 1 / v["config_release_period_s"],
         abs(v["f_tick_hz"] * v["config_release_period_s"] - 1) < 1e-9),
        ("tick = T x F_CLK (cycles)", v["tick_cycles"], t_cycles, abs(v["tick_cycles"] - t_cycles) < 1e-6),
    ]
    return rows


def load_rttools(repo):
    sys.path.insert(0, os.path.join(repo, "orca-rt-tools"))
    from rttools.paper import exp23
    return exp23


def log_clock(repo, log_path):
    """F_CLK of the run of a log (f_clk_hz of the RUN_INFO next to it,
    exp23.run_info_path), or None (a log without clock fields: the
    defaults of the code, as run F)."""
    exp23 = load_rttools(repo)
    path = exp23.run_info_path(log_path)
    info = exp23.read_run_info(path) if path else {}
    return int(info["f_clk_hz"]) if "f_clk_hz" in info else None


def log_values(repo, log_path, v):
    """Per release of the log; the clock of the run comes from the RUN_INFO
    next to the log (exp23.load_run; else config clock_hz)."""
    exp23 = load_rttools(repo)
    cfg = exp23.load_config(os.path.join(repo, PATHS["config"]))
    tr, cfg, clk, clock = exp23.load_run(log_path, cfg)
    pairs = exp23.iteration_releases(tr, cfg, clk)
    half_fs = clock["half_period_fs"] or round(1e15 / (2 * cfg["clock_hz"]))
    period_ns = 2 * half_fs / 1e6
    release_cycles = exp23.exact(cfg["release_period_s"] * cfg["clock_hz"])
    requests = []   # cycle of each release request (start of the cycle)
    with open(log_path, errors="replace") as fh:
        for line in fh:
            m = re.search(r"TRIGGER: next release will be at (\d+) ns", line)
            if m:
                # manycore_pe.sv prints the start of the cycle truncated to ns;
                # the period exceeds 1 ns, so one cycle starts in [t, t + 1)
                c_next = -(-int(m.group(1)) * 10 ** 6 // (2 * half_fs))
                requests.append(c_next - release_cycles)

    def cyc(x):
        # cycles to 1/1000 (the request is the start of a cycle and the
        # events are rising edges: half cycles)
        return exp23.exact(round(x, 3))

    rows = []
    for r, s in pairs:
        rc, sc = clk.cycles(r), clk.cycles(s)
        req = max((q for q in requests if q <= rc), default=None)
        rows.append({
            "release_to_dispatch_cycles": cyc(sc - rc),
            "request_to_dispatch_cycles": None if req is None else cyc(sc - req),
            "ack_latency_cycles": None if req is None else cyc(rc - req),
            "dispatch": sc,
        })
    spacing = [cyc(b["dispatch"] - a["dispatch"]) for a, b in zip(rows, rows[1:])]
    rtd = [x["release_to_dispatch_cycles"] for x in rows]
    growth = [b - a for a, b in zip(rtd, rtd[1:])]
    qtd = [x["request_to_dispatch_cycles"] for x in rows if x["request_to_dispatch_cycles"] is not None]
    ack = [x["ack_latency_cycles"] for x in rows if x["ack_latency_cycles"] is not None]

    def span(xs):
        return {"min": min(xs), "max": max(xs)} if xs else None

    return {
        "log": log_path, "releases": len(rows),
        "release_to_dispatch_cycles": span(rtd),
        "release_to_dispatch_growth_per_release_cycles": None if not growth else sum(growth) / len(growth),
        "request_to_dispatch_cycles": span(qtd),
        "ack_latency_cycles": span(ack),
        "dispatch_spacing_cycles": span(spacing),
        "per_release": [{k: x[k] for k in ("release_to_dispatch_cycles", "request_to_dispatch_cycles",
                                          "ack_latency_cycles")} for x in rows],
    }


def log_checks(lv, v):
    sp, q = lv["dispatch_spacing_cycles"], lv["request_to_dispatch_cycles"]
    return [
        ("releases with a dispatch of A", lv["releases"], ">= 2", lv["releases"] >= 2),
        ("dispatch spacing of A = tick (cycles)", None if sp is None else f"{sp['min']}..{sp['max']}",
         v["tick_cycles"], sp is not None and sp["min"] == sp["max"] == v["tick_cycles"]),
        ("request_to_dispatch constant (cycles)", None if q is None else f"{q['min']}..{q['max']}",
         "one value", q is not None and q["min"] == q["max"]),
    ]


def print_rows(rows):
    w = max(len(r[0]) for r in rows)
    for name, val, exp, ok in rows:
        print(f"{'ok  ' if ok else 'FAIL'} {name:<{w}}  {val}  (expected {exp})")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", default=DEFAULT_REPO, help="repository root (default: two levels above this script)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("code")
    c.add_argument("--f-clk", type=int, default=None,
                   help="clock of a run (Hz): the parameters that simulate.sh derives from F_CLK")
    c.add_argument("--json", action="store_true")
    lg = sub.add_parser("log")
    lg.add_argument("events")
    lg.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    f_clk_run = getattr(a, "f_clk", None)
    if a.cmd == "log":
        f_clk_run = log_clock(a.repo, a.events)
    try:
        v = code_values(a.repo, f_clk_run)
    except (SourceError, OSError, KeyError) as e:
        print("source error: " + str(e), file=sys.stderr)
        return 2
    rows = code_checks(v)
    out = {"code": v, "code_checks": [list(r) for r in rows]}
    if a.cmd == "log":
        lv = log_values(a.repo, a.events, v)
        lrows = log_checks(lv, v)
        out["log"] = lv
        out["log_checks"] = [list(r) for r in lrows]
        rows = lrows
    ok = all(r[3] for r in rows)
    out["pass"] = ok
    if a.json:
        print(json.dumps(out, indent=1, default=str))
        return 0 if ok else 1
    print(f"F_CLK {v['f_clk_hz']} Hz, F_TICK {v['f_tick_hz']} Hz, TIMER1PRE {v['timer1pre']} "
          f"(1 step per {v['prescaler_cycles']} cycles), TIMER1CTC = {v['timer1ctc_expr']} = {v['timer1ctc']}")
    print(f"tick = {v['prescaler_cycles']} x ({v['timer1ctc']} + 1) = {v['tick_cycles']} cycles; "
          f"release period {v['release_cycles']} cycles; clock half period {v['clock_half_period_fs']} fs")
    if a.cmd == "log":
        lv = out["log"]
        def rng(x):
            # a log with fewer than two releases has no spacing or growth
            return "none" if x is None else f"{x['min']}..{x['max']}"
        g = lv["release_to_dispatch_growth_per_release_cycles"]
        print(f"{lv['releases']} releases; release_to_dispatch {rng(lv['release_to_dispatch_cycles'])} cycles "
              f"(growth {'none' if g is None else format(g, '+.2f')} per release); "
              f"request_to_dispatch {rng(lv['request_to_dispatch_cycles'])}; "
              f"IRQ 4 ack latency {rng(lv['ack_latency_cycles'])}; "
              f"dispatch spacing {rng(lv['dispatch_spacing_cycles'])}")
    print_rows(rows)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
