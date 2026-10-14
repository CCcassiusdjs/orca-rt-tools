"""Stored runs of tag r11-rc5 (release by tick, UCX-OS kernel without nested
interrupts, crt0.s with the return test of _isr and the read back of
_interrupt_set(0), crt0=guard_readback): UG and UH (application E,
experiments/exp23), UCV (CAR-V, experiments/car-v-rtl), UMA (carv_e,
experiments/multiapp), W3 (WCET-E, experiments/wcet) and CF4 (car_full,
experiments/car-full), the runs TG, TH, TCV, TMA, W2 and CF2 of tag r11-rc3
with the crt0.s of this tree. Each run of the release by tick conforms with
the phase model (no task twice in a phase, no execution before phase
j + n(v), no phase above t(V_k)), stays within R_bound and the deadline, has
no late packet and no monitor error, and matches its reference; CF4
completes every job within the general phase model."""
import json
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


@pytest.mark.parametrize("log,ref", [
    ("exp23/logs/UG.events.txt", "exp23/reference_UG.json"),
    ("exp23/logs/UH.events.txt", "exp23/reference_UH.json"),
    ("car-v-rtl/logs/UCV.events.txt", "car-v-rtl/reference_UCV.json"),
    ("multiapp/logs/UMA.events.txt", "multiapp/reference_UMA_CARV.json"),
    ("multiapp/logs/UMA.events.txt", "multiapp/reference_UMA_E.json"),
    ("wcet/logs/W3.events.txt", "wcet/reference_W3.json"),
    ("car-full/logs/CF4.events.txt", "car-full/reference_CF4.json"),
])
def test_r11e_runs_are_of_this_kernel(log, ref):
    """The runs of tag r11-rc5 have isr=no_nesting and crt0=guard_readback in
    the RUN_INFO, and the reference of each states clock.isr = no_nesting and
    clock.crt0 = guard_readback."""
    info = exp23.read_run_info(exp23.run_info_path(os.path.join(EXP, log)))
    assert info["repo_tag"] == "r11-rc5" and exp23.isr_rule(info) == "no_nesting"
    assert exp23.crt0_rule(info) == "guard_readback"
    with open(os.path.join(EXP, ref)) as f:
        flat = exp23.flatten(json.load(f))
    assert [v for k, v in flat.items() if k.endswith("clock.isr")] == ["no_nesting"]
    assert [v for k, v in flat.items() if k.endswith("clock.crt0")] == ["guard_readback"]


@pytest.mark.parametrize("run", ["UG", "UH"])
def test_runs_ug_uh(tmp_path, run):
    """make -C experiments/exp23 check-run."""
    log = os.path.join(EXP, "exp23", "logs", f"{run}.events.txt")
    info = exp23.read_run_info(exp23.run_info_path(log))
    assert (info["repo_tag"], info["isr"], info["release"]) == ("r11-rc5", "no_nesting", "tick")
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
    assert m["clock"]["crt0"] == "guard_readback"
    # one execution per phase: no pair of iterations in one run of J
    assert r["max_pair_excess_cycles"] < 1000


def test_run_ucv(tmp_path):
    """make -C experiments/car-v-rtl check (run UCV)."""
    m = rtlapp.analyze(os.path.join(EXP, "car-v-rtl", "logs", "UCV.events.txt"), os.path.join(APP_DIR, "car_v.json"),
                       os.path.join(APPS, "car-v", "car-v.csv"), os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map"),
                       str(tmp_path), arch=os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "car-v-rtl", "reference_UCV.json")) == []
    conforms(m["phase_conformance"])
    r = m["responses"]
    assert (r["complete"], r["above_bound"], r["above_deadline"]) == (13, 0, 0)
    assert m["packets"]["late"] == 0 and m["monitor"]["errors"] == 0
    assert m["releases"]["acks"]["pes_min"] == 16
    assert m["clock"]["crt0"] == "guard_readback"


