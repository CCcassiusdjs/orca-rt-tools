"""Fixes 3 and 4 (rttools/modules/io/appparser.py).

3. Task table schema: parseTaskRow read only the new schema
   (id, wcet, label); the applications with the old schema (id, period,
   capacity, deadline, label, description), como SyntheticA, SHI2010,
   DCT-Verify and STR2RTS-CFAR, failed in getTaskIdByName. Labels with
   spaces ("Task A") broke the GML without quotes.
4. Temporary file: loadFromFile wrote `.__tmp` to the current
   directory.
"""
import os
import shutil

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.io import appparser

APPS = os.path.join(REPO_ROOT, "apps")


def test_new_schema_sample_graph():
    g, name = appparser.loadFromFile(os.path.join(APPS, "sample-graph-a", "SAMPLE_GRAPH.csv"))
    assert name == "SAMPLE_GRAPH"
    assert g.number_of_nodes() == 10
    assert g.number_of_edges() == 11
    assert g.nodes["A"]["wcet"] == 1230
    assert g.nodes["J"]["wcet"] == 8900


@pytest.mark.parametrize("rel, ntasks, nflows, label", [
    ("synthetic-flow-a/SyntheticA.csv", 4, 5, "Task A"),
    ("shi-2010/SHI2010.csv", None, None, "TPMS"),
    ("str2rts-dct-verify/DCT-Verify.csv", None, None, "AFA"),
    ("str2rts-cfar/STR2RTS-CFAR.csv", None, None, "CMPX"),
])
def test_old_schema_apps(rel, ntasks, nflows, label):
    g, _ = appparser.loadFromFile(os.path.join(APPS, rel))
    assert label in g.nodes
    if ntasks is not None:
        assert g.number_of_nodes() == ntasks
        assert g.number_of_edges() == nflows


def test_old_schema_uses_capacity_as_wcet():
    g, _ = appparser.loadFromFile(os.path.join(APPS, "str2rts-cfar", "STR2RTS-CFAR.csv"))
    assert g.nodes["CMPX"]["wcet"] == 61760


def test_no_tmp_file_in_cwd(tmp_path, monkeypatch):
    """The current directory contains a `.__tmp` directory: the old code
    fails to open that path for writing; the new code does not use the
    current directory."""
    src = os.path.join(APPS, "sample-graph-a", "SAMPLE_GRAPH.csv")
    work = tmp_path / "cwd"
    work.mkdir()
    shutil.copy(src, work)
    (work / ".__tmp").mkdir()
    monkeypatch.chdir(work)
    before = sorted(os.listdir(work))
    g, _ = appparser.loadFromFile("SAMPLE_GRAPH.csv")
    assert g.number_of_nodes() == 10
    assert sorted(os.listdir(work)) == before
