"""Stored runs of tag r11-rc9 (release by tick, UCX-OS kernel without nested
interrupts, crt0=guard_readback, time-triggered injection of the packets
between PEs, injection=tt, with the tables of t(v) = max(CSV, static t(v) of
the image) and the deadline model tick, costs=max_csv_static, deadline=tick):
VG and VH (application E, experiments/exp23), VCV (CAR-V,
experiments/car-v-rtl), VMA (carv_e, experiments/multiapp), W4 and W5
(WCET-E, experiments/wcet). The analysis takes the model of the RUN_INFO
(network-interface model tt, the costs file and the deadline model: each
packet between PEs by the release tick of its reader, each job with the
handlers of the packet events of its PE). Each run conforms with the phase
model, stays within R_bound and the deadline, has no late packet and no
monitor error, injects every packet between PEs at or after its instant
s_{i,j} and within its bounds, ends every job at or before F(v), enqueues
every packet at or before s_{i,j}, and matches its reference. The test of
run CF5 (car_full of tag r11-rc7, deadline model start) stays here."""
import json
import os

import pytest

from rttools.modules.routing import router
from rttools.paper import exp23, rtlapp
from rttools.paper import wcet as pw
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments")
APP_DIR = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app")
APPS = os.path.join(REPO_ROOT, "apps")
COSTS = {"VG": "weird_a.json", "VH": "weird_a.json", "VCV": "car_v.json", "VMA": "carv_e.json",
         "W4": "wcet_e.json", "W5": "wcet_e.json"}


def conforms(pc):
    assert pc["release"] == "tick" and pc["conforms"]
    assert (pc["phases_with_a_task_twice"], pc["early_jobs"], pc["phases_cpu_above"]) == (0, 0, 0)


def injection_conforms(t, packets):
    """Every packet between PEs at or after s and within the bounds of the
    model tt; every job end before F and every enqueue before s."""
    assert t["packets"] == packets and t["unchecked"] == 0 and t["violations"] == 0
    assert t["early"] == 0 and 0 < t["inject_delay_max"] <= router.NI_INJECT_CYCLES
    assert t["rx_wait_max"] <= router.NI_RX_SIZE_CYCLES and t["end_wait_max"] <= router.NI_RX_END_CYCLES
    assert t["occupancy_slack_min"] > 0 and t["tick_grid_coverage_min"] == 1
    for k in ("jobs", "ready"):
        assert t[k]["events"] > 0 and t[k]["late"] == 0 and t[k]["unchecked"] == 0 and t[k]["slack_min"] > 0
        assert isinstance(t[k]["slack_min"], int)


@pytest.mark.parametrize("log,ref", [
    ("exp23/logs/VG.events.txt", "exp23/reference_VG.json"),
    ("exp23/logs/VH.events.txt", "exp23/reference_VH.json"),
    ("car-v-rtl/logs/VCV.events.txt", "car-v-rtl/reference_VCV.json"),
    ("multiapp/logs/VMA.events.txt", "multiapp/reference_VMA_CARV.json"),
    ("multiapp/logs/VMA.events.txt", "multiapp/reference_VMA_E.json"),
    ("wcet/logs/W4.events.txt", "wcet/reference_W4.json"),
    ("wcet/logs/W5.events.txt", "wcet/reference_W5.json"),
])
def test_r11g_runs_are_of_the_time_triggered_injection(log, ref):
    """The runs of tag r11-rc9 have injection=tt, deadline=tick and the costs
    file of the table of the image in the RUN_INFO; the reference of each states
    clock.crt0 = guard_readback and the injection tt."""
    from rttools.paper import ttcheck
    info = exp23.read_run_info(exp23.run_info_path(os.path.join(EXP, log)))
    assert info["repo_tag"] == "r11-rc9" and exp23.isr_rule(info) == "no_nesting"
    assert info["deadline"] == "tick"
    assert exp23.crt0_rule(info) == "guard_readback" and ttcheck.injection_rule(info) == "tt"
    run = os.path.basename(log).split(".")[0]
    # the costs file of the table of the image (costs/tt; the name of the RUN_INFO in the metrics)
    path = ttcheck.costs_of_run(info)
    assert ttcheck.costs_label(path) == COSTS[run] == info["costs_file"]
    with open(os.path.join(EXP, ref)) as f:
        flat = exp23.flatten(json.load(f))
    assert [v for k, v in flat.items() if k.endswith("clock.crt0")] == ["guard_readback"]
    assert [v for k, v in flat.items() if k.endswith("injection")] == ["tt"]


