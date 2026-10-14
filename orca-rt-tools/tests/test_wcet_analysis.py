"""rttools.wcet.analysis and rttools.wcet.ucx on the listing of run H
(application E, riscv64-elf-gcc 12.2.0) with the annotations of
experiments/wcet."""
import os

import pytest

from rttools.wcet import analysis, annotations, image, loopbound, ucx
from rttools.wcet.decode import A0
from tests.conftest import REPO_ROOT

LISTING = os.path.join(REPO_ROOT, "experiments", "exp23", "logs", "H.image.lst")
ANN = [os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "wcet", "ucx-os.json"),
       os.path.join(REPO_ROOT, "experiments", "wcet", "annotations", "weird_a.json"),
       os.path.join(REPO_ROOT, "experiments", "wcet", "annotations", "H.image.json")]


@pytest.fixture(scope="module")
def an():
    return analysis.Analyzer(image.load(LISTING), annotations.Annotations.load(ANN))


def test_ucx_sleep_cycles_by_hand(an):
    # prologue 17 (addi, sw, sw, addi, sw, lw, bge taken), nop 1, header
    # lw + addi + sw + bne = 10 per count (8 for the last, branch not
    # taken), epilogue 12 (two nops, two lw, addi, jalr)
    r = an.function("ucx_sleep", {A0: 1230})
    assert r.cycles == 17 + 1 + 1230 * 10 + 8 + 12
    assert r.loops[0][2:] == (1231, "annotation")


def test_set_iter_mark_matches_tb_cpu_cycles(an):
    # block call_body of tb_cpu_cycles.vhd: jal + lui + lw + sw + jalr = 13
    assert an.function("set_iter_mark").cycles == 13 - 3


def test_counted_and_shift_loops(an):
    r = an.function("__mulsi3")
    assert [(b, s) for _, _, b, s in r.loops] == [(33, "counted")]
    r = an.function("ucx_noc_send", {A0: 1, 11: 2, 13: 1230})
    bounds = {h: (b, s) for _, h, b, s in r.loops}
    assert bounds[0x40001e54] == (16, "counted")          # for (i < MAX_TASKS)
    assert bounds[0x40001e08] == (1, "annotation")        # DDMA idle (ddma_wait)
    assert bounds[0x40001edc] == (5, "annotation")        # enable_receiver (tcb)


def test_loop_without_bound_is_an_error():
    an0 = analysis.Analyzer(image.load(LISTING), annotations.Annotations(
        {"exclude_calls": ["tprintf"]}))
    with pytest.raises(analysis.WcetError, match="no bound"):
        an0.function("ucx_sleep", {A0: 10})


def test_bound_expressions():
    assert loopbound.evaluate("a0 + 1", {A0: 41}) == 42
    assert loopbound.evaluate("max(a0, 3) * 2", {A0: 1}) == 6
    assert loopbound.evaluate("u8(a0 + 1)", {A0: 0x100}, lambda a, w: {0x101: 7}.get(a)) == 7
    with pytest.raises(ValueError, match="unknown"):
        loopbound.evaluate("a1", {A0: 1})
    with pytest.raises(ValueError, match="not allowed"):
        loopbound.evaluate("a0.real", {A0: 1})
    with pytest.raises(ValueError, match="only min"):
        loopbound.evaluate("__import__('os')", {})


def test_kernel_terms(an):
    k = ucx.kernel_terms(an)
    assert k["dispatch"] == k["yield_save"] + k["yield_resume"]
    assert k["yield_resume"] == 8          # bne not taken, lw ra, addi sp, jalr
    assert k["receive_isr"] == k["receive_isr_size"] + k["receive_isr_end"]
    assert {x: k[x] for x in ("dispatch", "tick", "send_isr", "receive_isr", "release")} == \
        {"dispatch": 495, "tick": 1978, "send_isr": 235, "receive_isr": 4180, "release": 1038}


def test_job_of_task_a_covers_the_measured_run(an):
    k = ucx.kernel_terms(an)
    r = ucx.task_cost(an, "task_a", 0, 2, k, source=True)
    assert r["calls"]["ucx_noc_send"] == 2 and r["calls"]["ucx_sleep"] == 1
    assert r["t"] == sum(r["terms"].values())
    # one run of A from its dispatch to the next dispatch in run H: 14,333
    # cycles (paper, Section 7.5); job + dispatch of the static analysis
    run = r["t"] - sum(r["terms"][x] for x in ("send_isr", "receive_isr", "tick", "release"))
    assert 14333 <= run <= 14333 * 1.10


def test_job_of_task_j_receives_one_packet_per_input(an):
    k = ucx.kernel_terms(an)
    r = ucx.task_cost(an, "task_j", 3, 0, k)
    assert r["calls"]["ucx_noc_receive"] == 3 and r["calls"]["ucx_task_yield"] == 1
    assert r["terms"]["receive_isr"] == 3 * k["receive_isr"]
