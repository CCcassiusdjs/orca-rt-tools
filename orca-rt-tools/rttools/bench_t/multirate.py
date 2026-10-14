"""Phase model with several release periods and with cycles.

The phase model of rttools/bench_t/estimate.py takes one release period T
for every task, one job of each task per phase and an acyclic graph. This
module generalizes it; release.py, instantiator.py, flowUnwrapper.py and
search.py select it when the application has more than one task period,
a flow whose period differs from the period of its source task, or a
directed cycle (`applies`). An application with one period and no cycle
keeps the model of estimate.py.

Model (cycles at a frequency f; P = phase length):

| Quantity | Definition |
|---|---|
| T_v | Release period of task v: column Period of the task row of the application; without it, the smallest period of the flows that v sends, else of the flows that v receives |
| P | Phase (tick of the kernel): gcd of the task periods; k_v = T_v / P ticks between two releases of v |
| H | Hyperperiod: lcm of the task periods, H / P phases |
| m_e | T_e / T_u for flow e = (u, v): the job j of u sends a packet on e when j mod m_e = 0 (T_e must be a multiple of T_u) |
| Job j of v | Release r = j k_v P (tick), start S and finish F from the ORT/BENCH simulation of the PE of v over the hyperperiod (rttools/bench/ucx.py: round robin of UCX-OS, tick P, one job per release, a job may span several ticks) |
| Creation order of a PE | The dispatch order of estimate.dispatch_order on the graph without the feedback edges (release.pe_sequences); the generated application creates its tasks in this order |
| CPU test | Every job finishes before the next release of its task (F <= r + T_v) in a periodic schedule; f_CPU = P_min / P_s, P_min the smallest phase length in cycles that passes |
| Read | Job c of v reads, at its start S_c, the packet of the latest job i of u (i mod m_e = 0) with F_i <= r_c (u on another PE: the packet left u before the tick that releases c) or F_i <= S_c (u on the PE of v) |
| Packet i of flow e | Release F_i; absolute deadline S of the first job c of v with r_c >= F_i (the first job that reads it); local packets do not enter the NoC |
| Data age of a chain v_0 ... v_n | F of a job of v_n minus the release of the job of v_0 whose data the job of v_n read, following the reads backwards; the bound is the largest value over the jobs of a periodic hyperperiod |

Feedback edges (`feedback_edges`): the edges marked in the application
(feedback rows of #parameters) plus the back edges of a depth-first search
over the tasks in input order, successors in flow order. A feedback edge
delivers the data of the previous job of its source: it leaves the phase
index n(v) and the dispatch order of the PE (no wait), and its packets
stay in the link schedule. With one period and no cycle, the reads give
n(v) of estimate.phases and the largest data age is R_bound =
n(v_last) P + f^(v_last) (estimate.response_bound).

Communication semantics: implicit communication with the latest value
(each job reads its inputs at its start and writes its outputs at its
end), the semantics of the data age analysis of cause-effect chains of
Becker et al. (2016).
"""
from __future__ import annotations

import math
from fractions import Fraction

from rttools.bench import ucx


class MultirateError(ValueError):
    pass


def seconds(x):
    """Exact Fraction of a period in seconds (text or number)."""
    if isinstance(x, Fraction):
        return x
    return Fraction(str(x))