@pytest.mark.parametrize("run", ["VG", "VH"])
def test_runs_vg_vh(tmp_path, run, ni_off):
    """make -C experiments/exp23 check-run (NI ?= off: the analysis takes
    the model tt and the costs file of the RUN_INFO)."""
    log = os.path.join(EXP, "exp23", "logs", f"{run}.events.txt")
    cfg = exp23.load_config(os.path.join(EXP, "exp23", "config.json"))
    lst = os.path.join(EXP, "exp23", "logs", f"{run}.image.lst")
    m = exp23.analyze(log, cfg, str(tmp_path), listing=lst, listing_without=lst.replace("image.lst", "noinstr.lst"),
                      arch=os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"),
                      mapping=os.path.join(APPS, "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "exp23", f"reference_{run}.json")) == []
    conforms(m["phase_conformance"])
    assert m["injection"] == "tt" and m["costs"] == {"file": "weird_a.json", "rule": "max"}
    r = m["per_iteration"]["responses"]
    assert r["max_from_release_cycles"] <= m["response_bound"]["cycles"]
    # R_bound with F(J) of the handlers of the packet events of PE (1,1): 107,570 + 3,873
    assert m["response_bound"]["cycles"] == {"VG": 861443, "VH": 785171}[run]
    # t(V_k) of the model: max(CSV, static); D of ABDF takes its static t(v)
    est = {row["cluster"]: row["estimated"] for row in m["tab83"]["rows"]}
    assert est == {"ABDF": 188301, "C": 96330, "EHI": 173370, "GJ": 217450}
    assert all(row["measured"] <= row["estimated"] for row in m["tab83"]["rows"])
    assert m["monitor"]["errors"] == 0 and m["clock"]["crt0"] == "guard_readback"
    injection_conforms(m["tt"], 165)
    assert (m["tt"]["jobs"]["events"], m["tt"]["ready"]["events"]) == (329, 165)
    # ucx_noc_send_at: every call logs one send (its own write, or the tail call of ucx_noc_send)
    f = m["instrumentation"]["functions"]["ucx_noc_send_at"]
    assert f["rule"] == "every_return_path_with_tail_call" and f["tail_calls"] == ["ucx_noc_send"]


def test_run_vcv(tmp_path):
    """make -C experiments/car-v-rtl check (run VCV)."""
    m = rtlapp.analyze(os.path.join(EXP, "car-v-rtl", "logs", "VCV.events.txt"), os.path.join(APP_DIR, "car_v.json"),
                       os.path.join(APPS, "car-v", "car-v.csv"), os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map"),
                       str(tmp_path), arch=os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "car-v-rtl", "reference_VCV.json")) == []
    conforms(m["phase_conformance"])
    r = m["responses"]
    assert (r["complete"], r["above_bound"], r["above_deadline"]) == (13, 0, 0)
    assert m["model"]["response_bound"]["cycles"] == 977176
    assert m["packets"]["late"] == 0 and m["monitor"]["errors"] == 0
    assert m["releases"]["acks"]["pes_min"] == 16
    assert m["costs"]["static_above_csv"] == ["FDF1", "FDF2", "STPH"]
    injection_conforms(m["tt"], 262)
    assert m["tt"]["header_wait_max"] <= 20 * 2


@pytest.mark.parametrize("app,csv", [("CARV", os.path.join(APPS, "car-v", "car-v.csv")),
                                     ("E", os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv"))])
def test_run_vma(tmp_path, app, csv):
    """make -C experiments/multiapp check-vma: both applications of run VMA
    within R_bound, no header wait caused by the other application."""
    d = os.path.join(EXP, "multiapp")
    m = rtlapp.analyze(os.path.join(d, "logs", "VMA.events.txt"), os.path.join(APP_DIR, "carv_e.json"), csv,
                       os.path.join(d, "maps", app + ".map"), str(tmp_path), app_name=app,
                       composition=os.path.join(d, "composition.json"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, f"reference_VMA_{app}.json")) == []
    conforms(m["phase_conformance"])
    r = m["responses"]
    assert (r["complete"], r["above_bound"], r["above_deadline"]) == ({"CARV": 13, "E": 14}[app], 0, 0)
    assert m["model"]["response_bound"]["cycles"] == {"CARV": 1010200, "E": 802066}[app]
    assert m["packets"]["late"] == 0 and m["monitor"]["errors"] == 0
    assert m["releases"]["acks"]["pes_expected"] == 20
    assert m["network"]["header_waits_with_other_app_contender"] == 0
    injection_conforms(m["tt"], {"CARV": 262, "E": 80}[app])


@pytest.mark.parametrize("run,bound", [("W4", 796396), ("W5", 398380)])
def test_runs_w4_w5(tmp_path, run, bound):
    """make -C experiments/wcet run-analyze check-run LOG=logs/<run>.events.txt
    SPEC=specs/wcet_e_tt.json: the static t(v) of the image of the run
    covers every PE; rtlapp with the model of the run within R_bound."""
    d = os.path.join(EXP, "wcet")
    m = pw.run_log(os.path.join(d, "logs", f"{run}.events.txt"), os.path.join(d, "specs", "wcet_e_tt.json"),
                   os.path.join(d, "logs", f"{run}.image.elf"), os.path.join(APP_DIR, "wcet_e.json"),
                   os.path.join(APPS, "wcet-e", "wcet-e.csv"), os.path.join(APPS, "wcet-e", "wcet-e-ONTO-hermes2x2.map"),
                   str(tmp_path), os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, f"reference_{run}.json")) == []
    s = m["summary"]
    assert s["all_groups_sound"] and s["all_runs_sound"] and s["rtlapp"]["phase_conformance"]
    r = s["rtlapp"]
    assert r["response_bound_cycles"] == bound and r["response_max_cycles"] <= bound
    assert r["above_bound"] == 0 and r["above_deadline"] == 0 and r["packets_late"] == 0 and r["monitor_errors"] == 0
    assert m["rtlapp"]["costs"]["rule"] == "max"
    injection_conforms(m["rtlapp"]["tt"], 70)


def test_wcet_of_the_r11g_runs(tmp_path):
    """make -C experiments/wcet analyze-r11g check-r11g: t(V_k) of the images
    of VH, VCV and W5 covers the CPU time of every PE; the runs of I in VH
    are above job + dispatch only by the handlers of packets received
    inside them; w_NI of each image within NI_WAIT_CYCLES."""
    pytest.importorskip("scipy")
    pytest.importorskip("elftools")
    d = os.path.join(EXP, "wcet")
    m = pw.analyze(os.path.join(d, "config_r11g.json"), str(tmp_path))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_r11g.json")) == []
    for app in ("E", "CAR-V", "WCET-E"):
        s = m["apps"][app]["summary"]
        assert s["all_groups_sound"] and s["all_runs_with_receptions_sound"], app
        assert m["apps"][app]["ni"]["ni_wait"] <= router.NI_WAIT_CYCLES
    e = m["apps"]["E"]["tasks"]
    assert sorted(t for t, r in e.items() if r["run_sound"] is False) == ["I"]
    assert e["I"]["runs_with_receptions"] == e["I"]["single_runs"]


def test_run_images_equal_the_images_of_the_analysis():
    """The images of VH, VCV, W4 and VMA (riscv64-elf-gcc 12.2.0 of the
    simulation server) load the bytes of images/tt (container build of the
    same compiler): every allocated section has the same address and
    content, and the symbols are the same except the names of the mapping
    symbols of the assembler ($xrv32e1p9 against $x)."""
    pytest.importorskip("elftools")
    from elftools.elf.elffile import ELFFile

    def content(path):
        with open(path, "rb") as fh:
            elf = ELFFile(fh)
            secs = {sec.name: (sec["sh_addr"], sec.data()) for sec in elf.iter_sections()
                    if sec["sh_flags"] & 2 and sec["sh_type"] == "SHT_PROGBITS"}
            syms = sorted((("$x" if x.name.startswith("$x") else x.name), x["st_value"])
                          for x in elf.get_section_by_name(".symtab").iter_symbols())
        return secs, syms
    pairs = {"exp23/logs/VH.image.elf": "weird_a", "car-v-rtl/logs/VCV.image.elf": "car_v",
             "wcet/logs/W4.image.elf": "wcet_e", "multiapp/logs/VMA.image.elf": "carv_e"}
    for run, img in pairs.items():
        assert content(os.path.join(EXP, run)) == content(os.path.join(EXP, "wcet", "images", "tt", img + ".elf")), run


def test_run_cf5_jobs_after_their_finish(tmp_path, monkeypatch):
    """make -C experiments/car-full check-cf5: run CF5 (car_full of tag
    r11-rc7, 478.336 MHz) meets the checks of the injection, but jobs 3, 13,
    23, 33 and 43 of USOS (PE 0-1, phase 10 of each hyperperiod of 50
    phases) end after F of the model. In the log, the first job of OBDB ends
    before the tick of phase 11, USOS (id 2) starts in the rest of phase 10
    and the tick of phase 11 dispatches OBMG (id 3), the task after USOS in
    the round robin, while the model dispatches USOS at that tick."""
    import csv
    from rttools.paper import rtlmr
    # CF5 ran with a table built before the release guard of the link schedule (experiments/car-full, check-cf5)
    monkeypatch.setenv("RTTOOLS_RELEASE_GUARD", "off")
    d = os.path.join(EXP, "car-full")
    app = os.path.join(APPS, "car-full")
    log = os.path.join(d, "logs", "CF5.events.txt")
    m = rtlmr.analyze(log, os.path.join(APP_DIR, "car_full.json"), os.path.join(app, "car-full.csv"),
                      os.path.join(app, "car-full-ONTO-hermes4x4.map"), str(tmp_path),
                      arch=os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_CF5.json")) == []
    t = m["tt"]
    assert t["packets"] == 1695 and (t["early"], t["late"], t["occupancy_above"]) == (0, 0, 0)
    assert t["ready"]["late"] == 0 and m["jobs"]["complete"] == 2945
    assert m["reads"]["older_than_model"] == 0 and m["data_age"]["above_bound"] == 0
    with open(tmp_path / "tt_jobs.csv") as f:
        late = [(r["pe"], r["task"], int(r["j"]), int(r["q"])) for r in csv.DictReader(f) if float(r["slack"]) < 0]
    assert late == [("0-1", "USOS", j, 5 * (j - 1)) for j in (3, 13, 23, 33, 43)]
    assert t["jobs"]["late"] == 5 and t["jobs"]["slack_min"] == -106282
    # dispatches of PE 0-1 from the tick of phase 10 to the end of USOS 3 (ns of the log)
    rel = [int(x.split()[-2]) for x in open(log) if "TRIGGER: workflow iteration at" in x]
    seq = []
    for x in open(log):
        p = x.split()
        if len(p) > 4 and p[2] == "0-1" and p[1].isdigit() and rel[10] <= int(p[1]) <= rel[13]:
            if p[3] == "scheduled" or p[3] == "ITER":
                seq.append(" ".join(p[3:]))
    assert seq[:6] == ["scheduled 1", "ITER end R 1", "scheduled 2", "ITER begin E 3", "scheduled 3",
                       "scheduled 2"] and seq[6] == "ITER end E 3"


def test_run_cf6_within_the_model(tmp_path):
    """make -C experiments/car-full check-cf6: run CF6 (car_full of tag
    r11-rc9, 526.08 MHz, deadline model tick, tick hook of TT_TICK) ends
    every job at or before F of the model, misses no deadline, reads no
    data older than the model, keeps every chain within its bound DA and
    every packet between PEs within the checks of the injection."""
    from rttools.paper import rtlmr, ttcheck
    d = os.path.join(EXP, "car-full")
    app = os.path.join(APPS, "car-full")
    log = os.path.join(d, "logs", "CF6.events.txt")
    info = exp23.read_run_info(exp23.run_info_path(log))
    assert info["repo_tag"] == "r11-rc9" and info["deadline"] == "tick" and ttcheck.injection_rule(info) == "tt"
    m = rtlmr.analyze(log, os.path.join(APP_DIR, "car_full.json"), os.path.join(app, "car-full.csv"),
                      os.path.join(app, "car-full-ONTO-hermes4x4.map"), str(tmp_path),
                      arch=os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_CF6.json")) == []
    j = m["jobs"]
    assert (j["complete"], j["end_after_model_finish"], j["deadline_misses"]) == (2945, 0, 0)
    assert m["phases"]["jobs_begun_twice_in_a_phase"] == 0 and m["cpu_phases"]["phases_above_model"] == 0
    assert m["reads"]["older_than_model"] == 0
    a = m["data_age"]
    assert (a["measured_chains"], a["above_bound"]) == (34, 0) and a["margin_min_cycles"] > 0
    assert m["packets"]["after_deadline"] == 0 and m["monitor"]["errors"] == 0
    injection_conforms(m["tt"], 1695)
    assert m["tt"]["jobs"]["events"] == 2945
