"""Schedulability tests for periodic task sets on one processor.

Tasks are dicts with name, wcet (C), period (T, None for a one-shot job)
and deadline (D, defaults to T). Times in cycles. The tests consider only
periodic tasks.

| Test | Policy | Condition | Reference |
|---|---|---|---|
| Utilization | any | U = sum C/T <= 1 (necessary) | |
| Liu-Layland | RM, D = T | U <= n(2^(1/n) - 1) (sufficient) | Liu and Layland, 1973 |
| Hyperbolic | RM, D = T | prod(U_i + 1) <= 2 (sufficient) | Bini, Buttazzo and Buttazzo, 2003 |
| Response time | RM or DM, D <= T | R_i <= D_i (exact with J = 0) | Joseph and Pandya, 1986; Tindell et al., 1994 (jitter) |
| Processor demand | EDF, D <= T | dbf(t) <= t for every deadline t in the busy period | Baruah, Rosier and Howell, 1990 |

The ORT/BENCH engine preempts only at scheduler interrupts (every
quantum q) and at task completions, so a release waits up to q cycles.
response_times() models this delay as a release jitter J = q for every
task.
"""
from __future__ import annotations

from functools import reduce
from math import ceil, floor, gcd


def periodic(tasks):
    out = []
    for t in tasks:
        if t.get("period"):
            d = t.get("deadline") or t["period"]
            out.append({"name": t["name"], "C": int(t["wcet"]), "T": int(t["period"]), "D": int(d)})
    return out


def utilization(tasks):
    return sum(t["C"] / t["T"] for t in periodic(tasks))


def liu_layland_bound(n):
    return n * (2 ** (1 / n) - 1) if n > 0 else 1.0


def hyperbolic(tasks):
    return reduce(lambda acc, t: acc * (t["C"] / t["T"] + 1), periodic(tasks), 1.0)


def priority_order(tasks, policy):
    """Fixed-priority order of the bench: RM by period, DM by deadline;
    sorted() is stable, so ties keep the order of the task set."""
    p = periodic(tasks)
    key = (lambda t: t["T"]) if policy == "RM" else (lambda t: t["D"])
    return sorted(p, key=key)


def response_times(tasks, policy, jitter=0, limit_factor=100):
    """Worst-case response time of each periodic task under fixed priority
    with release jitter J for all tasks:
        w = C_i + sum_{j in hp(i)} ceil((w + J) / T_j) C_j,  R_i = w + J.
    Returns a list of dicts name, C, T, D, R (None if the iteration passes
    limit_factor * D), ok."""
    order = priority_order(tasks, policy)
    key = (lambda t: t["T"]) if policy == "RM" else (lambda t: t["D"])
    out = []
    for i, t in enumerate(order):
        # every other task with the same or higher priority: the engine
        # breaks ties by ready-queue order, so equal keys interfere both ways
        hp = [h for j, h in enumerate(order) if j != i and key(h) <= key(t)]
        w = t["C"]
        r = None
        while True:
            nxt = t["C"] + sum(ceil((w + jitter) / h["T"]) * h["C"] for h in hp)
            if nxt == w:
                r = w + jitter
                break
            if nxt > limit_factor * t["D"]:
                break
            w = nxt
        out.append({**t, "R": r, "ok": r is not None and r <= t["D"]})
    return out


def lcm(values):
    return reduce(lambda a, b: a * b // gcd(a, b), values, 1)


def busy_period(tasks):
    p = periodic(tasks)
    w = sum(t["C"] for t in p)
    for _ in range(100000):
        nxt = sum(ceil(w / t["T"]) * t["C"] for t in p)
        if nxt == w:
            return w
        w = nxt
    return None


def edf_demand(tasks, max_points=200000):
    """Processor demand test. Returns (ok, first failing t or None,
    number of checked points); ok is None (inconclusive) when the number
    of points passes max_points. U > 1 fails at once (t None)."""
    p = periodic(tasks)
    if not p:
        return True, None, 0
    if utilization(tasks) > 1:
        return False, None, 0
    if all(t["D"] >= t["T"] for t in p):
        return True, None, 0
    L = busy_period(tasks)
    if L is None:
        L = lcm(t["T"] for t in p)
    points = sorted({t["D"] + k * t["T"] for t in p for k in range(0, (L - t["D"]) // t["T"] + 1)
                     if t["D"] + k * t["T"] <= L})
    for n, x in enumerate(points[:max_points]):
        dbf = sum(max(0, floor((x - t["D"]) / t["T"]) + 1) * t["C"] for t in p)
        if dbf > x:
            return False, x, n + 1
    if len(points) > max_points:
        return None, None, max_points
    return True, None, len(points)


def analyze(tasks, policy, quantum=0):
    """Summary for the TUI: list of (test, result text, ok or None)."""
    p = periodic(tasks)
    n = len(p)
    rows = []
    if n == 0:
        return [("Periodic tasks", "none (one-shot jobs only)", None)]
    u = utilization(tasks)
    rows.append(("Utilization U", f"{u:.4f}", u <= 1))
    implicit = all(t["D"] == t["T"] for t in p)
    constrained = all(t["D"] <= t["T"] for t in p)
    if policy == "RM":
        b = liu_layland_bound(n)
        if implicit:
            rows.append((f"Liu-Layland (U <= {b:.4f})", "pass" if u <= b else "inconclusive",
                         True if u <= b else None))
            h = hyperbolic(tasks)
            rows.append((f"Hyperbolic (prod = {h:.4f} <= 2)", "pass" if h <= 2 else "inconclusive",
                         True if h <= 2 else None))
    if policy in ("RM", "DM") and constrained:
        for j, name in ((0, "RTA"), (quantum, f"RTA, J = q = {quantum}")):
            if name != "RTA" and not quantum:
                continue
            res = response_times(tasks, policy, j)
            ok = all(r["ok"] for r in res)
            rows.append((name, "pass" if ok else "fail", ok))
    if policy == "EDF" and constrained:
        ok, x, npts = edf_demand(tasks)
        if ok is None:
            text = f"inconclusive ({npts} points checked)"
        elif ok:
            text = "pass"
        else:
            text = "fail (U > 1)" if x is None else f"fail at t = {x}"
        rows.append(("EDF demand", text, ok))
    if not constrained:
        rows.append(("D > T", "exact tests skipped", None))
    return rows


def observed_responses(trace_slices, tasks, horizon):
    """Response time of each completed job from a bench trace (slices of
    one task lane, sorted). Job k of task t is released at k*T and
    completes when the executed time reaches (k+1)*C. Returns
    {name: (max response, completed jobs)}."""
    out = {}
    for t in tasks:
        name, C, T = t["name"], int(t["wcet"]), t.get("period")
        if C <= 0:
            out[name] = (None, 0)
            continue
        sl = [s for s in trace_slices if s.label == name]
        done = 0
        need = C
        k = 0
        rmax = None
        for s in sl:
            start = s.start
            while start < s.end:
                take = min(need, s.end - start)
                start += take
                need -= take
                if need == 0:
                    release = k * int(T) if T else 0
                    r = start - release
                    rmax = r if rmax is None else max(rmax, r)
                    done += 1
                    k += 1
                    need = C
                    if not T:
                        break
            if not T and done:
                break
        out[name] = (rmax, done)
    return out
