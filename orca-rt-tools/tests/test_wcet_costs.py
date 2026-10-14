"""Costs files of rttools.wcet in the analysis flow: the CLI of rttools.wcet,
costs.apply, the --costs option of the flow, of the frequency pipeline and
of rttools/bench_t/main.py."""
import json
import os

import pytest

from rttools.modules.io import appparser
from rttools.wcet import __main__ as wcli
from rttools.wcet import costs
from tests.conftest import REPO_ROOT, run_module

SPEC = os.path.join(REPO_ROOT, "experiments", "wcet", "specs", "weird_a_H.json")
APP = os.path.join(REPO_ROOT, "apps", "synthetic-app-e", "synthetic-app-e.csv")
MAP = os.path.join(REPO_ROOT, "apps", "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map")
ARCH = os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml")


@pytest.fixture(scope="module")
def costs_file(tmp_path_factory):
    out = tmp_path_factory.mktemp("wcet") / "costs.json"
    assert wcli.main(["analyze", "--spec", SPEC, "--out", str(out), "--csv", str(out.with_suffix(".csv"))]) == 0
    return str(out)


def test_costs_file(costs_file):
    d = json.load(open(costs_file))
    assert sorted(d["tasks"]) == list("ABCDEFGHIJ")
    assert d["scheduler_cycles"] == d["kernel"]["dispatch"]
    assert d["image"]["kind"] == "listing"
    for t, r in d["tasks"].items():
        assert r["t"] == sum(r["terms"].values())
    assert d["tasks"]["A"]["t"] == 19210 and d["tasks"]["J"]["t"] == 105924


def test_apply_replaces_the_capacity(costs_file):
    app, _ = appparser.loadFromFile(APP)
    # appparser: the node keys are the task labels (networkx.parse_gml)
    before = {n: d["wcet"] for n, d in app.nodes(data=True)}
    ch = costs.apply(app, costs_file)
    after = {n: d["wcet"] for n, d in app.nodes(data=True)}
    assert before["A"] == 28530 and after["A"] == 19210 and ch["A"] == (28530, 19210)
    assert app.graph["scheduler_cycles"] == json.load(open(costs_file))["scheduler_cycles"]


def test_apply_needs_every_task(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"tasks": {"A": {"t": 1}}}))
    app, _ = appparser.loadFromFile(APP)
    with pytest.raises(costs.CostsError, match="no cost for tasks"):
        costs.apply(app, str(p))


def test_split_flag():
    assert costs.split_flag(["a", "--costs", "x.json", "b"]) == (["a", "b"], "x.json")
    assert costs.split_flag(["--costs=y.json"]) == ([], "y.json")
    assert costs.split_flag(["a"]) == (["a"], None)
    with pytest.raises(costs.CostsError):
        costs.split_flag(["--costs"])


def test_frequency_pipeline_with_static_costs(costs_file, tmp_path):
    from rttools.paper import frequency
    m = frequency.run(APP, [MAP], ARCH, 500000000, str(tmp_path / "f"), header_wait="bound", costs=costs_file)
    r = m["runs"][os.path.basename(MAP)]
    d = json.load(open(costs_file))["tasks"]
    demand = {"0": ["A", "B", "D", "F"], "1": ["C"], "2": ["E", "H", "I"], "3": ["G", "J"]}
    assert r["cpu_demand_cycles"] == {k: sum(d[t]["t"] for t in v) for k, v in demand.items()}
    assert r["f_cpu_hz"] == max(r["cpu_demand_cycles"].values()) / 0.0005
    assert m["costs"] == os.path.basename(costs_file)


def test_cli_of_the_flow_with_costs(costs_file, tmp_path):
    # the command line writes results.svg next to the application file
    import shutil
    for f in (APP, MAP, ARCH):
        shutil.copy(f, tmp_path)
    r = run_module("rttools", os.path.basename(APP), os.path.basename(MAP), os.path.basename(ARCH), "500000000",
                   "1", "2000", "False", "--costs", costs_file, cwd=str(tmp_path), timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "t(A) = 19210 cycles (application: 28530)" in r.stdout + r.stderr


def test_bench_t_with_costs(costs_file, capsys):
    from rttools.bench_t import main as bench_t
    assert bench_t.main(["--costs", costs_file]) == 0
    out = capsys.readouterr().out
    assert "ABDF demand 171473" in out