def frac_gcd(values):
    vals = [seconds(v) for v in values]
    den = 1
    for v in vals:
        den = den * v.denominator // math.gcd(den, v.denominator)
    g = 0
    for v in vals:
        g = math.gcd(g, v.numerator * (den // v.denominator))
    return Fraction(g, den)


def frac_lcm(values):
    vals = [seconds(v) for v in values]
    p = frac_gcd(vals)
    n = 1
    for v in vals:
        q = int(v / p)
        n = n * q // math.gcd(n, q)
    return n * p


# ------------------------------------------------------------ graph

def task_periods(tasks, flows, given=None):
    """T_v of each task: `given` (task -> period, values <= 0 ignored),
    else the smallest period of the flows that v sends, else of the flows
    that v receives. `flows`: [(u, v, T_e)]."""
    given = given or {}
    out = {}
    for t in tasks:
        g = given.get(t)
        if g is not None and seconds(g) > 0:
            out[t] = seconds(g)
            continue
        sent = [seconds(T) for u, _, T in flows if u == t]
        recv = [seconds(T) for _, v, T in flows if v == t]
        if not sent and not recv:
            raise MultirateError(f"task {t}: no period (no task period and no flow)")
        out[t] = min(sent) if sent else min(recv)
    return out


def rates(tasks, flows, given=None):
    """{"phase_s", "hyper_s", "hyper_ticks", "ticks": {task: k_v},
    "task_period_s": {task: T_v}, "flow_jobs": [m_e per flow]} for
    `flows` = [(u, v, T_e)] in flow order."""
    T = task_periods(tasks, flows, given)
    P = frac_gcd(T.values())
    H = frac_lcm(T.values())
    ticks = {t: int(T[t] / P) for t in tasks}
    m = []
    for u, v, Te in flows:
        q = seconds(Te) / T[u]
        if q.denominator != 1 or q < 1:
            raise MultirateError(f"flow {u}->{v}: period {seconds(Te)} s is not a multiple of the period "
                                 f"{T[u]} s of {u}")
        m.append(int(q))
    return {"phase_s": P, "hyper_s": H, "hyper_ticks": int(H / P), "ticks": ticks, "task_period_s": T,
            "flow_jobs": m}


def feedback_edges(tasks, edges, marked=()):
    """Feedback edges: `marked` plus the back edges of a depth-first search
    over the other edges (roots in the order of `tasks`, successors in the
    order of `edges`). The graph without them is acyclic."""
    marked = [tuple(e) for e in marked]
    for e in marked:
        if e not in set(map(tuple, edges)):
            raise MultirateError(f"feedback edge {e[0]}->{e[1]} is not an edge of the graph")
    rest = [tuple(e) for e in edges if tuple(e) not in set(marked)]
    succ = {t: [] for t in tasks}
    for u, v in rest:
        succ[u].append(v)
    state = {}
    back = []
    for root in tasks:
        if root in state:
            continue
        stack = [(root, iter(succ[root]))]
        state[root] = 1
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
                continue
            s = state.get(nxt)
            if s == 1:
                back.append((node, nxt))
            elif s is None:
                state[nxt] = 1
                stack.append((nxt, iter(succ[nxt])))
    return marked + [e for e in back if e not in marked]


def is_cyclic(tasks, edges):
    return bool(feedback_edges(tasks, edges))


def applies(tasks, flows, given=None, marked=()):
    """True when the general model applies: several task periods, a flow
    period other than the period of its source, a marked feedback edge or
    a cycle. `flows`: [(u, v, T_e)]."""
    if marked:
        return True
    r = rates(tasks, flows, given)
    if len(set(r["task_period_s"].values())) > 1 or any(m != 1 for m in r["flow_jobs"]):
        return True
    return is_cyclic(tasks, [(u, v) for u, v, _ in flows])


def chains(tasks, edges, limit=100000):
    """Cause-effect chains: the simple paths of the graph (every edge,
    feedback edges included) from a task without input edge to a task
    without output edge, in the order of `tasks` and `edges`."""
    succ = {t: [] for t in tasks}
    indeg = {t: 0 for t in tasks}
    for u, v in edges:
        succ[u].append(v)
        indeg[v] += 1
    out = []

    def walk(path, seen):
        last = path[-1]
        if not succ[last]:
            out.append(list(path))
            if len(out) > limit:
                raise MultirateError(f"more than {limit} chains")
            return
        for v in succ[last]:
            if v in seen:
                continue
            seen.add(v)
            path.append(v)
            walk(path, seen)
            path.pop()
            seen.discard(v)

    for t in tasks:
        if indeg[t] == 0 and succ[t]:
            walk([t], {t})
    return out


# ------------------------------------------------------------ application

class Spec:
    """Application, mapping and rates of the general model, without a
    frequency (costs in cycles, periods in phases)."""

    def __init__(self, tasks, cost, ticks, phase_s, hyper_ticks, flows, node_of, orders, sigma, feedback,
                 offsets=None, task_period_s=None, sigma_pe=None):
        self.tasks = list(tasks)
        self.cost = {t: int(cost[t]) for t in tasks}
        self.ticks = dict(ticks)
        self.offsets = {t: int((offsets or {}).get(t, 0)) for t in tasks}
        self.phase_s = seconds(phase_s)
        self.hyper_ticks = int(hyper_ticks)
        self.flows = list(flows)            # [(label, u, v, m_e)]
        self.node_of = dict(node_of)
        self.orders = {n: list(ts) for n, ts in orders.items()}
        self.sigma = int(sigma)
        # scheduler cost of a PE when it differs from sigma (composition of
        # applications with their own kernel costs, rttools/multiapp)
        self.sigma_pe = {str(n): int(v) for n, v in (sigma_pe or {}).items()}
        self.feedback = [tuple(e) for e in feedback]
        self.task_period_s = task_period_s

    def edges(self):
        return [(u, v) for _, u, v, _ in self.flows]


def _orders(tasks, edges, feedback, mapping, settings):
    from rttools.modules.instances import release
    fb = set(map(tuple, feedback))
    dag = [e for e in edges if tuple(e) not in fb]
    return release.pe_sequences(list(tasks), dag, mapping, settings.get("sequences"), settings.get("creation"))


def _flow_index(label):
    s = str(label)
    return int(s[1:]) if s[:1] == "f" and s[1:].isdigit() else 0


def graph_rates(app, force=False):
    """Rates of an application graph (rttools.modules.io.appparser), or
    None when the model of estimate.py applies (one period, no cycle, no
    marked feedback edge) and `force` is false. The graph attributes give
    the task periods (task_periods) and the marked feedback edges
    (feedback)."""
    attrs = getattr(app, "graph", {}) or {}
    tasks = list(app.nodes)
    fl = sorted(app.edges(data=True), key=lambda e: _flow_index(e[2].get("label")))
    flows = [(u, v, seconds(d["period"])) for u, v, d in fl]
    given = attrs.get("task_periods") or {}
    marked = [tuple(e) for e in attrs.get("feedback") or []]
    if not force and not applies(tasks, flows, given, marked):
        return None
    r = rates(tasks, flows, given)
    edges = [(u, v) for u, v, _ in flows]
    r["feedback"] = feedback_edges(tasks, edges, marked)
    r["flow_jobs"] = {d["label"]: m for (_, _, d), m in zip(fl, r["flow_jobs"])}
    r["offsets"] = {t: 0 for t in tasks}
    return r


def instance_rates(app, frequency):
    """Rates of graph_rates with the phase in cycles at `frequency`
    (floor of P f) and the hyperperiod in cycles; None when the model of
    estimate.py applies."""
    r = graph_rates(app)
    if r is None:
        return None
    P = math.floor(r["phase_s"] * Fraction(frequency))
    r["phase_cycles"] = P
    r["hyper_cycles"] = P * r["hyper_ticks"]
    return r


def spec_from_graph(app, mapping, r=None):
    """Spec of an application graph and a mapping."""
    from rttools.modules.instances import release
    r = r or graph_rates(app)
    if r is None:
        raise MultirateError("the application has one period and no cycle (model of estimate.py)")
    settings = release.settings(getattr(app, "graph", {}) or {})
    tasks = list(app.nodes)
    cost = {t: int(d["wcet"]) for t, d in app.nodes(data=True)}
    fl = sorted(app.edges(data=True), key=lambda e: _flow_index(e[2].get("label")))
    flows = [(d["label"], u, v, r["flow_jobs"][d["label"]]) for u, v, d in fl]
    orders = _orders(tasks, [(u, v) for _, u, v, _ in flows], r["feedback"], mapping, settings)
    node_of = {t: n for n, ts in orders.items() for t in ts}
    return Spec(tasks, cost, r["ticks"], r["phase_s"], r["hyper_ticks"], flows, node_of, orders,
                settings["scheduler_cycles"], r["feedback"], r.get("offsets"), r["task_period_s"],
                settings.get("scheduler_cycles_pe"))


def spec_from_instance(instance, mapping):
    """Spec of an instance of instantiator.createInstance (key "rates")."""
    r = instance["rates"]
    settings = instance.get("release") or {}
    tasks = [t for t, _ in instance["tasks"]]
    cost = {t: int(d["wcet"]) for t, d in instance["tasks"]}
    fl = sorted(instance["flows"], key=lambda e: _flow_index(e[2]["label"]))
    flows = [(d["label"], u, v, r["flow_jobs"][d["label"]]) for u, v, d in fl]
    orders = _orders(tasks, [(u, v) for _, u, v, _ in flows], r["feedback"], mapping, settings)
    node_of = {t: n for n, ts in orders.items() for t in ts}
    return Spec(tasks, cost, r["ticks"], r["phase_s"], r["hyper_ticks"], flows, node_of, orders,
                settings.get("scheduler_cycles", 0), r["feedback"], r.get("offsets"), r["task_period_s"],
                settings.get("scheduler_cycles_pe"))


# ------------------------------------------------------------ schedule

class Schedule:
    """ORT/BENCH sequences of every PE over the hyperperiod at a phase of
    P cycles. Jobs of hyperperiod h > h0 repeat the jobs of h0 shifted by
    (h - h0) H (periodic schedule)."""

    def __init__(self, spec, P, sims, h0, periodic):
        self.spec = spec
        self.P = P
        self.H = P * spec.hyper_ticks
        self.sims = sims
        self.h0 = h0
        self.periodic = periodic
        self.jobs = {}
        for sim in sims.values():
            self.jobs.update(sim["jobs"])
        self.misses = []
        self.incomplete = []
        if periodic:
            for t, js in self.jobs.items():
                n = self.per_h(t)
                for j in js[: (h0 + 1) * n]:
                    if j.finish is None:
                        self.incomplete.append((t, j.index))
                    elif j.finish > j.deadline:
                        self.misses.append((t, j.index, j.deadline, j.finish))
        self.feasible = periodic and not self.misses and not self.incomplete

    def per_h(self, task):
        return self.spec.hyper_ticks // self.spec.ticks[task]

    def job(self, task, j):
        """(release, start, finish) of job j of `task` (periodic
        extension); None for j < 0."""
        if j < 0:
            return None
        n = self.per_h(task)
        h = j // n
        shift = 0
        if h > self.h0:
            shift = (h - self.h0) * self.H
            j -= (h - self.h0) * n
        x = self.jobs[task][j]
        return (x.release + shift, x.start + shift, x.finish + shift)

    def busy_per_phase(self):
        """{node: busy cycles in each phase of the periodic hyperperiod h0}."""
        out = {}
        base = self.h0 * self.spec.hyper_ticks
        for node, sim in self.sims.items():
            b = ucx.busy_per_phase(sim["slices"], self.P, (self.h0 + 1) * self.spec.hyper_ticks)
            out[node] = b[base:]
        return out


def schedule(spec, P, max_hyperperiods=32):
    """Simulates every PE at a phase of P cycles until the state of each PE
    at a hyperperiod boundary repeats (periodic schedule)."""
    if P <= 0:
        raise MultirateError("phase length must be positive")
    Ht = spec.hyper_ticks
    W = 2
    while True:
        sims = {}
        h0s = {}
        for node, ts in spec.orders.items():
            tasks = [{"name": t, "cost": spec.cost[t], "period": spec.ticks[t], "offset": spec.offsets[t]}
                     for t in ts]
            sigma = spec.sigma_pe.get(str(node), spec.sigma)
            sim = ucx.simulate(tasks, P, (W + 1) * Ht, sigma, tail=(W + 1) * Ht, boundary=Ht)
            sims[node] = sim
            st = sim["states"]
            h0s[node] = next((h for h in range(W) if (h * Ht) in st and ((h + 1) * Ht) in st
                              and st[h * Ht] == st[(h + 1) * Ht]), None)
        if all(h is not None for h in h0s.values()):
            return Schedule(spec, P, sims, max(h0s.values()), True)
        if W >= max_hyperperiods:
            return Schedule(spec, P, sims, None, False)
        W *= 2


def demand_per_phase(spec):
    """c(V_k, p): sum of c^(v) of the jobs of the PE released in phase p
    of the hyperperiod, {node: [cycles per phase]}."""
    out = {}
    for node, ts in spec.orders.items():
        row = [0] * spec.hyper_ticks
        for t in ts:
            for p in range(spec.offsets[t], spec.hyper_ticks, spec.ticks[t]):
                row[p] += spec.cost[t]
        out[node] = row
    return out


def utilization_bound(spec):
    """Smallest phase length (cycles) at which no PE exceeds a utilization
    of 1: max_k ceil(sum over V_k of c^(v) / k_v)."""
    out = 0
    for ts in spec.orders.values():
        tot = sum(Fraction(spec.cost[t], spec.ticks[t]) for t in ts)
        out = max(out, math.ceil(tot))
    return max(out, 1)


def cpu_test(spec):
    """CPU test of the general model: the smallest phase length P_min in
    cycles with a feasible schedule (bisection on integer P between the
    utilization bound and the largest sum of the costs of a PE, assuming
    that a feasible P stays feasible at larger P), f_CPU = P_min / P_s.
    Returns {"phase_cycles", "f_cpu_hz", "steps", "utilization_cycles",
    "demand_per_phase", "f_cpu_phase_hz" (largest c(V_k, p) / P_s: every job
    inside its release phase), "schedule"}."""
    lo = utilization_bound(spec)
    hi = max(max(sum(spec.cost[t] for t in ts) for ts in spec.orders.values()), lo)
    steps = 0
    sched = schedule(spec, hi)
    steps += 1
    while not sched.feasible:
        lo = hi + 1
        hi *= 2
        sched = schedule(spec, hi)
        steps += 1
        if hi > 1 << 40:
            raise MultirateError("no feasible phase length")
    best = sched
    lo = min(lo, hi)
    while lo < hi:
        mid = (lo + hi) // 2
        s = schedule(spec, mid)
        steps += 1
        if s.feasible:
            hi, best = mid, s
        else:
            lo = mid + 1
    if best.P != hi:
        best = schedule(spec, hi)
    dpp = demand_per_phase(spec)
    P_s = float(spec.phase_s)
    return {"phase_cycles": hi, "f_cpu_hz": frequency_of(hi, spec.phase_s), "steps": steps,
            "utilization_cycles": utilization_bound(spec), "demand_per_phase": dpp,
            "f_cpu_phase_hz": max(max(r) for r in dpp.values()) / P_s, "schedule": best}


def frequency_of(P, phase_s):
    """Frequency f (float, Hz) at which floor(phase_s f) = P: P / phase_s,
    moved up to the next float when the division rounds down."""
    f = P / float(phase_s)
    while math.floor(seconds(phase_s) * Fraction(f)) < P:
        f = math.nextafter(f, math.inf)
    return f


# ------------------------------------------------------------ communication

def _first_job_released_at_or_after(spec, task, t, P):
    """Index of the first job of `task` with release >= t (cycles)."""
    q = -(-t // P)                      # first tick at or after t
    o, k = spec.offsets[task], spec.ticks[task]
    return max(0, -(-(q - o) // k))


def read_index(spec, sched, u, v, m, c):
    """Index of the job of u whose packet job c of v reads on a flow (u, v)
    with m_e = m, or None when no packet exists yet."""
    rel_c, S_c, _ = sched.job(v, c)
    limit = S_c if spec.node_of[u] == spec.node_of[v] else rel_c
    P = sched.P
    o, k = spec.offsets[u], spec.ticks[u]
    i = (limit - o * P) // (k * P)
    if i < 0:
        return None
    i -= i % m
    while i >= 0:
        if sched.job(u, i)[2] <= limit:
            return i
        i -= m
    return None


def reader_index(spec, sched, u, v, F):
    """Index of the first job of v that reads a packet that u finished at
    F: on another PE, the first job released at or after F; on the same
    PE, the first job that starts at or after F."""
    P = sched.P
    if spec.node_of[u] != spec.node_of[v]:
        return _first_job_released_at_or_after(spec, v, F, P)
    o, k = spec.offsets[v], spec.ticks[v]
    c = max(0, (F // P - o) // k)
    while sched.job(v, c)[1] < F:
        c += 1
    return c


def packet_windows(spec, sched):
    """Packets of one periodic hyperperiod (jobs of the sources released in
    hyperperiod h0), in cycles from the start of h0: {label: [(job index
    in the hyperperiod, release, deadline, local)]}."""
    if not sched.feasible:
        raise MultirateError("the CPU schedule misses a deadline or is not periodic at this phase length")
    base = sched.h0 * sched.H
    out = {}
    for label, u, v, m in spec.flows:
        n = sched.per_h(u)
        rows = []
        for j in range(sched.h0 * n, (sched.h0 + 1) * n):
            if j % m:
                continue
            F = sched.job(u, j)[2]
            c = reader_index(spec, sched, u, v, F)
            d = sched.job(v, c)[1]
            rows.append((j - sched.h0 * n, F - base, d - base, spec.node_of[u] == spec.node_of[v]))
        out[label] = rows
    return out


def data_age(spec, sched, chain_list=None, max_extra=64):
    """Largest data age of each chain over the output jobs of a periodic
    hyperperiod: [{"chain", "max_cycles", "min_cycles", "output_job",
    "source_job", "jobs", "hyperperiod"}]. The evaluated hyperperiod is the
    first one, after h0, in which every job of the backward walk lies in a
    periodic hyperperiod (>= h0)."""
    if not sched.feasible:
        raise MultirateError("the CPU schedule misses a deadline or is not periodic at this phase length")
    chain_list = chains(spec.tasks, spec.edges()) if chain_list is None else chain_list
    m_of = {(u, v): m for _, u, v, m in spec.flows}
    out = []
    for ch in chain_list:
        res = None
        for extra in range(1, max_extra + 1):
            h = sched.h0 + extra
            last = ch[-1]
            n = sched.per_h(last)
            ages, ok = [], True
            for c in range(h * n, (h + 1) * n):
                j = c
                for a, b in zip(reversed(ch[:-1]), reversed(ch[1:])):
                    j = read_index(spec, sched, a, b, m_of[(a, b)], j)
                    if j is None or j // sched.per_h(a) < sched.h0:
                        ok = False
                        break
                if not ok:
                    break
                ages.append((sched.job(last, c)[2] - sched.job(ch[0], j)[0], c, j))
            if ok:
                hi = max(ages)
                res = {"chain": list(ch), "max_cycles": hi[0], "min_cycles": min(ages)[0],
                       "output_job": hi[1] - h * n, "source_job": hi[2], "jobs": len(ages), "hyperperiod": h}
                break
        if res is None:
            raise MultirateError("chain " + "->".join(ch) + ": no periodic hyperperiod within the search")
        out.append(res)
    return out
