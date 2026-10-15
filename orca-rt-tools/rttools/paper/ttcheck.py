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
| job end (jobs) | ITER end marker of job j - tick of its phase | <= F of the job in the model with t(v) = max(CSV, static) |
| ready (ready) | `->` TAG line of the packet (ucx_noc_send_at enqueues it) - tau | <= s |

occupancy_used = inject_delay + header_wait + 6 (m + 1) + p + 1 + rx_wait
+ end_wait, so the four waits within their bounds give occupancy_used <=
o_i. ni_overlaps counts, per PE, the pairs of packets whose intervals at
the network interface of the PE overlap (send: TX.head to TX.last; receive:
RX.head to END), which the resource of the link schedule excludes.
"""
from __future__ import annotations

import contextlib
import os
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


@contextlib.contextmanager
def run_ni(log_path, run_info="auto"):
    """Selects, for the analysis of the run of `log_path`, the
    network-interface model of its images: "tt" for a run with
    injection=tt in its RUN_INFO, "off" otherwise (the runs up to tag
    r11-rc5); and the deadline model of its table (router.set_deadline:
    deadline= of the RUN_INFO, start without the line, the runs up to tag
    r11-rc8). run_info: RUN_INFO path, "auto" (next to the log) or None
    (no RUN_INFO)."""
    from rttools.paper import exp23
    path = exp23.run_info_path(log_path) if run_info == "auto" else run_info
    info = exp23.read_run_info(path) if path else {}
    prev = router.set_ni(router.NI_TT if injection_rule(info) == "tt" else router.NI_OFF)
    prev_d = router.set_deadline(info.get("deadline", "start"))
    try:
        yield
    finally:
        router.set_ni(prev)
        router.set_deadline(prev_d)


REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
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


def schedule_rows(csv_path, map_path, arch_path, f_clk, composition=None, costs=None):
    """Rows of the link schedule of the time-triggered injection at f_clk
    (rttools.ucxgen.tt, network-interface model tt, the costs file of the
    run under the rule max), as the generator of the table of the image:
    {"rows", "hyperperiod", "model"}."""
    from rttools.wcet import costs as wcosts
    from rttools.modules.io import appparser, mapparser, nocparser
    from rttools.tui.model import network as tnet
    from rttools.ucxgen import tt
    prev = router.set_ni("tt")
    try:
        if composition:
            from rttools.multiapp import compose
            spec = compose.read_spec(composition)
            if costs:
                compose.set_costs(spec, {x["name"]: costs for x in spec["apps"]})
            with tnet.quiet():
                comp = compose.load(spec)
            return tt.union(comp, f_clk)
        with tnet.quiet():
            g, appname = appparser.loadFromFile(csv_path)
            noc = nocparser.loadFromFile(arch_path)
            entries = mapparser.loadFromFile(map_path)
        if costs:
            wcosts.apply(g, costs, wcosts.MAX)
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


def all_phase_ticks(release_cycles, grids, period):
    """({pe: [tick of phase q]}, PEs whose phase ticks are not one tick
    apart)."""
    ticks, irregular = {}, 0
    for pe, g in grids.items():
        ticks[pe], ok = phase_ticks(release_cycles, g, period)
        irregular += not ok
    return ticks, irregular


def deadlines(events, ticks, to_cycles):
    """Events against a bound from the tick of a phase: `events` = [{"pe",
    "t_raw" (instant in raw units of the log), "q" (phase), "bound" (cycles
    from the tick of phase q), ...}]. Returns {"events", "unchecked",
    "late", "slack_min", "rows"} (slack = bound - (instant - tick))."""
    rows, unchecked = [], 0
    for e in events:
        tk = ticks.get(e["pe"])
        if tk is None or e["t_raw"] is None or not 0 <= e["q"] < len(tk):
            unchecked += 1
            continue
        d = to_cycles(e["t_raw"]) - tk[e["q"]]
        rows.append(dict(e, after_tick=exact_cycles(d), slack=exact_cycles(e["bound"] - d)))
    return {"events": len(rows), "unchecked": unchecked, "late": sum(1 for r in rows if r["slack"] < 0),
            "slack_min": min((r["slack"] for r in rows), default=None), "rows": rows}


def exact_cycles(x):
    r = round(x)
    return r if abs(x - r) < 1e-6 else x


def attach(packets, table, phase_of, release_cycles, grids, period):
    """Sets tau, s, s16, occupancy, deadline and phase of each packet with
    `flow_label` (label of the schedule rows) and `n` (0-based position of
    the packet in its flow, in the order of TX.head). `phase_of(packet,
    row, h)`: phase index (release, from 0) of the sending job of the
    packet, given its row and hyperperiod h. Packets without a row, a grid
    or a release keep tau None. The deadline counts from the tick of phase
    q on the PE of the target (the tick of the job that reads the packet
    comes from that PE), given from tau. Returns the count of PEs whose
    phase ticks are not one tick apart."""
    by = rows_by_flow(table)
    ticks, irregular = all_phase_ticks(release_cycles, grids, period)
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
        dst = ticks.get(p.get("dst"))
        shift = dst[q] - ticks[p["src"]][q] if dst is not None and q < len(dst) else 0
        p.update(tau=ticks[p["src"]][q], phase=q, s=row["offset"], s16=row["s16"], occupancy=row["occupancy"],
                 deadline=row["deadline"] - row["phase_start"] + shift)
    return irregular


def summary_lines(t):
    if t is None:
        return ["time-triggered injection: no FLIT END or TIMER lines"]
    b = t["bounds"]
    extra = []
    for key, what in (("jobs", "job ends after F"), ("ready", "packets enqueued after s")):
        if key in t:
            x = t[key]
            extra.append(f"  {what}: {x['late']} of {x['events']} ({x['unchecked']} unchecked), smallest slack "
                         f"{x['slack_min']}")
    return extra + [f"time-triggered injection: {t['packets']} packets ({t['unchecked']} unchecked), violations "
            f"{t['violations']}: early {t['early']}, inject > {b['inject']}: {t['inject_above_bound']}, header > "
            f"w_h (m + 1): {t['header_above_bound']}, rx wait > {b['rx_size']}: {t['rx_wait_above_bound']}, end wait > "
            f"{b['rx_end']}: {t['end_wait_above_bound']}, latency > o_i: {t['latency_above_occupancy']}, "
            f"occupancy > o_i: {t['occupancy_above']}, late {t['late']}, NI overlaps {t['ni_overlaps']}",
            f"  inject delay {t['inject_delay_min']} to {t['inject_delay_max']}, header wait max "
            f"{t['header_wait_max']}, rx wait max {t['rx_wait_max']}, end wait max {t['end_wait_max']}, "
            f"smallest occupancy slack {t['occupancy_slack_min']}, smallest deadline slack {t['deadline_slack_min']}"]


def analyze_run(log_path, clk, releases_raw, table, packets, phase_of, w_h=None, relabel=None, jobs=None,
                ready=None):
    """Time-triggered injection of a run: `packets` from the FLIT lines
    (dicts with src, dst, tag, size, hops, tx_head, tx_last, rx_head,
    rx_last, flow (name of the analysis), flow_label (label of the rows of
    `table`) and n), `releases_raw`: TRIGGER instants in raw units of the
    log (exp23.Clock clk); `relabel` maps the PE labels of the monitor to
    the labels of the packets (swap_xy of the trace). Returns None without
    TIMER lines, else the result of evaluate plus the tick grid of each
    PE. `jobs`: the end of each job ({"pe", "task", "j", "t_raw", "q",
    "bound" = F of the job in the model}); `ready`: the enqueue of each
    packet between PEs (`->` TAG line; {"pe", "flow", "n", "t_raw", "q",
    "bound" = s}): deadlines() of each, "jobs" and "ready" of the result."""
    ends, timers = read(log_path)
    if relabel is not None:
        for e in ends:
            e["src"], e["dst"] = relabel(e["src"]), relabel(e["dst"])
        for x in timers:
            x["pe"] = relabel(x["pe"])
    if not timers:
        return None
    ns_raw = 1e-9 / clk.unit.seconds
    # the TIMER lines on the rising edges of the clock, as the marks of the
    # trace (exp23.snap_to_edges), so that c0 converts them to whole cycles
    edge = getattr(clk, "edge", None) or (lambda t: t)
    c0 = cycle_offset(timers, lambda t: clk.cycles(edge(t * ns_raw)))
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
    ticks, _ = all_phase_ticks(rel, grids, period)
    to_cyc = (lambda t: clk.cycles(t) - c0)
    for key, ev in (("jobs", jobs), ("ready", ready)):
        if ev is not None:
            d = deadlines(ev, ticks, to_cyc)
            out[key] = {k: v for k, v in d.items() if k != "rows"}
            out[key + "_rows"] = d["rows"]
            out["violations"] += d["late"] + d["unchecked"]
    out["violations"] += irregular + (out["tick_grid_coverage_min"] < GRID_MIN_COVERAGE)
    return out


def costs_of_run(info):
    """Costs file of a run from its RUN_INFO (costs=max_csv_static
    costs_file=<file> costs_sha256=<hash>, experiments/exp23/simulate.sh):
    the path of the file in experiments/wcet/costs/tt of this tree, or of
    the file of an earlier image in costs/tt/previous/<stem>-<first 12
    digits of the hash>.json, after a check of its hash; None for a run
    with the costs of the CSV."""
    import hashlib
    info = info or {}
    if info.get("costs") != "max_csv_static":
        return None
    name, sha = info["costs_file"], info["costs_sha256"].strip()
    base = os.path.join(REPO, "experiments", "wcet", "costs", "tt")
    stem = os.path.splitext(name)[0]
    for path in (os.path.join(base, name), os.path.join(base, "previous", f"{stem}-{sha[:12]}.json")):
        if not os.path.exists(path):
            continue
        with open(path, "rb") as f:
            got = hashlib.sha256(f.read()).hexdigest()
        if got == sha:
            return path
    raise ValueError(f"RUN_INFO costs: no {name} with sha256 {sha} in {base} or {base}/previous")


def costs_label(path):
    """Name of a costs file in the metrics of a run: the name in the RUN_INFO
    (costs_file=<stem>.json) also for a file of an earlier image kept in
    costs/tt/previous/<stem>-<first 12 digits of the hash>.json."""
    name = os.path.basename(path)
    if os.path.basename(os.path.dirname(path)) == "previous":
        m = re.match(r"^(.*)-[0-9a-f]{12}(\.json)$", name)
        if m:
            return m.group(1) + m.group(2)
    return name


ROW_FILES = (("per_packet", "tt_packets.csv"), ("jobs_rows", "tt_jobs.csv"), ("ready_rows", "tt_ready.csv"))


def pop_rows(t):
    """Removes the rows of a result of analyze_run (per packet, per job,
    per enqueue) and returns them: {file name: rows}."""
    if not t:
        return {}
    return {name: t.pop(key) for key, name in ROW_FILES if key in t}


def write_rows(out_dir, rows):
    """Writes the rows of pop_rows as CSV files in out_dir."""
    import csv
    for name, rs in rows.items():
        if not rs:
            continue
        cols = list(dict.fromkeys(k for r in rs for k in r))
        with open(os.path.join(out_dir, name), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rs:
                w.writerow([r.get(c) for c in cols])
