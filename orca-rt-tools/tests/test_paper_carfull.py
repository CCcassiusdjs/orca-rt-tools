"""CAR as a whole on the scale of CAR-V (rttools/paper/carfull.py): the
generated application and mapping; CAR-full through the general phase
model (release, instantiator, flowUnwrapper, search, data age); the
analysis flow of the chosen candidate, the rule of the cost factor and
the outputs of `run`."""
import json
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.bench_t import multirate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.io import appparser, nocparser
from rttools.modules.mapping import mapfile
from rttools.modules.unwrapper import flowUnwrapper
from rttools.paper import carfull, exp23
from rttools.paper.frequency import search_config
from rttools.tui.model import network

# reference.json of experiments/car-full: network-interface model off (NI ?= off)
pytestmark = pytest.mark.usefixtures("ni_off")

APPS = os.path.join(REPO_ROOT, "apps")
EXP = os.path.join(REPO_ROOT, "experiments", "car-full")
ARCH = os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml")
CAR_FULL = (os.path.join(APPS, "car-full", "car-full.csv"), os.path.join(APPS, "car-full", "car-full-ONTO-hermes4x4.map"),
            ARCH)


def load(paths):
    csv, mp, arch = paths
    with network.quiet():
        g, name = appparser.loadFromFile(csv)
        noc = nocparser.loadFromFile(arch)
    return g, name, noc, mapfile.read(mp)


def config():
    with open(os.path.join(EXP, "config.json")) as f:
        return json.load(f)


def test_generated_files_match_the_generator():
    cfg = config()
    app = carfull.build(cfg, APPS)
    with open(os.path.join(APPS, "car-full", "car-full.csv")) as f:
        assert f.read() == carfull.csv_text(app, cfg)
    with open(os.path.join(APPS, "car-full", "car-full-ONTO-hermes4x4.map")) as f:
        assert f.read() == carfull.map_text(carfull.mapping(cfg, APPS)["mapping"])
    assert carfull.main(["generate", "--config", os.path.join(EXP, "config.json"), "--apps", APPS, "--check"]) == 0


