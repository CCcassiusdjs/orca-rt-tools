"""Composition of periodic applications on disjoint PEs of one mesh.

Model (Section 6 of the paper, extended to applications a = 1..A):

| Quantity | Definition |
|---|---|
| PE_a | PEs of application a; PE_a and PE_b are disjoint for a != b |
| f_CPU,a | max over the PEs k of a of t(V_k) / T_a (release.cpu_bound) |
| f_CPU | max_a f_CPU,a |
| P_i | period of flow i in cycles at f (T_a f for a flow of a) |
| H | lcm of the hyperperiods of the applications (lcm of all P_i) |
| Packet instance | packet j of flow i of application a: r = j P_i + F(u), d = (j + 1) P_i + S(v), j = 0 .. H / P_i - 1 (release.phase_flows per application) |
| f_NoC | lowest f at which AGS places every packet of the union within its window |
| f | max(f_NoC, f_CPU), with the network check at f_CPU of search.minimum_frequency |
| R_bound,a | n(v_last) T_a + F(v_last) / f per application |

Assumptions: the applications start their first phase at the same
instant (synchronous release, one release generator period per
application); a PE runs the tasks of one application, so the sequence of
each PE, its windows S(v), F(v) and the CPU test of each application do
not change with the other applications; the routes are XY, so the packets
of two applications meet only on the links of routes that cross.

The packets of application a keep their flow and packet names with the
prefix "<a>/" (SEP), so the flows of two applications stay distinct in
the AGS criteria (heuristics._flow counts packets per flow).

Several release periods (general phase model, rttools/bench_t/multirate.py):
when every application has release_model phase and the task periods of the
composition are not all equal, or one application has a cycle or a flow
period other than the period of its source, the composition is analyzed
as one application of the general model on the mesh (union_graph: the
disjoint union of the graphs, flows numbered across the applications, the
mapping entries of every application). The phase is P = gcd of all task
periods and the hyperperiod H = lcm of them, so the periods in cycles
share floor(P f) at every frequency. f_CPU,a is P_min,a / P with the
ORT/BENCH sequences of the PEs of a (multirate.cpu_test); f_CPU = max_a
f_CPU,a; the packets of every application are the windows [F of the
sending job, S of the reading job] of one periodic hyperperiod; f is the
lowest frequency at or above f_CPU with a feasible link schedule (network
check at f_CPU, search above when it fails, as search.minimum_frequency);
the response of application a is the largest data age over its
cause-effect chains (multirate.data_age), which equals R_bound for an
application with one period and no cycle. The applications keep distinct
task labels and their own scheduler cost (scheduler_cycles) on their PEs.
"""
from __future__ import annotations

import json
import math
import os

from rttools.bench_t import estimate, multirate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.io import appparser, nocparser
from rttools.modules.mapping import mapfile, spiral
from rttools.modules.unwrapper import flowUnwrapper

SEP = "/"
MAP_SPIRAL = "spiral"


class CompositionError(ValueError):
    pass


# ------------------------------------------------------------ inputs

def mesh_size(noc):
    xs = [int(d["X"]) for _, d in noc.nodes(data=True)]
    ys = [int(d["Y"]) for _, d in noc.nodes(data=True)]
    return max(xs) + 1, max(ys) + 1


def read_spec(path):
    """Composition file: {"arch", "apps": [{"name", "csv", "map", "pes",
    "costs", "cost_rule"}]}, paths resolved against the directory of the
    file; "costs": costs file of rttools.wcet, "cost_rule": rule of that
    file (rttools/wcet/costs.py, RULES; default max)."""
    with open(path) as f:
        spec = json.load(f)
    base = os.path.dirname(os.path.abspath(path))

    def res(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))
    out = {"file": path, "arch": res(spec["arch"]), "apps": []}
    for a in spec["apps"]:
        m = a.get("map", MAP_SPIRAL)
        out["apps"].append({"name": a["name"], "csv": res(a["csv"]),
                            "map": m if m == MAP_SPIRAL else res(m), "pes": a.get("pes"),
                            "costs": res(a["costs"]) if a.get("costs") else None,
                            "cost_rule": a.get("cost_rule", "max")})
    return out


