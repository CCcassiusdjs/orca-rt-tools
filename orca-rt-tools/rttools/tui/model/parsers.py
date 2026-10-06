"""Readers for the trace formats of the repository.

| Format | Source | Lines |
|---|---|---|
| rtl | Transcript of the manycore RTL (ModelSim/Questa) or the events extracted from it | `<t> <x-y> scheduled <i>`, `<t> <x-y> -> TAG <n>`, `<t> <x-y> <- TAG <n>`, optionally prefixed by `#` |
| bench | Output of `python -m rttools.bench` | `<start> <end> <task>` |
| kprofiler | Trace of HellfireOS/KProfiler (.sch) | header line, then `<task> <period> <capacity> <deadline> <start> (<event> <time>)+` |
| csv | Export of this TUI | `lane,start,end,label,kind` |
"""
from __future__ import annotations

import csv
import io
import json
import re

from rttools.tui.model.timeunit import (
    RTL_CLOCK_HZ, SI, TimeUnit, cycle_unit, unit_from_text,
)
from rttools.tui.model.trace import Mark, Slice, Trace

# default PE -> task map of rttools/log2gannt (application of Ch. 8),
# keys in the X-Y order of the logs of the original RTL (4c299fc)
DEFAULT_RTL_NAMES = {
    "0-0": ["IDLE", "F", "D", "B", "A"],
    "0-1": ["IDLE", "C"],
    "1-1": ["IDLE", "J", "G"],
    "1-0": ["IDLE", "H", "I", "E"],
}

RE_SCHED = re.compile(r"^(\d+)\s+(\d+-\d+)\s+scheduled\s+(\d+)\s*$")
RE_TAG = re.compile(r"^(\d+)\s+(\d+-\d+)\s+(->|<-)\s+TAG\s+(\S+)\s*$")
RE_TIMESCALE = re.compile(r"Time scale of \(([^)]*)\) is\s*(\d+)\s*(fs|ps|ns|us|ms|s)\b")
# a component of the hierarchical path that names the PE
# (manycore_pe, pe0, pe_x[0], pe_mod; not pipeline or perf)
RE_PE_PATH = re.compile(r"(?:^|\.)(?:manycore_pe|pe(?:\d+|_\w*)?)(?:$|[.\[])")
# release of the source task, printed by manycore_pe.sv with $time of the
# PE (the "ns" in the text is the label of the format string, not the unit)
RE_TRIGGER = re.compile(r"TRIGGER: workflow iteration at (\d+)")
RE_BENCH = re.compile(r"^(\d+)\s+(\d+)\s+(\S+)\s*$")


class TraceFormatError(ValueError):
    pass


def _strip(line):
    line = line.rstrip("\n").strip()
    if line.startswith("#"):
        line = line[1:].strip()
    return line


def swap_node(node):
    a, b = node.split("-")
    return b + "-" + a


def _swap_line(line):
    s = _strip(line)
    m = RE_SCHED.match(s)
    if m:
        return f"{m.group(1)} {swap_node(m.group(2))} scheduled {m.group(3)}"
    return s


def detect_format(lines, filename=""):
    """Returns rtl, bench, kprofiler or csv."""
    name = filename.lower()
    if name.endswith(".sch"):
        return "kprofiler"
    head = [l for l in lines[:2000] if l.strip()]
    if head and (head[0].strip().lower().startswith("lane,start,end")
                 or head[0].startswith("# unit_seconds=")):
        return "csv"
    for l in head:
        s = _strip(l)
        if RE_SCHED.match(s) or RE_TAG.match(s):
            return "rtl"
    bench = sum(1 for l in head if RE_BENCH.match(l.strip()))
    if bench and bench >= len([l for l in head if l.strip() and l.strip()[0].isdigit()]) * 0.9:
        return "bench"
    toks = head[1].split() if len(head) > 1 else []
    if len(toks) >= 7 and all(t.lstrip("-").isdigit() for t in toks[:5]):
        return "kprofiler"
    raise TraceFormatError("unknown trace format")


def rtl_task_name(names, node, idx):
    lst = names.get(node)
    if lst is not None and idx < len(lst):
        return lst[idx]
    return "IDLE" if idx == 0 else f"T{idx}"


def map_mismatch(lines, names):
    """True when a `scheduled` index falls outside the task list of its
    PE, the sign of logs whose X-Y order differs from the map."""
    for raw in lines:
        m = RE_SCHED.match(_strip(raw))
        if m and m.group(2) in names and int(m.group(3)) >= len(names[m.group(2)]):
            return True
    return False