@pytest.mark.parametrize("app,csv", [("CARV", os.path.join(APPS, "car-v", "car-v.csv")),
                                     ("E", os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv"))])
def test_run_uma(tmp_path, app, csv):
    """make -C experiments/multiapp check-uma: both applications of run UMA
    within R_bound, no header wait caused by the other application."""
    d = os.path.join(EXP, "multiapp")
    m = rtlapp.analyze(os.path.join(d, "logs", "UMA.events.txt"), os.path.join(APP_DIR, "carv_e.json"), csv,
                       os.path.join(d, "maps", app + ".map"), str(tmp_path), app_name=app,
                       composition=os.path.join(d, "composition.json"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, f"reference_UMA_{app}.json")) == []
    conforms(m["phase_conformance"])
    r = m["responses"]
    assert (r["complete"], r["above_bound"], r["above_deadline"]) == ({"CARV": 13, "E": 14}[app], 0, 0)
    assert m["packets"]["late"] == 0 and m["monitor"]["errors"] == 0
    assert m["releases"]["acks"]["pes_expected"] == 20
    assert m["network"]["header_waits_with_other_app_contender"] == 0
    assert m["clock"]["crt0"] == "guard_readback"
    if app == "CARV":
        assert m["tasks"]["BFE3"]["iterations"] == 16          # 17 releases - n(BFE3) = 1


def test_run_w3(tmp_path):
    """make -C experiments/wcet run-analyze check-run LOG=logs/W3.events.txt: the
    static t(v) of the image of the run covers every PE; within R_bound."""
    d = os.path.join(EXP, "wcet")
    m = pw.run_log(os.path.join(d, "logs", "W3.events.txt"), os.path.join(d, "specs", "wcet_e.json"),
                   os.path.join(d, "logs", "W3.image.elf"), os.path.join(APP_DIR, "wcet_e.json"),
                   os.path.join(APPS, "wcet-e", "wcet-e.csv"), os.path.join(APPS, "wcet-e", "wcet-e-ONTO-hermes2x2.map"),
                   str(tmp_path), os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_W3.json")) == []
    s = m["summary"]
    assert s["all_groups_sound"] and s["all_runs_sound"] and s["rtlapp"]["phase_conformance"]
    r = s["rtlapp"]
    assert r["above_bound"] == 0 and r["above_deadline"] == 0 and r["packets_late"] == 0 and r["monitor_errors"] == 0


def test_wcet_of_the_r11e_runs(tmp_path):
    """make -C experiments/wcet analyze-r11e check-r11e: t(V_k) of the images
    of UH, UCV and W3 covers the CPU time of every PE; the runs of G, I and J
    in UH are above job + dispatch only by the handlers of packets received
    inside them."""
    pytest.importorskip("scipy")
    pytest.importorskip("elftools")
    d = os.path.join(EXP, "wcet")
    m = pw.analyze(os.path.join(d, "config_r11e.json"), str(tmp_path))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_r11e.json")) == []
    for app in ("E", "CAR-V", "WCET-E"):
        s = m["apps"][app]["summary"]
        assert s["all_groups_sound"] and s["all_runs_with_receptions_sound"], app
    e = m["apps"]["E"]["tasks"]
    assert sorted(t for t, r in e.items() if r["run_sound"] is False) == ["G", "I", "J"]
    assert all(e[t]["runs_with_receptions"] == e[t]["single_runs"] for t in ("G", "I", "J"))


def test_run_cf4(tmp_path):
    """make -C experiments/car-full check-cf4: run CF4 (car_full of tag
    r11-rc5) against reference_CF4.json. Every job completes (CF2: six jobs
    loop on the jalr of the return of _isr), no job begins twice in a phase,
    no deadline miss, no read older than the model, no phase above the busy
    time of the model, every chain has a measured data age within its bound,
    no packet after its deadline, no monitor error."""
    from rttools.paper import rtlmr
    d = os.path.join(EXP, "car-full")
    app = os.path.join(APPS, "car-full")
    m = rtlmr.analyze(os.path.join(d, "logs", "CF4.events.txt"), os.path.join(APP_DIR, "car_full.json"),
                      os.path.join(app, "car-full.csv"), os.path.join(app, "car-full-ONTO-hermes4x4.map"),
                      str(tmp_path))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_CF4.json")) == []
    assert (m["clock"]["isr"], m["clock"]["crt0"]) == ("no_nesting", "guard_readback")
    assert m["releases"]["count"] == 244 and m["markers"]["jobs"] == m["jobs"]["complete"] == 2945
    assert m["progress"]["stalled_tasks"] == [] and m["progress"]["stalled_pes"] == []
    assert (m["jobs"]["end_after_model_finish"], m["jobs"]["deadline_misses"]) == (0, 0)
    assert m["phases"]["jobs_begun_twice_in_a_phase"] == 0 and m["reads"]["older_than_model"] == 0
    assert m["cpu_phases"]["phases_above_model"] == 0
    a = m["data_age"]
    assert (a["chains"], a["measured_chains"], a["above_bound"]) == (34, 34, 0) and a["margin_min_cycles"] > 0
    assert m["packets"]["after_deadline"] == 0 and m["monitor"]["errors"] == 0
    # phasecheck (no tolerance): no task twice, no early execution; the PEs
    # busy through a whole phase exceed its 108,000 cycles by at most
    # BUSY_TOLERANCE, the rounding of the phase boundaries
    pc = m["phase_conformance"]
    assert (pc["phases_with_a_task_twice"], pc["early_jobs"]) == (0, 0)
    assert max(p["excess_max"] for p in pc["pes"].values()) <= rtlmr.BUSY_TOLERANCE
