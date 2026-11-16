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


def test_apply_rules(costs_file):
    """Rule max (default): t(v) = max(CSV, static) and scheduler_cycles the
    larger of the two, with the source of each cost; rule static: the
    values of the file."""
    app, _ = appparser.loadFromFile(APP)
    # appparser: the node keys are the task labels (networkx.parse_gml)
    before = {n: d["wcet"] for n, d in app.nodes(data=True)}
    ch = costs.apply(app, costs_file)
    after = {n: d["wcet"] for n, d in app.nodes(data=True)}
    d = json.load(open(costs_file))
    assert before["A"] == 28530 and after["A"] == 28530 and ch["A"] == (28530, 28530)
    assert before["D"] == 14000 and after["D"] == 20953 == d["tasks"]["D"]["t"]
    assert after == {n: max(int(before[n]), d["tasks"][n]["t"]) for n in before}
    assert costs.sources(app) == {n: "static" if d["tasks"][n]["t"] > int(before[n]) else "csv" for n in before}
    assert app.graph["scheduler_cycles"] == 11000 > d["scheduler_cycles"]
    app, _ = appparser.loadFromFile(APP)
    ch = costs.apply(app, costs_file, costs.STATIC)
    assert ch["A"] == (28530, 19210) and set(costs.sources(app).values()) == {"static"}
    assert app.graph["scheduler_cycles"] == d["scheduler_cycles"]
    with pytest.raises(costs.CostsError, match="cost rule"):
        costs.apply(app, costs_file, "min")


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
    d = json.load(open(costs_file))["tasks"]
    csv = {n: int(x["wcet"]) for n, x in appparser.loadFromFile(APP)[0].nodes(data=True)}
    demand = {"0": ["A", "B", "D", "F"], "1": ["C"], "2": ["E", "H", "I"], "3": ["G", "J"]}
    for rule, cost in (("static", lambda t: d[t]["t"]), ("max", lambda t: max(csv[t], d[t]["t"]))):
        m = frequency.run(APP, [MAP], ARCH, 500000000, str(tmp_path / rule), header_wait="bound", costs=costs_file,
                          cost_rule=rule)
        r = m["runs"][os.path.basename(MAP)]
        assert r["cpu_demand_cycles"] == {k: sum(cost(t) for t in v) for k, v in demand.items()}
        assert r["f_cpu_hz"] == max(r["cpu_demand_cycles"].values()) / 0.0005
        assert m["costs"] == os.path.basename(costs_file) and m["cost_rule"] == rule


def test_cli_of_the_flow_with_costs(costs_file, tmp_path):
    # the command line writes results.svg next to the application file
    import shutil
    for f in (APP, MAP, ARCH):
        shutil.copy(f, tmp_path)
    r = run_module("rttools", os.path.basename(APP), os.path.basename(MAP), os.path.basename(ARCH), "500000000",
                   "1", "2000", "False", "--costs", costs_file, cwd=str(tmp_path), timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "Task costs t(v) = max(CSV, static WCET" in r.stdout + r.stderr
    assert "t(A) = 28530 cycles (application: 28530)" in r.stdout + r.stderr
    assert "t(D) = 20953 cycles (application: 14000)" in r.stdout + r.stderr


def test_bench_t_with_costs(costs_file, capsys):
    from rttools.bench_t import main as bench_t
    assert bench_t.main(["--costs", costs_file]) == 0
    out = capsys.readouterr().out
    assert "ABDF demand 171473" in out
