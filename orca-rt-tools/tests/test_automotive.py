"""Engine-control workload (rttools/paper/automotive.py,
experiments/automotive): the generation follows the tables of the config,
the run reproduces reference.json, and no simulated job with an execution
time between BCET and WCET ends after its F_j(v)."""
import json
import os

from rttools.paper import automotive, cputime
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments", "automotive")


def test_generation_rules():
    cfg = json.load(open(os.path.join(EXP, "config.json")))
    app = automotive.generate(cfg)
    period = {t: T for t, T, *_ in app["tasks"]}
    assert len(app["chains"]) == cfg["chains"]
    for u, v, T, d in app["flows"]:
        assert T == max(period[u], period[v]) and (T / period[u]).denominator == 1
        assert 1 <= d <= 64
    for ch in app["chains"]:
        ps = [int(period[t] * 1000) for t in ch["tasks"]]
        assert ps == ch["periods_ms"] and len(set(ps)) == len(ps)
        assert ch["constraint_ms"] == sum(ps)
    for t, T, c, bc, wc, ac in app["tasks"]:
        assert bc <= ac <= wc and c == max(1, round(wc * cfg["cycles_per_us"])) + cfg["scheduler_cycles"]


def test_reference(tmp_path):
    m = automotive.run(os.path.join(EXP, "config.json"), str(tmp_path))
    assert cputime.check(os.path.join(tmp_path, "metrics.json"), os.path.join(EXP, "reference.json"))
    assert m["variation"]["late"] == 0 and m["variation"]["jobs"] > 0
