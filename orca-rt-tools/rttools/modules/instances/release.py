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
optionally, one sequence per PE. A PE takes the sequence that holds the
same tasks (the sequence of its own node first), so the sequence follows
its cluster to another node. Without a sequence, the tasks of a PE run in
the order of the mapping file, moved only as much as the edges between
tasks of the same PE require (stable topological order).
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
    return {
        "model": model,
        "scheduler_cycles": int(app_graph_attrs.get("scheduler_cycles", 0)),
        "sequences": {str(k): list(v) for k, v in sequences.items()} if sequences else None,
    }


def pe_sequences(tasks, edges, mapping, sequences=None):
    """Dispatch order of the tasks of each PE: {node: [task, ...]}.

    `tasks`: task ids of the instance; `edges`: (u, v) pairs; `mapping`:
    entries {"node", "tasks"} of the mapping file (mapper.getMap gives the
    PE of a task); `sequences`: explicit order per node, which wins."""
    node_of = {t: mapper.getMap(t, mapping) for t in tasks}
    missing = sorted(str(t) for t, n in node_of.items() if n is None)
    if missing:
        raise ValueError("tasks without a PE in the mapping: " + ", ".join(missing))
    order = {}
    for m in mapping:
        for t in m["tasks"]:
            if t in node_of and node_of[t] == m["node"] and t not in order.get(m["node"], []):
                order.setdefault(m["node"], []).append(t)
    out = {}
    for node, ts in order.items():
        seq = matching_sequence(node, ts, sequences)
        if seq is not None:
            out[node] = seq
            continue
        out[node] = stable_topological(ts, [(u, v) for u, v in edges if u in ts and v in ts])
    return out


def matching_sequence(node, tasks, sequences):
    """Sequence of the PE `node` with `tasks`: the sequence of the same
    node when it holds the same tasks, otherwise the sequence (of any
    node) that holds the same tasks, so a sequence follows its cluster when
    a mapping places the cluster on another node (Spiral Mapping). None
    when no sequence holds the tasks of the PE and no sequence shares a
    task with it; ValueError when a sequence shares tasks with the PE but
    differs from its tasks."""
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
            raise ValueError(f"sequence of PE {key} ({', '.join(seq)}) differs from the tasks of PE {node} "
                             f"in the mapping ({', '.join(tasks)})")
    return None


def stable_topological(tasks, edges):
    """Topological order of `tasks` that keeps the given order where the
    edges allow; with a cycle, the remaining tasks keep the given order."""
    indeg = {t: 0 for t in tasks}
    succ = {t: [] for t in tasks}
    for u, v in edges:
        succ[u].append(v)
        indeg[v] += 1
    out = []
    left = list(tasks)
    while left:
        ready = [t for t in left if indeg[t] == 0]
        if not ready:
            return out + left
        t = ready[0]
        out.append(t)
        left.remove(t)
        for v in succ[t]:
            indeg[v] -= 1
    return out


def task_windows(instance, mapping):
    """Start s^ and finish f^ of each task in the sequence of its PE, in
    cycles from the start of the phase."""
    rel = instance.get("release") or settings({})
    cost = {t: d["wcet"] for t, d in instance["tasks"]}
    edges = [(s, t) for s, t, _ in instance["flows"]]
    seqs = pe_sequences(list(cost), edges, mapping, rel["sequences"])
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
    flows (all flows must share it)."""
    if period_s is None:
        periods = {float(d["period"]) for _, _, d in app.edges(data=True)}
        if len(periods) != 1:
            raise ValueError("the flows have different periods; give period_s")
        period_s = periods.pop()
    rel = settings(getattr(app, "graph", {}) or {})
    cost = {t: d["wcet"] for t, d in app.nodes(data=True)}
    seqs = pe_sequences(list(cost), list(app.edges()), mapping, rel["sequences"])
    demand = {node: estimate.demand([(t, cost[t]) for t in ts]) for node, ts in seqs.items()}
    return {"demand": demand, "period_s": period_s, "f_cpu_hz": estimate.cpu_frequency(demand, period_s)}
