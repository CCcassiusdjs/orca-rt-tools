"""Release and absolute deadline of the packets of each flow.

Packet k of flow i = (u, v), with period P_i in cycles:

| Model | Release | Absolute deadline |
|---|---|---|
| phase | k P_i + f^(u) | (k + 1) P_i + s^(v); time-triggered platform: the tick of the phase of v (phase_flows) |
| cpa | k P_i + CP(u) | release + D_i |

phase: the analysis flow of the article. s^ and f^ are the start and
finish of each task in the sequence of its PE (ORT/BENCH, rttools/bench_t/
estimate.py) with the task costs c^(v) of the instance (column wcet of the
application, cycles) and the scheduler cost sigma; the target task
receives the packet in the phase after the source phase. Both values
count cycles from the start of the phase in which the source sends, so
the packets of all flows share the window of one hyperperiod. The relative
deadline of the input is not used.

cpa: model of ORT/FNS in the thesis (Ch. 6). CP(u) is the critical path up
to u computed by ORT/GCPA on the whole application, and D_i the relative
deadline of the flow in the input.

The application selects the model in its parameters (rttools/modules/io/
appparser.py, section #parameters): release_model, scheduler_cycles and,
optionally, the creation order of the tasks of each PE (`creation` rows:
the order of ucx_task_add in app_main). The dispatch order of each PE
follows the rule of the UCX/OS kernel (rttools/bench_t/estimate.py,
dispatch_order): round robin over the creation order from the idle task;
a task waits for its predecessors of the same phase on the PE. Without a
creation row, the order of the mapping file is the creation order. A PE
takes the row that holds the same tasks (the row of its own node first),
so the row follows its cluster to another node. A `sequence` row gives
the dispatch order of a PE directly (a kernel with another rule) and
wins over the creation row; the phase index then follows that order
(estimate.phases: a target that runs before its source on the same PE
gets one more phase).

Several release periods, a flow period other than the period of its
source, or a directed cycle select the general model of
rttools/bench_t/multirate.py (one ORT/BENCH sequence per PE over the
hyperperiod, latest-value reads, feedback edges): cpu_bound below,
instantiator.createInstance (key "rates" of the instance) and
flowUnwrapper (packet windows per job).
"""
from __future__ import annotations

from rttools.bench_t import estimate
from rttools.modules.mapping import mapper

PHASE = "phase"
CPA = "cpa"
MODELS = (PHASE, CPA)
# applications without the parameter keep the model of the thesis (Ch. 6)
DEFAULT_MODEL = CPA


def settings(app_graph_attrs):
    """Release settings of an application from its graph attributes."""
    model = str(app_graph_attrs.get("release_model", DEFAULT_MODEL)).strip().lower()
    if model not in MODELS:
        raise ValueError("unknown release model " + repr(model) + "; options: " + ", ".join(MODELS))
    sequences = app_graph_attrs.get("sequences")
    creation = app_graph_attrs.get("creation")
    return {
        "model": model,
        "scheduler_cycles": int(app_graph_attrs.get("scheduler_cycles", 0)),
        "sequences": {str(k): list(v) for k, v in sequences.items()} if sequences else None,
        "creation": {str(k): list(v) for k, v in creation.items()} if creation else None,
        "feedback": [tuple(e) for e in app_graph_attrs.get("feedback") or []],
        # handlers of the packet events of the time-triggered images (rttools/wcet/costs.py,
        # graph_handlers): {"inject", "receive", "budget": {task: cycles}}
        "handlers": app_graph_attrs.get("handlers"),
        # scheduler cost per PE (general phase model of a composition of
        # applications, rttools/multiapp/compose.py union_graph)
        "scheduler_cycles_pe": {str(k): int(v) for k, v in (app_graph_attrs.get("scheduler_cycles_pe") or {}).items()}
                               or None,
    }