def set_costs(spec, costs):
    """Sets the costs file (rttools.wcet, option --costs) of applications of
    a composition (read_spec): `costs` = {application name: path}."""
    names = [a["name"] for a in spec["apps"]]
    for n in costs:
        if n not in names:
            raise CompositionError(f"--costs: application {n!r} not in the composition ({', '.join(names)})")
    for a in spec["apps"]:
        if a["name"] in costs:
            a["costs"] = costs[a["name"]]
    return spec


def load(spec):
    """Loads the graphs and the architecture of a composition (read_spec)
    and places the applications (place). Returns {"arch", "noc", "width",
    "height", "apps": [{"name", "graph", "appname", "csv", "map", "pes",
    "entries", "placement"}]}; CompositionError on any mapping problem."""
    names = [a["name"] for a in spec["apps"]]
    if len(set(names)) != len(names):
        raise CompositionError("repeated application name in the composition")
    for n in names:
        if not n or SEP in n or ":" in n:
            raise CompositionError(f"application name {n!r}: empty or with {SEP!r} or ':'")
    for p in [spec["arch"]] + [a["csv"] for a in spec["apps"]] + [
            a["map"] for a in spec["apps"] if a["map"] != MAP_SPIRAL] + [
            a["costs"] for a in spec["apps"] if a.get("costs")]:
        if not os.path.isfile(p):
            raise CompositionError("missing file " + p)
    noc = nocparser.loadFromFile(spec["arch"])
    apps = []
    for a in spec["apps"]:
        g, appname = appparser.loadFromFile(a["csv"])
        if a.get("costs"):
            # static t(v) of rttools.wcet against the Capacity column, under the
            # rule of the application (default max: t(v) = max(CSV, static))
            from rttools.wcet import costs as wcosts
            try:
                wcosts.apply(g, a["costs"], a.get("cost_rule", wcosts.MAX))
            except (wcosts.CostsError, ValueError) as e:
                raise CompositionError(f"application {a['name']}: {e}") from None
        apps.append(dict(a, graph=g, appname=appname))
    width, height = mesh_size(noc)
    place(apps, width, height, list(noc.nodes))
    return {"arch": spec["arch"], "noc": noc, "width": width, "height": height, "apps": apps}


# ------------------------------------------------------------ mapping

