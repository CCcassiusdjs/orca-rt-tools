"""Bound of the instrumentation writes in the measured CPU time of exp23
(rttools/paper/instrumentation.py): listings of run F, cycles of the
HF-RISC core (pkt-sim/tests/rtl/tb_cpu_cycles.vhd) and the checks of the
alignment."""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from rttools.paper import exp23
from rttools.paper import instrumentation as ins

EXP = os.path.join(REPO_ROOT, "experiments", "exp23")
LST = os.path.join(EXP, "logs", "F.image.lst")
LST_WITHOUT = os.path.join(EXP, "logs", "F.noinstr.lst")
RTL = os.path.join(REPO_ROOT, "pkt-sim", "tests", "rtl")


def cfg():
    # load_config: the application CSV of the config as an absolute path
    # (creation rows of the dispatch order)
    return exp23.load_config(os.path.join(EXP, "config.json"))


@pytest.fixture(scope="module")
def run_f(tmp_path_factory):
    d = tmp_path_factory.mktemp("F")
    return exp23.analyze(os.path.join(EXP, "logs", "F.events.txt"), cfg(), str(d),
                         listing=LST, listing_without=LST_WITHOUT), str(d)


# ------------------------------------------------------------ run F

def test_event_costs_of_run_f(run_f):
    m, _ = run_f
    i = m["instrumentation"]
    assert i["cycles_per_class"] == {"alu": 1, "load": 3, "store": 3, "jump": 3, "branch": 3}
    assert {k: (e["instructions"], e["cycles"], e["worst_function"]) for k, e in i["events"].items()} == {
        "dispatch": (42, 100, "krnl_schedule"), "send": (23, 55, "ucx_noc_send"),
        "receive": (8, 20, "irq3_handler")}
    f = i["functions"]
    assert f["krnl_schedule"]["calls"] == ["set_cacc", "set_counter_1", "set_counter_2"]
    assert f["krnl_schedule"]["rule"] == "every_return_path"
    # the local delivery of ucx_noc_send (set_counter_4) is part of the charge of the send
    assert f["ucx_noc_send"]["rule"] == "every_return_path" and list(f["ucx_noc_send"]["charges"]) == ["send"]
    assert f["irq3_handler"]["rule"] == "block" and list(f["irq3_handler"]["charges"]) == ["receive"]
    assert all(v == {"instructions": 4, "cycles": 10} for v in i["callees"].values())


def test_bound_per_cluster_of_run_f(run_f):
    m, _ = run_f
    c = m["instrumentation"]["clusters"]
    assert {k: v["events_per_iteration_at_max"] for k, v in c.items()} == {
        "ABDF": {"dispatch": 5.0, "send": 5.0, "receive": 3.0},
        "C": {"dispatch": 1.5, "send": 1.0, "receive": 1.0},
        "EHI": {"dispatch": 2.5, "send": 4.0, "receive": 3.0},
        "GJ": {"dispatch": 2.5, "send": 1.0, "receive": 4.0}}
    assert {k: v["max_cycles"] for k, v in c.items()} == {"ABDF": 835, "C": 225, "EHI": 530, "GJ": 385}
    assert {k: round(v["max_percent"], 2) for k, v in c.items()} == {"ABDF": 0.58, "C": 0.28, "EHI": 0.44, "GJ": 0.21}
    assert (m["instrumentation"]["max_cluster"], round(m["instrumentation"]["max_percent"], 2)) == ("ABDF", 0.58)
    # the bound stays below the overestimation of every cluster
    for r in m["tab83"]["rows"]:
        assert c[r["cluster"]]["max_percent"] < r["difference_percent"]


def test_values_and_reference_of_run_f(run_f):
    m, d = run_f
    assert exp23.check(os.path.join(d, "metrics.json"), os.path.join(EXP, "reference_head.json")) == []
    values = open(os.path.join(d, "values.tex")).read()
    for line in ("\\newcommand{\\ExpInstrumentationDispatchCycles}{100}",
                 "\\newcommand{\\ExpInstrumentationSendCycles}{55}",
                 "\\newcommand{\\ExpInstrumentationReceiveCycles}{20}",
                 "\\newcommand{\\ExpAbdfInstrumentationPercent}{0.58}",
                 "\\newcommand{\\ExpGjInstrumentationCycles}{385}",
                 "\\newcommand{\\ExpInstrumentationMaxPercent}{0.58}",
                 "\\newcommand{\\ExpInstrumentationMaxCluster}{ABDF}"):
        assert line in values


def test_without_listing_no_bound(tmp_path):
    if not os.path.exists(os.path.join(EXP, "logs", "D.events.txt")):
        pytest.skip("run D is not part of this copy of the artifact")
    m = exp23.analyze(os.path.join(EXP, "logs", "D.events.txt"), cfg(), str(tmp_path), join="any3")
    assert "instrumentation" not in m
    assert "Instrumentation" not in open(tmp_path / "values.tex").read()
    with pytest.raises(ValueError, match="--listing-without"):
        exp23.analyze(os.path.join(EXP, "logs", "F.events.txt"), cfg(), str(tmp_path), listing=LST)


