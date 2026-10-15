"""Analysis of an RTL run of a time-triggered application of
rttools.ucxgen (several release periods or cycles: CAR-full,
experiments/car-full) against the general phase model
(rttools/bench_t/multirate.py).

    python -m rttools.paper.rtlapp analyze <log> --manifest <name>.json --csv <app.csv> --map <app.map>
        --out <dir> [--run-info <RUN_INFO>] [--f-clk <Hz>]
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

rttools.paper.rtlapp calls this module when the manifest has "model":
"time_triggered".

Model at the clock F_CLK of the run: phase P = phase_ns F_CLK / 1e9 cycles,
ORT/BENCH sequence of every PE over the hyperperiod (multirate.schedule),
job j of task v released at phase o_v + j k_v, reads of each job
(multirate.read_index), packet windows (multirate.packet_windows) and the
largest data age of every cause-effect chain (multirate.data_age).

Measurement (log of the run):

| Quantity | Definition |
|---|---|
| r_p | p-th `TRIGGER: workflow iteration` line (release interrupt of phase p, PE with the lowest index of the mask); the jobs of phase p start at the next tick of each PE |
| Job j of v (from 1) | ITER begin and ITER end markers of the letter of v with iteration j |
| Read of a job | the read markers after the begin marker of the job on its PE (iteration 0x800000 + i, letter of the source): job i of the source (0: no packet) |
| CPU per phase | non-IDLE time of each PE in [r_p, r_{p+1}) against the busy time of the PE in phase p of the model (periodic hyperperiod), above it by more than BUSY_TOLERANCE cycles |
| Job end against the model | end of job j minus r_p of its release phase, against F - r of the model job; a deadline miss is an end after r of the next release of the task |
| Begin after the release | begin marker of a job minus r_p of its release phase: the smallest value bounds the delay from the release interrupt to the tick plus the dispatch |
| Jobs per phase | begin markers of each task in each interval [r_p, r_{p+1}); more than one is a job that waited past its next release |
| Progress | a task stalls when it ends fewer jobs than it has releases up to two of its periods before the end of the log |
| Data age of a chain v_0 ... v_n | for each job of v_n, the reads backwards along the chain give the job of v_0; age = end of the job of v_n minus r_p of the release phase of that job of v_0, against the bound of the chain (largest model value) |
| Read against the model | the job of the source that a job read, against the job of the model (multirate.read_index): older reads break the assumption of the bound |
| Packet against its deadline | arrival (TAG receive line on the target PE) minus r_0, against the deadline of the model packet (S of the reading job) from the tick of phase 0 |
| Phase conformance | executions (begin markers) of each task per phase [r_p, r_{p+1}): at most one, none before the release phase o_v + (j - 1) k_v of the job; CPU of each PE per phase against the busy time of the model in that phase (rttools/paper/phasecheck.py) |
| Time-triggered injection (RUN_INFO injection=tt, with --arch) | FLIT lines paired by source, destination and tag; the n-th packet of a flow (n from 0) is packet n mod N_e of hyperperiod n div N_e of the link schedule of the table of the image (N_e packets of flow e per hyperperiod), sent by the job of phase H_t (n div N_e) + phase_start / P; rttools/paper/ttcheck.py (metrics.json "tt", tt_packets.csv) |

Times measured from r_p include the delay from the release interrupt to
the tick of the PE, so they are not smaller than the times of the model
from the tick.
"""
from __future__ import annotations

import json
import os
from fractions import Fraction

from rttools.bench_t import multirate
from rttools.modules.io import appparser
from rttools.modules.mapping import mapfile
from rttools.paper import exp23
from rttools.tui.model import metrics as tmetrics
from rttools.tui.model import network as tnet

exact = exp23.exact
READ_BIT = 0x800000
# busy time of a phase from the `scheduled` lines: each edge of a slice is
# a time in ns rounded to the clock, at most one cycle per edge of the phase
BUSY_TOLERANCE = 2


