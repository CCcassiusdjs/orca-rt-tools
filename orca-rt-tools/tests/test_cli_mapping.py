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


# f* of application E: the default network-interface model (tt, w_NI =
# NI_WAIT_CYCLES and the network interface of each PE as a resource) and
# the model off of the stored references (RTTOOLS_NI=off, experiments/exp23
# make frequency)
F_STAR = {None: "413921356.2011719Hz (413.9 MHz)", "off": "327690124.51171875Hz (327.7 MHz)"}


@pytest.mark.parametrize("ni", [None, "off"])
@pytest.mark.parametrize("mapping", [MAP, "spiral"])
def test_app_e_minimum_frequency(work, mapping, ni, monkeypatch):
    """f* from the bisection (phase model), f_CPU from the CPU test and the
    maximum; experiments/exp23 make frequency (RTTOOLS_NI=off) keeps the
    numbers of the model off (default link occupancy o_i = L0 + 20 (m + 1)
    + w_NI)."""
    if ni:
        monkeypatch.setenv("RTTOOLS_NI", ni)
    r = run(work, mapping, "500000000")
    assert r.returncode == 0, r.stderr[-2000:]
    # dispatch order of the kernel rule (E, H, I and J, G): I->J sets f*
    assert "Network frequency f* = " + F_STAR[ni] in r.stdout
    assert ("w_NI = 15169 cycles" if ni is None else "network interface off") in r.stdout
    assert "CPU frequency f_CPU = 434900000.0Hz (434.9 MHz)" in r.stdout
    assert "Minimum frequency max(f*, f_CPU) = 434900000.0Hz (434.9 MHz)" in r.stdout
    # f_CPU > f*: one network evaluation at f_CPU with the phase model
    assert "Network at f_CPU: feasible (5 packets, 0 skipped, hyperperiod 217450 cycles)" in r.stdout
