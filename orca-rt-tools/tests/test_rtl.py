"""Runs the RTL tests in pkt-sim/tests/rtl with open-source simulators
(Verilator, GHDL, Icarus). Each testbench prints "PASS <name>"."""
import os
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT

RTL = os.path.join(REPO_ROOT, "pkt-sim", "tests", "rtl")

TESTS = {
    "tb_ddma_send": "verilator",     # fix 20 (and 21, concurrent reception)
    "tb_ddma_recv": "verilator",     # fixes 21 and 22
    "tb_hermes_local": "ghdl",       # fix 23
    "tb_tcd": "verilator",           # fix 24
    "tb_manycore_pe": "verilator",   # fixes 25 to 27
    "tb_release": "verilator",       # release generator by parameter (4x4 and 2x2)
}


@pytest.mark.parametrize("name", sorted(TESTS))
def test_rtl(name, tmp_path):
    tool = TESTS[name]
    if shutil.which(tool) is None:
        pytest.skip(tool + " ausente")
    r = subprocess.run(["sh", os.path.join(RTL, "run.sh"), name],
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=1200)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-4000:]
    assert ("PASS " + name) in r.stdout, out[-4000:]
    assert "FAIL" not in r.stdout, out[-4000:]
