"""Static WCET of the bodies of rttools.ucxgen --bodies against the cycles of
the HF-RISC RTL (GHDL, pkt-sim/tests/rtl/tb_cpu_trace.vhd on
wcet_bodies.hex): every measured call takes at most the WCET of its
wrapper, and the largest call takes at least 95 % of it."""
import os
import shutil
import subprocess

import pytest

from rttools.paper import wcet as pw
from tests.conftest import REPO_ROOT

RTL = os.path.join(REPO_ROOT, "pkt-sim", "tests", "rtl")
STORED = os.path.join(REPO_ROOT, "experiments", "wcet", "logs", "bodies.trace.txt")


def check(rows):
    assert set(rows) == {"sort", "search", "count"}
    for b, r in rows.items():
        assert r["calls"] == 12
        assert r["sound"], b
        assert r["measured_max"] >= 0.95 * r["wcet_wrapper"], b
        assert r["wcet_body"] < r["wcet_wrapper"]


def test_stored_trace():
    check(pw.bodies(os.path.join(RTL, "wcet_bodies.elf"), STORED))


def test_ghdl_trace(tmp_path):
    if shutil.which("ghdl") is None:
        pytest.skip("ghdl ausente")
    r = subprocess.run(["sh", os.path.join(RTL, "run.sh"), "tb_cpu_trace"],
                       env={**os.environ, "OUT": str(tmp_path)}, capture_output=True, text=True, timeout=1200)
    assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    assert "DONE" in r.stdout and "TIMEOUT" not in r.stdout
    trace = tmp_path / "trace.txt"
    trace.write_text(r.stdout)
    rows = pw.bodies(os.path.join(RTL, "wcet_bodies.elf"), str(trace))
    check(rows)
    # the stored trace is the output of this testbench
    assert [l for l in r.stdout.splitlines() if l.startswith(("MARK", "DONE"))] == \
        [l for l in open(STORED).read().splitlines() if l.startswith(("MARK", "DONE"))]
