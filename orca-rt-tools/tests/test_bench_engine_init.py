"""Fix 9 (rttools/bench/engine.py, constructor; rttools/gff/orca.py).

1. self._blocked.append(tlb) was outside the loop: only the last task
   entered the simulation.
2. TaskControlBlock(i, label, wcet, 0, 0) passed the WCET as the period and
   capacity 0.
3. The ORCA format had no way to specify period and deadline; the reader
   now accepts `label wcet [period [deadline]]`.
"""
import os

from tests.conftest import REPO_ROOT
from rttools.gff.orca import import_graph, export_graph
from rttools.bench.engine import SingleCoreEngine
from rttools.bench.scheduling import RoundRobinSchedule

SRC = os.path.join(REPO_ROOT, "apps", "sample-graph-a", "sample_graph.txt")


def test_all_tasks_enter_blocked_list():
    eng = SingleCoreEngine(import_graph(SRC), RoundRobinSchedule)
    assert len(eng._blocked) == 10
    caps = {t._name: t._capacity for t in eng._blocked}
    assert caps["A"] == 1230
    assert caps["J"] == 8900
    assert all(t._period is None for t in eng._blocked)   # single-shot task


def test_periodic_fields(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("# nodes\nT1 3 10 8\nT2 5 20\n\n# edges\nT1 T2 4\n")
    g = import_graph(str(f))
    eng = SingleCoreEngine(g, RoundRobinSchedule)
    t1, t2 = sorted(eng._blocked, key=lambda t: t._name)
    assert (t1._capacity, t1._period, t1._deadline) == (3, 10, 8)
    assert (t2._capacity, t2._period, t2._deadline) == (5, 20, 20)
    out = tmp_path / "q.txt"
    export_graph(str(out), g)
    g2 = import_graph(str(out))
    assert [n._data for n in g2._nodes] == [n._data for n in g._nodes]