def test_software_record_of_run_f():
    rec = dict(l.split("=", 1) for l in open(os.path.join(EXP, "logs", "F.software.txt")).read().splitlines()
               if l and not l.startswith("#"))
    assert rec["gcc"] == "riscv64-elf-gcc (Arch Linux Repositories) 12.2.0"
    run_info = open(os.path.join(EXP, "logs", "F.RUN_INFO")).read()
    assert "gcc=" + rec["gcc"] + "\n" in run_info
    # the image with the writes is the image of tag exp23-F
    assert rec["with_image.bin"] == rec["exp23-F_archive_image.bin"]
    import hashlib
    for key, path in (("with_image.lst", LST), ("without_image.lst", LST_WITHOUT)):
        assert hashlib.sha256(open(path, "rb").read()).hexdigest() == rec[key]


# ------------------------------------------------------- cycle table

@pytest.mark.skipif(shutil.which("ghdl") is None, reason="ghdl ausente")
def test_cycles_of_config_match_the_core(tmp_path):
    r = subprocess.run(["sh", os.path.join(RTL, "run.sh"), "tb_cpu_cycles"], env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0 and "PASS tb_cpu_cycles" in r.stdout, (r.stdout + r.stderr)[-3000:]
    cpi = {m.group(1): int(m.group(2)) for m in re.finditer(r"^CPI (\S+) (\d+)$", r.stdout, re.M)}
    c = cfg()["instrumentation"]["cycles"]
    assert cpi["alu"] == cpi["lui"] == c["alu"]
    assert cpi["lw"] == cpi["lhu"] == cpi["lbu"] == cpi["lw_mmio"] == c["load"]
    assert cpi["sw"] == cpi["sh"] == cpi["sb"] == cpi["sw_mmio"] == c["store"]
    assert cpi["jal"] == c["jump"]
    assert (cpi["branch_taken"], cpi["branch_not_taken"]) == (c["branch_taken"], c["branch_not_taken"])
    # sequences cost the sum of their classes (no stall between them)
    assert cpi["call_ret"] == 2 * c["jump"]
    assert cpi["call_body"] == 2 * c["jump"] + c["alu"] + c["load"] + c["store"]
    assert cpi["inc64"] == 4 * c["alu"] + 2 * c["load"] + 2 * c["store"]


# ------------------------------------------- rules on small listings

def listing(tmp_path, name, funcs):
    """objdump-style listing; funcs: {name: [(mnemonic, operands)]} at
    consecutive addresses; operands may use {L<k>} for the address of
    instruction k of the same function and {F:<name>} for a function."""
    addr, base = 0x1000, {}
    for f, insns in funcs.items():
        base[f] = addr
        addr += 4 * len(insns) + 0x100
    lines = ["x.elf:     file format elf32-littleriscv", "", "Disassembly of section .text:", ""]
    for f, insns in funcs.items():
        lines.append(f"{base[f]:08x} <{f}>:")
        for k, (mn, op) in enumerate(insns):
            op = re.sub(r"\{L(\d+)\}", lambda m: f"{base[f] + 4 * int(m.group(1)):x} <{f}+0x{4 * int(m.group(1)):x}>", op)
            op = re.sub(r"\{F:(\w+)\}", lambda m: f"{base[m.group(1)]:x} <{m.group(1)}>", op)
            lines.append(f"{base[f] + 4 * k:8x}:\t00000013          \t{mn}\t{op}")
        lines.append("")
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n")
    return str(p)


SET = [("lui", "a4,0x40003"), ("lw", "a4,-180(a4)"), ("sw", "a0,0(a4)"), ("jalr", "zero,0(ra)")]
CFG = {"callees": ["set_a", "set_b"], "events": {"dispatch": "set_a", "receive": "set_b"},
       "cycles": {"alu": 1, "load": 3, "store": 3, "jump": 3, "branch_taken": 3, "branch_not_taken": 1}}


def test_every_return_path_charges_the_whole_function(tmp_path):
    with_ = {"set_a": SET, "set_b": SET,
             "f": [("addi", "sp,sp,-4"), ("sw", "ra,0(sp)"), ("jal", "ra,{F:set_a}"),
                   ("beq", "a0,zero,{L5}"), ("jal", "ra,{F:set_b}"),
                   ("lw", "ra,0(sp)"), ("addi", "sp,sp,4"), ("jalr", "zero,0(ra)")]}
    without = {"f": [("beq", "a0,zero,{L1}"), ("jalr", "zero,0(ra)")]}
    c = ins.event_costs(listing(tmp_path, "w.lst", with_), listing(tmp_path, "o.lst", without), CFG)
    f = c["functions"]["f"]
    assert f["rule"] == "every_return_path"
    # unmatched: addi, sw, jal, jal, lw, addi (6, 1+3+3+3+3+1 = 14) + two bodies (2 x 10)
    assert (f["instructions"], f["cycles"]) == (6 + 8, 14 + 20)
    assert c["events"]["dispatch"]["cycles"] == 34 and c["events"]["receive"]["cycles"] == 0


def test_block_rule_charges_the_block_of_the_write(tmp_path):
    with_ = {"set_a": SET, "set_b": SET,
             "g": [("beq", "a0,zero,{L4}"), ("lhu", "a0,10(s1)"), ("jal", "ra,{F:set_b}"),
                   ("jalr", "zero,0(ra)"), ("jalr", "zero,0(ra)")]}
    without = {"g": [("beq", "a0,zero,{L2}"), ("jalr", "zero,0(ra)"), ("jalr", "zero,0(ra)")]}
    c = ins.event_costs(listing(tmp_path, "w.lst", with_), listing(tmp_path, "o.lst", without), CFG)
    g = c["functions"]["g"]
    assert g["rule"] == "block"
    assert g["charges"] == {"receive": {"instructions": 2 + 4, "cycles": 3 + 3 + 10}}


def test_unmatched_instruction_in_a_loop_is_refused(tmp_path):
    with_ = {"set_a": SET, "set_b": SET,
             "h": [("jal", "ra,{F:set_a}"), ("addi", "a0,a0,-1"), ("addi", "a1,a1,1"),
                   ("bne", "a0,zero,{L1}"), ("jalr", "zero,0(ra)")]}
    without = {"h": [("addi", "a0,a0,-1"), ("bne", "a0,zero,{L0}"), ("jalr", "zero,0(ra)")]}
    with pytest.raises(ValueError, match="inside a loop"):
        ins.event_costs(listing(tmp_path, "w.lst", with_), listing(tmp_path, "o.lst", without), CFG)


def test_other_functions_must_not_change(tmp_path):
    with_ = {"set_a": SET, "set_b": SET, "f": [("jal", "ra,{F:set_a}"), ("jalr", "zero,0(ra)")],
             "k": [("addi", "a0,a0,1"), ("jalr", "zero,0(ra)")]}
    without = {"f": [("jalr", "zero,0(ra)")], "k": [("addi", "a0,a0,2"), ("addi", "a0,a0,1"), ("jalr", "zero,0(ra)")]}
    with pytest.raises(ValueError, match="differ between the listings: k"):
        ins.event_costs(listing(tmp_path, "w.lst", with_), listing(tmp_path, "o.lst", without), CFG)


def test_instrumentation_function_must_be_straight_line(tmp_path):
    bad = [("beq", "a0,zero,{L2}"), ("sw", "a0,0(a4)"), ("jalr", "zero,0(ra)")]
    with_ = {"set_a": bad, "set_b": SET, "f": [("jal", "ra,{F:set_a}"), ("jalr", "zero,0(ra)")]}
    without = {"f": [("jalr", "zero,0(ra)")]}
    with pytest.raises(ValueError, match="not straight-line"):
        ins.event_costs(listing(tmp_path, "w.lst", with_), listing(tmp_path, "o.lst", without), CFG)


def test_instruction_classes():
    assert [ins.insn_class(m) for m in ("lui", "sltu", "lhu", "sb", "bgeu", "jalr", "ret")] == \
        ["alu", "alu", "load", "store", "branch", "jump", "jump"]
    with pytest.raises(ValueError, match="csrrw"):
        ins.insn_class("csrrw")


# --------------------------------------------- build of this tree

@pytest.mark.skipif(shutil.which("riscv64-elf-gcc") is None, reason="riscv64-elf-gcc ausente")
def test_build_of_this_tree_gives_the_stored_costs(tmp_path):
    """build_sw.sh with and without the writes (make software): the costs
    of the events equal those of the stored listings of run F when the
    compiler is riscv64-elf-gcc 12.2.0 (logs/F.software.txt). The image of
    run F: the data-driven application (APP=weird_a_data) with the injection
    at the end of each task (INJECTION=finish)."""
    run_f = {"APP": "weird_a_data", "INJECTION": "finish"}
    for v, extra in (("with", {}), ("without", {"UCX_CFLAGS": "-DUCX_NO_INSTRUMENTATION"})):
        r = subprocess.run(["bash", os.path.join(EXP, "build_sw.sh"), str(tmp_path / v)],
                           env={**os.environ, **run_f, **extra}, capture_output=True, text=True, timeout=1200)
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    img = os.path.join("pkt-sim", "software", "ucx-os", "build", "target", "image.lst")
    got = ins.event_costs(str(tmp_path / "with" / img), str(tmp_path / "without" / img), cfg()["instrumentation"])
    ref = ins.event_costs(LST, LST_WITHOUT, cfg()["instrumentation"])
    if (tmp_path / "with" / "gcc.txt").read_text().strip() == "riscv64-elf-gcc (Arch Linux Repositories) 12.2.0":
        assert got["events"] == ref["events"]
    else:
        # another compiler: the checks of the module hold and the costs exist
        assert set(got["events"]) == set(ref["events"])
