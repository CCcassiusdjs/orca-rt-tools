"""Release and deadline of the flows (rttools/modules/instances/release.py):
phase model of the analysis flow, selected in the #parameters section of
the application, and the ORT/GCPA model of the thesis as the default."""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.io import appparser
from rttools.modules.unwrapper import flowUnwrapper
from rttools.tui.model import network

# application E in real cycles (costs c^ of rttools/bench_t/main.py / 10)
COSTS = {"A": 28530, "B": 58600, "C": 96330, "D": 14000, "E": 52700, "F": 80800,
         "G": 109880, "H": 45300, "I": 75370, "J": 107570}
PAYLOAD = [("A", "C", 1230), ("A", "B", 4560), ("B", "D", 7890), ("C", "E", 1200), ("D", "F", 3450),
           ("F", "G", 6780), ("E", "I", 9010), ("E", "H", 2340), ("I", "J", 5670), ("H", "J", 8900),
           ("G", "J", 1230)]
MAP = "0:A,B,D,F\n1:C\n2:E,H,I\n3:G,J\n"
ARCH = os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml")
# Tab. 8.2 / tab-flows: (release, deadline) from the start of the source phase
EXPECTED = {("A", "C"): (28530, 261000), ("F", "G"): (181930, 261000), ("C", "E"): (96330, 261000),
            ("I", "J"): (128070, 370880), ("H", "J"): (173370, 370880)}


def write_case(tmp_path, params):
    rows = ["#tasks,,,,,", "Task,Wcet,Label,,,"]
    rows += [f"{i},{c},{t},,," for i, (t, c) in enumerate(sorted(COSTS.items()), start=1)]
    rows += ["#flows,,,,,", "Flow,Period,Data,Deadline,Source,Target"]
    rows += [f"{i},0.0005,{w},0.0005,{u},{v}" for i, (u, v, w) in enumerate(PAYLOAD, start=1)]
    if params:
        rows += ["#parameters,,,,,", "Parameter,Value,,,,"] + params
    app = tmp_path / "app-e.csv"
    app.write_text("\n".join(rows) + "\n")
    mp = tmp_path / "app-e.map"
    mp.write_text(MAP)
    return str(app), str(mp)


def packets(app_file, map_file, frequency=500000000):
    case = network.load_case(app_file, map_file, ARCH)
    with network.quiet():
        inst = instantiator.createInstance(case["app"], case["noc"], frequency)
        pk, hp, _ = flowUnwrapper.unwrap(inst, case["noc"], case["mapping"])
    return case, {(p["source"], p["target"]): (p["min_start"], p["abs_deadline"]) for p in pk}, hp


PHASE = ["release_model,phase", "scheduler_cycles,11000", "sequence,2,E,I,H"]


def test_parameters_section(tmp_path):
    app, _ = write_case(tmp_path, PHASE)
    g, _ = appparser.loadFromFile(app)
    assert g.graph["release_model"] == "phase" and g.graph["scheduler_cycles"] == 11000
    assert g.graph["sequences"] == {"2": ["E", "I", "H"]}
    assert g.number_of_edges() == len(PAYLOAD)


def test_phase_model_reproduces_tab_flows(tmp_path):
    _, pk, hp = packets(*write_case(tmp_path, PHASE))
    assert hp == 250000
    # one packet per flow between PEs; the edges inside a PE leave the problem
    assert pk == EXPECTED


def test_phase_model_frequency_scales_the_phase_only(tmp_path):
    """c^ and sigma are cycles; only the phase P = T f changes with f."""
    _, pk, hp = packets(*write_case(tmp_path, PHASE), frequency=400000000)
    assert hp == 200000
    assert pk[("A", "C")] == (28530, 200000 + 11000)
    assert pk[("I", "J")] == (128070, 200000 + 120880)


def test_sequence_defaults_to_mapping_order(tmp_path):
    """Without a sequence row, PE 2 runs E, H, I (mapping order)."""
    _, pk, _ = packets(*write_case(tmp_path, PHASE[:2]))
    assert pk[("H", "J")] == (52700 + 45300, 370880)
    assert pk[("I", "J")] == (52700 + 45300 + 75370, 370880)


def test_stable_topological_order():
    assert release.stable_topological(["J", "G"], [("G", "J")]) == ["G", "J"]
    assert release.stable_topological(["E", "H", "I"], [("E", "H"), ("E", "I")]) == ["E", "H", "I"]
    assert release.stable_topological(["a", "b"], [("a", "b"), ("b", "a")]) == ["a", "b"]


def test_sequence_must_match_the_mapping(tmp_path):
    case = network.load_case(*write_case(tmp_path, PHASE[:2] + ["sequence,2,E,I"]), ARCH)
    inst = instantiator.createInstance(case["app"], case["noc"], 500000000)
    with pytest.raises(ValueError):
        release.phase_flows(inst, case["mapping"])


def test_link_schedule_with_phase_model(tmp_path):
    case = network.load_case(*write_case(tmp_path, PHASE), ARCH)
    cfg = {"pruning_factor": 2000, "fail_threshold": 500, "heuristic": network.HEURISTICS["mbcf"]}
    with network.quiet():
        res = search.schedule_at(case["app"], case["noc"], case["mapping"], case["appname"], 500000000, cfg)
    assert search.feasible(res)
    assert network.validate(res) == []
    for p in res["problem"]["packets"]:
        assert (p["min_start"], p["abs_deadline"]) == EXPECTED[(p["source"], p["target"])]


def test_default_model_is_the_gcpa_model(tmp_path):
    """Without #parameters, release = CP(u) of ORT/GCPA and deadline =
    release + relative deadline of the input (model of Ch. 6)."""
    case, pk, _ = packets(*write_case(tmp_path, None))
    table = flowUnwrapper.task_wcet_table(instantiator.createInstance(case["app"], case["noc"], 500000000))
    assert pk[("A", "C")] == (table["A"], table["A"] + 250000)
    assert table["A"] == COSTS["A"]


def test_unknown_model_is_an_error():
    with pytest.raises(ValueError):
        release.settings({"release_model": "x"})


def test_cpu_bound_outside_the_frequency_search(tmp_path):
    case = network.load_case(*write_case(tmp_path, PHASE), ARCH)
    cpu = release.cpu_bound(case["app"], case["mapping"])
    assert cpu["demand"] == {"0": 181930, "1": 96330, "2": 173370, "3": 217450}
    assert cpu["period_s"] == 0.0005
    assert cpu["f_cpu_hz"] == pytest.approx(434.9e6)
