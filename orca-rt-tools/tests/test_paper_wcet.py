"""rttools.paper.wcet: static t(v) against the stored runs (experiments/wcet)."""
import json
import os

import pytest

from rttools.paper import wcet as pw
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments", "wcet")


@pytest.fixture(scope="module")
def cfg():
    return pw.load_config(os.path.join(EXP, "config.json"))


def test_application_e_against_run_h(cfg, tmp_path_factory):
    a = cfg["apps"]["E"]
    res = pw.static(a["spec"], str(tmp_path_factory.mktemp("e")))
    meas = pw.measured_e(a["log"], a["exp23_config"])
    tasks, groups = pw.compare_e(res, meas)
    assert set(groups) == {"ABDF", "C", "EHI", "GJ"}
    for g in groups.values():
        # t(V_k) covers the CPU time per iteration of every hyperperiod and
        # is closer to it than the measured costs of the CSV
        assert g["sound"] and g["static"] >= g["window_max"]
        assert 0 < g["static_margin_percent"] < g["input_margin_percent"]
    for t, r in tasks.items():
        assert r["run_sound"] is not False, t
    # the longest one-iteration run of A in run H (paper: 14,333 cycles)
    assert round(meas["tasks"]["A"]["single_max"]) == 14333


def test_set_csv(tmp_path):
    src = os.path.join(REPO_ROOT, "apps", "wcet-e", "wcet-e.csv")
    p = tmp_path / "a.csv"
    p.write_text(open(src).read().replace(",9317,", ",1,"))
    c = tmp_path / "c.json"
    c.write_text(json.dumps({"tasks": {"A": {"t": 9317}}}))
    pw.set_csv(str(c), str(p))
    assert p.read_text() == open(src).read()


def test_reference_values(cfg):
    ref = json.load(open(os.path.join(EXP, "reference.json")))
    e = ref["apps"]["E"]
    assert e["summary"]["all_groups_sound"] and e["summary"]["all_runs_sound"]
    c = ref["apps"]["CAR-V"]
    assert c["summary"]["all_groups_sound"] and c["summary"]["all_runs_sound"]
    assert ref["apps"]["WCET-E"]["csv_equals_static"]
    for key, r in ref["flow"].items():
        assert r["static"]["f_cpu_hz"] < r["measured"]["f_cpu_hz"]


def test_run_w1_of_wcet_e(tmp_path):
    """Run W1 (RTL of WCET-E, gcc 12.2.0): the static t(v) of the image of
    the run covers the CPU time per iteration of every PE and the runs of
    every task; the responses stay within R_bound of these t(v) and the
    deadline; no late packet and no monitor error."""
    from rttools.paper import exp23
    logs = os.path.join(EXP, "logs")
    app = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app", "wcet_e.json")
    m = pw.run_log(os.path.join(logs, "W1.events.txt"), os.path.join(EXP, "specs", "wcet_e.json"),
                   os.path.join(logs, "W1.image.elf"), app,
                   os.path.join(REPO_ROOT, "apps", "wcet-e", "wcet-e.csv"),
                   os.path.join(REPO_ROOT, "apps", "wcet-e", "wcet-e-ONTO-hermes2x2.map"), str(tmp_path),
                   os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"))
    s = m["summary"]
    assert s["all_groups_sound"] and s["all_runs_sound"]
    r = s["rtlapp"]
    assert r["responses"] == 12 and r["above_bound"] == 0 and r["above_deadline"] == 0
    assert r["response_max_cycles"] <= r["response_bound_cycles"] <= r["deadline_cycles"]
    assert r["packets_late"] == 0 and r["monitor_errors"] == 0
    assert m["image"]["file"] == "W1.image.elf"
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "reference_W1.json")) == []
