"""CPU time estimate per PE (rttools/bench_t/estimate.py): sequence from
the ORT/BENCH engine, demand, f_CPU, phases and response bound."""
import json
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.bench_t import estimate, main as bench_t

# application E in real cycles (thesis scale / 10)
SETS = {c: [(n, w // 10) for n, w in ts] for c, ts in bench_t.TASK_SETS.items()}
SIGMA = bench_t.SCHEDULER_CYCLES // 10


def closed_form(tasks, sigma):
    """s^(v_j) = sigma + sum_{l<j} c^(v_l); f^(v_j) = sum_{l<=j} c^(v_l)."""
    out, t = {}, 0
    for n, c in tasks:
        out[n] = (t + sigma, t + c)
        t += c
    return out


def app_e_edges():
    edges = []
    with open(os.path.join(REPO_ROOT, "apps", "synthetic-app-e", "synthetic-app-e.txt")) as f:
        section = None
        for line in f:
            line = line.strip()
            if line.startswith("#"):
                section = line[1:].strip()
            elif line and section == "edges":
                u, v, _ = line.split()
                edges.append((u, v))
    return edges


PE_OF = {t: c for c, ts in SETS.items() for t, _ in ts}


def test_engine_sequence_equals_prefix_sums():
    for cluster, tasks in SETS.items():
        seq = estimate.sequence(tasks, SIGMA)
        assert {n: (v["start"], v["finish"]) for n, v in seq.items()} == closed_form(tasks, SIGMA), cluster


def test_application_e_values():
    fin = {}
    for tasks in SETS.values():
        fin.update({n: v["finish"] for n, v in estimate.sequence(tasks, SIGMA).items()})
    assert fin == {"A": 28530, "B": 87130, "D": 101130, "F": 181930, "C": 96330,
                   "E": 52700, "H": 98000, "I": 173370, "J": 107570, "G": 217450}
    demands = {c: estimate.demand(ts) for c, ts in SETS.items()}
    assert demands == {"ABDF": 181930, "C": 96330, "EHI": 173370, "GJ": 217450}
    assert estimate.cpu_frequency(demands, 0.0005) == pytest.approx(434.9e6)


def test_sequence_keeps_order_with_equal_costs_and_quantum():
    seq = estimate.sequence([("x", 7), ("y", 7), ("z", 3)])
    assert [(seq[n]["start"], seq[n]["finish"]) for n in "xyz"] == [(0, 7), (7, 14), (14, 17)]


def test_sequence_rejects_bad_costs():
    with pytest.raises(ValueError):
        estimate.sequence([("x", 1.5)])
    with pytest.raises(ValueError):
        estimate.sequence([("x", 1), ("x", 2)])


def test_phases_and_response_bound_of_application_e():
    phi = estimate.phases(app_e_edges(), PE_OF)
    assert phi == {"A": 0, "B": 0, "D": 0, "F": 0, "C": 1, "G": 1, "E": 2, "H": 2, "I": 2, "J": 3}
    fin = {}
    for tasks in SETS.values():
        fin.update({n: v["finish"] for n, v in estimate.sequence(tasks, SIGMA).items()})
    assert estimate.response_bound(phi, fin, 250000) == (857570, "J")


def creation_rows():
    """{cluster: creation order} from the creation rows of the CSV of
    application E (the order of app_main of weird_a.c:405-422)."""
    from rttools.modules.io import appparser
    rows = appparser.readParameters(os.path.join(REPO_ROOT, "apps", "synthetic-app-e", "synthetic-app-e.csv"))
    return {"".join(sorted(ts)): ts for ts in rows["creation"].values()}


CREATION = creation_rows()


def test_dispatch_order_of_application_e():
    """Round robin in creation order from the idle task: A, B, D, F wait
    for their predecessor of the same phase; E runs first and H, I follow
    in queue order from E (idle skipped); J (phase 3) and G (phase 1) are
    both ready at the tick and J comes first in the queue."""
    phi = estimate.phases(app_e_edges(), PE_OF)
    got = {c: estimate.dispatch_order(ts, app_e_edges(), phi) for c, ts in CREATION.items()}
    assert got == {"ABDF": ["A", "B", "D", "F"], "C": ["C"], "EHI": ["E", "H", "I"], "GJ": ["J", "G"]}


def test_dispatch_order_scans_from_the_task_that_finished():
    edges = [("E", "H"), ("E", "I")]
    phi = {"E": 0, "H": 0, "I": 0}
    assert estimate.dispatch_order(["I", "E", "H"], edges, phi) == ["E", "H", "I"]
    assert estimate.dispatch_order(["E", "I", "H"], edges, phi) == ["E", "I", "H"]
    assert estimate.dispatch_order(["H", "I", "E"], edges, phi) == ["E", "H", "I"]


def test_dispatch_order_waits_only_for_predecessors_of_the_same_phase():
    # G -> J on the same PE: same phase, J waits for G; J in a later phase, J is ready at the tick
    assert estimate.dispatch_order(["J", "G"], [("G", "J")], {"G": 1, "J": 1}) == ["G", "J"]
    assert estimate.dispatch_order(["J", "G"], [("G", "J")], {"G": 1, "J": 3}) == ["J", "G"]
    # edges with a task of another PE do not block
    assert estimate.dispatch_order(["J", "G"], [("I", "J")], {"G": 1, "J": 1, "I": 0}) == ["J", "G"]


def test_dispatch_order_rejects_bad_input():
    with pytest.raises(ValueError):
        estimate.dispatch_order(["a", "a"], [], {"a": 0})
    with pytest.raises(ValueError):
        estimate.dispatch_order(["a", "b"], [("a", "b"), ("b", "a")], {"a": 0, "b": 0})


def test_phases_follow_the_sequence_inside_a_pe():
    """A target that runs before its source on the same PE serves the
    iteration of the source in the next phase."""
    pe = {"G": 3, "J": 3}
    assert estimate.phases([("G", "J")], pe) == {"G": 0, "J": 0}
    assert estimate.phases([("G", "J")], pe, {"G": 0, "J": 1}) == {"G": 0, "J": 0}
    assert estimate.phases([("G", "J")], pe, {"J": 0, "G": 1}) == {"G": 0, "J": 1}
    # application E: the kernel order J, G does not move J (phi(J) = 3 comes from I and H)
    order = {"A": 0, "B": 1, "D": 2, "F": 3, "C": 0, "E": 0, "H": 1, "I": 2, "J": 0, "G": 1}
    assert estimate.phases(app_e_edges(), PE_OF, order) == estimate.phases(app_e_edges(), PE_OF)


def test_phases_reject_cycles():
    with pytest.raises(ValueError):
        estimate.phases([("a", "b"), ("b", "a")], {"a": 0, "b": 1})


def test_task_sets_follow_the_kernel_order():
    """The lists of bench_t (and of the exp23 config) are in the order that
    the kernel rule gives on the creation rows of the CSV."""
    phi = estimate.phases(app_e_edges(), PE_OF)
    for cluster, ts in bench_t.TASK_SETS.items():
        assert [n for n, _ in ts] == estimate.dispatch_order(CREATION[cluster], app_e_edges(), phi), cluster


def test_config_of_exp23_holds_the_bench_t_costs():
    with open(os.path.join(REPO_ROOT, "experiments", "exp23", "config.json")) as f:
        est = json.load(f)["estimate"]
    assert est["scheduler_cycles"] == bench_t.SCHEDULER_CYCLES
    assert {c: [tuple(t) for t in ts] for c, ts in est["clusters"].items()} == bench_t.TASK_SETS


def test_main_prints_sequence(capsys):
    assert bench_t.main() == 0
    out = capsys.readouterr().out.splitlines()
    assert "GJ J start 110000 finish 1075700" in out and "GJ G start 1185700 finish 2174500" in out
    assert "GJ demand 2174500" in out
