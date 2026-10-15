"""Model of the runs of round r11f (rttools/paper/ttflow.py, experiments/tt):
the defaults of rttools (network-interface model tt, cost rule max), the
clock rule of the paper, the tables of the conferencia of run_r11f.sh and
the network-interface model of the analysis of a stored run."""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.routing import router
from rttools.paper import exp23, ttcheck, ttflow

EXP = os.path.join(REPO_ROOT, "experiments", "tt")
CONFIG = os.path.join(EXP, "config.json")


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    out = tmp_path_factory.mktemp("tt")
    return ttflow.run(CONFIG, str(out)), out


def test_run_matches_reference(run):
    m, out = run
    assert exp23.check(str(out / "metrics.json"), os.path.join(EXP, "reference.json")) == []
    assert (m["ni"], m["w_ni_cycles"], m["cost_rule"]) == ("tt", router.NI_WAIT_CYCLES, "max")


def test_every_task_takes_the_larger_of_the_two_costs(run):
    """Every task of every image has a static bound; the flow takes
    max(CSV, static) and records the source."""
    m, _ = run
    for name, a in m["apps"].items():
        assert a["costs"]["tasks"], name
        for t, c in a["costs"]["tasks"].items():
            assert isinstance(c["static"], int) and c["static"] > 0, (name, t)
            assert c["used"] == max(c["csv"], c["static"])
            assert c["source"] == ("static" if c["static"] > c["csv"] else "csv")
        for pe, p in a["pes"].items():
            assert p["used"] == sum(a["costs"]["tasks"][t]["used"] for t in p["tasks"])
            assert p["static_above_csv"] == sorted(t for t in p["tasks"]
                                                   if a["costs"]["tasks"][t]["source"] == "static")


def test_clock_of_each_run(run):
    """The run of the flow: the lowest clock at or above the minimum
    frequency whose phase is a multiple of 16 cycles; the kept runs at
    their clock; every run feasible with its injection table."""
    m, _ = run
    cfg = ttflow.load_config(CONFIG)
    for name, a in m["apps"].items():
        c = cfg["apps"][name]
        for run_id, r in a["runs"].items():
            assert r["feasible"] and r["table"] == {"clock": True, "costs": True}, run_id
            assert r["period_cycles"] % 16 == 0
            if run_id == c["runs"]["flow"]:
                assert r["rule"] == "flow" and a["minimum_hz"] <= r["clock_hz"]
                if "period_s" in c:
                    assert r["clock_hz"] == exp23.flow_clock(a["minimum_hz"], c["period_s"])["f_clk_hz"]
            else:
                assert r["rule"] == "kept" and r["clock_hz"] == c["runs"]["keep"][run_id]


def test_model_follows_the_network_interface_model_in_use(tmp_path, ni_off):
    m = ttflow.run(CONFIG, str(tmp_path))
    assert m["ni"] == "off" and m["w_ni_cycles"] == 0
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(EXP, "reference.json")) != []


def test_tables_of_the_conferencia(run, tmp_path):
    m, _ = run
    ttflow.write_tables(CONFIG, str(tmp_path))
    runs = {run_id: r for a in m["apps"].values() for run_id, r in a["runs"].items()}
    assert sorted(os.listdir(tmp_path)) == sorted(f"{r}.{e}" for r in runs for e in ("packets", "jobs"))
    for run_id, r in runs.items():
        lines = (tmp_path / f"{run_id}.packets").read_text().splitlines()
        head = lines[0].split()
        assert head[:3] == ["#", "P", str(r["period_cycles"])]
        assert len(lines) - 1 == r["packets_between_pes"]
        for x in lines[1:]:
            src, dst, key, k, ne, q0, s, o, hops = x.split()
            assert int(o) > router.NI_WAIT_CYCLES and int(hops) >= 1
    # one release period: one line per task, F of the model after the tick of its phase
    for run_id in ("VH", "VG", "VCV", "W5", "W4"):
        tasks = runs[run_id]["tasks"]
        rows = [x.split() for x in (tmp_path / f"{run_id}.jobs").read_text().splitlines()]
        assert len(rows) == len(tasks)
        for pe, letter, j, q0, f in rows:
            assert j == "0" and int(f) in {t["finish"] for t in tasks.values() if str(t["phase"]) == q0}


def test_analysis_of_a_run_takes_the_model_of_its_images(tmp_path):
    """ttcheck.run_ni: injection=tt in the RUN_INFO selects tt; a RUN_INFO
    without it (runs up to tag r11-rc5) or no RUN_INFO selects off."""
    log = tmp_path / "X.events.txt"
    log.write_text("")
    with ttcheck.run_ni(str(log), None):
        assert router.ni_model() == (False, 0)
    (tmp_path / "X.RUN_INFO").write_text("f_clk=500000000\n")
    with ttcheck.run_ni(str(log)):
        assert router.ni_model() == (False, 0)
    (tmp_path / "X.RUN_INFO").write_text("f_clk=500000000 injection=tt\n")
    with ttcheck.run_ni(str(log)):
        assert router.ni_model() == (True, router.NI_WAIT_CYCLES)
    assert router.ni_model() == (True, router.NI_WAIT_CYCLES)