def pe_members(tasks, mapping):
    """Tasks of each PE in the order of the mapping file: {node: [task, ...]}.
    `tasks`: task ids of the instance; `mapping`: entries {"node", "tasks"}
    (mapper.getMap gives the PE of a task)."""
    node_of = {t: mapper.getMap(t, mapping) for t in tasks}
    missing = sorted(str(t) for t, n in node_of.items() if n is None)
    if missing:
        raise ValueError("tasks without a PE in the mapping: " + ", ".join(missing))
    order = {}
    for m in mapping:
        for t in m["tasks"]:
            if t in node_of and node_of[t] == m["node"] and t not in order.get(m["node"], []):
                order.setdefault(m["node"], []).append(t)
    return order


def pe_sequences(tasks, edges, mapping, sequences=None, creation=None):
    """Dispatch order of the tasks of each PE: {node: [task, ...]}.

    `tasks`: task ids of the instance; `edges`: (u, v) pairs of the task
    graph (all of them: the phase index decides which predecessor a task
    waits for); `mapping`: entries {"node", "tasks"} of the mapping file;
    `sequences`: explicit dispatch order per node, which wins; `creation`:
    creation order per node, from which estimate.dispatch_order gives the
    dispatch order (default: the order of the mapping file)."""
    edges = list(edges)
    members = pe_members(tasks, mapping)
    node_of = {t: n for n, ts in members.items() for t in ts}
    phi = None
    out = {}
    for node, ts in members.items():
        seq = matching_sequence(node, ts, sequences)
        if seq is not None:
            out[node] = seq
            continue
        made = matching_sequence(node, ts, creation, "creation order")
        if phi is None:
            phi = estimate.phases(edges, node_of)
        out[node] = estimate.dispatch_order(made if made is not None else ts, edges, phi)
    return out


def sequence_positions(seqs):
    """task -> position in the sequence of its PE (input of estimate.phases)."""
    return {t: i for ts in seqs.values() for i, t in enumerate(ts)}


def matching_sequence(node, tasks, sequences, what="sequence"):
    """Row (sequence or creation order) of the PE `node` with `tasks`: the
    row of the same node when it holds the same tasks, otherwise the row
    (of any node) that holds the same tasks, so a row follows its cluster
    when a mapping places the cluster on another node (Spiral Mapping).
    None when no row holds the tasks of the PE and no row shares a task
    with it; ValueError when a row shares tasks with the PE but differs
    from its tasks."""
    if not sequences:
        return None
    own = sorted(tasks)
    if node in sequences and sorted(sequences[node]) == own:
        return list(sequences[node])
    for seq in sequences.values():
        if sorted(seq) == own:
            return list(seq)
    for key, seq in sequences.items():
        if set(seq) & set(tasks):
            raise ValueError(f"{what} of PE {key} ({', '.join(seq)}) differs from the tasks of PE {node} "
                             f"in the mapping ({', '.join(tasks)})")
    return None


def _sequences(instance, mapping):
    """(release settings, dispatch order of each PE, ORT/BENCH sequence of
    each task with its node: {task: {"start", "finish", "cost", "node"}})."""
    rel = instance.get("release") or settings({})
    cost = {t: d["wcet"] for t, d in instance["tasks"]}
    edges = [(s, t) for s, t, _ in instance["flows"]]
    seqs = pe_sequences(list(cost), edges, mapping, rel["sequences"], rel.get("creation"))
    out = {}
    for node, ts in seqs.items():
        seq = estimate.sequence([(t, cost[t]) for t in ts], rel["scheduler_cycles"])
        for t in ts:
            out[t] = dict(seq[t], node=node)
    return rel, seqs, out


