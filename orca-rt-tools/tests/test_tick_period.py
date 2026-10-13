"""Tick period of the UCX-OS (hf-riscv-e) against the release period of A
(experiments/exp23/tick_period.py; pkt-sim/tests/rtl/tb_timer1.vhd).

TIMER1 counts from 0 to TIMER1CTC inclusive, one step per 16 cycles:
tick = 16 x (TIMER1CTC + 1). hal.c before this fix wrote
F_CPU / F_TIMER / 16 = 15625 (tick of 250016 cycles against a release
period of 250000); the fix writes 15624."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

from tests.conftest import REPO_ROOT

SCRIPT = os.path.join(REPO_ROOT, "experiments", "exp23", "tick_period.py")
LOG_F = os.path.join(REPO_ROOT, "experiments", "exp23", "logs", "F.events.txt")
RUN_SH = os.path.join(REPO_ROOT, "pkt-sim", "tests", "rtl", "run.sh")


def run(*args, repo=REPO_ROOT):
    r = subprocess.run([sys.executable, "-I", SCRIPT, "--repo", repo, *args, "--json"],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode in (0, 1), r.stdout + r.stderr
    return r.returncode, json.loads(r.stdout)


def copy_sources(tmp_path):
    """Copy of the sources that tick_period.py reads, for edited variants."""
    sys.path.insert(0, os.path.dirname(SCRIPT))
    try:
        import tick_period
    finally:
        sys.path.pop(0)
    for rel in tick_period.PATHS.values():
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(os.path.join(REPO_ROOT, rel), dst)
    return tick_period.PATHS


def edit(path, pattern, repl):
    s = path.read_text()
    t, n = re.subn(pattern, repl, s, flags=re.M)
    assert n >= 1, pattern
    path.write_text(t)


def test_tick_equals_release_period():
    rc, out = run("code")
    v = out["code"]
    assert rc == 0 and out["pass"]
    assert v["timer1ctc"] == 15624
    assert v["prescaler_cycles"] == 16
    assert v["tick_cycles"] == 250000
    assert v["release_period_ns"] * v["f_clk_hz"] // 10 ** 9 == 250000


def test_previous_hal_expression_gives_250016(tmp_path):
    paths = copy_sources(tmp_path)
    edit(tmp_path / paths["hal_c"], r"TIMER1CTC = \(F_CPU / F_TIMER\) / 16 - 1;",
         "TIMER1CTC = (F_CPU / F_TIMER) / 16;")
    rc, out = run("code", repo=str(tmp_path))
    assert rc == 1 and not out["pass"]
    assert out["code"]["timer1ctc"] == 15625
    assert out["code"]["tick_cycles"] == 250016


def test_tick_follows_another_release_period(tmp_path):
    """T = 1 ms (F_TICK = 1000, wake_up_alarm = 1000000 ns): tick of
    T x F_CLK = 500000 cycles, TIMER1CTC = 31249."""
    paths = copy_sources(tmp_path)
    edit(tmp_path / paths["arch_mak"], r"^F_TICK = 2000$", "F_TICK = 1000")
    edit(tmp_path / paths["pe_sv"], r"wake_up_alarm = 500_000;", "wake_up_alarm = 1_000_000;")
    cfg = tmp_path / paths["config"]
    edit(cfg, r'"release_period_s": 0\.0005', '"release_period_s": 0.001')
    rc, out = run("code", repo=str(tmp_path))
    assert rc == 0 and out["pass"]
    assert out["code"]["timer1ctc"] == 31249
    assert out["code"]["tick_cycles"] == 500000


def test_tick_differs_from_release_period(tmp_path):
    """F_TICK = 2000 against wake_up_alarm = 1 ms: the check fails."""
    paths = copy_sources(tmp_path)
    edit(tmp_path / paths["pe_sv"], r"wake_up_alarm = 500_000;", "wake_up_alarm = 1_000_000;")
    rc, out = run("code", repo=str(tmp_path))
    assert rc == 1 and not out["pass"]


def test_log_of_run_f_drifts_16_cycles_per_release():
    """Run F (tick of 250016 cycles): the dispatches of A come every 250016
    cycles and release_to_dispatch grows 16 cycles per release; the same
    range as metrics.json (release_to_dispatch_all_releases)."""
    rc, out = run("log", LOG_F)
    lv = out["log"]
    assert rc == 1 and not out["pass"]
    assert lv["releases"] == 34
    assert lv["dispatch_spacing_cycles"] == {"min": 250016, "max": 250016}
    assert lv["release_to_dispatch_cycles"] == {"min": 1396, "max": 1924}
    assert lv["release_to_dispatch_growth_per_release_cycles"] == pytest.approx(16.0)
    q = [x["request_to_dispatch_cycles"] for x in lv["per_release"]]
    assert all(b - a == 16 for a, b in zip(q, q[1:]))
    assert lv["ack_latency_cycles"] == {"min": 387.5, "max": 389.5}


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="ghdl ausente")
@pytest.mark.parametrize("variant", ["code", "previous"])
def test_rtl_timer1_period(variant, tmp_path):
    """GHDL on peripherals_minimal.vhd with the TIMER1CTC of hal.c: the
    measured tick equals the release period T x F_CLK; with the previous
    expression (TIMER1CTC + 1), it lasts 16 cycles more."""
    _, out = run("code")
    v = out["code"]
    ctc = v["timer1ctc"] if variant == "code" else v["timer1ctc"] + 1
    expect = v["release_period_ns"] * v["f_clk_hz"] // 10 ** 9
    if variant == "previous":
        expect += v["prescaler_cycles"]
    r = subprocess.run(["sh", RUN_SH, "tb_timer1"],
                       env={**os.environ, "OUT": str(tmp_path),
                            "TB_TIMER1_CTC": str(ctc), "TB_TIMER1_EXPECT": str(expect)},
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-4000:]
    assert "PASS tb_timer1" in r.stdout, r.stdout[-4000:]
    ticks = [int(x) for x in re.findall(r"TICK (\d+) cycles", r.stdout)]
    assert ticks and all(t == expect for t in ticks)
