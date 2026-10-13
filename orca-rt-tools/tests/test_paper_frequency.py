"""Minimum frequency of application E (rttools/paper/frequency.py,
experiments/exp23 make frequency)."""
import json
import os

from tests.conftest import REPO_ROOT
from rttools.paper import exp23, frequency

EXP = os.path.join(REPO_ROOT, "experiments", "exp23")
APP_E = os.path.join(REPO_ROOT, "apps", "synthetic-app-e")


def test_frequency_pipeline_matches_reference(tmp_path):
    m = frequency.run(os.path.join(APP_E, "synthetic-app-e.csv"),
                      [os.path.join(APP_E, "synthetic-app-e-ONTO-hermes2x2.map"), "spiral"],
                      os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"), 500000000, str(tmp_path),
                      os.path.join(EXP, "config.json"))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "reference_frequency.json")) == []
    assert m["f_cpu_equals_exp23"] is True
    for r in m["runs"].values():
        # the bisection brackets f*; the CPU test sets the result
        assert r["f_star_lower_hz"] < r["f_star_hz"] < r["f_cpu_hz"] == r["frequency_hz"]
        assert r["binding"] == "cpu"
        assert r["final_check"] == {"frequency_hz": 434900000.0, "feasible": True, "hyperperiod": 217450,
                                    "packets": 5, "skipped": 0}
    values = (tmp_path / "values.tex").read_text()
    assert "\\ExpFrequencyMapMinimumMhz}{434.9}" in values
    assert "\\ExpFrequencySpiralCpuNetwork}{feasible}" in values


def test_network_frequency_is_set_by_flow_f_to_g():
    """f* = (f^(F) - s^(G) + o(F->G)) / T: the phase must hold the window of
    F->G (release 181 930, start of G 11 000 in the next phase, occupancy
    o = L0 + 20 (m + 1) = 1 717 + 60 cycles for 6 780 bytes over 2 hops,
    the default occupancy)."""
    with open(os.path.join(EXP, "reference_frequency.json")) as f:
        ref = json.load(f)
    need = (181930 - 11000 + 1717 + 60) / 0.0005
    for r in ref["runs"].values():
        assert r["f_star_lower_hz"] < need <= r["f_star_hz"]


def test_frequency_pipeline_with_zero_load_occupancy(tmp_path):
    """make frequency-l0: o_i = L0 (--header-wait off)."""
    from rttools.modules.routing import router
    m = frequency.run(os.path.join(APP_E, "synthetic-app-e.csv"),
                      [os.path.join(APP_E, "synthetic-app-e-ONTO-hermes2x2.map"), "spiral"],
                      os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"), 500000000, str(tmp_path),
                      os.path.join(EXP, "config.json"), header_wait="off")
    assert exp23.check(str(tmp_path / "metrics.json"),
                       os.path.join(EXP, "reference_frequency_l0.json")) == []
    # the run leaves the selection of the process unchanged (default: the bound)
    assert router.header_wait() == router.HEADER_WAIT_CYCLES == 20
    assert m["header_wait_cycles"] == 0 and m["occupancy"] == "L0"
    # F->G (2 hops) holds L0 = 1 717 cycles
    need = (181930 - 11000 + 1717) / 0.0005
    for r in m["runs"].values():
        assert r["f_star_lower_hz"] < need <= r["f_star_hz"] < r["f_cpu_hz"] == r["frequency_hz"]
        assert r["binding"] == "cpu"
        assert r["final_check"]["feasible"] is True and r["final_check"]["skipped"] == 0
    values = (tmp_path / "values.tex").read_text()
    assert "\\ExpFrequencyHeaderWaitCycles}{0}" in values
    assert "\\ExpFrequencyMapNetworkMhz}{345.3}" in values
    assert "\\ExpFrequencyMapMinimumMhz}{434.9}" in values


def test_frequency_default_header_wait_is_the_bound(tmp_path):
    with open(os.path.join(EXP, "reference_frequency.json")) as f:
        ref = json.load(f)
    assert ref["header_wait_cycles"] == 20 and ref["occupancy"] == "L0 + 20 (m + 1)"
    with open(os.path.join(EXP, "reference_frequency_l0.json")) as f:
        ref = json.load(f)
    assert ref["header_wait_cycles"] == 0 and ref["occupancy"] == "L0"
    m = frequency.run(os.path.join(APP_E, "synthetic-app-e.csv"),
                      [os.path.join(APP_E, "synthetic-app-e-ONTO-hermes2x2.map")],
                      os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"), 500000000, str(tmp_path))
    assert m["header_wait_cycles"] == 20 and m["occupancy"] == "L0 + 20 (m + 1)"
    assert "\\ExpFrequencyHeaderWaitCycles}{20}" in (tmp_path / "values.tex").read_text()


def test_frequency_cli_header_wait_option(tmp_path):
    from tests.conftest import run_module
    r = run_module("rttools.paper.frequency", "run", "--app", os.path.join(APP_E, "synthetic-app-e.csv"),
                   "--arch", os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"),
                   "--map", os.path.join(APP_E, "synthetic-app-e-ONTO-hermes2x2.map"),
                   "--header-wait", "off", "--out", str(tmp_path))
    assert r.returncode == 0, r.stderr
    assert "o_i = L0\n" in r.stdout
    with open(tmp_path / "metrics.json") as f:
        assert json.load(f)["header_wait_cycles"] == 0