def parse_rtl(lines, names=None, swap_xy=False, unit=None, name="rtl"):
    """Trace of the manycore RTL. Each `scheduled` event opens a slice on
    the PE until the next `scheduled` event of the same PE; the last slice
    of each PE ends at the last time of the log. `->` and `<-` lines become
    send and receive marks.

    The raw unit is $time of manycore_pe. The parser reads it from a
    `$printtimescale` line when the log has one; otherwise it assumes
    1 ns and flags the unit as assumed (the commit 4c299fc prints in units
    of 100 ps, see the TUI unit presets). swap_xy "auto" swaps X and Y when
    a task index falls outside the map and the swapped labels fit it."""
    names = DEFAULT_RTL_NAMES if names is None else names
    if swap_xy == "auto":
        swap_xy = map_mismatch(lines, names) and not map_mismatch(
            [_swap_line(l) for l in lines], names)
    sched = {}
    marks = []
    sends = []
    recvs = []
    t_end = 0
    detected = None
    for raw in lines:
        if "Time scale of" in raw and detected is None:
            m = RE_TIMESCALE.search(raw)
            if m and RE_PE_PATH.search(m.group(1)):
                detected = (m.group(2), m.group(3))
        s = _strip(raw)
        m = RE_TRIGGER.search(s)
        if m:
            t = int(m.group(1))
            marks.append(Mark("TRIGGER", t, "release", "workflow iteration"))
            t_end = max(t_end, t)
            continue
        m = RE_SCHED.match(s)
        if m:
            t, node, idx = int(m.group(1)), m.group(2), int(m.group(3))
            if swap_xy:
                node = swap_node(node)
            sched.setdefault(node, []).append((t, idx))
            t_end = max(t_end, t)
            continue
        m = RE_TAG.match(s)
        if m:
            t, node, direction, tag = int(m.group(1)), m.group(2), m.group(3), m.group(4)
            if swap_xy:
                node = swap_node(node)
            kind = "send" if direction == "->" else "recv"
            marks.append(Mark(node, t, kind, "TAG " + tag))
            (sends if kind == "send" else recvs).append((t, node, tag))
            t_end = max(t_end, t)

    if not sched and not marks:
        raise TraceFormatError("no `scheduled` or `TAG` lines in the log")

    slices = []
    for node, evs in sched.items():
        evs.sort()
        for (t, idx), nxt in zip(evs, evs[1:] + [(t_end, None)]):
            label = rtl_task_name(names, node, idx)
            kind = "idle" if label == "IDLE" else "task"
            slices.append(Slice(node, t, nxt[0], label, kind, f"task index {idx}"))

    if unit is None:
        if detected is not None:
            unit = unit_from_text(detected[0], detected[1], RTL_CLOCK_HZ)
        else:
            unit = unit_from_text(1, "ns", RTL_CLOCK_HZ, assumed=True)

    lanes = [k for k in names if k in sched or any(m.lane == k for m in marks)]
    lanes += sorted(k for k in sched if k not in lanes)
    lanes += sorted({m.lane for m in marks} - set(lanes))
    trace = Trace(name, unit, lanes, slices, marks, {
        "format": "rtl",
        "swap_xy": swap_xy,
        "timescale_detected": detected is not None,
        "packets": pair_packets(sends, recvs),
    })
    return trace


def pair_packets(sends, recvs):
    """Pairs each receive with the oldest pending send of the same tag
    (FIFO). Returns dicts with tag, src, dst, send, recv, latency; a send
    without receive has recv None."""
    pending = {}
    for t, node, tag in sorted(sends):
        pending.setdefault(tag, []).append((t, node))
    out = []
    for t, node, tag in sorted(recvs):
        q = pending.get(tag)
        if q:
            ts, src = q.pop(0)
            out.append({"tag": tag, "src": src, "dst": node, "send": ts, "recv": t,
                        "latency": t - ts})
        else:
            out.append({"tag": tag, "src": None, "dst": node, "send": None, "recv": t,
                        "latency": None})
    for tag, q in pending.items():
        for ts, src in q:
            out.append({"tag": tag, "src": src, "dst": None, "send": ts, "recv": None,
                        "latency": None})
    out.sort(key=lambda p: p["send"] if p["send"] is not None else p["recv"])
    return out


