"""Model of the runs with the time-triggered injection (round r11g): the
analysis flow with the network-interface model tt and the cost rule max on
the image of each run.

    python -m rttools.paper.ttflow run --config experiments/tt/config.json --out <dir>
    python -m rttools.paper.ttflow tables --config experiments/tt/config.json --out <dir>
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

| Step | Rule |
|---|---|
| Costs | t(v) = max(t(v) of the CSV, static t(v) of the image of the run: costs file of experiments/wcet, costs/tt) and scheduler_cycles the larger of the two (rttools/wcet/costs.py, rule max); every task of every image has a static bound |
| Occupancy | o_i = L0 + w_h (m + 1) + w_NI, the network interface of each PE as a resource of the link schedule (rttools/modules/routing/router.py: the default model, tt; metrics.json "ni") |
| f_CPU, f_NoC, minimum | search.minimum_frequency (one application), compose.minimum_frequency (composition) with these costs |
| Clock of a run | the lowest F_CLK at or above the minimum whose phase is a whole number of 16-cycle steps of TIMER1 (exp23.flow_clock: grid 16 / P Hz); the runs of "keep" (E and WCET-E: the clock of the runs of round r11e) at their clock when the flow is feasible there |
| At each clock | sequences, S and F of every task (release.task_windows), n(v), R_bound (one release period) or the schedule of the general phase model, the data age of every chain and the finish of every job (time-triggered application), the link schedule of the injection tables (rttools.ucxgen.tt) |
| Simulation length | one release period: warmup + (n(v_last) + N - 1) T + R_bound + T against SIM_NS (N = iterations of the run); general model: warmup + the largest data age against SIM_NS |

| General phase model (CAR-FULL) | P_min of the CPU test, the utilization-bound frequency (the smallest phase at which the largest utilization of a PE reaches 1, over P_s), the phase-rule frequency (the largest demand of a PE in one phase, every job confined to the phase of its release, over P_s), the chains and the largest data age at the clock and at the minimum frequency, the flows on one PE, the packets between PEs in one hyperperiod |

`run` writes metrics.json and values.tex (macros \\ExpTt...). `tables` writes, for each run, the expected link schedule (packets) and
the finish of every job (jobs) that the check of run_r11g.sh checks
(awk), in the format of the docstring of write_tables.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from fractions import Fraction

from rttools.bench_t import estimate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.io import appparser, mapparser, nocparser
from rttools.modules.routing import router
from rttools.paper import exp23
from rttools.paper.frequency import search_config
from rttools.tui.model import network as tnet
from rttools.wcet import costs as wcosts

exact = exp23.exact


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(path))

    def rel(v):
        return os.path.normpath(os.path.join(base, v)) if isinstance(v, str) and ("/" in v or v.endswith(
            (".csv", ".map", ".gml", ".json"))) else v
    for a in cfg["apps"].values():
        a.setdefault("f0_hz", cfg["f0_hz"])
        for k in ("csv", "map", "arch", "costs", "composition", "manifest", "exp23_config", "terms"):
            if k in a:
                a[k] = rel(a[k])
    return cfg


def load_app(csv_path, map_path, arch_path, costs_path, rule=wcosts.MAX):
    """(graph with the costs of the rule, appname, noc, entries, rows of the
    costs per task)."""
    with tnet.quiet():
        g, appname = appparser.loadFromFile(csv_path)
        noc = nocparser.loadFromFile(arch_path)
        entries = mapparser.loadFromFile(map_path)
    csv_cost = {str(d.get("label", n)): int(float(d["wcet"])) for n, d in g.nodes(data=True)}
    sc_csv = int(g.graph.get("scheduler_cycles", 0) or 0)
    c = wcosts.load(costs_path)
    wcosts.apply(g, c, rule)
    rows = cost_rows(g, csv_cost, c, entries)
    return g, appname, noc, entries, {"tasks": rows, "scheduler_cycles": {
        "csv": sc_csv, "static": c["scheduler_cycles"], "used": int(g.graph.get("scheduler_cycles", 0))},
        "file": os.path.basename(costs_path), "sha256": exp23_sha(costs_path)}


def exp23_sha(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def cost_rows(g, csv_cost, c, entries):
    src = wcosts.sources(g)
    node = {t: str(e["node"]) for e in entries for t in e["tasks"]}
    return {t: {"pe": node.get(t), "csv": csv_cost[t], "static": c["tasks"][t],
                "used": int(float(g.nodes[n]["wcet"])) if n in g.nodes else None, "source": src[t]}
            for n, t in ((n, str(d.get("label", n))) for n, d in g.nodes(data=True))}


def pe_rows(tasks):
    """t(V_k) per PE: CSV, static and used sums, and the tasks whose static
    cost is above the CSV."""
    out = {}
    for t, r in sorted(tasks.items()):
        p = out.setdefault(r["pe"], {"tasks": [], "csv": 0, "static": 0, "used": 0, "static_above_csv": []})
        p["tasks"].append(t)
        p["csv"] += r["csv"]
        p["static"] += r["static"]
        p["used"] += r["used"]
        if r["source"] == wcosts.STATIC:
            p["static_above_csv"].append(t)
    for p in out.values():
        p["source"] = "static" if p["static"] > p["csv"] else "csv"
    return out


def phase_model(g, noc, entries, f):
    """One release period at f: P, S and F of every task, n(v), R_bound."""
    inst = instantiator.createInstance(g, noc, f)
    win = release.task_windows(inst, entries)
    edges = [(s, t) for s, t, _ in inst["flows"]]
    rel = inst["release"]
    seqs = release.pe_sequences(list(win), edges, entries, rel["sequences"], rel.get("creation"))
    pe_of = {t: win[t]["node"] for t in win}
    phi = estimate.phases(edges, pe_of, release.sequence_positions(seqs))
    P = inst["flows"][0][2]["period"]
    rb, vlast = estimate.response_bound(phi, {t: win[t]["finish"] for t in win}, P)
    return {"period_cycles": P, "tasks": {t: {"pe": str(win[t]["node"]), "start": win[t]["start"],
                                              "finish": win[t]["finish"], "phase": phi[t]} for t in win},
            "sequences": {str(n): list(ts) for n, ts in seqs.items()},
            "response_bound": {"cycles": rb, "task": vlast, "phase": phi[vlast], "ms": rb / f * 1e3},
            "cpu_fits": all(win[t]["finish"] <= P for t in win)}


def tt_rows(g, noc, entries, appname, f):
    from rttools.ucxgen import tt
    with tnet.quiet():
        return tt.single(g, noc, entries, appname, f)


def run_single(name, a):
    g, appname, noc, entries, costs = load_app(a["csv"], a["map"], a["arch"], a["costs"])
    with tnet.quiet():
        freq = search.minimum_frequency(g, noc, entries, appname, search_config(a["f0_hz"]))
    fmin = freq["frequency_hz"]
    out = {"kind": "single", "costs": costs, "pes": pe_rows(costs["tasks"]),
           "f_cpu_hz": freq["f_cpu_hz"], "f_noc_hz": freq["f_star_hz"], "minimum_hz": fmin,
           "binding": None if fmin is None else ("cpu" if fmin == freq["f_cpu_hz"] else "f_noc"), "runs": {}}
    T = a["period_s"]
    clocks = {}
    fc = exp23.flow_clock(fmin, T)
    clocks[a["runs"]["flow"]] = fc["f_clk_hz"]
    clocks.update(a["runs"].get("keep", {}))
    for run, f in clocks.items():
        r = {"clock_hz": f, "rule": "flow" if run == a["runs"]["flow"] else "kept"}
        r["cpu_feasible"] = freq["f_cpu_hz"] <= f
        try:
            rows = tt_rows(g, noc, entries, appname, f)
            r["link_schedule_feasible"] = True
            r["packets_between_pes"] = len(rows["rows"])
            r["premise_release"] = _premise(a, rows["rows"])
        except ValueError as e:
            r["link_schedule_feasible"] = False
            r["link_schedule_error"] = str(e)
        m = phase_model(g, noc, entries, f)
        r["period_cycles"] = m["period_cycles"]
        r["response_bound"] = m["response_bound"]
        r["tasks"] = m["tasks"]
        r["sequences"] = m["sequences"]
        n_last = m["response_bound"]["phase"]
        need = (a["warmup_s"] + (n_last + a["iterations"] - 1) * T + m["response_bound"]["cycles"] / f + T)
        r["sim_ns"] = a["sim_ns"]
        r["sim_ns_min"] = int(-(-need * 1e9 // 1))
        r["sim_fits"] = a["sim_ns"] >= r["sim_ns_min"]
        r["feasible"] = r["cpu_feasible"] and r["link_schedule_feasible"] and m["cpu_fits"]
        out["runs"][run] = r
    return out


def run_composition(name, a):
    from rttools.multiapp import compose
    spec = compose.read_spec(a["composition"])
    compose.set_costs(spec, {x["name"]: a["costs"] for x in spec["apps"]})
    with tnet.quiet():
        comp = compose.load(spec)
        freq = compose.minimum_frequency(comp["apps"], comp["noc"], search_config(a["f0_hz"]))
    c = wcosts.load(a["costs"])
    tasks = {}
    for x in comp["apps"]:
        with tnet.quiet():
            g0, _ = appparser.loadFromFile(x["csv"])
        csv_cost = {str(d.get("label", n)): int(float(d["wcet"])) for n, d in g0.nodes(data=True)}
        tasks.update(cost_rows(x["graph"], csv_cost, c, x["entries"]))
    fmin = freq["frequency_hz"]
    out = {"kind": "composition", "costs": {"tasks": tasks, "file": os.path.basename(a["costs"]),
                                            "sha256": exp23_sha(a["costs"])},
           "pes": pe_rows(tasks), "f_cpu_hz": freq["f_cpu_hz"], "f_noc_hz": freq["f_star_hz"], "minimum_hz": fmin,
           "binding": None if fmin is None else ("cpu" if fmin == freq["f_cpu_hz"] else "f_noc"), "runs": {}}
    T = a["period_s"]
    f = exp23.flow_clock(fmin, T)["f_clk_hz"]
    r = {"clock_hz": f, "rule": "flow", "cpu_feasible": freq["f_cpu_hz"] <= f, "apps": {}}
    from rttools.ucxgen import tt
    try:
        with tnet.quiet():
            rows = tt.union(comp, f)
        r["link_schedule_feasible"] = True
        r["packets_between_pes"] = len(rows["rows"])
        r["premise_release"] = _premise(a, rows["rows"])
    except ValueError as e:
        r["link_schedule_feasible"] = False
        r["link_schedule_error"] = str(e)
    need = 0
    fits = True
    for x in comp["apps"]:
        m = phase_model(x["graph"], comp["noc"], x["entries"], f)
        fits = fits and m["cpu_fits"]
        r["apps"][x["name"]] = {"period_cycles": m["period_cycles"], "response_bound": m["response_bound"],
                                "tasks": m["tasks"], "sequences": m["sequences"]}
        need = max(need, a["warmup_s"] + (m["response_bound"]["phase"] + a["iterations"] - 1) * T
                   + m["response_bound"]["cycles"] / f + T)
    r["period_cycles"] = exact(T * f)
    r["sim_ns"] = a["sim_ns"]
    r["sim_ns_min"] = int(-(-need * 1e9 // 1))
    r["sim_fits"] = a["sim_ns"] >= r["sim_ns_min"]
    r["feasible"] = r["cpu_feasible"] and r["link_schedule_feasible"] and fits
    out["runs"][a["runs"]["flow"]] = r
    return out


def run_multirate(name, a):
    from rttools.bench_t import multirate
    from rttools.paper import carfull
    g, appname, noc, entries, costs = load_app(a["csv"], a["map"], a["arch"], a["costs"])
    rates = multirate.graph_rates(g)
    spec = multirate.spec_from_graph(g, entries, rates, noc)
    with tnet.quiet():
        freq = search.minimum_frequency(g, noc, entries, appname, search_config(a["f0_hz"]))
    fmin = freq["frequency_hz"]
    phase_s = float(rates["phase_s"])
    out = {"kind": "multirate", "costs": costs, "pes": pe_rows(costs["tasks"]),
           "f_cpu_hz": freq["f_cpu_hz"], "f_noc_hz": freq["f_star_hz"], "minimum_hz": fmin,
           "binding": None if fmin is None else ("cpu" if fmin == freq["f_cpu_hz"] else "f_noc"), "runs": {}}
    f = exp23.flow_clock(fmin, phase_s)["f_clk_hz"]
    at, sched, ages = carfull.at_frequency(g, noc, entries, f, spec)
    cpu = freq["cpu"]
    flows = [(label, spec.node_of[u] != spec.node_of[v]) for label, u, v, _ in spec.flows]
    out["model"] = {
        "phase_ms": phase_s * 1e3, "hyperperiod_ms": float(rates["hyper_s"]) * 1e3,
        "phases_per_hyperperiod": rates["hyper_ticks"], "flows": len(flows),
        "flows_on_one_pe": sum(1 for _, noc_flow in flows if not noc_flow),
        "p_min_cycles": cpu["phase_cycles"], "f_cpu_hz": cpu["f_cpu_hz"],
        "utilization_bound_cycles": cpu["utilization_cycles"],
        "utilization_bound_hz": cpu["utilization_cycles"] / phase_s,
        "f_cpu_phase_hz": cpu["f_cpu_phase_hz"]}
    if fmin is not None:
        mn, _, _ = carfull.at_frequency(g, noc, entries, fmin, spec)
        if mn.get("data_age_max"):
            out["model"]["data_age_max_at_minimum"] = mn["data_age_max"]
    r = {"clock_hz": f, "rule": "flow", "cpu_feasible": bool(sched.feasible), "period_cycles": at["phase_cycles"],
         "hyper_cycles": at["hyper_cycles"], "periodic_from_hyperperiod": at["periodic_from_hyperperiod"]}
    try:
        rows = tt_rows(g, noc, entries, appname, f)
        r["link_schedule_feasible"] = True
        r["packets_between_pes"] = len(rows["rows"])
        r["premise_release"] = _premise(a, rows["rows"])
    except ValueError as e:
        r["link_schedule_feasible"] = False
        r["link_schedule_error"] = str(e)
    if sched.feasible:
        win = multirate.packet_windows(spec, sched)
        r["chains"] = len(at["data_age"])
        r["packets_per_hyperperiod"] = sum(len(win[label]) for label, noc_flow in flows if noc_flow)
        r["data_age"] = {x["chain"]: x["max_cycles"] for x in at["data_age"]}
        r["data_age_max"] = at["data_age_max"]
        need = a["warmup_s"] + at["data_age_max"]["cycles"] / f
        r["sim_ns_min"] = int(-(-need * 1e9 // 1))
    r["sim_ns"] = a["sim_ns"]
    r["sim_fits"] = sched.feasible and a["sim_ns"] >= r["sim_ns_min"]
    r["feasible"] = bool(sched.feasible) and r["link_schedule_feasible"]
    out["runs"][a["runs"]["flow"]] = r
    return out


def premise_release(rows, lead, terms):
    """Premise (ii) of the paper on a link schedule: the release handler of
    each phase runs on every PE, to its end, before the tick of that phase.

    The release request of the tick kP comes `lead` cycles before it. The
    CPU enters _isr (no nesting) when the activity with interrupts disabled
    in progress at the request ends, reads the cause word once, at most
    router.ISR_ENTRY_CYCLES later, and serves its causes in bit order, the
    release (bit 4) after the packet causes (bits 0 to 3). The network
    interface of a PE serves one packet at a time, so the activity is a
    kernel section (at most max(sections) cycles) or the handlers of one
    packet. A packet of the PE whose reservation starts by the request ends
    its size-flit handler and its last flit by s_i + o_i - NI_RX_END_CYCLES
    (the latest instant X_i); after X_i, the routine that reads the request
    can serve the end-of-reception handler of the packet first. The release
    handler therefore ends before kP when, for every such packet,
    X_i + entry + end-of-reception handler + release handler < kP (margin_min
    = kP - X_i above that sum), when no reservation starts within a kernel
    section plus the entry after a request (its size flit could be pending
    with the request), and when a kernel section, the injection handler or
    the end-of-reception handler in progress at the request, plus the entry
    and the release handler, fits in the lead. rttools.modules.routing.router.
    release_guard rejects the releases of AGS that break the first two
    conditions.

    `terms`: {"kernel": {...}, "sections": {...}} of the image
    (experiments/wcet/reference_tt.json, ni_images)."""
    from rttools.wcet import ucx
    k = terms["kernel"]
    entry = router.ISR_ENTRY_CYCLES
    rel = k["release"] + ucx.IRQ_DECISION
    end = k["receive_isr_end"] + ucx.IRQ_DECISION
    section = max(v for v in terms["sections"].values())
    need = entry + end + rel
    in_lead = max(section, k["send_isr"] + ucx.IRQ_DECISION, end) + entry + rel
    checked = violations = after = 0
    margin = None
    for r in rows:
        P = r["period"]
        kP = -(-(r["s"] + lead) // P) * P       # first tick whose request comes at or after s
        checked += 1
        m = kP - (r["s"] + r["occupancy"] - router.NI_RX_END_CYCLES)
        violations += m <= need
        margin = m if margin is None else min(margin, m)
        if r["s"] - (kP - P - lead) <= section + entry:
            after += 1
    return {"lead_cycles": lead, "entry_cycles": entry, "release_cycles": rel, "end_cycles": end,
            "section_max_cycles": section, "required_margin_cycles": need, "activity_in_lead_cycles": in_lead,
            "checks": checked, "violations": violations, "after_request": after, "margin_min_cycles": margin,
            "holds": in_lead < lead and violations == 0 and after == 0}


def _premise(a, rows):
    if "lead_cycles" not in a:
        return None
    with open(a["terms"]) as f:
        img = json.load(f)["ni_images"][a["terms_image"]]
    return premise_release(rows, a["lead_cycles"], img)


KINDS = {"single": run_single, "composition": run_composition, "multirate": run_multirate}
APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
                       "pkt-sim", "software", "ucx-os", "app")


def table_check(image, clock, costs):
    """The injection table app/<image>_tt.h has a table for `clock` and the
    line Costs of the costs file (name and sha256)."""
    with open(os.path.join(APP_DIR, image + "_tt.h")) as f:
        text = f.read()
    line = f"max(CSV, static) {os.path.basename(costs)} sha256 {exp23_sha(costs)}"
    return {"clock": f"F_CPU == {clock}\n" in text, "costs": f" * Costs: {line}\n" in text}


def run(cfg_path, out_dir):
    cfg = load_config(cfg_path)
    resource, w_ni = router.ni_model()
    m = {"_doc": "rttools.paper.ttflow run", "ni": "tt" if (resource, w_ni) == router.parse_ni("tt") else
         ("off" if not resource else w_ni), "w_ni_cycles": w_ni,
         "header_wait_cycles": router.header_wait(), "cost_rule": wcosts.MAX, "apps": {}}
    for name, a in cfg["apps"].items():
        m["apps"][name] = KINDS[a["kind"]](name, a)
        for r in m["apps"][name]["runs"].values():
            r["table"] = table_check(a["image"], r["clock_hz"], a["costs"])
            r["feasible"] = r["feasible"] and all(r["table"].values())
            if r.get("premise_release") is not None:
                r["feasible"] = r["feasible"] and r["premise_release"]["holds"]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1, default=str)
        f.write("\n")
    write_values(os.path.join(out_dir, "values.tex"), m)
    return m


def write_values(path, m):
    """LaTeX macros \\ExpTt<application>...: f_CPU, f_NoC, the minimum
    frequency and the clock, period and bound of each run, and the values
    of the general phase model of the time-triggered application
    (CAR-FULL)."""
    lines = ["% generated by python -m rttools.paper.ttflow run; do not edit"]

    def put(text, *name):
        lines.append(f"\\newcommand{{\\{exp23.macro_name('tt', *name)}}}{{{text}}}")

    put(str(m["w_ni_cycles"]), "w", "ni")
    for app, a in m["apps"].items():
        k = app.replace("-", "")
        for key in ("f_cpu_hz", "f_noc_hz", "minimum_hz"):
            put(mhz(a[key]), k, key.replace("_hz", "").replace("_", " "), "mhz")
        for run_id, r in a["runs"].items():
            put(f"{r['clock_hz'] / 1e6:g}", k, run_id, "mhz")
            put(f"{r['period_cycles']:,}", k, run_id, "phase", "cycles")
            rb = r.get("response_bound")
            if rb:
                put(f"{rb['cycles']:,}", k, run_id, "bound", "cycles")
            for n, x in (r.get("apps") or {}).items():
                put(f"{x['response_bound']['cycles']:,}", k, run_id, n, "bound", "cycles")
            if r.get("data_age_max"):
                put(f"{r['data_age_max']['cycles']:,}", k, run_id, "age", "max", "cycles")
                put(f"{r['data_age_max']['ms']:.3f}", k, run_id, "age", "max", "ms")
                put(r["data_age_max"]["chain"].replace("-", "$\\to$"), k, run_id, "age", "max", "chain")
                put(str(r["chains"]), k, run_id, "chains")
                put(str(r["packets_per_hyperperiod"]), k, run_id, "packets")
        md = a.get("model")
        if md:
            put(f"{md['phase_ms']:g}", k, "phase", "ms")
            put(f"{md['hyperperiod_ms']:g}", k, "hyperperiod", "ms")
            put(str(md["phases_per_hyperperiod"]), k, "phases")
            put(str(md["flows_on_one_pe"]), k, "local", "flows")
            put(f"{md['p_min_cycles']:,}", k, "p", "min", "cycles")
            put(mhz(md["utilization_bound_hz"]), k, "utilization", "bound", "mhz")
            put(mhz(md["f_cpu_phase_hz"]), k, "cpu", "phase", "mhz")
            if md.get("data_age_max_at_minimum"):
                put(f"{md['data_age_max_at_minimum']['ms']:.3f}", k, "age", "max", "minimum", "ms")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def summary_lines(m):
    out = []
    for name, a in m["apps"].items():
        above = {pe: p["static_above_csv"] for pe, p in sorted(a["pes"].items()) if p["static_above_csv"]}
        out.append(f"{name}: f_CPU {mhz(a['f_cpu_hz'])} MHz, f_NoC {mhz(a['f_noc_hz'])} MHz, minimum "
                   f"{mhz(a['minimum_hz'])} MHz ({a['binding']}); static above the CSV: "
                   + ("; ".join(f"PE {pe} {' '.join(ts)}" for pe, ts in above.items()) or "none"))
        for run_id, r in a["runs"].items():
            rb = r.get("response_bound") or (r.get("data_age_max") and {"cycles": r["data_age_max"]["cycles"]}) or (
                r.get("apps") and {"cycles": " / ".join(f"{n} {x['response_bound']['cycles']}"
                                                        for n, x in r["apps"].items())})
            out.append(f"  {run_id}: {mhz(r['clock_hz'])} MHz ({r['rule']}), P {r['period_cycles']} cycles, "
                       f"bound {rb['cycles'] if rb else '-'} cycles, SIM_NS {r['sim_ns']} (min {r.get('sim_ns_min')}), "
                       f"feasible {r['feasible']}")
    return out


def mhz(v):
    return "-" if v is None else f"{v / 1e6:.3f}"


# ------------------------------------------------------------ tables of the check

def write_tables(cfg_path, out_dir):
    """For each run, <out>/<run>.packets and <out>/<run>.jobs (text tables
    of run_r11g.sh, monitor labels X-Y of the node index):

    packets: "# P <cycles per phase> Ht <phases per hyperperiod> tagmod <0|1024>"
    and one line per packet k of a flow between PEs in a hyperperiod:
    "src dst key k N_e q0 s o_i m d" (key = tag for weird_a, flow id
    otherwise; q0 = phase of the sending job in the hyperperiod; s =
    instant from the tick of that phase; m = XY hops; d = deadline of the
    packet from the same tick: the tick of the phase of the job that reads
    it on the time-triggered platform).

    jobs: one line per task of one release period, "pe letter 0 q0 F"
    (job j in phase j - 1 + q0, ends at or before F cycles after the tick
    of that phase), or, for the general model, one line per job,
    "pe letter j q F" (job j released at phase q); for the general model a
    line "# READS" and one line per job j of a reader and input edge,
    "pe reader input j want n_v n_u j0" (want: number of the job of the
    input whose packet job j reads in the model, multirate.read_index, 0
    for none; the job reads that job or a newer one; for j beyond the
    lines, want(j) = want(j - h n_v) + h n_u with h = (j - j0) div n_v and
    want(j) = 0 when want(j - h n_v) = 0, with n_v and n_u the jobs of the
    reader and of the input per hyperperiod)."""
    from rttools.ucxgen import tt
    cfg = load_config(cfg_path)
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for name, a in cfg["apps"].items():
        for run_id, f, text_p, text_j in _tables(name, a, tt):
            for ext, text in (("packets", text_p), ("jobs", text_j)):
                p = os.path.join(out_dir, f"{run_id}.{ext}")
                with open(p, "w") as fo:
                    fo.write(text)
                written.append(p)
    return written


def _label(node, width):
    return f"{int(node) % width}-{int(node) // width}"


def _tables(name, a, tt):
    m = json.load(open(a["manifest"])) if "manifest" in a else None
    kind = a["kind"]
    if kind == "composition":
        from rttools.multiapp import compose
        spec = compose.read_spec(a["composition"])
        compose.set_costs(spec, {x["name"]: a["costs"] for x in spec["apps"]})
        with tnet.quiet():
            comp = compose.load(spec)
        width = comp["width"]
        f = exp23.flow_clock(compose.minimum_frequency(comp["apps"], comp["noc"], search_config(a["f0_hz"]))
                             ["frequency_hz"], a["period_s"])["f_clk_hz"]
        with tnet.quiet():
            rows = tt.union(comp, f)
        by = _by_flow(rows)
        P = rows["rows"][0]["period"]
        tp = [f"# P {P} Ht 1 tagmod {m['tag_mod']}"]
        tj = []
        for x in comp["apps"]:
            pm = phase_model(x["graph"], comp["noc"], x["entries"], f)
            for fl in m["flows"]:
                if fl["local"] or fl.get("app") != x["name"]:
                    continue
                r = by[compose.qualify(x["name"], "f" + str(fl["csv_id"]))][0]
                tp.append(f"{fl['src_label']} {fl['dst_label']} {fl['id']} 0 1 {pm['tasks'][fl['source']]['phase']} "
                          f"{r['offset']} {r['occupancy']} {exp23._hops(fl['src_label'], fl['dst_label'])} "
                          f"{r['deadline'] - r['phase_start']}")
            for t in m["tasks"]:
                if t.get("app") != x["name"]:
                    continue
                tm = pm["tasks"][t["name"]]
                tj.append(f"{t['pe_label']} {t['iter_letter']} 0 {tm['phase']} {tm['finish']}")
        yield a["runs"]["flow"], f, "\n".join(tp) + "\n", "\n".join(tj) + "\n"
        return
    g, appname, noc, entries, _ = load_app(a["csv"], a["map"], a["arch"], a["costs"])
    width = int(a["mesh"].split("x")[0])
    if kind == "multirate":
        from rttools.bench_t import multirate
        from rttools.paper import carfull
        rates = multirate.graph_rates(g)
        spec = multirate.spec_from_graph(g, entries, rates, noc)
        with tnet.quiet():
            fmin = search.minimum_frequency(g, noc, entries, appname, search_config(a["f0_hz"]))["frequency_hz"]
        f = exp23.flow_clock(fmin, float(rates["phase_s"]))["f_clk_hz"]
        _, sched, _ = carfull.at_frequency(g, noc, entries, f, spec)
        rows = tt_rows(g, noc, entries, appname, f)
        by = _by_flow(rows)
        P = rows["rows"][0]["period"]
        tp = [f"# P {P} Ht {m['hyper_ticks']} tagmod {m['tag_mod']}"]
        for fl in m["flows"]:
            if fl["local"]:
                continue
            rs = by["f" + str(fl["csv_id"])]
            for k, r in enumerate(rs):
                tp.append(f"{fl['src_label']} {fl['dst_label']} {fl['id']} {k} {len(rs)} {r['phase_start'] // P} "
                          f"{r['offset']} {r['occupancy']} {exp23._hops(fl['src_label'], fl['dst_label'])} "
                          f"{r['deadline'] - r['phase_start']}")
        tj = []
        phases = a["releases"]
        for t in m["tasks"]:
            v = t["name"]
            o, k = spec.offsets[v], spec.ticks[v]
            per_h = sched.per_h(v)
            j = 1
            while o + (j - 1) * k < phases:
                idx = j - 1
                lim = (sched.h0 + 1) * per_h
                if idx >= lim:
                    idx = sched.h0 * per_h + (idx - sched.h0 * per_h) % per_h
                rel_c, _, fin = sched.job(v, idx)
                tj.append(f"{t['pe_label']} {t['iter_letter']} {j} {o + (j - 1) * k} {fin - rel_c}")
                j += 1
        tj += read_lines(spec, sched, m)
        yield a["runs"]["flow"], f, "\n".join(tp) + "\n", "\n".join(tj) + "\n"
        return
    with tnet.quiet():
        fmin = search.minimum_frequency(g, noc, entries, appname, search_config(a["f0_hz"]))["frequency_hz"]
    clocks = {a["runs"]["flow"]: exp23.flow_clock(fmin, a["period_s"])["f_clk_hz"]}
    clocks.update(a["runs"].get("keep", {}))
    for run_id, f in clocks.items():
        rows = tt_rows(g, noc, entries, appname, f)
        by = _by_flow(rows)
        pm = phase_model(g, noc, entries, f)
        P = rows["rows"][0]["period"]
        if a.get("style") == "named":
            # weird_a: the tag of a flow is its payload (experiments/exp23/config.json); label of
            # the monitor x-y of the node index of the .map
            from rttools.ucxgen.model import read_csv
            _, csv_flows, _ = read_csv(a["csv"])
            node = {t: _label(e["node"], width) for e in entries for t in e["tasks"]}
            tags = {(x["source"], x["target"]): x["tag"] for x in json.load(open(a["exp23_config"]))["flows"]}
            tp = [f"# P {P} Ht 1 tagmod 0"]
            for fl in csv_flows:
                s, d = node[fl["source"]], node[fl["target"]]
                if s == d:
                    continue
                r = by["f" + str(fl["id"])][0]
                tp.append(f"{s} {d} {tags[(fl['source'], fl['target'])]} 0 1 "
                          f"{pm['tasks'][fl['source']]['phase']} {r['offset']} {r['occupancy']} {exp23._hops(s, d)} "
                          f"{r['deadline'] - r['phase_start']}")
            tj = [f"{node[t]} {t} 0 {tm['phase']} {tm['finish']}" for t, tm in sorted(pm["tasks"].items())]
        else:
            tp = [f"# P {P} Ht 1 tagmod {m['tag_mod']}"]
            for fl in m["flows"]:
                if fl["local"]:
                    continue
                r = by["f" + str(fl["csv_id"])][0]
                tp.append(f"{fl['src_label']} {fl['dst_label']} {fl['id']} 0 1 {pm['tasks'][fl['source']]['phase']} "
                          f"{r['offset']} {r['occupancy']} {exp23._hops(fl['src_label'], fl['dst_label'])} "
                          f"{r['deadline'] - r['phase_start']}")
            tj = [f"{t['pe_label']} {t['iter_letter']} 0 {pm['tasks'][t['name']]['phase']} "
                  f"{pm['tasks'][t['name']]['finish']}" for t in m["tasks"]]
        yield run_id, f, "\n".join(tp) + "\n", "\n".join(tj) + "\n"


def read_lines(spec, sched, man):
    """Lines "# READS" and "pe reader input j want n_v n_u j0" of the
    tables (write_tables) for the general model: the jobs j = 1 ..
    (h0 + 2) n_v of each reader of each input edge, j0 = (h0 + 1) n_v + 1."""
    from rttools.bench_t import multirate
    letter = {t["name"]: (t["pe_label"], t["iter_letter"]) for t in man["tasks"]}
    out = ["# READS"]
    for _, u, v, m in spec.flows:
        nv, nu = sched.per_h(v), sched.per_h(u)
        for c in range((sched.h0 + 2) * nv):
            i = multirate.read_index(spec, sched, u, v, m, c)
            out.append(f"{letter[v][0]} {letter[v][1]} {letter[u][1]} {c + 1} {0 if i is None else i + 1} "
                       f"{nv} {nu} {(sched.h0 + 1) * nv + 1}")
    return out


def _by_flow(rows):
    out = {}
    for r in rows["rows"]:
        out.setdefault(r["flow"], []).append(r)
    for v in out.values():
        v.sort(key=lambda r: r["k"])
    return out


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.ttflow", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for c in ("run", "tables"):
        a = sub.add_parser(c)
        a.add_argument("--config", required=True)
        a.add_argument("--out", required=True)
    args = p.parse_args(argv)
    if args.cmd == "run":
        m = run(args.config, args.out)
        for line in summary_lines(m):
            print(line)
    else:
        for path in write_tables(args.config, args.out):
            print("wrote " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
