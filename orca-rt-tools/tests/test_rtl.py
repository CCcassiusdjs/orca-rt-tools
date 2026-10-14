"""Runs the RTL tests in pkt-sim/tests/rtl with open-source simulators
(Verilator, GHDL, Icarus). Each testbench prints "PASS <name>"."""
import os
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT

RTL = os.path.join(REPO_ROOT, "pkt-sim", "tests", "rtl")

TESTS = {
    "tb_ddma_send": "verilator",     # DDMA send handshake under backpressure, send with concurrent reception
    "tb_ddma_recv": "verilator",     # DDMA reception timing and destination check
    "tb_hermes_local": "ghdl",       # Hermes LOCAL to LOCAL route and zero-load latency
    "tb_tcd": "verilator",           # TCD hyperperiod counter
    "tb_manycore_pe": "verilator",   # PE address labels, register read, reset of the counters, ITER marker
    "tb_release": "verilator",       # release generator in cycles, clock half period in fs
    "tb_cpu_cycles": "ghdl",         # cycles per instruction (bound of the instrumentation writes)
    "tb_release_mask": "verilator",  # release generator on the PEs of RELEASE_MASK (4x4 and 2x2)
    "tb_release_mask_4x5": "verilator",  # the same on the 4x5 mesh of experiments/multiapp
    "tb_cpu_irq": "ghdl",            # interrupt return of _isr with and without nested interrupts
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
    if name == "tb_cpu_irq":
        # a handler that enables interrupts before it returns lets a second
        # interrupt corrupt the return of _isr (UCX_ISR_NO_NESTING avoids it)
        assert "NESTED tb_cpu_irq MODE=1" in r.stdout, out[-4000:]
    if name == "tb_manycore_pe":
        # the printed iteration markers have the format of the trace parser
        from rttools.tui.model import parsers
        iters = [m.groups()[1:] for m in map(parsers.RE_ITER.match, r.stdout.splitlines()) if m]
        assert iters == [("2-1", "begin", "E", "5"), ("2-1", "end", "J", "70000")], out[-4000:]
