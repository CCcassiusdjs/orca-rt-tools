"""Release and deadline of the flows (rttools/modules/instances/release.py):
phase model of the analysis flow, selected in the #parameters section of
the application, and the ORT/GCPA model of the ORCA RT-Tools reference as the default."""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.io import appparser
from rttools.modules.unwrapper import flowUnwrapper
from rttools.tui.model import network

# the model of the ORCA RT-Tools reference of the phase windows: deadline at the start of the reader
pytestmark = pytest.mark.usefixtures("deadline_start")

# application E in real cycles (costs c^ of rttools/bench_t/main.py / 10)
COSTS = {"A": 28530, "B": 58600, "C": 96330, "D": 14000, "E": 52700, "F": 80800,
         "G": 109880, "H": 45300, "I": 75370, "J": 107570}
PAYLOAD = [("A", "C", 1230), ("A", "B", 4560), ("B", "D", 7890), ("C", "E", 1200), ("D", "F", 3450),
           ("F", "G", 6780), ("E", "I", 9010), ("E", "H", 2340), ("I", "J", 5670), ("H", "J", 8900),
           ("G", "J", 1230)]
MAP = "0:A,B,D,F\n1:C\n2:E,H,I\n3:G,J\n"
ARCH = os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml")
# Tab. 8.2 / tab-flows: (release, deadline) from the start of the source phase, with the
# dispatch order of the kernel rule on the creation order of weird_a.c (A B D F, C, E H I, J G)
EXPECTED = {("A", "C"): (28530, 261000), ("F", "G"): (181930, 250000 + 107570 + 11000),
            ("C", "E"): (96330, 261000), ("I", "J"): (52700 + 45300 + 75370, 261000),
            ("H", "J"): (52700 + 45300, 261000)}
# the same flows with the order E, I, H and G, J of the earlier sequence rows
EXPECTED_EIH_GJ = {("A", "C"): (28530, 261000), ("F", "G"): (181930, 261000), ("C", "E"): (96330, 261000),
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


# creation order of app_main (pkt-sim/software/ucx-os/app/weird_a.c:405-422)
CREATION = ["creation,0,F,D,B,A", "creation,1,C", "creation,2,H,I,E", "creation,3,J,G"]
PHASE = ["release_model,phase", "scheduler_cycles,11000"] + CREATION


def test_parameters_section(tmp_path):
    app, _ = write_case(tmp_path, PHASE)
    g, _ = appparser.loadFromFile(app)
    assert g.graph["release_model"] == "phase" and g.graph["scheduler_cycles"] == 11000
    assert g.graph["creation"] == {"0": ["F", "D", "B", "A"], "1": ["C"], "2": ["H", "I", "E"], "3": ["J", "G"]}
    assert "sequences" not in g.graph
    assert g.number_of_edges() == len(PAYLOAD)


def test_two_rows_for_one_node_are_an_error(tmp_path):
    app, _ = write_case(tmp_path, PHASE + ["creation,2,E,H,I"])
    with pytest.raises(ValueError):
        appparser.loadFromFile(app)


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
    assert pk[("I", "J")] == (173370, 200000 + 11000)


def test_dispatch_order_follows_the_kernel_rule(tmp_path):
    """The creation rows give the order of the kernel: E, H, I on PE 2
    (round robin from E) and J, G on PE 3 (both ready at the tick, J first
    in the queue)."""
    case = network.load_case(*write_case(tmp_path, PHASE), ARCH)
    inst = instantiator.createInstance(case["app"], case["noc"], 500000000)
    edges = [(s, t) for s, t, _ in inst["flows"]]
    seqs = release.pe_sequences([t for t, _ in inst["tasks"]], edges, case["mapping"],
                                creation=inst["release"]["creation"])
    assert {str(k): v for k, v in seqs.items()} == {"0": ["A", "B", "D", "F"], "1": ["C"], "2": ["E", "H", "I"],
                                                    "3": ["J", "G"]}


def test_mapping_order_is_the_creation_order_without_rows(tmp_path):
    """Without a creation row, the mapping order (2:E,H,I and 3:G,J) is the
    creation order: E, H, I on PE 2 and G, J on PE 3."""
    _, pk, _ = packets(*write_case(tmp_path, PHASE[:2]))
    assert pk[("H", "J")] == (52700 + 45300, 370880)
    assert pk[("I", "J")] == (52700 + 45300 + 75370, 370880)


def test_sequence_rows_win_over_the_creation_rows(tmp_path):
    """A sequence row is the dispatch order of its PE (a kernel with
    another rule); with E, I, H and G, J the windows are the earlier ones."""
    _, pk, _ = packets(*write_case(tmp_path, PHASE + ["sequence,2,E,I,H", "sequence,3,G,J"]))
    assert pk == EXPECTED_EIH_GJ


def test_sequence_must_match_the_mapping(tmp_path):
    case = network.load_case(*write_case(tmp_path, PHASE[:2] + ["sequence,2,E,I"]), ARCH)
    inst = instantiator.createInstance(case["app"], case["noc"], 500000000)
    with pytest.raises(ValueError):
        release.phase_flows(inst, case["mapping"])


def test_creation_must_match_the_mapping(tmp_path):
    case = network.load_case(*write_case(tmp_path, PHASE[:2] + ["creation,2,H,E"]), ARCH)
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


def test_creation_order_follows_its_cluster_to_another_node(tmp_path):
    """A mapping that places the clusters on other nodes (Spiral Mapping:
    C on 0, ABDF on 1, GJ on 2, EHI on 3) keeps the creation order of
    each cluster."""
    app, _ = write_case(tmp_path, PHASE)
    other = tmp_path / "other.map"
    other.write_text("0:C\n1:A,B,D,F\n2:G,J\n3:E,H,I\n")
    _, pk, _ = packets(app, str(other))
    assert pk == EXPECTED
