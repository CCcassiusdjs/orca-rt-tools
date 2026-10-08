"""CPU time estimate per processing element (PE).

Each task v has a characterized cost c^(v) in cycles: its demand plus the
kernel work it causes on its PE (dispatch, network driver, payload copy).
The costs are inputs (rttools/bench_t/main.py keeps the values of
application E); this module does not compose them.

| Function | Result |
|---|---|
| sequence | Start and finish of each task of one PE: ORT/BENCH (SingleCoreEngine) with round robin, one job per task and quantum >= the largest cost |
| demand | c^(V_k), sum of the costs of the tasks of one PE |
| cpu_frequency | f_CPU = max_k c^(V_k) / T, the lowest frequency at which every PE meets the release period T |
| phases | Phase index phi(v) of each task (a packet between two PEs reaches its target in the next phase) |
| response_bound | R^ = phi(v_out) P + f^(v_out), in cycles, with P the phase length in cycles |

c^(V_k) and f_CPU do not depend on the candidate frequency of the link
schedule, so the analysis computes them once, outside the frequency search.
"""
from __future__ import annotations

import contextlib
import io

from rttools.bench.engine import SingleCoreEngine
from rttools.bench.scheduling import RoundRobinSchedule
from rttools.gsl.graph import Graph, GraphNode


def sequence(costs, scheduler_cycles=0):
    """Sequence of one PE.

    `costs`: list of (task, c^) in dispatch order, c^ in cycles (int >= 0).
    The engine runs every task once (no period) with round robin and
    quantum = the largest cost, so no task is preempted and the tasks run
    in list order. Returns {task: {"start", "finish", "cost"}} in cycles
    from the start of the phase: finish = end of the slice of the task
    (f^(v_j) = sum of c^(v_l), l <= j); start = start of the slice plus
    `scheduler_cycles` (s^(v_j) = sigma + sum of c^(v_l), l < j), because
    each cost includes the dispatch of the task."""
    names = [n for n, _ in costs]
    if len(set(names)) != len(names):
        raise ValueError("repeated task in the sequence: " + ", ".join(names))
    values = []
    for n, c in costs:
        if int(c) != c or c < 0:
            raise ValueError(f"task {n}: cost must be a non-negative integer, got {c!r}")
        values.append(int(c))
    if not costs:
        return {}

    g = Graph()
    for i, (n, c) in enumerate(zip(names, values)):
        g._nodes.append(GraphNode(i, {"label": n, "wcet": c}))
    engine = SingleCoreEngine(g, RoundRobinSchedule, quantum=max(max(values), 1))
    with contextlib.redirect_stdout(io.StringIO()):
        engine.simulate(sum(values) + 1)
    slices = {n: (b, e) for (b, e, n) in engine.merged_trace()}

    # a task with cost 0 has no slice; it starts and finishes at the
    # finish of the previous task
    ran = [n for (_, _, n) in engine.merged_trace()]
    if ran != [n for n, c in zip(names, values) if c > 0]:
        raise RuntimeError("ORT/BENCH did not run the tasks in list order: " + ", ".join(ran))
    out = {}
    t = 0
    for n, c in zip(names, values):
        b, e = slices.get(n, (t, t))
        out[n] = {"start": b + scheduler_cycles, "finish": e, "cost": c}
        t = e
    return out


def demand(costs):
    """c^(V_k): sum of the costs of the tasks of one PE (cycles)."""
    return sum(int(c) for _, c in costs)


def cpu_frequency(demands, period_s):
    """f_CPU = max_k c^(V_k) / T in Hz; `demands` maps PE -> cycles."""
    if period_s <= 0:
        raise ValueError("period must be positive")
    return max(demands.values()) / period_s


def phases(edges, pe_of):
    """phi(v) = max over (u, v) in E of phi(u) + [pe(u) != pe(v)]; 0 for
    tasks without predecessors. `edges`: iterable of (u, v); `pe_of`: task
    -> PE. Raises ValueError on a cycle (the phase is undefined)."""
    edges = list(edges)
    tasks = set(pe_of)
    for u, v in edges:
        tasks.add(u)
        tasks.add(v)
    preds = {t: [] for t in tasks}
    for u, v in edges:
        preds[v].append(u)
    phi = {}
    state = {}

    def visit(v):
        if state.get(v) == 2:
            return phi[v]
        if state.get(v) == 1:
            raise ValueError("the task graph has a cycle through " + str(v))
        state[v] = 1
        best = 0
        for u in preds[v]:
            hop = 0 if pe_of.get(u) is not None and pe_of.get(u) == pe_of.get(v) else 1
            best = max(best, visit(u) + hop)
        phi[v] = best
        state[v] = 2
        return best

    for t in sorted(tasks, key=str):
        visit(t)
    return phi


def response_bound(phi, finish, period_cycles, outputs=None):
    """R^ = phi(v_out) P + f^(v_out) in cycles. `finish`: task -> f^;
    `outputs`: the output tasks (default: every task of `finish`, so the
    bound covers the last task of the iteration). Returns (R^, v_out) for
    the output task with the largest bound."""
    if outputs is None:
        outputs = list(finish)
    best = max(outputs, key=lambda t: (phi[t] * period_cycles + finish[t], str(t)))
    return phi[best] * period_cycles + finish[best], best
