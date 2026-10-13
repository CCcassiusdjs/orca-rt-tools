#!/usr/bin/env python3
"""Tick period of the UCX-OS (hf-riscv-e) against the release period of A.

    tick_period.py code [--repo ROOT] [--json]
    tick_period.py log EVENTS [--repo ROOT] [--json]

`code` reads the sources that set the two periods and checks that the
tick lasts exactly the release period T, in cycles (T * F_CLK):

| Source | Value |
|---|---|
| arch/riscv/hf-riscv-e/arch.mak | F_CLK, F_TICK |
| arch/riscv/hf-riscv-e/hal.c, hal.h | TIMER1PRE (prescaler code), TIMER1CTC expression |
| hw/peripherals/peripherals_minimal.vhd | prescaler bit per code; counter from 0 to TIMER1CTC inclusive |
| manycore_modelsim/manycore_pe.sv | wake_up_alarm (release period, ns), wake_up_delay (first release, ns) |
| manycore_modelsim/manycore_top.sv | CLOCK_BORDER_PERIOD (clock period, ns) |
| experiments/exp23/config.json | clock_hz, release_period_s |

tick (cycles) = prescaler * (TIMER1CTC + 1), with TIMER1CTC evaluated as
C integer arithmetic on F_CPU = F_CLK and F_TIMER = F_TICK.

`log` reads a simulation log (events.txt of simulate.sh) and reports,
per release of A: release_to_dispatch (TRIGGER line, the acknowledgement
of IRQ 4, to the first dispatch of A; the metric of metrics.json),
request_to_dispatch (release request of the testbench, "next release will
be at" minus wake_up_alarm, to the same dispatch) and the spacing of the
dispatches of A. The log passes when every spacing equals the tick of the
code and request_to_dispatch takes one value; release_to_dispatch then
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


def code_values(repo):
    """Values of the sources (see the module docstring)."""
    mak = strip_comments(read(repo, "arch_mak"), "#")
    f_clk = last_int(r"^\s*F_CLK\s*=\s*(\d+)\s*$", mak, "F_CLK in arch.mak")
    f_tick = last_int(r"^\s*F_TICK\s*=\s*(\d+)\s*$", mak, "F_TICK in arch.mak")

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
    alarm_ns = last_int(r"integer\s+wake_up_alarm\s*=\s*([\d_]+)\s*;", pe, "wake_up_alarm")
    delay_ns = last_int(r"integer\s+wake_up_delay\s*=\s*([\d_]+)\s*;", pe, "wake_up_delay")

    top_raw = read(repo, "top_sv")
    top = strip_comments(top_raw, "//")
    if not re.search(r"`timescale\s+1ns/", top_raw):
        raise SourceError("manycore_top.sv: time unit is not 1 ns")
    clk_period_ns = last_int(r"CLOCK_BORDER_PERIOD\s*=\s*(\d+)", top, "CLOCK_BORDER_PERIOD")

    with open(os.path.join(repo, PATHS["config"])) as f:
        cfg = json.load(f)

    return {
        "f_clk_hz": f_clk, "f_tick_hz": f_tick,
        "timer1pre": pre_name, "timer1pre_code": pre_code, "prescaler_cycles": prescaler,
        "timer1ctc_expr": ctc_expr, "timer1ctc": ctc, "steps_per_tick": steps,
        "tick_cycles": prescaler * steps,
        "release_period_ns": alarm_ns, "first_release_ns": delay_ns,
        "clock_period_ns": clk_period_ns,
        "config_clock_hz": cfg["clock_hz"], "config_release_period_s": cfg["release_period_s"],
    }


def code_checks(v):
    """(name, value, expected, ok) rows."""
    f = v["f_clk_hz"]
    release_cycles = v["release_period_ns"] * f / 1e9
    t_cycles = v["config_release_period_s"] * f
    rows = [
        ("F_CLK = config clock_hz (Hz)", f, v["config_clock_hz"], f == v["config_clock_hz"]),
        ("F_CLK = 1 / CLOCK_BORDER_PERIOD (Hz)", f, 1e9 / v["clock_period_ns"],
         abs(f - 1e9 / v["clock_period_ns"]) < 1e-6),
        ("TIMER1CTC fits 16 bits", v["timer1ctc"], "0..65535", 0 <= v["timer1ctc"] <= 0xFFFF),
        ("wake_up_alarm = config T (cycles)", release_cycles, t_cycles, abs(release_cycles - t_cycles) < 1e-6),
        ("F_TICK = 1 / T (Hz)", v["f_tick_hz"], 1 / v["config_release_period_s"],
         abs(v["f_tick_hz"] * v["config_release_period_s"] - 1) < 1e-9),
        ("tick = T x F_CLK (cycles)", v["tick_cycles"], t_cycles, abs(v["tick_cycles"] - t_cycles) < 1e-6),
    ]
    return rows


def load_rttools(repo):
    sys.path.insert(0, os.path.join(repo, "orca-rt-tools"))
    from rttools.paper import exp23
    return exp23


def log_values(repo, log_path, v):
    exp23 = load_rttools(repo)
    with open(os.path.join(repo, PATHS["config"])) as f:
        cfg = json.load(f)
    tr = exp23.load(log_path, cfg)
    clk = exp23.Clock(tr.unit, cfg["clock_hz"])
    pairs = exp23.iteration_releases(tr, cfg, clk)
    ns_raw = 1e-9 / tr.unit.seconds
    requests = []
    with open(log_path, errors="replace") as fh:
        for line in fh:
            m = re.search(r"TRIGGER: next release will be at (\d+) ns", line)
            if m:
                requests.append((int(m.group(1)) - v["release_period_ns"]) * ns_raw)
    def cyc(raw):
        # cycles to 1/1000 (the request falls between clock edges: half cycles)
        return exp23.exact(round(clk.cycles(raw), 3))

    rows = []
    for r, s in pairs:
        req = max((q for q in requests if q <= r), default=None)
        rows.append({
            "release_to_dispatch_cycles": cyc(s - r),
            "request_to_dispatch_cycles": None if req is None else cyc(s - req),
            "ack_latency_cycles": None if req is None else cyc(r - req),
            "dispatch": s,
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
    c.add_argument("--json", action="store_true")
    lg = sub.add_parser("log")
    lg.add_argument("events")
    lg.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    try:
        v = code_values(a.repo)
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
          f"release period {v['release_period_ns']} ns = {v['release_period_ns'] * v['f_clk_hz'] / 1e9:g} cycles")
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
