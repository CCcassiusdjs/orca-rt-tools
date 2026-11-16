"""crt0.s of UCX-OS (pkt-sim/software/ucx-os/arch/riscv/hf-riscv-e) in every
image: _isr returns an interrupt taken inside its own return (after the sb
that enables interrupts, before the jump) to the address of that return,
and _interrupt_set(0) reads IRQ_STATUS back until it is 0 (an interrupt
raised before the store that disables interrupts is taken after it;
pkt-sim/tests/rtl/tb_cpu_irq.vhd, modes 2 and 3). The assembler symbols
UCX_ISR_NO_RETURN_GUARD and UCX_ISR_NO_DI_READBACK (CRT0 of
experiments/exp23/build_sw.sh and simulate.sh) build the crt0.s of the
earlier images; the stored runs carry clock.crt0 = plain."""
import json
import os
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from tests.test_isr_nesting import PLAIN_ASDEFS, disassembly, make
from rttools.paper import exp23

UCX = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os")
APP_DIR = os.path.join(UCX, "app")
EXP = os.path.join(REPO_ROOT, "experiments")
IMAGES = os.path.join(EXP, "wcet", "images")


def test_crt0_sources():
    with open(os.path.join(UCX, "arch", "riscv", "hf-riscv-e", "crt0.s")) as f:
        crt0 = f.read()
    isr = crt0[crt0.index("_isr:"):crt0.index("_interrupt_set:")]
    assert ".ifndef UCX_ISR_NO_RETURN_GUARD" in isr and "lw\ta5, 36(sp)" in isr
    assert ".Lisr_resume:" in isr and "_isr_resume" not in crt0.replace(".Lisr_resume", "")
    di = crt0[crt0.index("_interrupt_set:"):crt0.index("setjmp:")]
    assert ".ifndef UCX_ISR_NO_DI_READBACK" in di and di.count("\tnop\n") == 6 and "lw\ta3, 0(a1)" in di
    with open(os.path.join(UCX, "Makefile")) as f:
        mk = f.read()
    assert "TT_ASDEFS" not in mk and "UCX_ISR_RETURN_GUARD" not in mk


def test_crt0_rule():
    assert exp23.crt0_rule(None) == "plain"
    assert exp23.crt0_rule({}) == "plain"
    assert exp23.crt0_rule({"repo_tag": "r11-rc3", "app": "car_full"}) == "plain"
    assert exp23.crt0_rule({"repo_tag": "r11-rc4", "app": "car_full"}) == "guard"
    assert exp23.crt0_rule({"repo_tag": "r11-rc4", "app": "weird_a"}) == "plain"
    for v in exp23.CRT0_RULES:
        assert exp23.crt0_rule({"crt0": v, "repo_tag": "r11-rc4", "app": "car_full"}) == v
    with pytest.raises(ValueError):
        exp23.crt0_rule({"crt0": "other"})


@pytest.mark.parametrize("env,line,asdefs", [
    ({}, "crt0=guard_readback", None),
    ({"ISR_NESTING": "1"}, "crt0=plain", "UCX_ASDEFS=" + PLAIN_ASDEFS),
    ({"CRT0": "plain"}, "crt0=plain", "UCX_ASDEFS=" + PLAIN_ASDEFS),
    ({"CRT0": "guard"}, "crt0=guard", "UCX_ASDEFS=--defsym UCX_ISR_NO_DI_READBACK=1"),
    ({"CRT0": "other"}, None, None),
])
def test_simulate_crt0_line(tmp_path, env, line, asdefs):
    """simulate.sh passes CRT0 to build_sw.sh (UCX_ASDEFS of make) and
    writes crt0=<value> in RUN_INFO; an unknown value stops with status 2."""
    from tests.test_simulate_options import stub_repo
    repo, e, log = stub_repo(tmp_path)
    e = {k: v for k, v in e.items() if k not in ("CRT0", "ISR_NESTING")}
    sh = str(repo / "experiments" / "exp23" / "simulate.sh")
    r = subprocess.run(["bash", sh, str(tmp_path / "o"), "1000000"], capture_output=True, text=True,
                       env={**e, **env})
    if line is None:
        assert r.returncode == 2 and "CRT0 must be" in r.stderr
        return
    assert r.returncode == 0, r.stdout + r.stderr
    info = (tmp_path / "o" / "RUN_INFO").read_text()
    assert f"\n{line}\n" in info, info
    assert info.index("\nisr=") < info.index("\ncrt0=") < info.index("\nrelease=")
    assert exp23.crt0_rule(exp23.read_run_info(str(tmp_path / "o" / "RUN_INFO"))) == line.split("=")[1]
    made = log.read_text()
    if asdefs:
        assert made.count(asdefs) == 2, made          # incl and the application
    else:
        assert "UCX_ASDEFS" not in made, made