def _deadlines(instance, seqs, base):
    """End of the window of each flow from the start of the phase of its
    source: P + s^(target) (the target reads in the phase after the source
    phase); with the time-triggered platform (router.tick_deadline), a flow
    between PEs whose target runs n(v) - n(u) = d phases after its source
    ends at min(P + s^(target), d P), the tick of the phase of the target:
    the earliest start of the job that reads it (the tick dispatches it
    when the tasks before it end at once), so the job never waits for the
    packet (a blocked task runs again at the next tick, since the idle
    task does not yield)."""
    from rttools.modules.routing import router
    edges = [(s, t) for s, t, _ in instance["flows"]]
    node_of = {t: base[t]["node"] for t in base}
    tick = router.tick_deadline()
    phi = estimate.phases(edges, node_of, sequence_positions(seqs)) if tick else None
    out = {}
    for s, t, d in instance["flows"]:
        end = d["period"] + base[t]["start"]
        if tick and node_of[s] != node_of[t]:
            end = min(end, (phi[t] - phi[s]) * d["period"])
        out[d["label"]] = end
    return out


def _instances(a, b, lo, hi, P):
    """Number of windows [a + k P, b + k P], k integer, that meet (lo, hi)."""
    n = 0
    k = (lo - b) // P
    while a + k * P < hi:
        if b + k * P > lo:
            n += 1
        k += 1
    return n


def handler_windows(instance, mapping, base, seqs, ends):
    """Finish of each task with the handlers of the packet events of its PE
    (time-triggered images: rttools/wcet/costs.py, handlers file). Every
    packet between PEs costs `inject` on the PE of its source and `receive`
    on the PE of its target, inside the window of the packet [f(u), end of
    the flow] of every phase; t(v) holds the handlers of the own packets of
    v (budget B_v). The window holds every instant at which the handler of
    the event can start (the compare interrupt at s16 <= s + 15, its wait
    within NI_INJECT_CYCLES, the receive handlers up to the end of the
    occupancy, s + o_i <= the end of the flow). The tasks of a PE run in
    their sequence from the tick (the phase starts with the idle task and
    no job waits for a packet), so the handlers that delay the finish of
    task y are those of the events that start in (-c_e, F(y)) (a handler
    that starts before the tick delays the tick), whatever task holds the
    CPU:

        F(y) = f^(y) + max(0, sum of the events that start in (-c_e, F(y)) - sum of B_z for z <= y in the sequence)

    a fixed point over every PE (the windows start at F of the sources).
    Returns {task: F(y)}."""
    h = instance["release"]["handlers"]
    budget = h.get("budget") or {}
    P = {s: d["period"] for s, _, d in instance["flows"]}
    fin = {t: base[t]["finish"] for t in base}
    cross = [(s, t, d["label"]) for s, t, d in instance["flows"] if base[s]["node"] != base[t]["node"]]
    period = next(iter(P.values()), None)
    for _ in range(1000):
        ev = {}
        for s, t, label in cross:
            w = (fin[s], ends[label])
            ev.setdefault(base[s]["node"], []).append(w + (h["inject"],))
            ev.setdefault(base[t]["node"], []).append(w + (h["receive"],))
        new = dict(fin)
        for node, ts in seqs.items():
            pool = 0
            for y in ts:
                pool += budget.get(y, 0)
                F = fin[y]
                while True:
                    load = sum(c * _instances(a, b, -c, F, period) for a, b, c in ev.get(node, []))
                    G = max(F, base[y]["finish"] + max(0, load - pool))
                    if G == F:
                        break
                    F = G
                new[y] = F
        if new == fin:
            return fin
        fin = new
    raise ValueError("handlers of the packet events: no fixed point of the finish of the tasks")


