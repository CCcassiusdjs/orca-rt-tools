"""Conformance of an RTL run with the phase model: executions of each task
per phase and CPU time of each PE per phase against t(V_k).

    python -m rttools.paper.phasecheck <metrics.json> [<metrics.json> ...] [--rows N]

The analyses of a run (rttools.paper.exp23 for application E,
rttools.paper.rtlapp for a generated application, rttools.paper.rtlmr for a
time-triggered one) store the conformance in metrics.json under
"phase_conformance"; this command prints it and exits with status 1 when a
run does not conform (2 when a file has no conformance).

Model (paper, Section 6.3; rttools/bench_t/estimate.py): in every phase the
PE of cluster V_k runs each task of V_k at most once, task v serves
iteration j from phase j + n(v) of the release of iteration j, and the CPU
time of the PE in a phase is at most t(V_k). The release by tick of the
platform (pkt-sim/software/ucx-os/lib/tick_release.c) gives the first two
rules by construction; the runs before it (release rule "data": runs A to
H of application E, CV and CV2 of CAR-V, MA of the composition) let a task
serve every iteration whose packets are in its queue.

| Quantity | Definition |
|---|---|
| Phase p (from 0) | [r_{p+1}, r_{p+2}) between two consecutive release lines of the log (`TRIGGER: workflow iteration`); the phases that the log covers completely |
| Execution of v in phase p | ITER begin marker of v (one job, one iteration) at a time in phase p |
| Twice in a phase | a task with two or more executions in one phase |
| Early execution | the job j of v begins before phase a(v, j): a = j - 1 + n(v) for one release period (iteration j released at r_j), a = o_v + (j - 1) k_v for the general phase model |
| Dispatches of v in phase p | CPU slices of v (`scheduled` lines) that start in phase p; reported, not checked (a task that waits for a packet takes one slice per arrival) |
| CPU of PE k in phase p | non-IDLE time of the PE in phase p, cycles at F_CLK, against t(V_k) (one period) or the busy time of the PE in that phase of the hyperperiod of the model (general model) |

The run conforms when no task runs twice in a phase, no execution is
early and no phase exceeds the CPU bound.
"""
from __future__ import annotations

import argparse
import bisect
import json
import sys

from rttools.tui.model import metrics as tmetrics

TICK = "tick"
DATA = "data"
RULES = (TICK, DATA)


def release_rule(info, override=None):
    """Release rule of a run: `override` when given ("tick" or "data"),
    else the `release` line of the RUN_INFO (experiments/exp23/simulate.sh);
    a RUN_INFO without the line (runs before the release by tick) gives
    "data"."""
    if override not in (None, "auto"):
        if override not in RULES:
            raise ValueError(f"release rule must be one of {', '.join(RULES)}, got {override!r}")
        return override
    rule = (info or {}).get("release", DATA)
    if rule not in RULES:
        raise ValueError(f"RUN_INFO release={rule!r}: expected one of {', '.join(RULES)}")
    return rule


def _num(x):
    r = round(x, 6)
    return int(r) if float(r).is_integer() else r


