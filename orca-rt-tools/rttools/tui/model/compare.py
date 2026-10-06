"""Comparison of two traces lane by lane (for example, the original RTL
against the fixed RTL)."""
from __future__ import annotations


def lane_events(trace, lane):
    """Sequence of (start, label) of the slices of `lane`."""
    return [(s.start, s.label) for s in trace.lane_slices(lane)]


def compare(a, b, scale_b=1.0, offset_b=0, lanes=None):
    """Compares the slice starts of `a` and `b`. The times of `b` become
    b * scale_b + offset_b before the comparison (scale_b = 10 compares a
    trace in 100 ps units with one in 1 ns units).

    Returns a dict with one entry per lane: count_a, count_b, matched
    (same label at the same index), first_label_mismatch (index or None),
    equal_times (matched events with equal time), min_delta, max_delta
    (time of b minus time of a), and first_time_mismatch."""
    lanes = lanes or [l for l in a.lanes if l in b.lanes]
    out = {}
    for lane in lanes:
        ea = lane_events(a, lane)
        eb = [(t * scale_b + offset_b, n) for (t, n) in lane_events(b, lane)]
        n = min(len(ea), len(eb))
        matched = 0
        equal_times = 0
        first_label = None
        first_time = None
        deltas = []
        for i in range(n):
            (ta, la), (tb, lb) = ea[i], eb[i]
            if la != lb:
                if first_label is None:
                    first_label = i
                continue
            matched += 1
            d = tb - ta
            deltas.append(d)
            if d == 0:
                equal_times += 1
            elif first_time is None:
                first_time = (i, ta, tb)
        out[lane] = {
            "count_a": len(ea), "count_b": len(eb), "matched": matched,
            "equal_times": equal_times,
            "first_label_mismatch": first_label,
            "first_time_mismatch": first_time,
            "min_delta": min(deltas) if deltas else None,
            "max_delta": max(deltas) if deltas else None,
        }
    return out


def identical(result):
    return all(r["count_a"] == r["count_b"] == r["matched"] == r["equal_times"]
               for r in result.values())