def load_app(manifest_path, csv_path, map_path):
    with open(manifest_path) as f:
        man = json.load(f)
    if man.get("model") != "time_triggered":
        raise ValueError("the manifest is not a time-triggered application")
    with tnet.quiet():
        g, _ = appparser.loadFromFile(csv_path)
    entries = mapfile.read(map_path)
    r = multirate.graph_rates(g)
    if r is None:
        raise ValueError("the application has one period and no cycle")
    spec = multirate.spec_from_graph(g, entries, r)
    if int(r["phase_s"] * 10 ** 9) != man["phase_ns"]:
        raise ValueError(f"phase of the CSV {r['phase_s']} s differs from the manifest ({man['phase_ns']} ns)")
    for t in man["tasks"]:
        if str(spec.node_of[t["name"]]) != str(t["pe"]):
            raise ValueError(f"task {t['name']}: PE {t['pe']} of the manifest, {spec.node_of[t['name']]} of the .map")
    order = {exp_label(n, man["mesh"][0]): ts for n, ts in spec.orders.items()}
    if order != man["pe_dispatch"]:
        raise ValueError("creation order of the manifest differs from the model")
    return {"manifest": man, "graph": g, "entries": entries, "rates": r, "spec": spec,
            "inputs": {"csv": os.path.basename(csv_path), "map": os.path.basename(map_path),
                       "manifest": os.path.basename(manifest_path),
                       "csv_matches_manifest": multirate_sha(csv_path) == man["inputs"]["csv"]["sha256"],
                       "map_matches_manifest": multirate_sha(map_path) == man["inputs"]["map"]["sha256"]}}


def multirate_sha(path):
    from rttools.paper.rtlapp import sha256
    return sha256(path)


def exp_label(node, width):
    n = int(node)
    return f"{n % width}-{n // width}"


def model(app, f_clk):
    spec = app["spec"]
    P = Fraction(app["manifest"]["phase_ns"]) * f_clk / 10 ** 9
    if P.denominator != 1:
        raise ValueError(f"phase of {app['manifest']['phase_ns']} ns at {f_clk} Hz is not a whole number of cycles")
    sched = multirate.schedule(spec, int(P))
    out = {"clock_hz": f_clk, "phase_cycles": int(P), "hyper_ticks": spec.hyper_ticks,
           "hyper_cycles": sched.H, "cpu_feasible": sched.feasible, "periodic_from_hyperperiod": sched.h0,
           "misses": len(sched.misses)}
    if sched.feasible:
        ages = multirate.data_age(spec, sched)
        out["chains"] = {"-".join(a["chain"]): a["max_cycles"] for a in ages}
        busy = sched.busy_per_phase()
        out["busy_per_phase"] = {exp_label(n, app["manifest"]["mesh"][0]): b for n, b in busy.items()}
    return out, sched


def parse_marks(tr, app):
    """{(task, job): {"begin", "end", "reads": {source task: job}, "pe"}}
    from the ITER lines; read markers follow the begin marker of their job
    on the same PE."""
    man = app["manifest"]
    letter = {(t["pe_label"], t["iter_letter"]): t["name"] for t in man["tasks"]}
    by_letter = {t["iter_letter"]: t["name"] for t in man["tasks"]}
    jobs = {}
    last_begin = {}
    stray = 0
    for m in tr.meta.get("iterations") or []:
        k = m["iteration"]
        if m["edge"] == "begin" and k >= READ_BIT:
            cur = last_begin.get(m["lane"])
            src = by_letter.get(m["task"])
            if cur is None or src is None:
                stray += 1
                continue
            jobs[cur]["reads"][src] = k - READ_BIT
            continue
        name = letter.get((m["lane"], m["task"]))
        if name is None:
            stray += 1
            continue
        key = (name, k)
        row = jobs.setdefault(key, {"begin": None, "end": None, "reads": {}, "pe": m["lane"]})
        row[m["edge"]] = m["time"]
        if m["edge"] == "begin":
            last_begin[m["lane"]] = key
    return jobs, stray