def parse_bench(lines, clock_hz=None, name="bench", task_info=None):
    """Output of `python -m rttools.bench` (merged slices `start end task`).
    One lane per task, plus the lane CPU with all slices. task_info
    (name -> (wcet, period, deadline)) adds release and deadline marks."""
    slices = []
    for line in lines:
        m = RE_BENCH.match(line.strip())
        if m:
            b, e, n = int(m.group(1)), int(m.group(2)), m.group(3)
            slices.append(Slice("CPU", b, e, n))
            slices.append(Slice(n, b, e, n))
    if not slices:
        raise TraceFormatError("no `start end task` lines")
    tasks = []
    for s in slices:
        if s.lane != "CPU" and s.lane not in tasks:
            tasks.append(s.lane)
    return Trace(name, cycle_unit(clock_hz), ["CPU"] + tasks, slices, [], {"format": "bench"})


def parse_kprofiler(lines, name="kprofiler", unit=None):
    """Trace of KProfiler (.sch). The first line is a header. In each
    following line the task runs from <start> until the time of the first
    event; the kernel runs from that time until the start of the next
    line. The raw unit is 1 us (the resolution menu of KProfiler divides
    the values by 1000 to show ms)."""
    rows = []
    for line in lines[1:]:
        toks = line.split()
        if len(toks) < 7:
            continue
        try:
            task, period, capacity, deadline, start = (int(x) for x in toks[:5])
            events = [(toks[i], int(toks[i + 1])) for i in range(5, len(toks) - 1, 2)]
        except ValueError:
            continue
        rows.append((task, period, capacity, deadline, start, events))
    if not rows:
        raise TraceFormatError("no KProfiler rows")
    slices = []
    marks = []
    for row, nxt in zip(rows, rows[1:] + [None]):
        task, period, capacity, deadline, start, events = row
        lane = f"Task {task}"
        first = events[0][1]
        slices.append(Slice(lane, start, first, lane, "task",
                            f"period {period}, capacity {capacity}, deadline {deadline}"))
        k_end = nxt[4] if nxt is not None else events[-1][1]
        if k_end > first:
            slices.append(Slice("Kernel", first, k_end, events[0][0], "kernel",
                                " ".join(f"{e}@{t}" for e, t in events)))
        for e, t in events:
            marks.append(Mark("Kernel", t, "event", e))
    lanes = sorted({s.lane for s in slices if s.lane != "Kernel"},
                   key=lambda x: int(x.split()[1])) + ["Kernel"]
    unit = unit or TimeUnit(SI["us"], "1 us")
    return Trace(name, unit, lanes, slices, marks, {"format": "kprofiler"})


def parse_csv(lines, name="csv"):
    """CSV written by export.write_csv. Optional first line:
    `# unit_seconds=<s> unit_name=<n> clock_hz=<f>`."""
    unit = TimeUnit(None, "unit")
    body = lines
    if lines and lines[0].startswith("#"):
        opts = dict(kv.split("=", 1) for kv in lines[0][1:].split() if "=" in kv)
        sec = opts.get("unit_seconds")
        clk = opts.get("clock_hz")
        from urllib.parse import unquote
        unit = TimeUnit(float(sec) if sec not in (None, "None") else None,
                        unquote(opts.get("unit_name", "unit")),
                        float(clk) if clk not in (None, "None") else None)
        body = lines[1:]
    reader = csv.DictReader(io.StringIO("".join(body)))
    slices = []
    marks = []
    for r in reader:
        if r.get("kind") in ("send", "recv", "release", "deadline", "miss", "event"):
            marks.append(Mark(r["lane"], int(r["start"]), r["kind"], r["label"]))
        else:
            slices.append(Slice(r["lane"], int(r["start"]), int(r["end"]), r["label"],
                                r.get("kind") or "task"))
    return Trace(name, unit, [], slices, marks, {"format": "csv"})


def load_names(path):
    with open(path) as f:
        return json.load(f)


def load_trace(path, fmt=None, names=None, swap_xy=False, unit=None, clock_hz=None):
    """Reads a trace file; fmt None detects the format."""
    with open(path, errors="replace") as f:
        lines = f.readlines()
    fmt = fmt or detect_format(lines, path)
    short = path.rsplit("/", 1)[-1]
    if fmt == "rtl":
        return parse_rtl(lines, names, swap_xy, unit, short)
    if fmt == "bench":
        return parse_bench(lines, clock_hz, short)
    if fmt == "kprofiler":
        return parse_kprofiler(lines, short, unit)
    if fmt == "csv":
        return parse_csv(lines, short)
    raise TraceFormatError("unknown format " + str(fmt))
