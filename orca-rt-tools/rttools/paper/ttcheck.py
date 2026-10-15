"""Packets of a run with the time-triggered injection (pkt-sim/software/
ucx-os/lib/noc_tt.c, RUN_INFO injection=tt) against the link schedule of
the model (rttools.ucxgen.tt: AGS with the network interface of each PE as
a resource, o_i = L0 + w_h (m + 1) + w_NI).

Lines of the packet monitor (experiments/exp23/rtl/pe_checker.sv), cycles
of the monitor (cyc):

| Line | Instant |
|---|---|
| FLIT TX ... head=<c> | the router of the source accepts the header (TX.head) |
| FLIT RX ... head=<c> last=<c> | header and last flit at the LOCAL port of the target (RX.head, RX.last) |
| FLIT END ... cyc=<c> | the CPU of the target writes the handshake after the last flit (irq3_handler): the network interface takes the next packet from the next cycle on (END) |
| TIMER pe=<x-y> cyc=<c> | rise of the timer interrupt of the PE: the tick (TIMER1 CTC) and the compare interrupt of the injection (TIMER1 OCR) |

Start of a phase: the ticks of a PE come every P cycles (P = tick period,
RUN_INFO release_cycles), so the residue of the TIMER cycles modulo P that
most lines share gives the ticks of the PE (tick_grid). The tick of phase
q on a PE is the tick nearest to release q (TRIGGER line: the release
request precedes the tick of its phase by less than P / 2, and the kernel
applies it at that tick, lib/tick_release.c and the hook of car_full.c).
The packet of the job of phase q has its instant s (cycles from the start
of that phase) in the table of the image (s16 = s rounded up to 16
cycles).

Quantities per packet between PEs, cycles (tau = tick of the phase of the
sending job):

| Quantity | Definition | Bound |
|---|---|---|
| inject_delay | TX.head - (tau + s) | 0 <= inject_delay <= NI_INJECT_CYCLES (the injection never precedes s; the compare interrupt at tau + s16, s16 - s <= 15) |
| header_wait | RX.head - TX.head - 6 (m + 1) | <= w_h (m + 1) |
| rx_wait | RX.last - RX.head - (p + 1) (stall and gap of the RX window) | <= NI_RX_SIZE_CYCLES |
| end_wait | END - RX.last | <= NI_RX_END_CYCLES |
| latency | RX.last - TX.head | <= o_i |
| occupancy_used | END - (tau + s) | <= o_i (the packet holds its links and the network interfaces of its PEs inside [s, s + o_i] of the schedule) |
| arrival | END - tau | <= s + o_i = a_{i,j} of the schedule, and <= the deadline of the packet |

occupancy_used = inject_delay + header_wait + 6 (m + 1) + p + 1 + rx_wait
+ end_wait, so the four waits within their bounds give occupancy_used <=
o_i. ni_overlaps counts, per PE, the pairs of packets whose intervals at
the network interface of the PE overlap (send: TX.head to TX.last; receive:
RX.head to END), which the resource of the link schedule excludes.
"""
from __future__ import annotations

import re
from collections import Counter

from rttools.modules.routing import router

INJECTIONS = ("tt", "finish")


def injection_rule(info):
    """Injection of the packets between PEs of a run: the line `injection`
    of the RUN_INFO (experiments/exp23/simulate.sh); a RUN_INFO without it
    (runs up to tag r11-rc5) gives "finish"."""
    v = (info or {}).get("injection", "finish")
    if v not in INJECTIONS:
        raise ValueError(f"RUN_INFO injection={v!r}: expected one of {', '.join(INJECTIONS)}")
    return v


RE_END = re.compile(r"FLIT END t=(\d+) src=(\d+-\d+) dst=(\d+-\d+) tag=(\d+) cyc=(\d+)")
RE_TIMER = re.compile(r"TIMER t=(\d+) pe=(\d+-\d+) cyc=(\d+)")
# share of the ticks of the run with a TIMER line (the line stays high from
# a compare interrupt to the tick only while interrupts are disabled)
GRID_MIN_COVERAGE = 0.9


def parse_lines(lines):
    """(ends, timers) of the END and TIMER lines of the packet monitor."""
    ends, timers = [], []
    for raw in lines:
        if "FLIT END" in raw:
            m = RE_END.search(raw)
            if m:
                ends.append({"t": int(m[1]), "src": m[2], "dst": m[3], "tag": int(m[4]), "cyc": int(m[5])})
        elif "TIMER t=" in raw:
            m = RE_TIMER.search(raw)
            if m:
                timers.append({"t": int(m[1]), "pe": m[2], "cyc": int(m[3])})
    return ends, timers