def place(apps, width, height, nodes=None):
    """Sets "entries" (mapping entries {"node", "tasks"}) and "placement"
    of each application.

    An application with a .map file keeps its file (node indices
    y * width + x of the mesh). The Spiral Mapping places the other
    applications in the order of the composition: application a takes the
    next len(clusters) nodes of the spiral (spiral.spiral_order) that no
    .map file uses, and its clusters (ORT/GCM with pes_a clusters, the
    criterion of the smallest M2) take these nodes in increasing network
    volume, ties in the order of ORT/GCM, as spiral.spiral_map does on the
    whole mesh. Raises CompositionError when two applications use one PE,
    when a .map file has a problem (mapfile.problems) or when the spiral
    has no free node left."""
    if nodes is None:
        nodes = [str(n) for n in range(width * height)]
    for a in apps:
        if a["map"] != MAP_SPIRAL:
            a["entries"] = mapfile.read(a["map"])
            a["placement"] = {"method": "file", "file": os.path.basename(a["map"])}
            a["pes"] = len({e["node"] for e in a["entries"] if e["tasks"]})
    used = {e["node"] for a in apps if a["map"] != MAP_SPIRAL for e in a["entries"] if e["tasks"]}
    free = [n for n in spiral.spiral_order(width, height) if str(n) not in used]
    pos = 0
    for a in apps:
        if a["map"] != MAP_SPIRAL:
            continue
        n = a.get("pes")
        if not isinstance(n, int) or n < 1:
            raise CompositionError(f"application {a['name']}: `pes` (number of PEs) is required with the Spiral Mapping")
        tasks, edges = spiral.from_networkx(a["graph"])
        criterion, clusters, rows = spiral.cluster_application(tasks, edges, n)
        names = list(clusters)
        if pos + len(names) > len(free):
            raise CompositionError(f"application {a['name']}: {len(names)} clusters, {len(free) - pos} free nodes "
                                   f"left on the {width}x{height} mesh")
        vol = spiral.cluster_volumes(clusters, edges)
        ranked = sorted(range(len(names)), key=lambda i: (vol[names[i]], i))
        block = free[pos:pos + len(names)]
        pos += len(names)
        cnodes = {names[i]: block[k] for k, i in enumerate(ranked)}
        tmap = {t: cnodes[c] for c, ts in clusters.items() for t in ts}
        a["entries"] = mapfile.from_dict(tmap)
        a["placement"] = {"method": MAP_SPIRAL, "criterion": criterion, "nodes": sorted(block),
                          "cluster_nodes": cnodes, "volumes": vol,
                          "rows": [{"criterion": r["criterion"], "sigma": r["sigma"], "wcet": r["wcet"]}
                                   for r in rows]}
    bad = problems(apps, nodes)
    if bad:
        raise CompositionError("; ".join(bad))
    return apps


def problems(apps, nodes=None):
    """Mapping problems of the composition: the problems of each mapping
    (mapfile.problems: task on two nodes, task not mapped, node outside the
    architecture) and every PE that holds tasks of two applications."""
    out = []
    owner = {}
    for a in apps:
        tasks = list(a["graph"].nodes) if a.get("graph") is not None else None
        out += [f"application {a['name']}: {p}" for p in mapfile.problems(a["entries"], tasks, nodes)]
        for e in a["entries"]:
            if e["tasks"]:
                owner.setdefault(str(e["node"]), []).append((a["name"], list(e["tasks"])))
    for node, apps_on in sorted(owner.items(), key=lambda kv: int(kv[0])):
        if len(apps_on) > 1:
            out.append(f"PE {node} is mapped by applications "
                       + " and ".join(f"{n} (tasks {', '.join(ts)})" for n, ts in apps_on))
    return out


def node_owner(apps):
    """node index (str) -> application name."""
    return {str(e["node"]): a["name"] for a in apps for e in a["entries"] if e["tasks"]}


# ------------------------------------------------------------ general phase model

def _phase_model(a):
    return release.settings(getattr(a["graph"], "graph", {}) or {})["model"] == release.PHASE


def _app_rates(a):
    """multirate.graph_rates of application a (None: one period, no cycle)."""
    try:
        return multirate.graph_rates(a["graph"])
    except multirate.MultirateError as e:
        raise CompositionError(f"application {a['name']}: {e}") from None


def _task_periods(a):
    g = a["graph"]
    flows = [(u, v, d["period"]) for u, v, d in g.edges(data=True)]
    try:
        return multirate.task_periods(list(g.nodes), flows, (getattr(g, "graph", {}) or {}).get("task_periods"))
    except multirate.MultirateError as e:
        raise CompositionError(f"application {a['name']}: {e}") from None


def general(apps):
    """True when the composition takes the general phase model of
    rttools/bench_t/multirate.py (module docstring): every application has
    release_model phase and the task periods of the composition differ, or
    one application has several periods or a cycle. With another release
    model (cpa) the applications keep their own instances over the lcm of
    their hyperperiods; an application of the general model then raises
    CompositionError."""
    phase = [a for a in apps if _phase_model(a)]
    gen = [a["name"] for a in phase if _app_rates(a) is not None]
    if len(phase) != len(apps):
        if gen:
            raise CompositionError("applications " + ", ".join(gen) + " follow the general phase model (several "
                                   "periods or a cycle); the composition then needs release_model phase in "
                                   "every application")
        return False
    if gen:
        return True
    periods = {multirate.seconds(T) for a in apps for T in _task_periods(a).values()}
    return len(periods) > 1


