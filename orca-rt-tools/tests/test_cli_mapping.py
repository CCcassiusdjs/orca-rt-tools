"""<map> argument of the command line (rttools/__main__.py): a .map file
or `spiral` (ORT/GCM clustering and Spiral Mapping, thesis Section 8.1).
The command line checks that the mapping puts every task of the
application on exactly one node of the architecture; before, a task
mapped twice or not mapped reached the router (None node)."""
import os
import shutil

import pytest

from tests.conftest import run_module, REPO_ROOT

APP_E = os.path.join(REPO_ROOT, "apps", "synthetic-app-e")
CSV = "synthetic-app-e.csv"
MAP = "synthetic-app-e-ONTO-hermes2x2.map"
NOC = os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml")


@pytest.fixture
def work(tmp_path):
    for f in (os.path.join(APP_E, CSV), os.path.join(APP_E, MAP), NOC):
        shutil.copy(f, tmp_path)
    return tmp_path


def run(cwd, mapping, *extra):
    return run_module("rttools", CSV, mapping, "hermes-2x2.gml", *extra, cwd=str(cwd), timeout=600)


def test_app_e_with_map_file(work):
    r = run(work, MAP, "500000000", "2000", "500", "False")
    assert r.returncode == 0, r.stderr[-2000:]
    assert os.path.exists(work / "results.svg")
    assert "SPIRAL" not in r.stdout


def test_app_e_with_spiral(work):
    r = run(work, "spiral", "500000000", "2000", "500", "False")
    assert r.returncode == 0, r.stderr[-2000:]
    assert "Clustering criterion: MAX_PROC" in r.stdout
    out = work / "synthetic-app-e-SPIRAL-hermes-2x2.map"
    assert out.read_text() == "0:C\n1:A,B,D,F\n2:G,J\n3:E,H,I\n"
    assert os.path.exists(work / "results.svg")


def test_app_e_frequency_search_with_spiral(work):
    r = run(work, "spiral", "500000000")
    assert r.returncode == 0, r.stderr[-2000:]
    assert "Minimum frequency found at" in r.stdout


def test_map_with_a_task_twice_is_rejected(work):
    (work / "old.map").write_text("0:A,B,D,F\n1:C\n2:E,H,I\n3:G,H")
    r = run(work, "old.map", "500000000", "2000", "500", "False")
    assert r.returncode == 1
    assert "task H mapped 2 times (nodes 2, 3)" in r.stdout
    assert "task J not mapped" in r.stdout
    assert "Traceback" not in r.stderr


def test_missing_map_file(work):
    r = run(work, "nothing.map", "500000000", "2000", "500", "False")
    assert r.returncode == 1
    assert "Could not locate file" in r.stdout