def conformance(tr, clk, releases, begins, allowed, pe_of, demand, rule, ms=None):
    """Executions per phase and task and CPU per phase and PE.

    releases: release times of the log (raw units, sorted); begins: {task:
    {j: begin time of job j}}; allowed: callable (task, j) -> first phase
    of job j (from 0) or None; pe_of: {task: lane}; demand: callable (pe,
    p) -> CPU bound of the PE in phase p (cycles) or None; rule: release
    rule of the run; ms: callable raw -> ms for the rows (default
    clk.ms)."""
    ms = ms or clk.ms
    rel = sorted(releases)
    n = 0
    while n + 1 < len(rel) and rel[n + 1] <= tr.t1:
        n += 1
    tasks = sorted(pe_of)
    per = {v: [0] * n for v in tasks}
    early = {v: 0 for v in tasks}
    jobs = 0
    for v in tasks:
        for j, t in sorted((begins.get(v) or {}).items()):
            if t is None:
                continue
            p = bisect.bisect_right(rel, t) - 1
            if p < 0 or p >= n:
                continue
            jobs += 1
            per[v][p] += 1
            a = allowed(v, j)
            if a is not None and p < a:
                early[v] += 1
    disp = {v: [0] * n for v in tasks}
    for v in tasks:
        for s in tr.lane_slices(pe_of[v]):
            if s.label != v:
                continue
            p = bisect.bisect_right(rel, s.start) - 1
            if 0 <= p < n:
                disp[v][p] += 1
    pes = {}
    above_at = {}
    for pe in sorted(set(pe_of.values())):
        busy, bound, above = [], [], 0
        for p in range(n):
            b = _num(clk.cycles(tmetrics.lane_stats(tr, pe, rel[p], rel[p + 1]).busy))
            d = demand(pe, p)
            busy.append(b)
            bound.append(d)
            if d is not None and b > d:
                above += 1
                above_at.setdefault(p, []).append(pe)
        pes[pe] = {"tasks": [v for v in tasks if pe_of[v] == pe],
                   "bound_max": max((d for d in bound if d is not None), default=None),
                   "busy_max": max(busy) if busy else None,
                   "phases_above": above,
                   "excess_max": max((b - d for b, d in zip(busy, bound) if d is not None and b > d), default=0)}
    twice_at = {}
    for v in tasks:
        for p in range(n):
            if per[v][p] >= 2:
                twice_at.setdefault(p, []).append(v)
    rows = []
    for p in sorted(set(twice_at) | set(above_at)):
        rows.append({"phase": p, "start_ms": ms(rel[p]), "twice": twice_at.get(p, []),
                     "cpu_above": above_at.get(p, [])})
    out = {
        "release": rule,
        "phases": n,
        "jobs": jobs,
        "tasks": {v: {"pe": pe_of[v], "jobs": sum(per[v]), "phases_with_jobs": sum(1 for x in per[v] if x),
                      "max_jobs_per_phase": max(per[v], default=0),
                      "phases_twice": sum(1 for x in per[v] if x >= 2), "early": early[v],
                      "max_dispatches_per_phase": max(disp[v], default=0)} for v in tasks},
        "pes": pes,
        "phases_with_a_task_twice": len(twice_at),
        "early_jobs": sum(early.values()),
        "phases_cpu_above": len(above_at),
        "rows": rows,
    }
    out["conforms"] = out["phases_with_a_task_twice"] == 0 and out["early_jobs"] == 0 \
        and out["phases_cpu_above"] == 0 and n > 0
    return out


def summary(pc, name=""):
    """Lines of text for one conformance."""
    head = (f"{name}: release {pc['release']}, {pc['phases']} phases, {pc['jobs']} executions: "
            f"{pc['phases_with_a_task_twice']} phases with a task twice, {pc['early_jobs']} early executions, "
            f"{pc['phases_cpu_above']} phases above the CPU bound -> "
            + ("conforms" if pc["conforms"] else "does not conform"))
    lines = [head]
    for v, t in pc["tasks"].items():
        if t["phases_twice"] or t["early"]:
            lines.append(f"  task {v} ({t['pe']}): {t['jobs']} executions in {t['phases_with_jobs']} phases, "
                         f"twice in {t['phases_twice']} phases (at most {t['max_jobs_per_phase']}), "
                         f"{t['early']} early")
    for pe, x in pc["pes"].items():
        if x["phases_above"]:
            lines.append(f"  PE {pe} ({' '.join(x['tasks'])}): {x['phases_above']} phases above the bound "
                         f"{x['bound_max']}, largest busy {x['busy_max']} (excess up to {x['excess_max']})")
    return lines


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m rttools.paper.phasecheck", description=__doc__.split("\n\n")[0])
    ap.add_argument("metrics", nargs="+", help="metrics.json of an analysis of a run")
    ap.add_argument("--rows", type=int, default=0, help="print the first N phases that do not conform")
    a = ap.parse_args(argv)
    status = 0
    for path in a.metrics:
        with open(path) as f:
            m = json.load(f)
        pc = m.get("phase_conformance")
        if pc is None:
            print(f"{path}: no phase_conformance (log without ITER lines or analysis before this check)")
            status = max(status, 2)
            continue
        for line in summary(pc, path):
            print(line)
        for r in pc["rows"][:a.rows]:
            print(f"  phase {r['phase']} at {r['start_ms']:.4f} ms: twice {' '.join(r['twice']) or '-'}; "
                  f"CPU above {' '.join(r['cpu_above']) or '-'}")
        if not pc["conforms"]:
            status = max(status, 1)
    return status


if __name__ == "__main__":
    sys.exit(main())
