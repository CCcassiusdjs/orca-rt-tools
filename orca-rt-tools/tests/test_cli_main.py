"""Fixes 1 and 2 (rttools/__main__.py).

1. Optional command-line parameters: the assignments inside
   main() created local variables and raised UnboundLocalError with fewer
   than 7 arguments.
2. Exit code: main() returned 1 on a usage error, but the process
   ended with 0.
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
