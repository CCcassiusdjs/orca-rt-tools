"""Command line of rttools (rttools/__main__.py).

1. Optional command-line parameters: main() accepts 3 to 7 arguments and
   applies each optional one to the configuration.
2. Exit code: a usage error ends the process with the nonzero return
   value of main().
"""
import shutil
import os

import pytest

from tests.conftest import run_module, REPO_ROOT

APP = os.path.join(REPO_ROOT, "apps", "sample-graph-a", "SAMPLE_GRAPH.csv")
MAP = os.path.join(REPO_ROOT, "apps", "sample-graph-a", "SAMPLE_GRAPH-ONTO-hermes2x2.map")
NOC = os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml")


@pytest.fixture
def inputs(tmp_path):
    for f in (APP, MAP, NOC):
        shutil.copy(f, tmp_path)
    return tmp_path, ["SAMPLE_GRAPH.csv", "SAMPLE_GRAPH-ONTO-hermes2x2.map", "hermes-2x2.gml"]


@pytest.mark.parametrize("extra", [
    ["1000000"],
    ["1000000", "1"],
    ["1000000", "1", "2000"],
    ["1000000", "1", "2000", "False"],
])
def test_optional_args_do_not_raise(inputs, extra):
    cwd, files = inputs
    r = run_module("rttools", *files, *extra, cwd=str(cwd), timeout=600)
    assert "UnboundLocalError" not in r.stderr, r.stderr[-2000:]
    assert r.returncode == 0, r.stderr[-2000:]


def test_optional_args_are_applied():
    from rttools.__main__ import parse_args
    cfg = parse_args(["a", "m", "n", "123", "7", "9", "False"])
    assert cfg["frequency"] == 123
    assert cfg["pruning_factor"] == 7
    assert cfg["fail_threshold"] == 9
    assert cfg["optimize"] is False
    cfg = parse_args(["a", "m", "n"])
    assert cfg["frequency"] is None
    assert cfg["optimize"] is True


def test_usage_error_returns_nonzero():
    r = run_module("rttools", "only_one_arg")
    assert r.returncode != 0


def test_fixed_frequency_zero_hyperperiod_exits_cleanly(tmp_path):
    """Non-optimized mode with hyperperiod 0 (periods shorter than one cycle
    at the given frequency): the CLI ended with a TypeError when unpacking
    schedule = None."""
    app_dir = os.path.join(REPO_ROOT, "apps", "synthetic-flow-a")
    for f in ("SyntheticA.csv", "Synthetic-Flow-A-ONTO-hermes2x2.map"):
        shutil.copy(os.path.join(app_dir, f), tmp_path)
    shutil.copy(NOC, tmp_path)
    r = run_module("rttools", "SyntheticA.csv", "Synthetic-Flow-A-ONTO-hermes2x2.map",
                   "hermes-2x2.gml", "1", "1", "500", "False", cwd=str(tmp_path))
    assert "Traceback" not in r.stderr, r.stderr[-2000:]
    assert r.returncode == 1


@pytest.mark.parametrize("value,ni,text", [
    (None, None, "o_i = L0 + 20 (m + 1) + 15169 ("), ("off", None, "o_i = L0 + 15169 ("),
    ("bound", None, "o_i = L0 + 20 (m + 1) + 15169 ("), ("3", None, "o_i = L0 + 3 (m + 1) + 15169 ("),
    (None, "off", "o_i = L0 + 20 (m + 1) ("), ("off", "off", "o_i = L0 ("), ("off", "7", "o_i = L0 + 7 (")])
def test_link_occupancy_follows_header_wait(inputs, monkeypatch, value, ni, text):
    """o_i = L0 + w_h (m + 1) + w_NI: w_h of RTTOOLS_HEADER_WAIT and w_NI of
    RTTOOLS_NI (default tt, w_NI = NI_WAIT_CYCLES = 15169)."""
    d, files = inputs
    if value is not None:
        monkeypatch.setenv("RTTOOLS_HEADER_WAIT", value)
    if ni is not None:
        monkeypatch.setenv("RTTOOLS_NI", ni)
    r = run_module("rttools", *files, "1000000", cwd=str(d))
    assert text in r.stdout + r.stderr
    assert ("network interface off" if ni == "off" else "network interface as a resource") in r.stdout + r.stderr


def test_bad_network_interface_model_returns_nonzero(inputs, monkeypatch):
    d, files = inputs
    monkeypatch.setenv("RTTOOLS_NI", "x")
    r = run_module("rttools", *files, "1000000", cwd=str(d))
    assert r.returncode != 0
    assert "RTTOOLS_NI" in r.stdout + r.stderr


def test_bad_header_wait_returns_nonzero(inputs, monkeypatch):
    d, files = inputs
    monkeypatch.setenv("RTTOOLS_HEADER_WAIT", "-4")
    r = run_module("rttools", *files, "1000000", cwd=str(d))
    assert r.returncode != 0
    assert "RTTOOLS_HEADER_WAIT" in r.stdout + r.stderr
