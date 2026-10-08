"""Table 7.1 pipeline (rttools/paper/ch7.py) on the stored graphs."""
import json
import os

from tests.conftest import REPO_ROOT
from rttools.gff.orca import import_graph
from rttools.paper import ch7

EXP = os.path.join(REPO_ROOT, "experiments", "ch7")


def cfg():
    with open(os.path.join(EXP, "config.json")) as f:
        return json.load(f)


def test_fast_loader_equals_import_graph():
    p = os.path.join(EXP, "graphs", "10_20.txt")
    a, b = ch7.load_graph(p), import_graph(p)
    assert [n._data for n in a._nodes] == [n._data for n in b._nodes]
    assert [(e._from._data["label"], e._to._data["label"], e._data["payload"]) for e in a._edges] == \
        [(e._from._data["label"], e._to._data["label"], e._data["payload"]) for e in b._edges]


def test_n4_reproduces_table(tmp_path):
    m = ch7.run(cfg(), os.path.join(EXP, "graphs"), str(tmp_path))
    assert ch7.check_metrics(str(tmp_path / "metrics.json"), os.path.join(EXP, "reference.json")) == []
    assert m["summary"]["cells_agree"] == m["summary"]["cells"] == 12 * 9


def test_n16_differs_from_table(tmp_path):
    m = ch7.run(cfg(), os.path.join(EXP, "graphs"), str(tmp_path), sizes=[20], n=16)
    c = m["rows"][0]["calc"]
    assert (c["mc"]["E"], c["mp"]["E"]) == (220, 222)


def test_run_records_cluster_sizes(tmp_path):
    m = ch7.run(cfg(), os.path.join(EXP, "graphs"), str(tmp_path), sizes=[20])
    c = m["rows"][0]["calc"]
    assert c["mc"]["cluster_sizes"] == [1, 1, 1, 17]
    assert c["mp"]["cluster_sizes"] == [3, 5, 6, 6]