def tt_check(log_path, app, clk, rel, csv_path, map_path, arch, f_clk):
    """Packets between PEs of a run with the time-triggered injection
    against the link schedule of the table of its image (module
    docstring)."""
    from rttools.modules.routing import router
    from rttools.paper import ttcheck
    man = app["manifest"]
    mod = man["tag_mod"]
    flows = {fl["id"]: fl for fl in man["flows"]}
    with open(log_path, errors="replace") as f:
        tx, rx = exp23.parse_flit_lines(f)
    q = {}
    for t in sorted(tx, key=lambda d: d["head"]):
        q.setdefault((t["src"], t["dst"], t["tag"]), []).append(t)
    pk = []
    for r in sorted(rx, key=lambda d: d["last"]):
        lst = q.get((r["src"], r["dst"], r["tag"]))
        if not lst:
            continue
        t = lst.pop(0)
        fl = flows.get(t["tag"] // mod)
        if fl is None or fl["local"]:
            continue
        pk.append({"flow": fl["id"], "flow_label": f"f{fl['csv_id']}", "src": t["src"], "dst": t["dst"],
                   "tag": t["tag"], "size": t["size"], "hops": exp23._hops(t["src"], t["dst"]),
                   "tx_head": t["head"], "tx_last": t["last"], "rx_head": r["head"], "rx_last": r["last"]})
    count = {}
    for p in sorted(pk, key=lambda p: p["tx_head"]):
        p["n"] = count.get(p["flow"], 0)
        count[p["flow"]] = p["n"] + 1
    table = ttcheck.schedule_rows(csv_path, map_path, arch, f_clk)
    Ht = man["hyper_ticks"]

    def phase_of(p, row, h):
        return h * Ht + row["phase_start"] // row["period"]
    return ttcheck.analyze_run(log_path, clk, rel, table, pk, phase_of, w_h=router.header_wait())


def analyze(log_path, manifest_path, csv_path, map_path, out_dir, run_info="auto", f_clk=None, arch=None):
    app = load_app(manifest_path, csv_path, map_path)
    man, spec = app["manifest"], app["spec"]
    cfg = {"pe_tasks": man["pe_tasks"], "release_period_s": man["phase_ns"] / 1e9, "clock_hz": f_clk}
    path = exp23.run_info_path(log_path) if run_info == "auto" else run_info
    if path is None and f_clk is None:
        raise ValueError("no RUN_INFO next to the log; give --f-clk")
    tr, _, clk, clock = exp23.load_run(log_path, cfg, None, path)
    from rttools.paper import ttcheck
    injection = ttcheck.injection_rule(exp23.read_run_info(path) if path else {})
    mdl, sched = model(app, clock["clock_hz"])
    if not sched.feasible:
        raise ValueError("the CPU schedule of the model misses a deadline at the clock of the run")
    rel = sorted(m.time for m in tr.lane_marks("TRIGGER"))
    if not rel:
        raise ValueError("no TRIGGER lines (releases) in the log")

    def cyc(raw):
        return exact(clk.cycles(raw))

    def r_of(p):
        if p < len(rel):
            return rel[p]
        return None

    jobs, stray = parse_marks(tr, app)
    ticks = spec.ticks

    # ---------------------------------------------------------- jobs
    late = misses = complete = 0
    over = []
    begin_off = []
    for (v, j), row in jobs.items():
        if row["begin"] is None or row["end"] is None:
            continue
        p = spec.offsets[v] + (j - 1) * ticks[v]
        if r_of(p) is None:
            continue
        complete += 1
        begin_off.append(cyc(row["begin"] - r_of(p)))
        rel_m, _, fin_m = sched.job(v, j - 1)
        end = cyc(row["end"] - r_of(p))
        over.append(end - (fin_m - rel_m))
        late += end > fin_m - rel_m
        nxt = r_of(p + ticks[v])
        if nxt is not None and row["end"] > nxt:
            misses += 1

    # ---------------------------------------------------------- jobs per phase and progress
    # a task begins at most one job per phase (one release per k_v
    # phases; a second begin in a phase is a job that waited for the CPU
    # past its next release); a task whose jobs stop before the end of the
    # log while releases go on does not progress
    twice = []
    progress = {}
    n_rel = len(rel)
    for v in spec.tasks:
        begins = sorted(row["begin"] for (t, _), row in jobs.items() if t == v and row["begin"] is not None)
        per_phase = {}
        for b in begins:
            p = max(i for i in range(n_rel) if rel[i] <= b) if b >= rel[0] else -1
            per_phase[p] = per_phase.get(p, 0) + 1
        twice += [{"task": v, "phase": p, "jobs": c} for p, c in sorted(per_phase.items()) if c > 1]
        ends = [row["end"] for (t, _), row in jobs.items() if t == v and row["end"] is not None]
        released = (n_rel - 1 - spec.offsets[v]) // ticks[v] + 1 if n_rel > spec.offsets[v] else 0
        # jobs released at least two periods of the task before the end of the log
        due = max(0, released - 2)
        progress[v] = {"pe": exp_label(spec.node_of[v], man["mesh"][0]), "released": released,
                       "begun": len(begins), "ended": len(ends),
                       "last_end_ms": clk.ms(max(ends)) if ends else None,
                       "stalled": len(ends) < due}
    stalled = sorted(v for v, d in progress.items() if d["stalled"])
    stalled_pes = sorted({progress[v]["pe"] for v in stalled})

    # ---------------------------------------------------------- reads
    m_of = {(u, v): m for _, u, v, m in spec.flows}
    older = newer = equal = 0
    for (v, j), row in jobs.items():
        if row["begin"] is None:
            continue
        for u, i in row["reads"].items():
            if (u, v) not in m_of:
                continue
            want = multirate.read_index(spec, sched, u, v, m_of[(u, v)], j - 1)
            got = i - 1 if i > 0 else None
            if want is None and got is None:
                equal += 1
            elif got is None or (want is not None and got < want):
                older += 1
            elif want is None or got > want:
                newer += 1
            else:
                equal += 1

    # ---------------------------------------------------------- CPU per phase
    Ht = spec.hyper_ticks
    first = sched.h0 * Ht
    pes = {}
    for pe, row in mdl["busy_per_phase"].items():
        meas = []
        above = 0
        for p in range(first, len(rel) - 1):
            b = cyc(tmetrics.lane_stats(tr, pe, rel[p], rel[p + 1]).busy)
            m = row[p % Ht]
            meas.append(b)
            above += b > m + BUSY_TOLERANCE
        pes[pe] = {"tasks": man["pe_dispatch"][pe], "model_busy_max": max(row), "model_busy_hyperperiod": sum(row),
                   "measured_busy_max": max(meas) if meas else None, "phases": len(meas),
                   "phases_above_model": above}

    # ---------------------------------------------------------- data age
    rows = []
    above_total = 0
    margins = []
    for ch in multirate.chains(spec.tasks, spec.edges()):
        name = "-".join(ch)
        bound = mdl["chains"][name]
        vals = []
        for (v, j), row in jobs.items():
            if v != ch[-1] or row["end"] is None:
                continue
            jj, ok = j, True
            for a, b in zip(reversed(ch[:-1]), reversed(ch[1:])):
                r = jobs.get((b, jj))
                if r is None or r["reads"].get(a, 0) == 0:
                    ok = False
                    break
                jj = r["reads"][a]
            if not ok:
                continue
            p0 = spec.offsets[ch[0]] + (jj - 1) * ticks[ch[0]]
            if r_of(p0) is None:
                continue
            vals.append(cyc(row["end"] - r_of(p0)))
        mx = max(vals) if vals else None
        above = sum(1 for x in vals if x > bound)
        above_total += above
        if mx is not None:
            margins.append(bound - mx)
        rows.append({"chain": name, "bound_cycles": bound, "measured_max_cycles": mx, "jobs": len(vals),
                     "above_bound": above, "margin_cycles": None if mx is None else bound - mx})

    # ---------------------------------------------------------- packets
    from rttools.paper.rtlapp import tag_events
    flows = {fl["id"]: fl for fl in man["flows"]}
    ev, tagc = tag_events(tr, {"manifest": man, "flows": flows})
    pk_late = pk_n = 0
    slack = []
    by_label = {f"f{fl['id']}": fl for fl in man["flows"]}
    for label, u, v, m in spec.flows:
        fl = by_label[label]
        if fl["local"]:
            continue
        for k, t_arr in ev[fl["id"]]["recv"].items():
            j = k - 1
            F = sched.job(u, j)[2]
            c = multirate.reader_index(spec, sched, u, v, F)
            dl = sched.job(v, c)[1]
            arr = cyc(t_arr - rel[0])
            pk_n += 1
            pk_late += arr > dl
            slack.append(dl - arr)

    m = {
        "log": os.path.basename(log_path),
        "inputs": app["inputs"],
        "clock": clock,
        "model": {k: v for k, v in mdl.items() if k != "busy_per_phase"},
        "releases": {"count": len(rel), "first_ms": clk.ms(rel[0]),
                     "period_cycles_min": exact(min(clk.cycles(b - a) for a, b in zip(rel, rel[1:])))
                     if len(rel) > 1 else None,
                     "period_cycles_max": exact(max(clk.cycles(b - a) for a, b in zip(rel, rel[1:])))
                     if len(rel) > 1 else None},
        "markers": {"jobs": len(jobs), "stray": stray},
        "jobs": {"complete": complete, "end_after_model_finish": late, "deadline_misses": misses,
                 "end_minus_model_max_cycles": max(over) if over else None,
                 # begin marker of a job after the release interrupt of its phase: the delay to
                 # the tick of the PE plus the dispatch (the model counts from the tick)
                 "begin_after_release_min_cycles": min(begin_off) if begin_off else None,
                 "begin_after_release_max_cycles": max(begin_off) if begin_off else None},
        "phases": {"jobs_begun_twice_in_a_phase": len(twice), "rows": twice},
        "progress": {"stalled_tasks": stalled, "stalled_pes": stalled_pes, "tasks": progress},
        "reads": {"older_than_model": older, "newer_than_model": newer, "equal_to_model": equal},
        "cpu_phases": {"first_phase": first, "pes": pes,
                       "phases_above_model": sum(p["phases_above_model"] for p in pes.values())},
        "data_age": {"chains": len(rows), "measured_chains": sum(1 for r in rows if r["jobs"]),
                     "above_bound": above_total, "margin_min_cycles": min(margins) if margins else None,
                     "rows": rows},
        "packets": {"remote_received": pk_n, "after_deadline": pk_late,
                    "min_slack_cycles": min(slack) if slack else None, "tags": tagc},
        "monitor": exp23.monitor_summary(log_path),
        "phase_conformance": phase_conformance(tr, clk, rel, jobs, man, spec, mdl, sched),
        "injection": injection,
        "tt": tt_check(log_path, app, clk, rel, csv_path, map_path, arch, clock["clock_hz"])
        if injection == "tt" and arch else None,
    }
    tt_packets = m["tt"].pop("per_packet") if m["tt"] else []
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1, default=str)
    import csv
    if tt_packets:
        with open(os.path.join(out_dir, "tt_packets.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(list(tt_packets[0]))
            for r in tt_packets:
                w.writerow(list(r.values()))
    with open(os.path.join(out_dir, "chains.csv"), "w", newline="") as f:
        w = csv.writer(f)
        cols = ["chain", "bound_cycles", "measured_max_cycles", "jobs", "above_bound", "margin_cycles"]
        w.writerow(cols)
        for r in rows:
            w.writerow([r[c] for c in cols])
    with open(os.path.join(out_dir, "cpu.csv"), "w", newline="") as f:
        w = csv.writer(f)
        cols = ["pe", "tasks", "model_busy_max", "measured_busy_max", "phases", "phases_above_model"]
        w.writerow(cols)
        for pe, p in pes.items():
            w.writerow([pe, " ".join(p["tasks"])] + [p[c] for c in cols[2:]])
    return m


def phase_conformance(tr, clk, rel, jobs, man, spec, mdl, sched):
    """Executions per phase of each task and CPU per phase of each PE
    against the busy time of the model in that phase of the hyperperiod
    (from phase h0 H_t, where the schedule is periodic); the jobs of a
    time-triggered application are released by the tick hook (rule
    "tick")."""
    from rttools.paper import phasecheck
    begins = {}
    for (v, j), row in jobs.items():
        begins.setdefault(v, {})[j] = row["begin"]
    Ht = spec.hyper_ticks
    first = sched.h0 * Ht
    busy = mdl["busy_per_phase"]
    return phasecheck.conformance(
        tr, clk, rel, begins, lambda v, j: spec.offsets[v] + (j - 1) * spec.ticks[v],
        {t["name"]: t["pe_label"] for t in man["tasks"]},
        lambda pe, p: busy[pe][p % Ht] if p >= first else None, "tick")


def summary_lines(m):
    mdl = m["model"]
    d = m["data_age"]
    out = [f"{m['log']}: F_CLK {exp23.mhz_text(m['clock']['clock_hz'])} MHz from {m['clock']['source']}, "
           f"P {mdl['phase_cycles']:,} cycles, {m['releases']['count']} releases, {m['markers']['jobs']} jobs",
           f"  jobs: {m['jobs']['complete']} complete, {m['jobs']['end_after_model_finish']} after the model finish, "
           f"{m['jobs']['deadline_misses']} deadline misses",
           f"  progress: {len(m['progress']['stalled_tasks'])} tasks stop before the end of the log "
           f"(PEs {', '.join(m['progress']['stalled_pes']) or '-'}); "
           f"{m['phases']['jobs_begun_twice_in_a_phase']} task phases with two job begins",
           f"  reads: {m['reads']['older_than_model']} older than the model, {m['reads']['newer_than_model']} newer",
           f"  CPU: {m['cpu_phases']['phases_above_model']} phases above the model busy time",
           f"  data age: {d['measured_chains']} of {d['chains']} chains measured, {d['above_bound']} above the bound, "
           f"smallest margin {d['margin_min_cycles']} cycles",
           f"  packets: {m['packets']['remote_received']} received between PEs, "
           f"{m['packets']['after_deadline']} after the deadline"]
    pc = m.get("phase_conformance")
    if pc is not None:
        from rttools.paper import phasecheck
        out.append("  phase conformance: " + phasecheck.summary(pc)[0][2:])
    if m.get("injection") == "tt":
        from rttools.paper import ttcheck
        out += ["  " + x.lstrip() for x in ttcheck.summary_lines(m.get("tt"))]
    return out
