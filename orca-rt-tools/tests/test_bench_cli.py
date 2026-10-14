"""Command line of the bench (rttools/bench/__main__.py and scheduling.py).

1. The CLI accepts the policies RR, RM, DM and EDF of scheduling.py.
2. RateMonotonicScheduling orders the ready tasks by period, shortest
   first.
3. An unknown algorithm or a usage error ends with a nonzero exit code.
"""
import os

import pytest

from tests.conftest import run_module, REPO_ROOT
from rttools.bench.kernel import TaskControlBlock
from rttools.bench.scheduling import RateMonotonicScheduling

SRC = os.path.join(REPO_ROOT, "apps", "sample-graph-a", "sample_graph.txt")


@pytest.mark.parametrize("algo", ["RR", "RM", "DM", "EDF"])
def test_cli_accepts_algorithms(algo):
    r = run_module("rttools.bench", SRC, "single", algo, "100000")
    assert r.returncode == 0, r.stderr[-2000:]
    assert "J" in r.stdout


def test_cli_unknown_algorithm_fails():
    r = run_module("rttools.bench", SRC, "single", "FOO")
    assert r.returncode != 0


def test_cli_usage_fails():
    r = run_module("rttools.bench", SRC)
    assert r.returncode != 0


def test_rate_monotonic_picks_shortest_period():
    a = TaskControlBlock(1, "A", 50, 1, 50)
    b = TaskControlBlock(2, "B", 10, 1, 10)
    c = TaskControlBlock(3, "C", 30, 1, 30)
    assert [t._name for t in RateMonotonicScheduling.schedule([a, b, c])] == ["B", "C", "A"]


def test_cli_one_shot_ends_at_sum_of_wcets():
    # sample_graph.txt: sum of WCETs = 51030; with no idle time, the last
    # task finishes at 51030
    r = run_module("rttools.bench", SRC, "single", "RR", "100000")
    last = [l for l in r.stdout.splitlines() if l and l[0].isdigit()][-1]
    assert int(last.split()[1]) == 51030