RUNS = [
    ("exp23/logs/D.events.txt", "exp23/reference_D.json"),  # anon:drop-line
    ("exp23/logs/E.events.txt", "exp23/reference_E.json"),  # anon:drop-line
    ("exp23/logs/F.events.txt", "exp23/reference_head.json"),
    ("exp23/logs/G.events.txt", "exp23/reference_G.json"),
    ("exp23/logs/H.events.txt", "exp23/reference_H.json"),
    ("exp23/logs/TG.events.txt", "exp23/reference_TG.json"),
    ("exp23/logs/TH.events.txt", "exp23/reference_TH.json"),
    ("car-v-rtl/logs/CV.events.txt", "car-v-rtl/reference_CV.json"),
    ("car-v-rtl/logs/CV2.events.txt", "car-v-rtl/reference_CV2.json"),
    ("car-v-rtl/logs/TCV.events.txt", "car-v-rtl/reference_TCV.json"),
    ("multiapp/logs/MA.events.txt", "multiapp/reference_MA_CARV.json"),
    ("multiapp/logs/MA.events.txt", "multiapp/reference_MA_E.json"),
    ("multiapp/logs/TMA.events.txt", "multiapp/reference_TMA_CARV.json"),
    ("multiapp/logs/TMA.events.txt", "multiapp/reference_TMA_E.json"),
    ("wcet/logs/W1.events.txt", "wcet/reference_W1.json"),
    ("wcet/logs/W2.events.txt", "wcet/reference_W2.json"),
    ("car-full/logs/CF.events.txt", "car-full/reference_CF.json"),
    ("car-full/logs/CF2.events.txt", "car-full/reference_CF2.json"),
]


@pytest.mark.parametrize("log,ref", RUNS)
def test_stored_runs_have_the_previous_crt0(log, ref):
    """No stored run has the crt0 line in its RUN_INFO (A to E: no
    RUN_INFO): the crt0.s up to tag r11-rc3, and the reference of each
    states clock.crt0 = plain (rtlapp.clock.crt0 for W1 and W2)."""
    path = exp23.run_info_path(os.path.join(EXP, log))
    info = exp23.read_run_info(path) if path else None
    assert "crt0" not in (info or {}) and exp23.crt0_rule(info) == "plain"
    with open(os.path.join(EXP, ref)) as f:
        flat = exp23.flatten(json.load(f))
    assert [v for k, v in flat.items() if k.endswith("clock.crt0")] == ["plain"]


def test_stored_run_cf2(tmp_path):
    """make -C experiments/car-full check-cf2: run CF2 (tag r11-rc3) against
    reference_CF2.json; the six jobs that loop on the jalr of the return of
    _isr (PR 408) stay unfinished, on four PEs."""
    from rttools.paper import rtlmr
    d = os.path.join(EXP, "car-full")
    app = os.path.join(REPO_ROOT, "apps", "car-full")
    m = rtlmr.analyze(os.path.join(d, "logs", "CF2.events.txt"), os.path.join(APP_DIR, "car_full.json"),
                      os.path.join(app, "car-full.csv"), os.path.join(app, "car-full-ONTO-hermes4x4.map"),
                      str(tmp_path))
    assert exp23.check(str(tmp_path / "metrics.json"), os.path.join(d, "reference_CF2.json")) == []
    assert (m["clock"]["isr"], m["clock"]["crt0"]) == ("no_nesting", "plain")
    assert m["progress"]["stalled_tasks"] == ["BFE3", "DIRC", "FDF1", "OBMG", "TPMS", "VIBS"]
    assert m["progress"]["stalled_pes"] == ["0-1", "0-2", "1-2", "3-0"]
    assert m["phases"]["jobs_begun_twice_in_a_phase"] == 0 and m["monitor"]["errors"] == 0
    assert m["releases"]["count"] == 244


