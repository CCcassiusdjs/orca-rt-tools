"""Injection instants of the packets between PEs for the time-triggered
injection of UCX-OS (pkt-sim/software/ucx-os/lib/noc_tt.c): the table
app/<name>_tt.h that the application includes when it is built with
-DUCX_NOC_TT (Makefile of UCX-OS, INJECTION=tt).

| Quantity | Definition | Source |
|---|---|---|
| s_{i,j} | Injection instant of packet j of flow i in the link schedule at the clock f (AGS, the parameters of the command line: rttools.paper.frequency.search_config), cycles from the start of the hyperperiod of the instance | search.schedule_at (one application), compose.schedule_union (composition) |
| Phase of the source job | One release period: phase j of the packet j (start j P); several periods (rttools/bench_t/multirate.py): phase o_u + j' k_u of the job j' of u that sends the packet | instance windows |
| offset | s_{i,j} minus the start of the phase of the source job (>= 0, since s_{i,j} >= r_{i,j}) | |
| s16 | offset rounded up to a multiple of TIMER_STEP = 16 cycles (TIMER1 counts one step per 16 cycles from the tick, hal.c) | |
| ticks, count | s16 = ticks P + 16 count, with P = cycles per tick (phase) | |

The compare interrupt of TIMER1 comes at the tick plus 16 count cycles,
so the injection never precedes s_{i,j}; the occupancy o_i of the model
covers the rounding (rttools/modules/routing/router.py, w_NI). The table
also gives, per PE, the largest number of packets that wait for their
instant at once (the queue of lib/noc_tt.c holds MAX_SLOTS) and, per flow,
the buffers that a job needs so that it does not write the buffer of a
packet that waits for its instant or that the DDMA reads (`buffers`:
time-triggered applications, whose packets carry the job number; the
applications of one release period reuse one buffer per flow, and the
generator stops when the next job of a source starts before the end of
the occupancy of its packet).
"""
from __future__ import annotations

import math
import os
import re

from rttools.modules.routing import router

TIMER_STEP = 16
MAX_SLOTS = 8          # NOC_TT_SLOTS of lib/noc_tt.c


class TTError(ValueError):
    pass