def union_graph(apps):
    """The composition as one application graph of the general model:
    (graph, mapping entries, {union flow label: (application, flow label)},
    {task: application}). Tasks keep their labels (distinct across the
    applications); flows are numbered f1, f2, ... in the order of the
    applications and of their flows; the creation and sequence rows keep
    their tasks under the key "<application>/<node>" (release.
    matching_sequence finds a row by its tasks); feedback rows and task
    periods are joined. Applications with different scheduler_cycles (for
    example static costs of rttools.wcet, --costs) keep their own on their
    PEs (graph attribute scheduler_cycles_pe, multirate.Spec.sigma_pe)."""
    g0 = apps[0]["graph"]
    U = type(g0)()
    owner, flow_of = {}, {}
    sigma = {}
    creation, sequences, feedback, periods = {}, {}, [], {}
    k = 0
    for a in apps:
        g = a["graph"]
        attrs = getattr(g, "graph", {}) or {}
        sigma[a["name"]] = release.settings(attrs)["scheduler_cycles"]
        for n, d in g.nodes(data=True):
            if n in owner:
                raise CompositionError(f"task {n} in applications {owner[n]} and {a['name']}: the general phase "
                                       "model of the composition needs distinct task labels")
            owner[n] = a["name"]
            U.add_node(n, **d)
        for u, v, d in sorted(g.edges(data=True), key=lambda e: multirate._flow_index(e[2].get("label"))):
            k += 1
            U.add_edge(u, v, **dict(d, label=f"f{k}"))
            flow_of[f"f{k}"] = (a["name"], d.get("label"))
        for key, grp in (("creation", creation), ("sequences", sequences)):
            for node, ts in (attrs.get(key) or {}).items():
                grp[f"{a['name']}{SEP}{node}"] = list(ts)
        feedback += [tuple(e) for e in attrs.get("feedback") or []]
        periods.update(attrs.get("task_periods") or {})
    U.graph.update({"release_model": release.PHASE, "scheduler_cycles": next(iter(sigma.values()))})
    if len(set(sigma.values())) > 1:
        # each PE keeps the scheduler cost of its application
        U.graph["scheduler_cycles_pe"] = {str(e["node"]): sigma[a["name"]] for a in apps for e in a["entries"]
                                          if e["tasks"]}
    if creation:
        U.graph["creation"] = creation
    if sequences:
        U.graph["sequences"] = sequences
    if feedback:
        U.graph["feedback"] = feedback
    if periods:
        U.graph["task_periods"] = periods
    entries = [dict(e, tasks=list(e["tasks"])) for a in apps for e in a["entries"]]
    return U, entries, flow_of, owner


def union_spec(apps):
    """(graph, entries, flow_of, owner, rates, multirate.Spec) of union_graph."""
    U, entries, flow_of, owner = union_graph(apps)
    try:
        r = multirate.graph_rates(U, force=True)
        spec = multirate.spec_from_graph(U, entries, r)
    except multirate.MultirateError as e:
        raise CompositionError(str(e)) from None
    return U, entries, flow_of, owner, r, spec


def app_spec(spec, tasks):
    """Part of the union spec with the tasks of one application (same phase
    and hyperperiod); the PEs of an application hold only its tasks."""
    ts = [t for t in spec.tasks if t in tasks]
    return multirate.Spec(ts, spec.cost, spec.ticks, spec.phase_s, spec.hyper_ticks,
                          [f for f in spec.flows if f[1] in tasks], {t: spec.node_of[t] for t in ts},
                          {n: list(q) for n, q in spec.orders.items() if q and q[0] in tasks}, spec.sigma,
                          [e for e in spec.feedback if e[0] in tasks], spec.offsets, spec.task_period_s,
                          spec.sigma_pe)


