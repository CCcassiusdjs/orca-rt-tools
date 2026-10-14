"""Analysis of a run of a time-triggered application (rttools/paper/rtlmr.py,
through rttools.paper.rtlapp) on logs written from the model of CAR-full:
a log that follows the model, one with a late job and one with an old
read."""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.bench_t import multirate
from rttools.paper import rtlapp, rtlmr
from rttools.ucxgen import model

APP = os.path.join(REPO_ROOT, "apps", "car-full")
CSV = os.path.join(APP, "car-full.csv")
MAP = os.path.join(APP, "car-full-ONTO-hermes4x4.map")
APP_DIR = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app")


def manifest():
    return model.build(CSV, MAP, "car_full", mesh="4x4")


F_CLK = 500_000_000            # 2 ns per cycle
R0_NS = 3_000_000


def model_log(path, hyperperiods=5, late=None, old_read=None, early=None, stop=None):
    """Log of a run that follows the model at F_CLK: TRIGGER lines at the
    ticks, scheduled lines of the ORT/BENCH slices, ITER and read markers
    at the start and the finish of each job, TAG lines of the packets.
    `late` = (task, job, cycles) delays the end marker of one job;
    `old_read` = (task, job, source) makes one read one job older;
    `early` = (task, job) writes the begin marker of one job one cycle
    after the begin of the previous job (two begins in one phase);
    `stop` = (task, job) drops the markers of that job and of the later
    jobs of the task."""
    from rttools.modules.io import appparser
    from rttools.modules.mapping import mapfile
    from rttools.tui.model import network
    with network.quiet():
        g, _ = appparser.loadFromFile(CSV)
    m = manifest()
    spec = multirate.spec_from_graph(g, mapfile.read(MAP))
    P = 125000
    s = multirate.schedule(spec, P)
    t = {x["name"]: x for x in m["tasks"]}
    lab = {x["name"]: x["pe_label"] for x in m["tasks"]}
    ns = lambda c: R0_NS + 2 * c
    end = hyperperiods * s.H
    lines = ["# Time scale of (manycore_top.pe_x[0].pe_y[0].pe_mod) is  1ns /  1fs"]
    ev = []
    for p in range(hyperperiods * spec.hyper_ticks + 1):
        ev.append((ns(p * P), 0, f"# TRIGGER: workflow iteration at {ns(p * P)} ns."))
    for node, sim in s.sims.items():
        pe = f"{int(node) % 4}-{int(node) // 4}"
        kid = {n: i + 1 for i, n in enumerate(spec.orders[node])}
        prev_end = None
        for b, e, n in sim["slices"]:
            if b >= end:
                break
            if prev_end is not None and prev_end != b:
                ev.append((ns(prev_end), 1, f"# {ns(prev_end)} {pe} scheduled 0"))
            ev.append((ns(b), 1, f"# {ns(b)} {pe} scheduled {kid[n]}"))
            prev_end = e
        if prev_end is not None:
            ev.append((ns(prev_end), 1, f"# {ns(prev_end)} {pe} scheduled 0"))
    m_of = {(u, v): mm for _, u, v, mm in spec.flows}
    for v in spec.tasks:
        n = s.per_h(v) * hyperperiods
        prev_S = None
        for j in range(n):
            rel, S, F = s.job(v, j)
            if stop and stop[0] == v and j + 1 >= stop[1]:
                break
            if early == (v, j + 1):
                S = prev_S + 1
            prev_S = S
            reads = []
            for i in t[v]["inputs"]:
                fl = m["flows"][i - 1]
                u = fl["source"]
                k = multirate.read_index(spec, s, u, v, m_of[(u, v)], j)
                k = 0 if k is None else k + 1
                if old_read == (v, j + 1, u):
                    k -= 1
                reads.append((t[u]["iter_letter"], k))
            ev.append((ns(S), 2, f"# {ns(S)} {lab[v]} ITER begin {t[v]['iter_letter']} {j + 1}"))
            for q, (letter, k) in enumerate(reads):
                ev.append((ns(S) + 0, 3 + q, f"# {ns(S)} {lab[v]} ITER begin {letter} {0x800000 + k}"))
            F2 = F + (late[2] if late and late[:2] == (v, j + 1) else 0)
            for o in t[v]["outputs"]:
                fl = m["flows"][o - 1]
                if j % fl["every"]:
                    continue
                tag = fl["id"] * 1024 + (j + 1) % 1024
                ev.append((ns(F), 10, f"# {ns(F)} {lab[v]} -> TAG {tag}"))
                ev.append((ns(F + 200), 10, f"# {ns(F + 200)} {fl['dst_label']} <- TAG {tag}"))
            ev.append((ns(F2), 20, f"# {ns(F2)} {lab[v]} ITER end {t[v]['iter_letter']} {j + 1}"))
    ev.sort(key=lambda x: (x[0], x[1]))
    lines += [x[2] for x in ev]
    path.write_text("\n".join(lines) + "\n")
    return s


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    d = tmp_path_factory.mktemp("rtlmr")
    out = {}
    for name, kw in (("ok", {}), ("late", {"late": ("DIRC", 30, 10_000_000)}),
                     ("old", {"old_read": ("NAVC", 20, "SPES")}), ("early", {"early": ("SPES", 7)}),
                     ("stop", {"stop": ("OBMG", 3)})):
        log = d / f"{name}.events.txt"
        model_log(log, **kw)
        m = rtlmr.analyze(str(log), os.path.join(APP_DIR, "car_full.json"), CSV, MAP, str(d / name),
                          run_info=None, f_clk=F_CLK)
        out[name] = m
    return out, d