def test_build_default_and_plain_crt0(tmp_path):
    """Default image: _isr with the return test (lw a5, 36(sp)) and
    _interrupt_set with the read back (lw a3, 0(a1)); with the symbols of
    CRT0=plain, neither, and the image is the one of images/isr (crt0.s of
    tag r11-rc3) when the compiler is the one of that image; the default
    image is the one of images/guard. Both builds take INJECTION=finish, the
    injection of the stored images (the default, tt, adds lib/noc_tt.c)."""
    from tests.test_ucxgen_carv import toolchain
    pytest.importorskip("elftools")
    path = toolchain(tmp_path)
    if path is None:
        pytest.skip("riscv64-elf toolchain ausente")
    ucx = tmp_path / "ucx-os"
    shutil.copytree(UCX, ucx, ignore=shutil.ignore_patterns("*.o", "*.pack", "image.*", "code.txt"))
    from elftools.elf.elffile import ELFFile

    def sections(p):
        with open(p, "rb") as fh:
            e = ELFFile(fh)
            return {s: e.get_section_by_name(s).data() for s in (".text", ".data")}
    built = open(os.path.join(IMAGES, "guard", "BUILD.txt")).readline().split(" (container")[0]
    gcc = subprocess.run(["riscv64-elf-gcc", "--version"], capture_output=True, text=True,
                         env={**os.environ, "PATH": path}).stdout.splitlines()[0]
    same_gcc = gcc.split(" ", 1)[-1].strip() == built.split(" ", 1)[-1].strip()
    for asdefs, guard, stored in ((None, True, "guard"), (PLAIN_ASDEFS, False, "isr")):
        elf = make(ucx, path, "weird_a", asdefs=asdefs, injection="finish", f_clk="434912000")
        f = disassembly(path, elf)
        isr, di = "\n".join(f["_isr"]), "\n".join(f["_interrupt_set"])
        assert ("lw\ta5,36(sp)" in isr) == guard and ("lw\ta3,0(a1)" in di) == guard
        assert "_isr_resume" not in f and ".Lisr_resume" not in f
        if same_gcc:
            assert sections(elf) == sections(os.path.join(IMAGES, stored, "weird_a.elf")), stored


def test_static_kernel_terms_of_crt0():
    """rttools.wcet on the images of this crt0.s (experiments/wcet/images/
    guard) against images/isr (crt0.s of tag r11-rc3), same kernel, compiler
    and clocks: the return test adds the same cycles to every interrupt term
    (send, tick, release; twice in receive, whose two handlers also call
    _di at their entry), and dispatch gains the read back of the two
    _interrupt_set calls of yield (state unknown at the restore). t(V_k) of
    E stays below the CSV costs."""
    pytest.importorskip("elftools")
    pytest.importorskip("scipy")
    from rttools.wcet.__main__ import load_spec, run_spec
    got = {}
    for app, sp in (("weird_a", "weird_a_H.json"), ("weird_a_data", "weird_a_H.json"), ("car_v", "car_v.json"),
                    ("wcet_e", "wcet_e.json")):
        spec = load_spec(os.path.join(EXP, "wcet", "specs", sp))
        spec["annotations"] = [a for a in spec["annotations"] if not a.endswith("H.image.json")]
        new = run_spec(spec, os.path.join(IMAGES, "guard", f"{app}.elf"))
        old = run_spec(spec, os.path.join(IMAGES, "isr", f"{app}.elf"))
        got[app] = new
        k, o = new["kernel"], old["kernel"]
        g = k["send_isr"] - o["send_isr"]
        assert g == 8, (app, k, o)
        assert k["tick"] - o["tick"] == g and k["release"] - o["release"] == g
        assert k["receive_isr"] - o["receive_isr"] > 2 * g
        assert k["dispatch"] - o["dispatch"] == 26
    cfg = exp23.load_config(os.path.join(EXP, "exp23", "config.json"))
    cfg["clock_hz"] = 434912000
    est = exp23.estimates(cfg)
    for cluster, tasks in exp23.dispatch_sequences(cfg).items():
        assert sum(got["weird_a"]["tasks"][v]["t"] for v in tasks) <= est[cluster]