def read(path):
    with open(path, errors="replace") as f:
        return parse_lines(f)


def cycle_offset(timers, ns_to_cycles):
    """Offset c0 with cyc = ns_to_cycles(t) - c0 for the lines of the
    monitor (median over the TIMER lines; t is $time in whole ns)."""
    vals = sorted(ns_to_cycles(x["t"]) - x["cyc"] for x in timers)
    if not vals:
        return None
    return vals[len(vals) // 2]


def tick_grid(timers, period):
    """{pe: {"residue", "first", "last", "ticks", "lines_on_grid", "coverage"}}:
    the ticks of each PE at cyc = residue (mod period) from the TIMER lines."""
    per = {}
    for x in timers:
        per.setdefault(x["pe"], []).append(x["cyc"])
    out = {}
    for pe, cs in per.items():
        res, n = Counter(c % period for c in cs).most_common(1)[0]
        on = sorted(c for c in cs if c % period == res)
        ticks = (on[-1] - on[0]) // period + 1
        out[pe] = {"residue": res, "first": on[0], "last": on[-1], "ticks": ticks, "lines_on_grid": n,
                   "coverage": n / ticks}
    return out


def nearest_tick(grid, cyc, period):
    """Tick of the grid of a PE nearest to cycle `cyc`."""
    r = grid["residue"]
    k = round((cyc - r) / period)
    return r + k * period


def pair_ends(packets, ends):
    """END cycle of each packet ({"src", "dst", "tag", "rx_last"}): the
    first END of the target with the same source and tag at or after
    RX.last, in order; sets packet["end"] (None without one). Returns the
    number of END lines without a packet."""
    q = {}
    for e in sorted(ends, key=lambda e: e["cyc"]):
        q.setdefault((e["src"], e["dst"], e["tag"]), []).append(e["cyc"])
    for p in sorted(packets, key=lambda p: p["rx_last"]):
        lst = q.get((p["src"], p["dst"], p["tag"]))
        while lst and lst[0] < p["rx_last"]:
            lst.pop(0)
        p["end"] = lst.pop(0) if lst else None
    return sum(len(v) for v in q.values())


def _overlaps(intervals):
    n = 0
    iv = sorted(intervals)
    for i, (a, b) in enumerate(iv):
        for c, d in iv[i + 1:]:
            if c > b:
                break
            n += 1
    return n


def evaluate(packets, w_h=None):
    """Quantities of each packet (dicts with src, dst, size, hops, tx_head,
    tx_last, rx_head, rx_last, end, tau, s, s16, occupancy, deadline (cycles
    from tau), flow) and the counts of the table of the module docstring.
    A packet without tau or end counts as unchecked."""
    w_h = router.header_wait() if w_h is None else w_h
    rows, unchecked = [], 0
    for p in packets:
        if p.get("tau") is None or p.get("end") is None:
            unchecked += 1
            continue
        m, n = p["hops"], p["size"]
        hop = router.getRoutingTime() * (m + 1)
        start = p["tau"] + p["s"]
        r = {k: p.get(k) for k in ("flow", "k", "phase", "src", "dst", "tag", "size", "hops", "tau", "s", "s16",
                                   "occupancy", "deadline", "tx_head", "tx_last", "rx_head", "rx_last", "end")}
        r.update(inject_delay=p["tx_head"] - start,
                 header_wait=p["rx_head"] - p["tx_head"] - hop,
                 header_wait_bound=w_h * (m + 1),
                 rx_wait=p["rx_last"] - p["rx_head"] - (n + 1),
                 end_wait=p["end"] - p["rx_last"],
                 latency=p["rx_last"] - p["tx_head"],
                 occupancy_used=p["end"] - start,
                 arrival=p["end"] - p["tau"])
        r["occupancy_slack"] = p["occupancy"] - r["occupancy_used"]
        r["deadline_slack"] = None if p.get("deadline") is None else p["deadline"] - r["arrival"]
        rows.append(r)
    # intervals at the network interface of each PE
    ni = {}
    for r in rows:
        ni.setdefault(r["src"], []).append((r["tx_head"], r["tx_last"]))
        ni.setdefault(r["dst"], []).append((r["rx_head"], r["end"]))
    bounds = {"inject": router.NI_INJECT_CYCLES, "rx_size": router.NI_RX_SIZE_CYCLES,
              "rx_end": router.NI_RX_END_CYCLES, "w_ni": router.NI_WAIT_CYCLES, "header_wait_per_router": w_h}

    def mx(key):
        v = [r[key] for r in rows if r[key] is not None]
        return max(v) if v else None

    def mn(key):
        v = [r[key] for r in rows if r[key] is not None]
        return min(v) if v else None
    out = {
        "model": "o_i = L0 + w_h (m + 1) + w_NI; tau = tick of the phase of the sending job",
        "bounds": bounds,
        "packets": len(rows),
        "unchecked": unchecked,
        "early": sum(1 for r in rows if r["inject_delay"] < 0),
        "inject_above_bound": sum(1 for r in rows if r["inject_delay"] > bounds["inject"]),
        "header_above_bound": sum(1 for r in rows if r["header_wait"] > r["header_wait_bound"]),
        "rx_wait_above_bound": sum(1 for r in rows if r["rx_wait"] > bounds["rx_size"]),
        "end_wait_above_bound": sum(1 for r in rows if r["end_wait"] > bounds["rx_end"]),
        "latency_above_occupancy": sum(1 for r in rows if r["latency"] > r["occupancy"]),
        "occupancy_above": sum(1 for r in rows if r["occupancy_slack"] < 0),
        "late": sum(1 for r in rows if r["deadline_slack"] is not None and r["deadline_slack"] < 0),
        "ni_overlaps": sum(_overlaps(v) for v in ni.values()),
        "inject_delay_min": mn("inject_delay"), "inject_delay_max": mx("inject_delay"),
        "header_wait_max": mx("header_wait"), "rx_wait_max": mx("rx_wait"), "end_wait_max": mx("end_wait"),
        "occupancy_slack_min": mn("occupancy_slack"), "deadline_slack_min": mn("deadline_slack"),
    }
    out["violations"] = sum(out[k] for k in VIOLATION_KEYS)
    by_flow = {}
    for r in rows:
        by_flow.setdefault(r["flow"], []).append(r)
    out["flows"] = []
    for f, rs in sorted(by_flow.items(), key=lambda x: str(x[0])):
        row = {"flow": f, "src": rs[0]["src"], "dst": rs[0]["dst"], "packets": len(rs),
               "s": sorted({r["s"] for r in rs}), "occupancy": max(r["occupancy"] for r in rs)}
        for k in ("inject_delay", "header_wait", "rx_wait", "end_wait", "latency", "occupancy_used"):
            row[k + "_max"] = max(r[k] for r in rs)
        row["inject_delay_min"] = min(r["inject_delay"] for r in rs)
        row["occupancy_slack_min"] = min(r["occupancy_slack"] for r in rs)
        out["flows"].append(row)
    out["per_packet"] = rows
    return out


# counts of evaluate() that break the model (rttools.paper.phasecheck)
VIOLATION_KEYS = ("early", "inject_above_bound", "header_above_bound", "rx_wait_above_bound", "end_wait_above_bound",
                  "latency_above_occupancy", "occupancy_above", "late", "ni_overlaps")


def phase_ticks(release_cycles, grid, period):
    """Tick of each phase (index of the release, from 0) on a PE: the tick
    nearest to the release; and whether consecutive phases are one tick
    apart."""
    ticks = [nearest_tick(grid, c, period) for c in release_cycles]
    return ticks, all(b - a == period for a, b in zip(ticks, ticks[1:]))


def schedule_rows(csv_path, map_path, arch_path, f_clk, composition=None):
    """Rows of the link schedule of the time-triggered injection at f_clk
    (rttools.ucxgen.tt, network-interface model tt), as the generator of
    the table of the image: {"rows", "hyperperiod", "model"}."""
    from rttools.modules.io import appparser, mapparser, nocparser
    from rttools.tui.model import network as tnet
    from rttools.ucxgen import tt
    prev = router.set_ni("tt")
    try:
        if composition:
            from rttools.multiapp import compose
            with tnet.quiet():
                comp = compose.load(compose.read_spec(composition))
            return tt.union(comp, f_clk)
        with tnet.quiet():
            g, appname = appparser.loadFromFile(csv_path)
            noc = nocparser.loadFromFile(arch_path)
            entries = mapparser.loadFromFile(map_path)
        return tt.single(g, noc, entries, appname, f_clk)
    finally:
        router.set_ni(prev)


def rows_by_flow(table):
    """{flow label: [rows in the order of k]} of a schedule_rows table."""
    out = {}
    for r in table["rows"]:
        out.setdefault(r["flow"], []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r["k"])
    return out


def attach(packets, table, phase_of, release_cycles, grids, period):
    """Sets tau, s, s16, occupancy, deadline and phase of each packet with
    `flow_label` (label of the schedule rows) and `n` (0-based position of
    the packet in its flow, in the order of TX.head). `phase_of(packet,
    row, h)`: phase index (release, from 0) of the sending job of the
    packet, given its row and hyperperiod h. Packets without a row, a grid
    or a release keep tau None. Returns the count of PEs whose phase ticks
    are not one tick apart."""
    by = rows_by_flow(table)
    ticks, irregular = {}, 0
    for pe, g in grids.items():
        ticks[pe], ok = phase_ticks(release_cycles, g, period)
        irregular += not ok
    for p in packets:
        p["tau"] = None
        rs = by.get(p.get("flow_label"))
        if not rs or p["src"] not in ticks:
            continue
        h, k = divmod(p["n"], len(rs))
        row = rs[k]
        q = phase_of(p, row, h)
        if q is None or q < 0 or q >= len(ticks[p["src"]]):
            continue
        p.update(tau=ticks[p["src"]][q], phase=q, s=row["offset"], s16=row["s16"], occupancy=row["occupancy"],
                 deadline=row["deadline"] - row["phase_start"])
    return irregular


def summary_lines(t):
    if t is None:
        return ["time-triggered injection: no FLIT END or TIMER lines"]
    b = t["bounds"]
    return [f"time-triggered injection: {t['packets']} packets ({t['unchecked']} unchecked), violations "
            f"{t['violations']}: early {t['early']}, inject > {b['inject']}: {t['inject_above_bound']}, header > "
            f"w_h (m + 1): {t['header_above_bound']}, rx wait > {b['rx_size']}: {t['rx_wait_above_bound']}, end wait > "
            f"{b['rx_end']}: {t['end_wait_above_bound']}, latency > o_i: {t['latency_above_occupancy']}, "
            f"occupancy > o_i: {t['occupancy_above']}, late {t['late']}, NI overlaps {t['ni_overlaps']}",
            f"  inject delay {t['inject_delay_min']} to {t['inject_delay_max']}, header wait max "
            f"{t['header_wait_max']}, rx wait max {t['rx_wait_max']}, end wait max {t['end_wait_max']}, "
            f"smallest occupancy slack {t['occupancy_slack_min']}, smallest deadline slack {t['deadline_slack_min']}"]


def analyze_run(log_path, clk, releases_raw, table, packets, phase_of, w_h=None, relabel=None):
    """Time-triggered injection of a run: `packets` from the FLIT lines
    (dicts with src, dst, tag, size, hops, tx_head, tx_last, rx_head,
    rx_last, flow (name of the analysis), flow_label (label of the rows of
    `table`) and n), `releases_raw`: TRIGGER instants in raw units of the
    log (exp23.Clock clk); `relabel` maps the PE labels of the monitor to
    the labels of the packets (swap_xy of the trace). Returns None without
    TIMER lines, else the result of evaluate plus the tick grid of each
    PE."""
    ends, timers = read(log_path)
    if relabel is not None:
        for e in ends:
            e["src"], e["dst"] = relabel(e["src"]), relabel(e["dst"])
        for x in timers:
            x["pe"] = relabel(x["pe"])
    if not timers:
        return None
    ns_raw = 1e-9 / clk.unit.seconds
    c0 = cycle_offset(timers, lambda t: clk.cycles(t * ns_raw))
    period = table["rows"][0]["period"] if table["rows"] else None
    grids = tick_grid(timers, period)
    unpaired_end = pair_ends(packets, ends)
    rel = [clk.cycles(r) - c0 for r in releases_raw]
    irregular = attach(packets, table, phase_of, rel, grids, period)
    out = evaluate(packets, w_h)
    out.update(period_cycles=period, cycle_offset=c0, unpaired_end=unpaired_end,
               phase_ticks_irregular_pes=irregular,
               tick_grid={pe: {k: (round(v, 6) if isinstance(v, float) else v) for k, v in g.items()}
                          for pe, g in sorted(grids.items())},
               tick_grid_coverage_min=round(min(g["coverage"] for g in grids.values()), 6),
               end_lines=len(ends), timer_lines=len(timers))
    out["violations"] += irregular + (out["tick_grid_coverage_min"] < GRID_MIN_COVERAGE)
    return out