def ceil_step(x):
    return -(-x // TIMER_STEP) * TIMER_STEP


def packet_start(attempt, j):
    """Injection instant of packet j in the schedule of an AGS attempt (the
    start on every link of its path), None when skipped."""
    vals = [row[j] for row in attempt["schedule"] if row[j] is not None]
    return min(vals) if vals else None


def _rows(attempt, period_of, phase_start_of, job_start_of):
    """Rows of the packets between PEs of an AGS attempt: flow label,
    packet index k, release, deadline, occupancy, s, offset from the phase of
    the source job, s16, ticks and count. `period_of(label)`: cycles per tick
    of the flow; `phase_start_of(label, k)`: start of the phase of the source
    job of packet k (cycles from the start of the hyperperiod);
    `job_start_of(label, k)`: start of that job in the model (the earliest
    instant at which the job hands the packet to the kernel)."""
    if attempt is None or attempt["schedule"] is None:
        raise TTError("no link schedule at this clock")
    if attempt["skipped"]:
        raise TTError(f"{len(attempt['skipped'])} packets without a place in the link schedule at this clock")
    out = []
    for j, p in enumerate(attempt["problem"]["packets"]):
        label, _, k = p["name"].rpartition(":")
        k = int(k)
        s = packet_start(attempt, j)
        P = period_of(p["flow"])
        if P % TIMER_STEP:
            raise TTError(f"{P} cycles per tick is not a multiple of {TIMER_STEP} (TIMER1)")
        base = phase_start_of(p["flow"], k)
        off = s - base
        if off < 0:
            raise TTError(f"packet {p['name']}: instant {s} before the start {base} of the phase of its source job")
        s16 = ceil_step(off)
        out.append({"flow": p["flow"], "k": k, "source": p["source"], "target": p["target"],
                    "src": str(p["path"][0]["data"]["label"])[2:], "dst": str(p["path"][-1]["data"]["label"])[:-2],
                    "release": p["min_start"], "deadline": p["abs_deadline"], "occupancy": p["net_time"],
                    "s": s, "phase_start": base, "offset": off, "s16": s16, "ticks": s16 // P,
                    "count": (s16 % P) // TIMER_STEP, "period": P, "job_start": job_start_of(p["flow"], k)})
    return out


def _check(rows, hyper):
    for r in rows:
        if r["s"] < r["release"] or r["s"] + r["occupancy"] > r["deadline"]:
            raise TTError(f"packet {r['flow']}:{r['k']}: instant {r['s']} outside [r, a - o] = "
                          f"[{r['release']}, {r['deadline'] - r['occupancy']}]")


def slots(rows, hyper, wait):
    """Largest number of packets of one PE that wait in the queue of
    lib/noc_tt.c at once: packet k waits from the start of its source job
    (the earliest send) to its instant plus `wait` (the latest injection),
    with the copies of the next and of the previous hyperperiod. Returns
    {PE label: count}."""
    per = {}
    for r in rows:
        a = r["job_start"]
        b = r["phase_start"] + r["s16"] + wait
        for h in (-1, 0, 1):
            per.setdefault(r["src"], []).append((a + h * hyper, b + h * hyper))
    out = {}
    for pe, ivs in per.items():
        ev = sorted([(a, 1) for a, _ in ivs] + [(b, -1) for _, b in ivs], key=lambda e: (e[0], -e[1]))
        n = best = 0
        for _, d in ev:
            n += d
            best = max(best, n)
        out[pe] = best
    return out


def buffers(rows, hyper):
    """Buffers per flow so that a job never writes a packet that waits for
    its instant or that the DDMA still reads: 1 + the largest number of
    later packets of the flow whose source job starts before the end of
    the occupancy of a packet (s + o_i, which covers the injection and the
    last flit), over two hyperperiods. Returns {flow label: count}."""
    per = {}
    for r in rows:
        per.setdefault(r["flow"], []).append(r)
    out = {}
    for f, rs in per.items():
        seq = sorted(([r["job_start"] + h * hyper, r["phase_start"] + r["offset"] + r["occupancy"] + h * hyper]
                      for h in (0, 1) for r in rs), key=lambda x: x[0])
        best = 0
        for i, (_, inj) in enumerate(seq):
            best = max(best, sum(1 for st, _ in seq[i + 1:] if st < inj))
        out[f] = 1 + best
    return out


# ------------------------------------------------------------ schedules

def single(graph, noc, entries, appname, f):
    """Rows of one application at clock f (search.schedule_at). One release
    period: packet k of a flow comes from the job of phase k. Several
    periods or a cycle (rates of multirate): packet k of flow e is the k-th
    sending job j' of its source in the hyperperiod (multirate.
    packet_windows), whose phase is o_u + j' k_u."""
    from rttools.modules.frequency import search
    from rttools.modules.instances import instantiator, release
    from rttools.paper.frequency import search_config
    from rttools.tui.model import network as tnet
    with tnet.quiet():
        a = search.schedule_at(graph, noc, entries, appname, f, search_config(f))
        inst = instantiator.createInstance(graph, noc, f)
    if a is None:
        raise TTError(f"no hyperperiod at {f} Hz")
    if inst.get("rates") is not None:
        from rttools.bench_t import multirate
        r = inst["rates"]
        P = r["phase_cycles"]
        spec = multirate.spec_from_instance(inst, entries)
        sched = multirate.schedule(spec, P)
        win = multirate.packet_windows(spec, sched)
        flows = {d["label"]: (u, v) for u, v, d in inst["flows"]}
        base = sched.h0 * sched.H
        job_of = {f: [row[0] for row in rows] for f, rows in win.items()}

        def phase_start(label, k):
            u = flows[label][0]
            return (spec.offsets.get(u, 0) + job_of[label][k] * spec.ticks[u]) * P

        def job_start(label, k):
            u = flows[label][0]
            jl = job_of[label][k]
            return sched.job(u, sched.h0 * sched.per_h(u) + jl)[1] - base

        rows = _rows(a, lambda label: P, phase_start, job_start)
        hyper = sched.H
        model = "multirate"
    else:
        win = release.task_windows(inst, entries)
        periods = {d["label"]: d["period"] for _, _, d in inst["flows"]}
        src = {d["label"]: u for u, _, d in inst["flows"]}
        rows = _rows(a, lambda label: periods[label], lambda label, k: k * periods[label],
                     lambda label, k: k * periods[label] + win[src[label]]["start"])
        hyper = a["hyperperiod"]
        model = "phase"
    _check(rows, hyper)
    return {"clock_hz": f, "hyperperiod": hyper, "model": model, "rows": rows}


def union(comp, f):
    """Rows of the packets of a composition at clock f (compose.
    schedule_union: one link schedule for the packets of every application
    over the lcm of their hyperperiods); one release period per
    application. The flow labels are "<application>/f<csv id>"."""
    from rttools.modules.instances import instantiator, release
    from rttools.multiapp import compose
    from rttools.paper.frequency import search_config
    from rttools.tui.model import network as tnet
    if compose.general(comp["apps"]):
        raise TTError("the composition follows the general phase model (several periods); "
                      "the table of a composition takes one release period")
    with tnet.quiet():
        a = compose.schedule_union(comp["apps"], comp["noc"], f, search_config(f))
        periods, starts, src = {}, {}, {}
        for x in comp["apps"]:
            inst = instantiator.createInstance(x["graph"], comp["noc"], f)
            win = release.task_windows(inst, x["entries"])
            for u, _, d in inst["flows"]:
                lab = compose.qualify(x["name"], d["label"])
                periods[lab] = d["period"]
                starts[lab] = win[u]["start"]
    if a is None:
        raise TTError(f"no hyperperiod at {f} Hz")
    rows = _rows(a, lambda label: periods[label], lambda label, k: k * periods[label],
                 lambda label, k: k * periods[label] + starts[label])
    _check(rows, a["hyperperiod"])
    return {"clock_hz": f, "hyperperiod": a["hyperperiod"], "model": "phase", "rows": rows}


# ------------------------------------------------------------ header

def _flow_key(label):
    """manifest key of a flow label: (application or None, csv id)."""
    app, _, f = label.rpartition("/")
    m = re.fullmatch(r"f(\d+)", f)
    if not m:
        raise TTError(f"flow label {label!r}")
    return (app or None, int(m[1]))


HEADER = """\
/*
 * {name}_tt.h: injection instants of the packets between PEs of {name}.c
 * (time-triggered injection, lib/noc_tt.c), generated by rttools.ucxgen tt
 * (orca-rt-tools). Do not edit: change the inputs and run the generator
 * again.
 *
 *   python -m rttools.ucxgen {cmd}
 *
{inputs}
 *
 * Link schedule of each clock below: AGS (rttools/modules/backend/ags, the
 * parameters of the command line of rttools) on the packets of one
 * hyperperiod, occupancy o_i = ZLL + w_h (m + 1) + w_NI with w_h = {w_h}
 * and w_NI = {w_ni} cycles, the network interface of each PE as one
 * resource (rttools/modules/routing/router.py). For packet j of flow i, s
 * is its instant in cycles from the start of the phase of the job that
 * sends it; the table holds s16, s rounded up to a multiple of 16 cycles
 * (TIMER1 step, hal.c): s16 = ticks P + 16 count, P = cycles per tick. The
 * comment of each entry gives s, the release r and the deadline a of the
 * packet (cycles from the same phase start) and o_i.
 *
 * Costs: {costs}
 */
"""


def _entry(r):
    return (f"{{{r['ticks']}, {r['count']}}}", f"s {r['offset']}, s16 {r['s16']}, r {r['release'] - r['phase_start']}, "
            f"a {r['deadline'] - r['phase_start']}, o {r['occupancy']}")


def header(name, cmd, inputs, tables, flows, style="array", w_h=None, w_ni=None, costs=None):
    """Text of app/<name>_tt.h. `tables`: results of single or union per
    clock; `flows`: manifest flows ({"id", "csv_id", "source", "target",
    "local", optional "app"}) or, with style "named", the flows of the CSV
    ({"id": csv id, "source", "target"}). Styles: "array" (TT_AT[flow id]:
    one entry per flow of one release period), "named" (TT_AT_<source>_<target>
    per flow between PEs: application E, weird_a.c) and "jobs" (several
    periods: TT_AT[flow id] points to the entries of the packets of the flow
    in one hyperperiod, TT_PACKETS[flow id] counts them, TT_BUFFERS[flow id]
    gives the buffers of the flow). `costs`: text of the line "Costs:"
    (the costs of the link schedule; experiments/exp23/simulate.sh copies
    it to the line costs of RUN_INFO); None: the costs of the CSV."""
    if style not in ("array", "named", "jobs"):
        raise TTError("style must be array, named or jobs")
    w_h = router.header_wait() if w_h is None else w_h
    w_ni = router.ni_wait() if w_ni is None else w_ni
    text = HEADER.format(name=name, cmd=cmd, inputs=inputs, w_h=w_h, w_ni=w_ni,
                         costs=costs or "CSV (Capacity column)")
    by_key = {}
    for f in flows:
        by_key[(f.get("app"), int(f["csv_id"] if "csv_id" in f else f["id"]))] = f
    first = True
    for t in tables:
        f_clk = t["clock_hz"]
        rows = t["rows"]
        P = rows[0]["period"] if rows else None
        need = max(slots(rows, t["hyperperiod"], w_ni).values(), default=0)
        if need > MAX_SLOTS:
            raise TTError(f"{f_clk} Hz: a PE needs {need} entries of the queue of lib/noc_tt.c (NOC_TT_SLOTS = {MAX_SLOTS})")
        text += ("#if" if first else "#elif") + f" F_CPU == {f_clk}\n"
        first = False
        text += (f"/* {f_clk} Hz: {len(rows)} packets between PEs in a hyperperiod of {t['hyperperiod']} cycles, "
                 f"{P} cycles per tick; at most {need} packets wait for their instant on one PE */\n")
        bufs = buffers(rows, t["hyperperiod"])
        if style != "jobs":
            many = sorted(f for f, b in bufs.items() if b > 1)
            if many:
                raise TTError(f"{f_clk} Hz: flows {', '.join(many)}: the next job of the source starts before "
                              f"the end of the occupancy of the packet (one buffer per flow in style {style})")
        per_flow = {}
        for r in rows:
            key = _flow_key(r["flow"])
            if key not in by_key:
                raise TTError(f"flow {r['flow']} of the schedule is not a flow of the application")
            per_flow.setdefault(by_key[key]["id"], []).append(r)
        if style == "named":
            for fid in sorted(per_flow):
                rs = sorted(per_flow[fid], key=lambda r: r["k"])
                if len(rs) != 1:
                    raise TTError(f"flow {fid}: {len(rs)} packets per hyperperiod; style named takes one")
                f = by_key[_flow_key(rs[0]["flow"])]
                e, c = _entry(rs[0])
                text += (f"/* f{fid} {f['source']}->{f['target']}: {c} */\n"
                         f"static const struct ucx_tt_at TT_AT_{f['source']}_{f['target']} = {e};\n")
        elif style == "array":
            n = max(int(f["id"]) for f in flows)
            text += f"static const struct ucx_tt_at TT_AT[{n + 1}] = {{\n  {{0, 0}},   /* no flow 0 */\n"
            for f in sorted(flows, key=lambda f: int(f["id"])):
                fid = int(f["id"])
                rs = sorted(per_flow.get(fid, []), key=lambda r: r["k"])
                if len(rs) > 1:
                    raise TTError(f"flow {fid}: {len(rs)} packets per hyperperiod; style array takes one")
                if not rs:
                    text += f"  {{0, 0}},   /* f{fid} {f['source']}->{f['target']}: same PE */\n"
                else:
                    e, c = _entry(rs[0])
                    text += f"  {e},   /* f{fid} {f['source']}->{f['target']}: {c} */\n"
            text += "};\n"
        else:
            n = max(int(f["id"]) for f in flows)
            names, npk, nbuf = [], [], []
            for f in sorted(flows, key=lambda f: int(f["id"])):
                fid = int(f["id"])
                rs = sorted(per_flow.get(fid, []), key=lambda r: r["k"])
                if not rs:
                    names.append("0")
                    npk.append("0")
                    nbuf.append("1")
                    continue
                text += f"/* f{fid} {f['source']}->{f['target']}: {len(rs)} packets per hyperperiod */\n"
                text += f"static const struct ucx_tt_at TT_F{fid}[{len(rs)}] = {{\n"
                for r in rs:
                    e, c = _entry(r)
                    text += f"  {e},   /* packet {r['k']}: {c} */\n"
                text += "};\n"
                names.append(f"TT_F{fid}")
                npk.append(str(len(rs)))
                nbuf.append(str(bufs[rs[0]["flow"]]))
            text += (f"static const struct ucx_tt_at *const TT_AT[{n + 1}] = {{0, " + ", ".join(names) + "};\n"
                     f"static const uint16_t TT_PACKETS[{n + 1}] = {{0, " + ", ".join(npk) + "};\n"
                     f"static const uint8_t TT_BUFFERS[{n + 1}] = {{1, " + ", ".join(nbuf) + "};\n"
                     f"#define TT_MAX_BUFFERS {max(int(b) for b in nbuf)}\n")
    text += "#else\n#error \"app/" + name + "_tt.h: no injection table for this F_CPU (rttools.ucxgen tt --clock)\"\n#endif\n"
    return text


def inputs_comment(paths):
    from rttools.ucxgen.model import sha256
    return "\n".join(f" * Input: {os.path.basename(p)} (sha256 {sha256(p)})" for p in paths)