def test_scale_rule():
    app = carfull.build(config(), APPS)
    tasks = {t: (T, c) for t, T, c, _ in app["tasks"]}
    assert len(tasks) == 33 and len(app["flows"]) == 38 and app["ratio"] == 80
    # c^(v) = 4 round(w(v) T_v / 1 s) + 11000: 350000 cycles per second on the basis
    assert tasks["FBU1"] == (pytest.approx(0.0005), 4 * 14000 + 11000)
    assert tasks["OBMG"][1] == 4 * 350000 + 11000 and float(tasks["OBMG"][0]) == 0.0125
    assert tasks["FBU4"][1] == 4 * round(233334 * 0.04) + 11000
    by = {(a, b): (T, d) for a, b, T, d in app["flows"]}
    assert by[("FBU1", "BFE1")] == (pytest.approx(0.0005), 153600 // 16)
    assert float(by[("STAC", "TPRC")][0]) == 0.0125
    assert app["feedback"] == [("OBDB", "NAVC"), ("OBMG", "OBDB")]


def test_mapping_is_figure_4():
    r = carfull.mapping(config(), APPS)
    assert r["criterion"] == "MAX_PROC"
    nodes = {}
    for t, n in r["mapping"].items():
        nodes.setdefault(n, set()).add(t)
    assert nodes[9] == {"BFE3", "FDF1", "STPH"} and nodes[8] == {"POSI", "NAVC", "DIRC"}
    assert nodes[4] == {"OBDB", "USOS", "OBMG"} and nodes[0] == {"TPRC"}


# ---------------------------------------------------------------- general phase model

def test_appparser_task_periods_and_feedback_rows(tmp_path):
    g, _, _, _ = load(CAR_FULL)
    assert g.graph["task_periods"]["OBMG"] == "0.0125" and g.graph["feedback"] == [("OBDB", "NAVC"), ("OBMG", "OBDB")]
    assert release.settings(g.graph)["feedback"] == [("OBDB", "NAVC"), ("OBMG", "OBDB")]
    bad = tmp_path / "a.csv"
    bad.write_text("#tasks,,,,,\nTask,Period,Capacity,Deadline,Acronym,Description\n1,0.001,10,0,S,S\n"
                   "2,0.001,10,0,X,X\n#flows,,,,,\nFlow,Period,Data,Deadline,Source,Target\n"
                   "1,0.001,64,0.001,S,X\n#parameters,,,,,\nParameter,Value,,,,\nfeedback,S,,,,\n")
    with pytest.raises(ValueError, match="feedback row"):
        appparser.readParameters(str(bad))


def test_car_full_cpu_frequency_and_instance():
    g, name, noc, entries = load(CAR_FULL)
    cpu = release.cpu_bound(g, entries)
    assert cpu["model"] == "multirate" and cpu["phase_cycles"] == 108000 and cpu["f_cpu_hz"] == 432e6
    assert cpu["utilization_cycles"] == 100500
    spec = multirate.spec_from_graph(g, entries)
    assert multirate.schedule(spec, 108000).feasible and not multirate.schedule(spec, 107999).feasible
    inst = instantiator.createInstance(g, noc, 500e6)
    assert inst["rates"]["phase_cycles"] == 125000 and inst["rates"]["hyper_cycles"] == 6250000
    per = {d["label"]: d["period"] for _, _, d in inst["flows"]}
    assert per["f2"] == 5 * 5 * 125000 and per["f12"] == 2 * 125000 and per["f36"] == 10 * 5 * 125000
    with network.quiet():
        packets, hp, _ = flowUnwrapper.unwrap(inst, noc, entries)
    assert hp == 6250000 and len(packets) == 347
    assert sum(1 for p in packets if p["flow"] == "f2") == 2 and sum(1 for p in packets if p["flow"] == "f14") == 25
    assert all(p["abs_deadline"] - p["min_start"] > p["net_time"] for p in packets)
    # below f_CPU the CPU schedule misses deadlines: no packet instance
    with network.quiet():
        assert flowUnwrapper.unwrap(instantiator.createInstance(g, noc, 400e6), noc, entries)[1] == 0


def test_car_full_minimum_frequency():
    g, name, noc, entries = load(CAR_FULL)
    with network.quiet():
        r = search.minimum_frequency(g, noc, entries, name, search_config(500e6))
    assert r["f_cpu_hz"] == 432e6 and r["frequency_hz"] == 432e6 and r["f_star_hz"] == 432e6
    assert r["final_check"]["feasible"] and r["final_check"]["packets"] == 347 and r["final_search"] is None


def test_car_full_data_age():
    g, _, _, entries = load(CAR_FULL)
    spec = multirate.spec_from_graph(g, entries)
    ages = {"-".join(a["chain"]): a["max_cycles"] for a in multirate.data_age(spec, multirate.schedule(spec, 108000))}
    assert len(ages) == 34 and ages["POSI-OBMG-OBDB-NAVC-DIRC"] == 15552000 == max(ages.values())
    # 36 ms at 432 MHz: about three hyperperiods of 12.5 ms
    assert ages["POSI-OBMG-OBDB-NAVC-DIRC"] / 432e6 == pytest.approx(0.036)


# ---------------------------------------------------------------- analysis flow


@pytest.fixture(scope="module")
def run(tmp_path_factory, ni_off_module):
    out = tmp_path_factory.mktemp("carfull")
    m = carfull.run(config(), APPS, ARCH, str(out))
    return m, out


def test_run_matches_reference(run):
    m, out = run
    assert exp23.check(os.path.join(out, "metrics.json"), os.path.join(EXP, "reference.json")) == []


def test_chosen_candidate(run):
    m, out = run
    c = m["chosen"]
    assert m["rule"]["chosen_cost_factor"] == 4 and m["rule"]["config_matches_rule"]
    assert c["cpu"]["f_cpu_hz"] == 432e6 and c["search"]["binding"] == "cpu"
    # utilization bound below f_CPU; every job inside its release phase needs 20 times more
    assert c["cpu"]["utilization_bound_hz"] == 402e6 and c["cpu"]["f_cpu_phase_hz"] > 20 * 432e6
    assert c["network_at_clock"]["feasible"] and c["network_at_clock"]["packets"] == 347
    assert c["at_minimum"]["data_age_max"]["chain"] == "POSI-OBMG-OBDB-NAVC-DIRC"
    assert c["memory"]["fits"] and c["memory"]["worst_pe"] == "9"
    # payload divisor 8 does not fit the heap
    assert not m["candidates"]["k4_q8"]["memory_fits"]
    # cost factor 5: f_CPU above the clock, no packet instance at 500 MHz
    assert m["candidates"]["k5_q16"]["f_cpu_hz"] > 500e6 and not m["candidates"]["k5_q16"]["network_at_clock_feasible"]


def test_outputs(run):
    m, out = run
    with open(os.path.join(out, "values.tex")) as f:
        text = f.read()
    assert "\\newcommand{\\ExpCarFullCpuMhz}{432.0}" in text
    assert "\\newcommand{\\ExpCarFullChains}{34}" in text
    for name in ("factors.csv", "chains.csv", "pes.csv", "flows.csv", "car-full.csv", "car-full.map"):
        assert os.path.exists(os.path.join(out, name))
