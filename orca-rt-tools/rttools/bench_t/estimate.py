"""CPU time estimate per processing element (PE).

Each task v has a characterized cost c^(v) in cycles: its demand plus the
kernel work it causes on its PE (dispatch, network driver, payload copy).
The costs are inputs (rttools/bench_t/main.py keeps the values of
application E); this module does not compose them.

| Function | Result |
|---|---|
| dispatch_order | Order of the tasks of one PE in one phase by the rule of the UCX/OS kernel: round robin over the circular queue in creation order, with the idle task |
| sequence | Start and finish of each task of one PE: ORT/BENCH (SingleCoreEngine) with round robin, one job per task and quantum >= the largest cost |
| demand | c^(V_k), CPU time estimate of one PE by ORT/GCPA: sum of the costs of its tasks |
| cpu_frequency | f_CPU = max_k c^(V_k) / T, the lowest frequency at which every PE meets the release period T |
| phases | Phase index phi(v) of each task (a packet between two PEs reaches its target in the next phase; inside a PE, in the same phase when the target runs after the source) |
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
    """c^(V_k): CPU time estimate of one PE by ORT/GCPA (the CPA rule sums the
    costs of the tasks of one processor, rttools/gcpa/method.cluster_time), in cycles."""
    from rttools.gcpa.method import cluster_time
    return cluster_time(c for _, c in costs)


def cpu_frequency(demands, period_s):
    """f_CPU = max_k c^(V_k) / T in Hz; `demands` maps PE -> cycles."""
    if period_s <= 0:
        raise ValueError("period must be positive")
    return max(demands.values()) / period_s


def dispatch_order(creation, edges, phi):
    """Dispatch order of the tasks of one PE in one phase, by the rule of
    the UCX/OS kernel.

    The kernel (pkt-sim/software/ucx-os) keeps the tasks of a PE in a
    circular queue in creation order (ucx_task_add, kernel/ucx.c:20-48),
    after the idle task, which app_main creates first (id 0,
    app/weird_a.c:401). At each scheduling point it advances from the
    current task to the next ready task other than the idle task and runs
    the idle task when no task is ready (krnl_schedule,
    kernel/sched.c:94-109). The phase starts at the tick
    with the idle task as the current task (every task of the PE finished
    in the previous phase, c^(V_k) <= P).

    A packet from another PE reaches its target in an earlier phase (phi);
    so does a packet from a task of the same PE with a lower phase index.
    A task is ready at the start of the phase when every predecessor on
    the PE has a lower phase index; otherwise it becomes ready when its
    last predecessor of the same phase finishes. Each task runs to the end
    of its slice (no preemption inside the phase).

    `creation`: tasks of the PE in creation order, without the idle task;
    `edges`: (u, v) pairs of the task graph (edges with a task outside the
    PE are ignored); `phi`: phase index of each task (phases). Returns the
    tasks in dispatch order."""
    tasks = list(creation)
    if len(set(tasks)) != len(tasks):
        raise ValueError("repeated task in the creation order: " + ", ".join(map(str, tasks)))
    on_pe = set(tasks)
    waits = {t: set() for t in tasks}
    for u, v in edges:
        if u in on_pe and v in on_pe and phi[u] == phi[v]:
            waits[v].add(u)
    queue = [None] + tasks  # position 0: idle task
    done, order, cur = set(), [], 0
    while len(order) < len(tasks):
        nxt = None
        for step in range(1, len(queue) + 1):
            pos = (cur + step) % len(queue)
            t = queue[pos]
            if t is not None and t not in done and waits[t] <= done:
                nxt = pos
                break
        if nxt is None:
            raise ValueError("no ready task on the PE: cycle among " + ", ".join(
                str(t) for t in tasks if t not in done))
        order.append(queue[nxt])
        done.add(queue[nxt])
        cur = nxt
    return order


def phases(edges, pe_of, order=None):
    """phi(v) = max over (u, v) in E of phi(u) + hop(u, v); 0 for tasks
    without predecessors. hop = 1 when u and v run on different PEs. On
    the same PE, hop = 0 when v runs after u in the sequence of the PE and
    1 when v runs before u: the packet of u of iteration k exists only
    after the slice of v of that phase, so v serves iteration k in the next
    phase. `edges`: iterable of (u, v); `pe_of`: task -> PE; `order`: task
    -> position in the sequence of its PE (default: every task of a PE runs
    after its predecessors on the PE, the order that dispatch_order gives).
    Raises ValueError on a cycle (the phase is undefined)."""
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

    def hop(u, v):
        if pe_of.get(u) is None or pe_of.get(u) != pe_of.get(v):
            return 1
        if order is not None and u in order and v in order and order[v] < order[u]:
            return 1
        return 0

    def visit(v):
        if state.get(v) == 2:
            return phi[v]
        if state.get(v) == 1:
            raise ValueError("the task graph has a cycle through " + str(v))
        state[v] = 1
        best = 0
        for u in preds[v]:
            best = max(best, visit(u) + hop(u, v))
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
