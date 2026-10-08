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
                   "E": 52700, "I": 128070, "H": 173370, "G": 109880, "J": 217450}
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
    assert estimate.response_bound(phi, fin, 250000) == (967450, "J")


def test_phases_reject_cycles():
    with pytest.raises(ValueError):
        estimate.phases([("a", "b"), ("b", "a")], {"a": 0, "b": 1})


def test_config_of_exp23_holds_the_bench_t_costs():
    with open(os.path.join(REPO_ROOT, "experiments", "exp23", "config.json")) as f:
        est = json.load(f)["estimate"]
    assert est["scheduler_cycles"] == bench_t.SCHEDULER_CYCLES
    assert {c: [tuple(t) for t in ts] for c, ts in est["clusters"].items()} == bench_t.TASK_SETS


def test_main_prints_sequence(capsys):
    assert bench_t.main() == 0
    out = capsys.readouterr().out.splitlines()
    assert "GJ J start 1208800 finish 2174500" in out and "GJ demand 2174500" in out