def general_cpu_tests(apps):
    """CPU test of each application in the general model of the
    composition: multirate.cpu_test on the PEs of the application with the
    phase P of the composition. {name: result of release.cpu_bound for the
    general model}; f_CPU of the composition is the largest f_CPU,a (the
    PEs are disjoint, so P_min of the union is max_a P_min,a)."""
    _, entries, _, _, r, spec = union_spec(apps)
    out = {}
    for a in apps:
        tasks = set(a["graph"].nodes)
        sub = app_spec(spec, tasks)
        try:
            test = multirate.cpu_test(sub)
        except multirate.MultirateError as e:
            raise CompositionError(f"application {a['name']}: {e}") from None
        members = release.pe_members(list(sub.tasks), entries)
        res = {k: v for k, v in test.items() if k != "schedule"}
        res.update({"demand": {node: sum(sub.cost[t] * (sub.hyper_ticks // sub.ticks[t]) for t in ts)
                               for node, ts in members.items()},
                    "period_s": float(r["phase_s"]), "model": "multirate", "hyper_s": float(r["hyper_s"])})
        out[a["name"]] = res
    return out


def general_packets(apps, noc, frequency):
    """union_packets in the general model: the instance of union_graph at
    `frequency` (packet windows of one periodic hyperperiod), names with the
    prefix of the application and its own flow label."""
    U, entries, flow_of, owner, r, spec = union_spec(apps)
    inst = instantiator.createInstance(U, noc, frequency)
    packets, hp, nlinks = flowUnwrapper.unwrap(inst, noc, entries)
    info = {a["name"]: {"hyperperiod": None, "packets": None} for a in apps}
    if hp == 0:
        return None, 0, None, info
    P = inst["rates"]["phase_cycles"]
    out = []
    for p in packets:
        app, label = flow_of[p["flow"]]
        q = dict(p)
        q["name"] = qualify(app, label) + ":" + p["name"].rpartition(":")[2]
        q["flow"] = qualify(app, label)
        q["app"] = app
        out.append(q)
    for a in apps:
        Ha = P * math.lcm(*[spec.ticks[t] for t in a["graph"].nodes])
        n = sum(1 for q in out if q["app"] == a["name"])
        info[a["name"]] = {"hyperperiod": Ha, "packets": n * Ha // hp, "packets_in_H": n}
    return out, hp, nlinks, info


def general_responses(apps, frequency):
    """Response of each application in the general model at `frequency`:
    the largest data age over its cause-effect chains (multirate.data_age;
    R_bound for an application with one period and no cycle)."""
    from fractions import Fraction
    _, _, _, _, _, spec = union_spec(apps)
    P = math.floor(spec.phase_s * Fraction(frequency))
    sched = multirate.schedule(spec, P)
    if not sched.feasible:
        raise CompositionError(f"the CPU schedule of the composition misses a deadline at {frequency} Hz")
    every = multirate.chains(spec.tasks, spec.edges())
    out = {}
    for a in apps:
        tasks = set(a["graph"].nodes)
        ages = multirate.data_age(spec, sched, [c for c in every if c[0] in tasks])
        worst = max(ages, key=lambda x: (x["max_cycles"], "-".join(x["chain"])))
        out[a["name"]] = {"model": "multirate", "chain": list(worst["chain"]), "v_last": worst["chain"][-1],
                          "cycles": worst["max_cycles"], "s": worst["max_cycles"] / frequency,
                          "phase_cycles": P, "chains": len(ages),
                          "ages": [{"chain": "-".join(x["chain"]), "max_cycles": x["max_cycles"]} for x in ages]}
    return out


# ------------------------------------------------------------ packets

def qualify(app_name, name):
    return app_name + SEP + name


def app_packets(a, noc, frequency):
    """(packets, hyperperiod, links) of one application at `frequency`
    (instantiator.createInstance and flowUnwrapper.unwrap, the steps of
    search.schedule_at); hyperperiod 0 when undefined."""
    inst = instantiator.createInstance(a["graph"], noc, frequency)
    packets, hp, nlinks = flowUnwrapper.unwrap(inst, noc, a["entries"])
    if hp == 0:
        return None, 0, None
    return packets, hp, nlinks


def extend(packets, hp, H, app_name):
    """Packets of one application over H (a multiple of its hyperperiod
    hp): copy r of packet j of a flow with period P is packet j + r hp / P,
    shifted by r hp, which is the packet that flowUnwrapper.getPacketsFromFlows
    gives over H. Names get the prefix of the application."""
    per_flow = {}
    for p in packets:
        per_flow[p["flow"]] = per_flow.get(p["flow"], 0) + 1
    out = []
    for r in range(H // hp):
        for p in packets:
            q = dict(p)
            flow, _, idx = p["name"].rpartition(":")
            q["name"] = qualify(app_name, flow) + ":" + str(int(idx) + r * per_flow[p["flow"]])
            q["flow"] = qualify(app_name, p["flow"])
            q["app"] = app_name
            q["min_start"] = p["min_start"] + r * hp
            q["abs_deadline"] = p["abs_deadline"] + r * hp
            out.append(q)
    return out


def union_packets(apps, noc, frequency):
    """Packet instance of the composition at `frequency`: (packets, H,
    links, per application {"hyperperiod", "packets"}), H = lcm of the
    hyperperiods of the applications; (None, 0, None, info) when one
    application has no hyperperiod. In the general phase model (general)
    the packets are those of union_graph (general_packets)."""
    if general(apps):
        return general_packets(apps, noc, frequency)
    per = []
    info = {}
    for a in apps:
        pk, hp, nlinks = app_packets(a, noc, frequency)
        info[a["name"]] = {"hyperperiod": hp, "packets": None if pk is None else len(pk)}
        if hp == 0:
            return None, 0, None, info
        per.append((a, pk, hp, nlinks))
    H = math.lcm(*[hp for _, _, hp, _ in per])
    packets = []
    for a, pk, hp, _ in per:
        ext = extend(pk, hp, H, a["name"])
        info[a["name"]]["packets_in_H"] = len(ext)
        packets += ext
    return packets, H, per[0][3], info


def schedule_union(apps, noc, frequency, cfg):
    """search.schedule_at for the union: AGS (ags.agsExport) on the packets
    of every application over H. Same keys as schedule_at plus "apps"."""
    from rttools.modules.backend.ags import ags
    packets, H, nlinks, info = union_packets(apps, noc, frequency)
    if H == 0:
        return None
    problem, result = ags.agsExport(packets, nlinks, H, None, noc, "+".join(a["name"] for a in apps),
                                    cfg["pruning_factor"], cfg["fail_threshold"], cfg["heuristic"])
    sched, skipped = (None, set()) if result is None else result
    return {"frequency": frequency, "hyperperiod": H, "problem": problem, "schedule": sched,
            "skipped": skipped, "apps": info}


def scheduler(apps):
    """schedule_at replacement for search.search_minimum_frequency and
    search.network_check."""
    def run(_app, noc, _mapping, _appname, frequency, cfg):
        return schedule_union(apps, noc, frequency, cfg)
    return run


# ------------------------------------------------------------ frequency

def cpu_tests(apps):
    """CPU test of each application (search.cpu_check): {name: result};
    general_cpu_tests in the general phase model."""
    if general(apps):
        return general_cpu_tests(apps)
    return {a["name"]: search.cpu_check(a["graph"], a["entries"]) for a in apps}


def minimum_frequency(apps, noc, cfg, on_attempt=None):
    """Minimum frequency of the platform: steps of search.minimum_frequency
    with f_CPU = max_a f_CPU,a and the network search on the union of the
    packets (schedule_union).

    In the general phase model (general) the packet windows exist only at
    f >= f_CPU: the network is evaluated at f_CPU first and the search runs
    above f_CPU when it fails, the steps of search.minimum_frequency for an
    application of that model ("network" is None, "model" = "multirate").

    Returns the keys of search.minimum_frequency ("cpu" holds the result
    per application) plus "f_cpu_by_app"."""
    cpu = cpu_tests(apps)
    f_by = {n: (c["f_cpu_hz"] if c is not None else None) for n, c in cpu.items()}
    known = [v for v in f_by.values() if v is not None]
    f_cpu = max(known) if known else None
    run = scheduler(apps)
    name = "+".join(a["name"] for a in apps)
    if general(apps):
        check = search.network_check(None, noc, None, name, f_cpu, cfg, schedule=run)
        above = None
        if check["feasible"]:
            final = f_cpu
        else:
            up = dict(cfg)
            up["frequency"] = 2 * f_cpu
            above = search.search_minimum_frequency(None, noc, None, name, up, on_attempt, floor=f_cpu,
                                                    schedule=run)
            final = above["frequency"] if above is not None else None
        return {"cpu": cpu, "f_cpu_by_app": f_by, "network": None, "f_star_hz": final, "f_cpu_hz": f_cpu,
                "final_check": check, "final_search": above, "frequency_hz": final, "model": "multirate"}
    net = search.search_minimum_frequency(None, noc, None, name, cfg, on_attempt, schedule=run)
    f_star = net["frequency"] if net is not None else None
    check = above = None
    if f_star is None:
        final = None
    elif f_cpu is None or f_star >= f_cpu:
        final = f_star
    else:
        check = search.network_check(None, noc, None, name, f_cpu, cfg, schedule=run)
        if check["feasible"]:
            final = f_cpu
        else:
            up = dict(cfg)
            up["frequency"] = 2 * f_cpu
            above = search.search_minimum_frequency(None, noc, None, name, up, on_attempt, floor=f_cpu,
                                                    schedule=run)
            final = above["frequency"] if above is not None else None
    return {"cpu": cpu, "f_cpu_by_app": f_by, "network": net, "f_star_hz": f_star, "f_cpu_hz": f_cpu,
            "final_check": check, "final_search": above, "frequency_hz": final}


# ------------------------------------------------------------ response

def app_period_s(a):
    periods = {float(d["period"]) for _, _, d in a["graph"].edges(data=True)}
    if len(periods) != 1:
        raise CompositionError(f"application {a['name']}: R_bound needs one release period; with several "
                               "periods the response is the data age of response_bounds")
    return periods.pop()


def response_bounds(apps, noc, frequency):
    """Response of every application at `frequency`: {name: result}.
    One release period for the composition: response_bound (R_bound, n(v_last)
    and F(v_last)); general phase model: general_responses (largest data age
    over the chains of the application, "model": "multirate")."""
    if general(apps):
        return general_responses(apps, frequency)
    return {a["name"]: response_bound(a, noc, frequency) for a in apps}


def response_bound(a, noc, frequency):
    """R_bound of application a at `frequency` (Section 6.3): v_last, n(v_last),
    F(v_last), P = T_a f in cycles, R_bound in cycles and seconds."""
    inst = instantiator.createInstance(a["graph"], noc, frequency)
    win = release.task_windows(inst, a["entries"])
    edges = [(s, t) for s, t, _ in inst["flows"]]
    rel = inst["release"]
    seqs = release.pe_sequences(list(win), edges, a["entries"], rel["sequences"], rel.get("creation"))
    pe_of = {t: win[t]["node"] for t in win}
    phi = estimate.phases(edges, pe_of, release.sequence_positions(seqs))
    T = app_period_s(a)
    P = inst["flows"][0][2]["period"] if inst["flows"] else int(T * frequency)
    rb, vlast = estimate.response_bound(phi, {t: win[t]["finish"] for t in win}, P)
    return {"v_last": vlast, "phase": phi[vlast], "finish_cycles": win[vlast]["finish"],
            "period_cycles": P, "cycles": rb, "s": phi[vlast] * T + win[vlast]["finish"] / frequency,
            "sequences": {str(n): list(ts) for n, ts in seqs.items()}}


# ------------------------------------------------------------ interference

def link_intervals(attempt):
    """Reservations of a schedule: [(link label, start, end, packet
    index)], closed intervals [k, k + o] (search3.allocate)."""
    p = attempt["problem"]
    out = []
    for l, row in enumerate(attempt["schedule"] or []):
        label = p["links"][l][2]["label"]
        for j, k in enumerate(row):
            if k is not None:
                out.append((label, k, k + p["occupancy"][l][j], j))
    return out


def shared_links(packets):
    """Link labels used by packets of more than one application."""
    users = {}
    for p in packets:
        for e in p["path"]:
            users.setdefault(e["data"]["label"], set()).add(p.get("app"))
    return sorted(l for l, s in users.items() if len(s) > 1)


def isolated(apps, noc, frequency, cfg):
    """Schedule of each application alone at `frequency` (the flow of one
    application, search.schedule_at): {name: attempt}."""
    return {a["name"]: search.schedule_at(a["graph"], noc, a["entries"], a["appname"], frequency, cfg)
            for a in apps}


def collisions(attempts, H):
    """Superposition of the schedules of `attempts` ({name: attempt of
    search.schedule_at}), each one repeated over H: the reservations of two
    applications that overlap on a link (closed intervals, the collision
    test of AGS). Returns {"pairs", "links", "packets": {name: number of
    packets over H with at least one overlap}, "packets_total": {name:
    packets over H}}."""
    res = []
    total = {}
    for name, att in attempts.items():
        if att is None or att["schedule"] is None:
            continue
        hp = att["hyperperiod"]
        n = len(att["problem"]["packets"])
        total[name] = n * (H // hp)
        for r in range(H // hp):
            for label, a, b, j in link_intervals(att):
                res.append((label, a + r * hp, b + r * hp, (name, j + r * n)))
    by_link = {}
    for label, a, b, key in res:
        by_link.setdefault(label, []).append((a, b, key))
    pairs = 0
    links = set()
    hit = set()
    for label, ivs in by_link.items():
        ivs.sort()
        for i, (a, b, k) in enumerate(ivs):
            for a2, b2, k2 in ivs[i + 1:]:
                if a2 > b:
                    break
                if k2[0] != k[0]:
                    pairs += 1
                    links.add(label)
                    hit.add(k)
                    hit.add(k2)
    return {"pairs": pairs, "links": sorted(links),
            "packets": {n: sum(1 for k in hit if k[0] == n) for n in total}, "packets_total": total}


def periodic_overlaps(attempt):
    """Reservations of a schedule that overlap when the schedule repeats
    every hyperperiod H (the reservations of hyperperiod h + 1 against
    those of hyperperiod h on the same link): number of pairs and links.
    AGS tests the overlap inside one instance only; a reservation that
    ends after H meets the reservations of the next hyperperiod."""
    if attempt is None or attempt["schedule"] is None:
        return None
    H = attempt["hyperperiod"]
    by_link = {}
    for label, a, b, j in link_intervals(attempt):
        by_link.setdefault(label, []).append((a, b, j))
    pairs = 0
    links = set()
    for label, ivs in by_link.items():
        for a, b, j in ivs:
            for a2, b2, j2 in ivs:
                # interval of the next hyperperiod
                if not (b < a2 + H or b2 + H < a):
                    pairs += 1
                    links.add(label)
    return {"pairs": pairs, "links": sorted(links)}
