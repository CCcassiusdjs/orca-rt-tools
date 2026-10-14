"""Release and absolute deadline of the packets of each flow.

Packet k of flow i = (u, v), with period P_i in cycles:

| Model | Release | Absolute deadline |
|---|---|---|
| phase | k P_i + f^(u) | (k + 1) P_i + s^(v) |
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


def task_windows(instance, mapping):
    """Start s^ and finish f^ of each task in the sequence of its PE, in
    cycles from the start of the phase."""
    rel = instance.get("release") or settings({})
    cost = {t: d["wcet"] for t, d in instance["tasks"]}
    edges = [(s, t) for s, t, _ in instance["flows"]]
    seqs = pe_sequences(list(cost), edges, mapping, rel["sequences"], rel.get("creation"))
    out = {}
    for node, ts in seqs.items():
        seq = estimate.sequence([(t, cost[t]) for t in ts], rel["scheduler_cycles"])
        for t in ts:
            out[t] = dict(seq[t], node=node)
    return out


def phase_flows(instance, mapping):
    """phase model: {flow label: (offset, end)}; packet k of the flow has
    release k P + offset and absolute deadline k P + end, with
    offset = f^(source) and end = P + s^(target)."""
    win = task_windows(instance, mapping)
    out = {}
    for s, t, d in instance["flows"]:
        out[d["label"]] = (win[s]["finish"], d["period"] + win[t]["start"])
    return out


def cpu_bound(app, mapping, period_s=None):
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
            spec = multirate.spec_from_graph(app, mapping, r)
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