def test_analysis_of_a_log_of_the_model(runs):
    m = runs[0]["ok"]
    assert m["model"]["phase_cycles"] == 125000 and m["model"]["cpu_feasible"]
    assert m["jobs"]["deadline_misses"] == 0 and m["jobs"]["end_after_model_finish"] == 0
    # the log of the model has its ticks at the release lines: begin = first dispatch + sigma
    assert m["jobs"]["begin_after_release_min_cycles"] == 11000
    assert m["reads"]["older_than_model"] == 0 and m["reads"]["newer_than_model"] == 0
    assert m["markers"]["stray"] == 0
    assert m["phases"]["jobs_begun_twice_in_a_phase"] == 0 and m["progress"]["stalled_tasks"] == []
    assert m["cpu_phases"]["phases_above_model"] == 0
    d = m["data_age"]
    assert d["chains"] == 34 and d["measured_chains"] == 34 and d["above_bound"] == 0
    # the log holds the worst job of every chain: measured max = bound
    assert d["margin_min_cycles"] == 0 and all(r["margin_cycles"] == 0 for r in d["rows"])
    assert m["packets"]["after_deadline"] == 0 and m["packets"]["remote_received"] > 0


def test_analysis_detects_late_end_and_old_read(runs):
    late, old = runs[0]["late"], runs[0]["old"]
    assert late["jobs"]["end_after_model_finish"] == 1 and late["data_age"]["above_bound"] > 0
    assert old["reads"]["older_than_model"] == 1


def test_analysis_detects_two_jobs_in_a_phase_and_a_stalled_task(runs):
    early, stop = runs[0]["early"], runs[0]["stop"]
    assert early["phases"]["rows"] == [{"task": "SPES", "phase": early["phases"]["rows"][0]["phase"], "jobs": 2}]
    assert early["progress"]["stalled_tasks"] == []
    assert stop["progress"]["stalled_tasks"] == ["OBMG"]
    obmg = stop["progress"]["tasks"]["OBMG"]
    assert obmg["ended"] == 2 and obmg["released"] > 4
    assert stop["progress"]["stalled_pes"] == [obmg["pe"]]
    assert stop["phases"]["jobs_begun_twice_in_a_phase"] == 0


def test_rtlapp_command_line_routes_to_rtlmr(runs, capsys):
    d = runs[1]
    rc = rtlapp.main(["analyze", str(d / "ok.events.txt"), "--manifest", os.path.join(APP_DIR, "car_full.json"),
                      "--csv", CSV, "--map", MAP, "--out", str(d / "cli"), "--f-clk", str(F_CLK)])
    assert rc == 0
    assert "34 of 34 chains measured, 0 above the bound" in capsys.readouterr().out

