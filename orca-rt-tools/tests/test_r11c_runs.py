"""Stored runs of tag r11-rc3 (release by tick, UCX-OS kernel without nested
interrupts): TG and TH (application E, experiments/exp23), TCV (CAR-V,
experiments/car-v-rtl), TMA (carv_e, experiments/multiapp) and W2 (WCET-E,
experiments/wcet). Each run conforms with the phase model (no task twice in
a phase, no execution before phase j + n(v), no phase above t(V_k)), stays
within R_bound and the deadline, has no late packet and no monitor error,
and matches its reference."""
import os

import pytest

from rttools.paper import exp23, rtlapp
from rttools.paper import wcet as pw
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments")
APP_DIR = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app")
APPS = os.path.join(REPO_ROOT, "apps")


def conforms(pc):
    assert pc["release"] == "tick" and pc["conforms"]
    assert (pc["phases_with_a_task_twice"], pc["early_jobs"], pc["phases_cpu_above"]) == (0, 0, 0)


@pytest.mark.parametrize("run", ["TG", "TH"])
def test_runs_tg_th(tmp_path, run):
    """make -C experiments/exp23 check-run."""
    log = os.path.join(EXP, "exp23", "logs", f"{run}.events.txt")
    info = exp23.read_run_info(exp23.run_info_path(log))
    assert (info["repo_tag"], info["isr"], info["release"]) == ("r11-rc3", "no_nesting", "tick")
    cfg = exp23.load_config(os.path.join(EXP, "exp23", "config.json"))
    lst = os.path.join(EXP, "exp23", "logs", f"{run}.image.lst")
    m = exp23.analyze(log, cfg, str(tmp_path), listing=lst, listing_without=lst.replace("image.lst", "noinstr.lst"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "exp23", f"reference_{run}.json")) == []
    conforms(m["phase_conformance"])
    r = m["per_iteration"]["responses"]
    assert r["max_from_release_cycles"] <= m["response_bound"]["cycles"]
    assert all(row["measured"] <= row["estimated"] for row in m["tab83"]["rows"])
    assert min(f["min_slack_cycles"] for f in m["per_iteration"]["flows"]) > 0
    assert m["monitor"]["errors"] == 0 and m["clock"]["isr"] == "no_nesting"
    # one execution per phase: no pair of iterations in one run of J
    assert r["max_pair_excess_cycles"] < 1000


def test_run_tcv(tmp_path):
    """make -C experiments/car-v-rtl check (run TCV)."""
    m = rtlapp.analyze(os.path.join(EXP, "car-v-rtl", "logs", "TCV.events.txt"), os.path.join(APP_DIR, "car_v.json"),
                       os.path.join(APPS, "car-v", "car-v.csv"), os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map"),
                       str(tmp_path), arch=os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "car-v-rtl", "reference_TCV.json")) == []
    conforms(m["phase_conformance"])
    r = m["responses"]
    assert (r["complete"], r["above_bound"], r["above_deadline"]) == (13, 0, 0)
    assert m["packets"]["late"] == 0 and m["monitor"]["errors"] == 0
    assert m["releases"]["acks"]["pes_min"] == 16


@pytest.mark.parametrize("app,csv", [("CARV", os.path.join(APPS, "car-v", "car-v.csv")),
                                     ("E", os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv"))])
def test_run_tma(tmp_path, app, csv):
    """make -C experiments/multiapp check-tma: both applications of run TMA
    within R_bound (run MA: BFE3 stopped after iteration 6, E above R_bound)."""
    d = os.path.join(EXP, "multiapp")
    m = rtlapp.analyze(os.path.join(d, "logs", "TMA.events.txt"), os.path.join(APP_DIR, "carv_e.json"), csv,
                       os.path.join(d, "maps", app + ".map"), str(tmp_path), app_name=app,
                       composition=os.path.join(d, "composition.json"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, f"reference_TMA_{app}.json")) == []
    conforms(m["phase_conformance"])
    r = m["responses"]
    assert (r["complete"], r["above_bound"], r["above_deadline"]) == ({"CARV": 13, "E": 14}[app], 0, 0)
    assert m["packets"]["late"] == 0 and m["monitor"]["errors"] == 0
    assert m["releases"]["acks"]["pes_expected"] == 20
    assert m["network"]["header_waits_with_other_app_contender"] == 0
    if app == "CARV":
        assert m["tasks"]["BFE3"]["iterations"] == 16          # 17 releases - n(BFE3) = 1


def test_run_w2(tmp_path):
    """make -C experiments/wcet run-analyze check-run LOG=logs/W2.events.txt: the
    static t(v) of the image of the run covers every PE; within R_bound."""
    d = os.path.join(EXP, "wcet")
    m = pw.run_log(os.path.join(d, "logs", "W2.events.txt"), os.path.join(d, "specs", "wcet_e.json"),
                   os.path.join(d, "logs", "W2.image.elf"), os.path.join(APP_DIR, "wcet_e.json"),
                   os.path.join(APPS, "wcet-e", "wcet-e.csv"), os.path.join(APPS, "wcet-e", "wcet-e-ONTO-hermes2x2.map"),
                   str(tmp_path), os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_W2.json")) == []
    s = m["summary"]
    assert s["all_groups_sound"] and s["all_runs_sound"] and s["rtlapp"]["phase_conformance"]
    r = s["rtlapp"]
    assert r["above_bound"] == 0 and r["above_deadline"] == 0 and r["packets_late"] == 0 and r["monitor_errors"] == 0


def test_receptions_inside_a_run():
    """task_row: a run longer than job + dispatch by the handlers of a packet
    received inside it is sound with receive_isr per received packet."""
    r = {"t": 1000, "terms": {"body": 600, "send": 0, "receive": 0, "dispatch": 100, "send_isr": 0,
                              "receive_isr": 200, "tick": 100, "release": 0}}
    run = pw.run_cycles(r)
    m = {"single_max": run + 50, "single_min": run, "single_runs": 2, "per_iteration": run + 25,
         "single": [[run + 50, 1], [run, 0]]}
    row = pw.task_row(r, m, receive_isr=200)
    assert row["run_sound"] is False and row["run_with_receptions_sound"] is True
    assert (row["runs_with_receptions"], row["runs_above_run_static"], row["receptions_per_run_max"]) == (1, 1, 1)
    m["single"] = [[run + 50, 0]]
    assert pw.task_row(r, m, receive_isr=200)["run_with_receptions_sound"] is False


def test_wcet_of_the_r11c_runs(tmp_path):
    """make -C experiments/wcet analyze-r11c check-r11c: t(V_k) of the images
    of TH, TCV and W2 covers the CPU time of every PE; the runs of G, I and J
    in TH are above job + dispatch only by the handlers of packets received
    inside them."""
    pytest.importorskip("scipy")
    pytest.importorskip("elftools")
    d = os.path.join(EXP, "wcet")
    m = pw.analyze(os.path.join(d, "config_r11c.json"), str(tmp_path))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_r11c.json")) == []
    for app in ("E", "CAR-V", "WCET-E"):
        s = m["apps"][app]["summary"]
        assert s["all_groups_sound"] and s["all_runs_with_receptions_sound"], app
    e = m["apps"]["E"]["tasks"]
    assert sorted(t for t, r in e.items() if r["run_sound"] is False) == ["G", "I", "J"]
    assert all(e[t]["runs_with_receptions"] == e[t]["single_runs"] for t in ("G", "I", "J"))
