"""CPU time of the stored runs with the kernel work in idle slices
(rttools/paper/cputime.py, experiments/cputime): the analysis reproduces
reference.json, every estimate t(V_k) stays above the measured CPU time of
every window and phase, and the windows start at r_{phi(v_last)}."""
import json
import os

from rttools.paper import cputime
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments", "cputime")


def _metrics(tmp_path):
    return cputime.analyze(os.path.join(EXP, "config.json"), str(tmp_path))


def test_reference(tmp_path):
    _metrics(tmp_path)
    assert cputime.check(os.path.join(tmp_path, "metrics.json"), os.path.join(EXP, "reference.json"))


def test_estimate_above_every_window_and_phase(tmp_path):
    res = _metrics(tmp_path)
    for rid, r in res["runs"].items():
        assert r["every_phase_below_estimate"], rid
        for lane, q in r["pes"].items():
            assert q["over_window_max_percent"] > 0, (rid, lane)
            assert q["mean"] >= q["busy_mean"], (rid, lane)


def test_windows_after_the_pipeline_fills():
    """Application E (n(J) + 1 = 4): the first window starts at the fourth
    release (4.5 ms in run VH, first release at 3.0 ms)."""
    rel = [3000 + 500 * k for k in range(34)]
    wins, phases = cputime.windows(rel, 4, 20000, 500)
    assert wins[0] == (4500, 6500) and phases[0] == (4500, 5000)
    assert all(b - a == 2000 for a, b in wins)
