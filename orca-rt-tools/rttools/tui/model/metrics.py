"""Metrics over a time window of a trace."""
from __future__ import annotations

from dataclasses import dataclass


def clip(s, t0, t1):
    return max(0, min(s.end, t1) - max(s.start, t0))


@dataclass
class LaneStats:
    lane: str
    window: int
    busy: int          # time of non-idle slices inside the window
    idle: int          # time of idle slices inside the window
    slices: int        # non-idle slices that intersect the window
    switches: int      # label changes between consecutive slices
    per_label: dict    # label -> time inside the window

    @property
    def utilization(self):
        return self.busy / self.window if self.window > 0 else 0.0


def lane_stats(trace, lane, t0=None, t1=None):
    t0 = trace.t0 if t0 is None else t0
    t1 = trace.t1 if t1 is None else t1
    busy = idle = n = switches = 0
    per = {}
    prev = None
    for s in trace.slices_between(lane, t0, t1):
        d = clip(s, t0, t1)
        if trace.is_idle(s):
            idle += d
        else:
            busy += d
            n += 1
        per[s.label] = per.get(s.label, 0) + d
        if prev is not None and prev != s.label:
            switches += 1
        prev = s.label
    return LaneStats(lane, t1 - t0, busy, idle, n, switches, per)


def all_stats(trace, t0=None, t1=None):
    return [lane_stats(trace, lane, t0, t1) for lane in trace.lanes]


def bursts(trace, lane, t0=None, t1=None):
    """Maximal runs of non-idle slices on `lane` (one burst = the CPU
    executes without passing through the idle task). Returns dicts with
    start, end, duration and the sequence of labels (consecutive repeats
    merged). A run that starts before t0 or ends after t1 is flagged
    partial."""
    t0 = trace.t0 if t0 is None else t0
    t1 = trace.t1 if t1 is None else t1
    out = []
    cur = None
    for s in trace.slices_between(lane, t0, t1):
        if trace.is_idle(s) or s.duration == 0:
            if cur is not None and s.duration > 0:
                out.append(cur)
                cur = None
            continue
        if cur is not None and s.start != cur["end"]:
            out.append(cur)
            cur = None
        if cur is None:
            cur = {"start": s.start, "end": s.end, "labels": [s.label],
                   "clipped": s.start < t0}
        else:
            cur["end"] = s.end
            if cur["labels"][-1] != s.label:
                cur["labels"].append(s.label)
    if cur is not None:
        out.append(cur)
    def busy_at(t):
        s = trace.slice_at(lane, t)
        return s is not None and not trace.is_idle(s) and s.duration > 0

    for b in out:
        if b["start"] == t0 and busy_at(t0 - 1):
            b["clipped"] = True
        if b["end"] == t1 and busy_at(t1):
            b["clipped"] = True
        b["duration"] = b["end"] - b["start"]
        b["sequence"] = "".join(b["labels"]) if all(len(x) == 1 for x in b["labels"]) \
            else ",".join(b["labels"])
        b["partial"] = b.pop("clipped") or b["end"] > t1
    return out


def packet_stats(packets):
    """Latency per tag of the paired RTL packets."""
    by = {}
    for p in packets:
        if p["latency"] is None:
            continue
        key = (p["tag"], p["src"], p["dst"])
        by.setdefault(key, []).append(p["latency"])
    out = []
    for (tag, src, dst), lat in by.items():
        out.append({"tag": tag, "src": src, "dst": dst, "count": len(lat),
                    "min": min(lat), "max": max(lat), "mean": sum(lat) / len(lat)})
    out.sort(key=lambda r: (r["src"] or "", r["tag"]))
    unmatched = sum(1 for p in packets if p["latency"] is None)
    return out, unmatched
