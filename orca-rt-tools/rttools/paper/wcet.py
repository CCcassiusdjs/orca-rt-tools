"""Static task costs t(v) (rttools.wcet) against the stored RTL runs.

    python -m rttools.paper.wcet analyze --config experiments/wcet/config.json --out <dir>
    python -m rttools.paper.wcet run-log <log> --spec <spec.json> --image <image.elf> --manifest ... --csv ...
        --map ... --out <dir>
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

`analyze` runs the static analysis on each image of the config and
compares it with the measured cycles:

| Part | Image | Measured | Comparison |
|---|---|---|---|
| bodies | pkt-sim/tests/rtl/wcet_bodies.elf (sort, search, count of rttools.ucxgen --bodies) | GHDL trace of tb_cpu_trace.vhd (logs/bodies.trace.txt): cycles between the markers of each call | WCET of the wrapper m_<body> (markers, call, return) >= every measured call; margin over the largest call |
| E | experiments/exp23/logs/H.image.lst (image of run H, riscv64-elf-gcc 12.2.0) | run H (logs/H.events.txt, 434.912 MHz): CPU time per iteration of each cluster in each hyperperiod (exp23, Tab. 8.3); per task, the runs (dispatch to the next dispatch on its PE) that serve one iteration | t(V_k) = sum of t(v) >= the CPU time per iteration of every hyperperiod; job + dispatch of v >= the longest one-iteration run of v |
| CAR-V | images/car_v.elf (car_v.c of this tree, built in the container: riscv64-unknown-elf-gcc 13.2.0, F_CLK 380 MHz) | run CV2 (experiments/car-v-rtl/logs/CV2.events.txt, gcc 12.2.0): CPU time per iteration of each PE, mean over the windows of rtlapp (cpu_windows) and attributed to the runs of its tasks (cpu_attributed); per task, the runs that serve one iteration | t(V_k) >= both; job + dispatch of v >= the longest one-iteration run of v |
| WCET-E | images/wcet_e.elf (wcet_e.c, application E with input-dependent bodies) | none until its RTL run (`make -C experiments/wcet sim`, then run-log) | t(v) of the CSV of apps/wcet-e equals the static costs of the image |

The busiest phase of a PE (phase_busy_max) is informative: a run that
serves two iterations in one phase (C, E, H, I and J in run H) puts the
CPU time of two iterations in one phase and none in the next, which the
phase model of the flow does not describe.

The flow runs with the static costs of E (frequency pipeline with
--costs): f_CPU, f* and the minimum frequency, against the measured costs
of the CSV.

Images with the time-triggered injection (pkt-sim/software/ucx-os/lib/
noc_tt.c; config_tt.json, images/tt and images/tt13):

| Part | Comparison |
|---|---|
| app with `csv` and `map` | t(V_k) = sum of the static t(v) of the tasks of each PE (map) <= the sum of the costs of the CSV, the t(V_k) of the model (pe_bound) |
| ni_images | terms of the network interface of each image (rttools.wcet.ucx.ni_terms: inject, rx_size, rx_end) <= router.NI_INJECT_CYCLES, NI_RX_SIZE_CYCLES and NI_RX_END_CYCLES, whose sum is NI_WAIT_CYCLES, the w_NI of the occupancy o_i of the model (ni_within_bound) |

Outputs in <dir>: metrics.json, values.tex (\\ExpWcet... macros),
<app>/costs.json and <app>/costs.csv (rttools.wcet), tasks.csv,
clusters.csv, bodies.csv, frequency/ (rttools.paper.frequency with the
static costs).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

from rttools.paper import exp23, rtlapp
from rttools.tui.model import metrics as tmetrics
from rttools.wcet import __main__ as wcli
from rttools.wcet import analysis as wan
from rttools.wcet import image as wimg

NOT_JOB = ("send_isr", "receive_isr", "tick", "release")


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(path))

    def rel(v):
        if isinstance(v, str) and not os.path.isabs(v) and ("/" in v or v.endswith((".json", ".txt", ".elf", ".lst", ".csv", ".map", ".gml"))):
            return os.path.normpath(os.path.join(base, v))
        return v

    def walk(d):
        if isinstance(d, dict):
            return {k: (walk(v) if not k.startswith("_") else v) for k, v in d.items()}
        if isinstance(d, list):
            return [walk(v) for v in d]
        return rel(d)
    return walk(cfg)


def pct(static, measured):
    return None if not measured else 100.0 * (static - measured) / measured


def run_cycles(r):
    """Static cycles of one run of a task on the CPU: from its resume to
    the next dispatch (job and the dispatch term), without the interrupt
    handlers that the terms charge per edge, per phase or per release."""
    return r["t"] - sum(r["terms"][k] for k in NOT_JOB)


# ------------------------------------------------------------ measured

def task_runs(tr, clk, lane, task, begins, t0, t1):
    """Runs of `task` on `lane` (slices from a dispatch to the next one)
    inside [t0, t1): cycles of each run and the ITER begin markers in it.
    Returns {"single_max", "single_min", "single_runs", "per_iteration",
    "single": [[cycles, receptions], ...]}; receptions = `<- TAG` events of
    the PE inside the run (packets of any task of the PE: the handlers
    irq2 and irq3 run inside the slice of the task on the CPU)."""
    runs = exp23.closed_runs(tr, lane, task)
    recv = sorted(m.time for m in tr.lane_marks(lane) if m.kind == "recv")
    single = []
    busy = 0.0
    n = 0
    for a, b in runs:
        if a < t0 or b > t1:
            continue
        k = sum(1 for x in begins if a <= x <= b)
        cyc = clk.cycles(b - a)
        if k:
            busy += cyc
            n += k
        if k == 1:
            single.append([exp23.exact(cyc), sum(1 for x in recv if a <= x <= b)])
    cycles = [c for c, _ in single]
    return {"single_max": max(cycles) if single else None,
            "single_min": min(cycles) if single else None,
            "single_runs": len(single),
            "per_iteration": exp23.exact(busy / n) if n else None,
            "single": single}


def phase_busy_max(tr, clk, lane, starts, period_raw):
    vals = [clk.cycles(tmetrics.lane_stats(tr, lane, a, a + period_raw).busy) for a in starts]
    return exp23.exact(max(vals)) if vals else None


def measured_e(log, exp23_config):
    """Run H of application E: per cluster (exp23 Tab. 8.3 mean per
    iteration over the hyperperiods, and the busiest phase) and per task."""
    cfg0 = exp23.load_config(exp23_config)
    tr, cfg, clk, clock = exp23.load_run(log, cfg0)
    windows = exp23.hyperperiods(tr, cfg, clk)
    cpu = exp23.cpu_per_iteration(tr, cfg, clk, windows)
    marks = exp23.iteration_marks(tr)
    t0, t1 = windows[0][0], windows[-1][1]
    period = clk.raw(cfg["release_period_s"])
    starts = []
    t = t0
    while t + period <= t1 + 1e-9:
        starts.append(t)
        t += period
    clusters = {}
    for pe, cl in cfg["clusters"].items():
        clusters[cl] = {"pe": pe, "measured": cpu[cl]["mean"], "window_max": max(cpu[cl]["per_hyperperiod"]),
                        "phase_busy_max": phase_busy_max(tr, clk, pe, starts, period)}
    tasks = {}
    for pe, ts in cfg["pe_tasks"].items():
        for task in ts:
            if task == "IDLE":
                continue
            begins = [m["begin"] for m in marks.get(task, {}).values() if m["begin"] is not None]
            tasks[task] = dict(task_runs(tr, clk, pe, task, begins, t0, t1), pe=pe)
    return {"clock_hz": clock["clock_hz"], "windows": len(windows), "clusters": clusters, "tasks": tasks,
            "cluster_of": {t: cfg["clusters"][pe] for pe, ts in cfg["pe_tasks"].items() for t in ts if t != "IDLE"},
            "estimated": {r["cluster"]: r["estimated"] for r in exp23.tab83(cpu, exp23.estimates(cfg), cfg)[0]}}


def measured_app(log, manifest, csv_path, map_path):
    """Run of a generated application (rtlapp): per PE (cpu_windows mean
    per iteration and busiest phase) and per task."""
    app = rtlapp.load_app(manifest, csv_path, map_path)
    tr, clk, clock = rtlapp.load_log(log, app)
    mdl = rtlapp.model(app, clock["clock_hz"])
    releases = sorted(m.time for m in tr.lane_marks("TRIGGER"))
    win = rtlapp.cpu_windows(tr, app, mdl, clk, releases)
    marks = rtlapp.iteration_marks(tr, app)
    ev, _ = rtlapp.tag_events(tr, app)
    att = rtlapp.cpu_attributed(mdl, rtlapp.task_iterations(tr, app, mdl, clk, releases, ev, marks))
    if win["windows"]:
        t0 = clk.raw(win["windows"][0]["start_ms"] / 1e3)
        t1 = clk.raw(win["windows"][-1]["end_ms"] / 1e3)
    else:
        t0, t1 = tr.t0, tr.t1
    pes = {pe: {"measured": d["mean"], "window_max": max(d["per_window"]) if d["per_window"] else None,
                "attributed": (att.get(pe) or {}).get("measured"),
                "phase_busy_max": d["phase_busy_max"], "estimated": d["estimated"],
                "tasks": d["tasks"]} for pe, d in win["pes"].items()}
    tasks = {}
    for t in app["manifest"]["tasks"]:
        begins = [m["begin"] for m in marks.get(t["name"], {}).values() if m["begin"] is not None]
        tasks[t["name"]] = dict(task_runs(tr, clk, t["pe_label"], t["name"], begins, t0, t1), pe=t["pe_label"])
    return {"clock_hz": clock["clock_hz"], "windows": len(win["windows"]), "pes": pes, "tasks": tasks}


def bodies(elf, trace):
    """WCET of the bodies against the GHDL trace of wcet_bodies.c."""
    img = wimg.load(elf)
    an = wan.Analyzer(img)
    marks = []
    with open(trace) as f:
        for line in f:
            p = line.split()
            if p and p[0] == "MARK":
                marks.append((int(p[1]), int(p[2])))
    if not marks:
        raise ValueError(f"{trace}: no MARK lines")
    names = {1: "sort", 3: "search", 5: "count"}
    got = {n: [] for n in names.values()}
    for (c0, m0), (c1, m1) in zip(marks, marks[1:]):
        if m0 in names and m1 == m0 + 1:
            got[names[m0]].append(c1 - c0)
    out = {}
    for b, vals in got.items():
        w = an.function("m_" + b).cycles
        body = an.function("body_" + b).cycles
        out[b] = {"calls": len(vals), "measured_max": max(vals), "measured_min": min(vals),
                  "wcet_wrapper": w, "wcet_body": body, "margin_percent": pct(w, max(vals)),
                  "sound": all(v <= w for v in vals)}
    return out


# ------------------------------------------------------------ analysis

def costs_file(res):
    """Costs file (rttools/wcet/costs.py) of a static analysis: t(v) of
    every task and scheduler_cycles, with the image."""
    return {"_doc": "static t(v) (rttools.wcet) of the image; the analysis flow takes max(t(v) of the CSV, this t(v)) "
                    "(rttools/wcet/costs.py, rule max)",
            "image": res["image"], "scheduler_cycles": res["scheduler_cycles"],
            "tasks": {t: {"t": r["t"]} for t, r in res["tasks"].items()}}


def static(spec_path, out_dir, image=None):
    spec = wcli.load_spec(spec_path)
    res = wcli.run_spec(spec, image)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "costs_file.json"), "w") as f:
        json.dump(costs_file(res), f, indent=1)
        f.write("\n")
    with open(os.path.join(out_dir, "costs.json"), "w") as f:
        json.dump(res, f, indent=1)
        f.write("\n")
    from rttools.wcet import ucx
    ucx.write_csv(os.path.join(out_dir, "costs.csv"), res)
    return res


def task_row(r, m, receive_isr=None):
    """Static run of a task against its longest one-iteration run; for a
    task whose runs all serve two iterations (C, E, H, I and J in run H),
    against its CPU time per iteration. With receive_isr (kernel term of
    one received packet), also each one-iteration run against the static
    run plus receive_isr per packet received inside the run: the handlers
    of a packet run in the slice of whichever task holds the CPU, and t(v)
    charges them to the receiving task (receive term)."""
    run = run_cycles(r)
    ref = m.get("single_max") if m.get("single_max") is not None else m.get("per_iteration")
    row = {"t_static": r["t"], "run_static": run, "terms": r["terms"],
           "measured_run_max": m.get("single_max"), "measured_run_min": m.get("single_min"),
           "measured_per_iteration": m.get("per_iteration"), "single_runs": m.get("single_runs"),
           "run_margin_percent": pct(run, m.get("single_max")),
           "per_iteration_margin_percent": pct(run, m.get("per_iteration")),
           "run_sound": None if ref is None else run >= ref}
    single = m.get("single") or []
    if receive_isr is not None and single:
        row["runs_with_receptions"] = sum(1 for _, k in single if k)
        row["receptions_per_run_max"] = max(k for _, k in single)
        row["runs_above_run_static"] = sum(1 for c, _ in single if c > run)
        row["run_with_receptions_margin_percent"] = min(pct(run + k * receive_isr, c) for c, k in single)
        row["run_with_receptions_sound"] = all(c <= run + k * receive_isr for c, k in single)
    return row


def compare_e(res, meas):
    tasks = {}
    for t, r in res["tasks"].items():
        tasks[t] = task_row(r, meas["tasks"].get(t, {}), res["kernel"]["receive_isr"])
    clusters = {}
    for cl, d in meas["clusters"].items():
        members = [t for t, c in meas["cluster_of"].items() if c == cl]
        s = sum(res["tasks"][t]["t"] for t in members)
        clusters[cl] = {"tasks": members, "static": s, "measured": d["measured"], "window_max": d["window_max"],
                        "phase_busy_max": d["phase_busy_max"], "estimated_input": meas["estimated"][cl],
                        "static_margin_percent": pct(s, d["measured"]),
                        "input_margin_percent": pct(meas["estimated"][cl], d["measured"]),
                        "sound": s >= d["window_max"]}
    return tasks, clusters


def compare_app(res, meas):
    tasks = {}
    for t, r in res["tasks"].items():
        tasks[t] = task_row(r, meas["tasks"].get(t, {}), res["kernel"]["receive_isr"])
    pes = {}
    for pe, d in meas["pes"].items():
        s = sum(res["tasks"][t]["t"] for t in d["tasks"])
        # CPU per iteration: the mean over the windows and the attribution to
        # the runs of the tasks (busy time over the iterations they serve);
        # a window holds the work of more iterations than releases when a
        # run serves two iterations at its border (window_max, informative)
        per_it = [x for x in (d["measured"], d["attributed"]) if x is not None]
        pes[pe] = {"tasks": d["tasks"], "static": s, "measured": d["measured"], "attributed": d["attributed"],
                   "window_max": d["window_max"], "phase_busy_max": d["phase_busy_max"],
                   "estimated_input": d["estimated"],
                   "static_margin_percent": pct(s, d["measured"]),
                   "input_margin_percent": pct(d["estimated"], d["measured"]),
                   "sound": bool(per_it) and s >= max(per_it)}
    return tasks, pes


def summary(rows, key):
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return {"min": None, "max": None, "mean": None}
    return {"min": min(vals), "max": max(vals), "mean": sum(vals) / len(vals)}


def flow(cfg, costs_path, out_dir):
    from rttools.paper import frequency
    f = cfg["flow"]
    m_static = frequency.run(f["app"], f["maps"], f["arch"], f["f0"],
                             os.path.join(out_dir, "frequency"), header_wait=f.get("header_wait", "bound"),
                             costs=costs_path)
    m_meas = frequency.run(f["app"], f["maps"], f["arch"], f["f0"],
                           os.path.join(out_dir, "frequency_measured"), header_wait=f.get("header_wait", "bound"))
    out = {}
    for key in m_static["runs"]:
        s, m = m_static["runs"][key], m_meas["runs"][key]
        out[key] = {"static": {k: s[k] for k in ("f_cpu_hz", "f_star_hz", "frequency_hz", "binding")},
                    "measured": {k: m[k] for k in ("f_cpu_hz", "f_star_hz", "frequency_hz", "binding")},
                    "cpu_demand_static": s["cpu_demand_cycles"], "cpu_demand_measured": m["cpu_demand_cycles"]}
    return out


def csv_costs(csv_path):
    from rttools.ucxgen.model import read_csv
    tasks, _, _ = read_csv(csv_path)
    return {t["label"]: int(float(str(t["wcet"]).replace(",", ""))) for t in tasks}


def pe_bound(res, csv_path, map_path):
    """t(V_k) of the static costs against the costs of the CSV per PE of
    the map: {pe: {"tasks", "static", "csv", "sound": static <= csv}}."""
    from rttools.modules.io import mapparser
    from rttools.tui.model import network as tnet
    with tnet.quiet():
        entries = mapparser.loadFromFile(map_path)
    want = csv_costs(csv_path)
    out = {}
    for e in entries:
        tasks = [t for t in e["tasks"] if t in res["tasks"]]
        if not tasks:
            continue
        st = sum(res["tasks"][t]["t"] for t in tasks)
        cs = sum(want[t] for t in tasks)
        out[str(e["node"])] = {"tasks": tasks, "static": st, "csv": cs, "sound": st <= cs}
    return out


def ni_image(name, a):
    """Terms of the network interface of an image with the time-triggered
    injection (rttools.wcet.ucx.ni_terms) and their bound in the model."""
    from rttools.modules.routing import router
    from rttools.wcet import annotations as wann
    from rttools.wcet import ucx
    img = wimg.load(a["image"])
    if not ucx.tt_image(img):
        raise ValueError(f"{name}: {a['image']} has no time-triggered injection (timer1ocr_handler)")
    an = wan.Analyzer(img, wann.Annotations.load(a["annotations"]))
    kernel = ucx.kernel_terms(an, True)
    secs = ucx.sections(an, kernel, an.ann.sections)
    ni = ucx.ni_terms(kernel, secs)
    return {"image": {"file": os.path.basename(a["image"]), "sha256": ucx.sha256(a["image"])},
            "kernel": {k: kernel[k] for k in ("tick", "send_isr", "receive_isr_size", "receive_isr_end",
                                              "release", "dispatch", "yield_save", "yield_resume") if k in kernel},
            "sections": secs["sections"], "tail": secs["tail"], "ni": ni,
            "within_bound": (ni["inject"] <= router.NI_INJECT_CYCLES and ni["rx_size"] <= router.NI_RX_SIZE_CYCLES
                             and ni["rx_end"] <= router.NI_RX_END_CYCLES and ni["ni_wait"] <= router.NI_WAIT_CYCLES)}


def analyze(cfg_path, out_dir):
    cfg = load_config(cfg_path)
    os.makedirs(out_dir, exist_ok=True)
    m = {"_doc": "rttools.paper.wcet analyze", "apps": {}}
    for name, a in cfg["apps"].items():
        res = static(a["spec"], os.path.join(out_dir, name))
        entry = {"image": res["image"], "kernel": res["kernel"], "params": res["params"],
                 "t": {t: r["t"] for t, r in res["tasks"].items()},
                 "terms": {t: r["terms"] for t, r in res["tasks"].items()}}
        if a.get("measured") == "exp23":
            meas = measured_e(a["log"], a["exp23_config"])
            tasks, groups = compare_e(res, meas)
            entry.update(clock_hz=meas["clock_hz"], windows=meas["windows"], tasks=tasks, groups=groups)
        elif a.get("measured") == "rtlapp":
            meas = measured_app(a["log"], a["manifest"], a["csv"], a["map"])
            tasks, groups = compare_app(res, meas)
            entry.update(clock_hz=meas["clock_hz"], windows=meas["windows"], tasks=tasks, groups=groups)
        if "ni" in res:
            entry["injection"] = res["injection"]
            entry["ni"] = res["ni"]
            entry["sections"] = res["sections"]["sections"]
        if "csv" in a and "map" in a and not a.get("measured"):
            entry["pe_bound"] = pe_bound(res, a["csv"], a["map"])
            entry["pe_bound_sound"] = all(r["sound"] for r in entry["pe_bound"].values())
        if "csv" in a and a.get("csv_costs"):
            want = csv_costs(a["csv"])
            entry["csv_equals_static"] = all(want.get(t) == r["t"] for t, r in res["tasks"].items())
            entry["csv_t"] = want
        if "groups" in entry:
            g = list(entry["groups"].values())
            ts = list(entry["tasks"].values())
            entry["summary"] = {
                "static_margin_percent": summary(g, "static_margin_percent"),
                "input_margin_percent": summary(g, "input_margin_percent"),
                "run_margin_percent": summary(ts, "run_margin_percent"),
                "run_with_receptions_margin_percent": summary(ts, "run_with_receptions_margin_percent"),
                "all_groups_sound": all(x["sound"] for x in g),
                "all_runs_sound": all(x["run_sound"] is not False for x in ts),
                "all_runs_with_receptions_sound": all(x.get("run_with_receptions_sound") is not False for x in ts)}
        m["apps"][name] = entry
    if "ni_images" in cfg:
        from rttools.modules.routing import router
        m["ni_images"] = {name: ni_image(name, a) for name, a in cfg["ni_images"].items()}
        m["ni_bound"] = router.NI_WAIT_CYCLES
        m["ni_term_bounds"] = {"inject": router.NI_INJECT_CYCLES, "rx_size": router.NI_RX_SIZE_CYCLES,
                               "rx_end": router.NI_RX_END_CYCLES}
        m["ni_max"] = max(r["ni"]["ni_wait"] for r in m["ni_images"].values())
        m["ni_within_bound"] = all(r["within_bound"] for r in m["ni_images"].values())
    if "bodies" in cfg:
        m["bodies"] = bodies(cfg["bodies"]["elf"], cfg["bodies"]["trace"])
    if "flow" in cfg:
        m["flow"] = flow(cfg, os.path.join(out_dir, cfg["flow"]["costs_of"], "costs.json"), out_dir)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
        f.write("\n")
    write_tables(out_dir, m)
    write_values(os.path.join(out_dir, "values.tex"), m)
    return m


def write_tables(out_dir, m):
    with open(os.path.join(out_dir, "tasks.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["app", "task", "t_static", "run_static", "measured_run_max", "measured_run_min",
                    "measured_per_iteration", "run_margin_percent", "body", "send", "receive", "dispatch",
                    "send_isr", "receive_isr", "tick", "release"])
        for app, e in m["apps"].items():
            for t, r in e.get("tasks", {}).items():
                tm = r["terms"]
                w.writerow([app, t, r["t_static"], r["run_static"], r["measured_run_max"], r["measured_run_min"],
                            r["measured_per_iteration"], _r(r["run_margin_percent"])]
                           + [tm[k] for k in ("body", "send", "receive", "dispatch", "send_isr", "receive_isr",
                                              "tick", "release")])
            if "tasks" not in e:
                for t, v in e["t"].items():
                    tm = e["terms"][t]
                    w.writerow([app, t, v, v - sum(tm[k] for k in NOT_JOB), "", "", "", ""]
                               + [tm[k] for k in ("body", "send", "receive", "dispatch", "send_isr", "receive_isr",
                                                  "tick", "release")])
    with open(os.path.join(out_dir, "clusters.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["app", "group", "tasks", "static", "measured", "window_max", "phase_busy_max", "estimated_input",
                    "static_margin_percent", "input_margin_percent", "sound"])
        for app, e in m["apps"].items():
            for g, r in e.get("groups", {}).items():
                w.writerow([app, g, " ".join(r["tasks"]), r["static"], r["measured"], r["window_max"], r["phase_busy_max"],
                            r["estimated_input"], _r(r["static_margin_percent"]), _r(r["input_margin_percent"]),
                            r["sound"]])
    if "bodies" in m:
        with open(os.path.join(out_dir, "bodies.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["body", "calls", "measured_min", "measured_max", "wcet_wrapper", "wcet_body",
                        "margin_percent", "sound"])
            for b, r in m["bodies"].items():
                w.writerow([b, r["calls"], r["measured_min"], r["measured_max"], r["wcet_wrapper"], r["wcet_body"],
                            _r(r["margin_percent"]), r["sound"]])


def _r(v, n=2):
    return "" if v is None else f"{v:.{n}f}"


def write_values(path, m):
    mn = exp23.macro_name
    num = exp23.fmt_int
    lines = ["% generated by python -m rttools.paper.wcet; do not edit"]

    def add(name_parts, v):
        lines.append(f"\\newcommand{{\\{mn('wcet', *name_parts)}}}{{{v}}}")
    for app, e in m["apps"].items():
        tag = app.replace("-", "")
        k = e["kernel"]
        for term in ("dispatch", "tick", "send_isr", "receive_isr", "release"):
            if term in k:
                add((tag, term.replace("_", " ")), num(k[term]))
        for t, v in e["t"].items():
            add((tag, "t", t), num(v))
        for g, r in e.get("groups", {}).items():
            add((tag, "group", g, "static"), num(r["static"]))
            add((tag, "group", g, "measured"), num(r["measured"]))
            add((tag, "group", g, "margin"), _r(r["static_margin_percent"]))
        if "summary" in e:
            s = e["summary"]
            for key in ("static_margin_percent", "input_margin_percent", "run_margin_percent",
                        "run_with_receptions_margin_percent"):
                if s.get(key) is None or (key == "run_with_receptions_margin_percent" and s[key]["min"] is None):
                    continue
                for stat in ("min", "max", "mean"):
                    add((tag, key.replace("_percent", "").replace("_", " "), stat), _r(s[key][stat]))
    for b, r in m.get("bodies", {}).items():
        add(("body", b, "wcet"), num(r["wcet_wrapper"]))
        add(("body", b, "measured"), num(r["measured_max"]))
        add(("body", b, "margin"), _r(r["margin_percent"]))
    for key, r in m.get("flow", {}).items():
        tag = "spiral" if key == "spiral" else "map"
        for kind in ("static", "measured"):
            for field, name in (("f_cpu_hz", "cpu"), ("f_star_hz", "network"), ("frequency_hz", "minimum")):
                v = r[kind][field]
                add(("flow", tag, kind, name, "mhz"), "-" if v is None else f"{v / 1e6:.1f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def run_log(log, spec, image, manifest, csv_path, map_path, out_dir, arch=None):
    """Static costs of the image of an RTL run against its log (WCET-E
    after `make sim`): CPU per PE and per task, and the phase-model
    analysis of rtlapp (responses against R_bound and the deadline,
    packets against [r, d], network, monitor) with the static t(v) of
    that image in the CSV (a copy in `out_dir`), under the key rtlapp."""
    import shutil
    res = static(spec, out_dir, image)
    meas = measured_app(log, manifest, csv_path, map_path)
    tasks, pes = compare_app(res, meas)
    csv_run = os.path.join(out_dir, os.path.basename(csv_path))
    shutil.copyfile(csv_path, csv_run)
    set_csv(os.path.join(out_dir, "costs.json"), csv_run)
    rt = rtlapp.analyze(log, manifest, csv_run, map_path, os.path.join(out_dir, "rtlapp"), arch=arch)
    resp = rt["responses"]
    m = {"log": os.path.basename(log), "image": res["image"], "clock_hz": meas["clock_hz"], "windows": meas["windows"],
         "kernel": res["kernel"], "tasks": tasks, "groups": pes,
         "summary": {"static_margin_percent": summary(list(pes.values()), "static_margin_percent"),
                     "run_margin_percent": summary(list(tasks.values()), "run_margin_percent"),
                     "run_with_receptions_margin_percent": summary(list(tasks.values()),
                                                                   "run_with_receptions_margin_percent"),
                     "per_iteration_margin_percent": summary(list(tasks.values()), "per_iteration_margin_percent"),
                     "all_groups_sound": all(x["sound"] for x in pes.values()),
                     "all_runs_sound": all(x["run_sound"] is not False for x in tasks.values()),
                     "all_runs_with_receptions_sound": all(x.get("run_with_receptions_sound") is not False
                                                           for x in tasks.values())},
         "rtlapp": {k: rt[k] for k in ("clock", "model", "releases", "markers", "responses", "cpu_windows",
                                       "cpu_attributed", "packets", "network", "monitor", "phase_conformance") if k in rt}}
    mdl = rt["model"]
    pk = rt["packets"]
    mon = rt.get("monitor") or {}
    m["summary"]["rtlapp"] = {
        "response_bound_cycles": mdl["response_bound"]["cycles"],
        "deadline_cycles": mdl["deadline"]["cycles"] if mdl.get("deadline") else None,
        "responses": resp["complete"], "response_max_cycles": resp["max_cycles"],
        "above_bound": resp["above_bound"], "above_deadline": resp["above_deadline"],
        "packets_late": pk["late"], "min_slack_remote_cycles": pk["min_slack_remote_cycles"],
        "monitor_errors": mon.get("errors"),
        "phase_conformance": (rt.get("phase_conformance") or {}).get("conforms")}
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(m, f, indent=1)
        f.write("\n")
    write_tables(out_dir, {"apps": {"run": dict(m, t={t: r["t_static"] for t, r in tasks.items()},
                                                terms={t: r["terms"] for t, r in tasks.items()})}})
    return m


def set_csv(costs_path, csv_path):
    """Writes t(v) of a costs file into the Capacity column of the task
    rows of an application CSV (the other lines stay as they are)."""
    with open(costs_path) as f:
        t = {k: v["t"] for k, v in json.load(f)["tasks"].items()}
    lines = open(csv_path).read().splitlines()
    out, mode = [], 0
    for line in lines:
        cells = line.split(",")
        if mode == 0 and cells[0] == "#tasks":
            mode = 1
        elif mode == 1:
            mode = 2
        elif mode == 2:
            if cells[0] == "#flows":
                mode = 3
            elif len(cells) >= 5 and cells[4] in t:
                cells[2] = str(t[cells[4]])
                line = ",".join(cells)
        out.append(line)
    with open(csv_path, "w") as f:
        f.write("\n".join(out) + "\n")


def print_summary(m):
    for app, e in m["apps"].items():
        k = e["kernel"]
        print(f"{app}: image {e['image']['file']} ({e['image']['kind']}); dispatch {k['dispatch']}, tick {k['tick']}, "
              f"send_isr {k['send_isr']}, receive_isr {k['receive_isr']}")
        for g, r in e.get("groups", {}).items():
            print(f"  {g:5s} static {r['static']:>8} measured {_r(r['measured'], 1):>10} (largest window "
                  f"{_r(r['window_max'], 1)}) input {r['estimated_input']:>8} margin {_r(r['static_margin_percent']):>7}% "
                  f"(input {_r(r['input_margin_percent'])}%) {'covers' if r['sound'] else 'BELOW'}")
        if "summary" in e:
            s = e["summary"]["run_margin_percent"]
            print(f"  runs: static job + dispatch over the longest one-iteration run: {_r(s['min'])}% to {_r(s['max'])}%"
                  f", all sound: {e['summary']['all_runs_sound']}; with receive_isr per packet received inside the "
                  f"run: all sound: {e['summary'].get('all_runs_with_receptions_sound')}")
            for t, r in e.get("tasks", {}).items():
                if r.get("run_sound") is False:
                    print(f"    {t}: {r.get('runs_above_run_static')} of {r['single_runs']} runs above job + dispatch "
                          f"({r['run_static']}; longest {r['measured_run_max']}); runs with a packet received inside: "
                          f"{r.get('runs_with_receptions')}; smallest margin with receive_isr per received packet: "
                          f"{_r(r.get('run_with_receptions_margin_percent'))}%")
        if "csv_equals_static" in e:
            print(f"  t(v) of the CSV equals the static costs: {e['csv_equals_static']}")
        for pe, r in e.get("pe_bound", {}).items():
            print(f"  PE {pe}: t(V_k) static {r['static']} CSV {r['csv']} {'covers' if r['sound'] else 'ABOVE'}")
        if "ni" in e:
            print(f"  network interface: w_NI {e['ni']['ni_wait']} (inject {e['ni']['inject']}, rx_size "
                  f"{e['ni']['rx_size']}, rx_end {e['ni']['rx_end']})")
    for name, r in m.get("ni_images", {}).items():
        n = r["ni"]
        print(f"ni {name}: {r['image']['file']} w_NI {n['ni_wait']} (inject {n['inject']}, rx_size {n['rx_size']}, "
              f"rx_end {n['rx_end']}, blocking {n['blocking']}) {'within' if r['within_bound'] else 'ABOVE'} "
              f"{m['ni_bound']}")
    for b, r in m.get("bodies", {}).items():
        print(f"bodies: {b} WCET {r['wcet_wrapper']} measured {r['measured_min']}-{r['measured_max']} "
              f"({r['calls']} calls) margin {_r(r['margin_percent'])}% {'sound' if r['sound'] else 'BELOW'}")
    for key, r in m.get("flow", {}).items():
        s, me = r["static"], r["measured"]
        print(f"flow {key}: f_CPU static {s['f_cpu_hz'] / 1e6:.1f} MHz (measured costs {me['f_cpu_hz'] / 1e6:.1f}), "
              f"minimum {s['frequency_hz'] / 1e6:.1f} MHz (measured costs {me['frequency_hz'] / 1e6:.1f})")


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.wcet", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--config", required=True)
    a.add_argument("--out", required=True)
    r = sub.add_parser("run-log")
    r.add_argument("log")
    r.add_argument("--spec", required=True)
    r.add_argument("--image", required=True)
    r.add_argument("--manifest", required=True)
    r.add_argument("--csv", required=True)
    r.add_argument("--map", required=True)
    r.add_argument("--arch", default=None, help="architecture of the run (link schedule of rtlapp)")
    r.add_argument("--out", required=True)
    c = sub.add_parser("set-csv")
    c.add_argument("costs")
    c.add_argument("csv")
    args = p.parse_args(argv)
    if args.cmd == "set-csv":
        set_csv(args.costs, args.csv)
        print("wrote " + args.csv)
        return 0
    if args.cmd == "analyze":
        m = analyze(args.config, args.out)
        print_summary(m)
        print("wrote " + args.out)
        return 0
    m = run_log(args.log, args.spec, args.image, args.manifest, args.csv, args.map, args.out, args.arch)
    print_summary({"apps": {"run": dict(m, t={}, terms={})}})
    print("wrote " + args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