def task_windows(instance, mapping):
    """Start s^ and finish f^ of each task in the sequence of its PE, in
    cycles from the start of the phase. With the handlers of the
    time-triggered images in the release settings (rttools/wcet/costs.py)
    and the time-triggered platform (router.tick_deadline), finish is F of
    handler_windows, start moves with the finish of the task before it,
    and "sequence_finish" keeps f^."""
    rel, seqs, base = _sequences(instance, mapping)
    if not (rel.get("handlers") and _tick()):
        return base
    fin = handler_windows(instance, mapping, base, seqs, _deadlines(instance, seqs, base))
    out = {}
    for node, ts in seqs.items():
        prev = None
        for t in ts:
            shift = 0 if prev is None else fin[prev] - base[prev]["finish"]
            out[t] = dict(base[t], start=base[t]["start"] + shift, finish=fin[t], sequence_finish=base[t]["finish"])
            prev = t
    return out


def handlers_fit(instance, mapping):
    """False when, in the phase model with the handlers of the
    time-triggered images (task_windows), a task finishes after the end of
    its phase (P cycles): the next phase would not start with the idle
    task. True otherwise (also without handlers and in the other models)."""
    rel = instance.get("release") or settings({})
    if rel["model"] != PHASE or instance.get("rates") is not None or not instance["flows"]:
        return True
    if not (rel.get("handlers") and _tick()):
        return True
    P = instance["flows"][0][2]["period"]
    return all(w["finish"] <= P for w in task_windows(instance, mapping).values())


def _tick():
    from rttools.modules.routing import router
    return router.tick_deadline()


def phase_flows(instance, mapping):
    """phase model: {flow label: (offset, end)}; packet k of the flow has
    release k P + offset and absolute deadline k P + end, with
    offset = f^(source) (task_windows: F with the handlers of the
    time-triggered images) and end = P + s^(target), or the tick of the
    phase of the target for a flow between PEs on the time-triggered
    platform (_deadlines)."""
    rel, seqs, base = _sequences(instance, mapping)
    ends = _deadlines(instance, seqs, base)
    win = task_windows(instance, mapping)
    out = {}
    for s, t, d in instance["flows"]:
        out[d["label"]] = (win[s]["finish"], ends[d["label"]])
    return out


def cpu_bound(app, mapping, period_s=None, noc=None):
    """CPU test of the analysis flow, computed once from the application
    graph (task wcet = c^ in cycles) and the mapping, outside the
    frequency search: {"demand": {node: c^(V_k)}, "period_s": T,
    "f_cpu_hz": max_k c^(V_k) / T}. T defaults to the period of the
    flows (all flows must share it).

    An application of the general model (multirate.graph_rates: several
    periods or a cycle) takes the CPU test of multirate.cpu_test instead:
    the result adds "phase_cycles", "model": "multirate" and the keys of
    that test, with "period_s" = P, the phase length, and "demand" = the
    cycles of the jobs of each PE in one hyperperiod."""
    if period_s is None and settings(getattr(app, "graph", {}) or {})["model"] == PHASE:
        from rttools.bench_t import multirate
        r = multirate.graph_rates(app)
        if r is not None:
            spec = multirate.spec_from_graph(app, mapping, r, noc)
            test = multirate.cpu_test(spec)
            members = pe_members(list(spec.tasks), mapping)
            demand = {node: sum(spec.cost[t] * (spec.hyper_ticks // spec.ticks[t]) for t in ts)
                      for node, ts in members.items()}
            out = {k: v for k, v in test.items() if k != "schedule"}
            out.update({"demand": demand, "period_s": float(r["phase_s"]), "model": "multirate",
                        "hyper_s": float(r["hyper_s"])})
            return out
    if period_s is None:
        periods = {float(d["period"]) for _, _, d in app.edges(data=True)}
        if len(periods) != 1:
            raise ValueError("the flows have different periods; give period_s")
        period_s = periods.pop()
    cost = {t: d["wcet"] for t, d in app.nodes(data=True)}
    # the demand does not depend on the order of the tasks
    members = pe_members(list(cost), mapping)
    demand = {node: estimate.demand([(t, cost[t]) for t in ts]) for node, ts in members.items()}
    return {"demand": demand, "period_s": period_s, "f_cpu_hz": estimate.cpu_frequency(demand, period_s)}
