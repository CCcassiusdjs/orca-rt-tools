"""Interrupts of the UCX-OS kernel (pkt-sim/software/ucx-os): every handler
leaves interrupts disabled until the return of _isr (crt0.s returns
through a5, which it does not save; pkt-sim/tests/rtl/tb_cpu_irq.vhd);
dispatch() of the tick does not enable them, yield() restores the state of
its caller and a task starts through _task_start (hal.c). -DUCX_ISR_NESTING
builds the kernel of the runs up to r11 (A to H, CV, CV2, MA, W1, CF)."""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from rttools.paper import exp23

UCX = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os")
APP_DIR = os.path.join(UCX, "app")
EXP = os.path.join(REPO_ROOT, "experiments")
GENERATED = ["car_v", "wcet_e", "carv_e", "e_ucx"]


def read(*p):
    with open(os.path.join(UCX, *p)) as f:
        return f.read()


def test_kernel_sources():
    sched = read("kernel", "sched.c")
    assert "#ifdef UCX_ISR_NESTING\n\t\t_interrupt_tick();\n#endif" in sched
    assert sched.count("#if defined(UCX_TICK_RELEASE) || !defined(UCX_ISR_NESTING)") == 2
    noc = read("lib", "noc.c")
    assert noc.count("#ifdef UCX_ISR_NESTING\n  _ei();") == 2 and "UCX_ISR_NO_NESTING" not in noc
    tr = read("lib", "tick_release.c")
    assert "#ifdef UCX_ISR_NESTING\n\t_ei();\n#endif\n}" in tr
    hal = read("arch", "riscv", "hf-riscv-e", "hal.c")
    assert "ctx_p[CONTEXT_RA] = (uint32_t)_task_start;" in hal
    mk = read("Makefile")
    assert "TT_DEFS = -DUCX_APP_IRQ4 -DUCX_APP_TICK -DUCX_NOC_LATEST\n" in mk
    assert "UCX_ISR_NO_NESTING" not in mk


@pytest.mark.parametrize("name", GENERATED + ["car_full"])
def test_generated_release_handlers(name):
    """The release handler of a generated application enables interrupts
    only with UCX_ISR_NESTING (data-driven code; the release by tick and
    the time-triggered code use the handler without _di/_ei)."""
    src = read("app", f"{name}.c")
    h = src[src.index("void irq4_handler(void)"):]
    h = h[:h.index("\n}\n")]
    if name == "car_full":
        assert "_ei()" not in h and "_di()" not in h
    else:
        assert h.count("#ifdef UCX_ISR_NESTING\n  _ei();\n#endif") == 1
        assert h.count("#ifdef UCX_ISR_NESTING\n  _di();\n#endif") == 1


# ---------------------------------------------------------------- RUN_INFO


def test_isr_rule():
    assert exp23.isr_rule({}) == "nesting"
    assert exp23.isr_rule({"isr": "no_nesting"}) == "no_nesting"
    assert exp23.isr_rule(None) == "nesting"
    with pytest.raises(ValueError):
        exp23.isr_rule({"isr": "other"})


def test_simulate_isr_line(tmp_path):
    """simulate.sh writes isr=no_nesting (default) or isr=nesting
    (ISR_NESTING=1, build with -DUCX_ISR_NESTING) in RUN_INFO."""
    from tests.test_simulate_options import stub_repo
    for flag, line in (("0", "isr=no_nesting"), ("1", "isr=nesting")):
        d = tmp_path / flag
        d.mkdir()
        repo, env, log = stub_repo(d)
        sh = str(repo / "experiments" / "exp23" / "simulate.sh")
        r = subprocess.run(["bash", sh, str(d / "o"), "1000000"], capture_output=True, text=True,
                           env={**env, "ISR_NESTING": flag})
        assert r.returncode == 0, r.stdout + r.stderr
        info = (d / "o" / "RUN_INFO").read_text()
        assert f"\n{line}\n" in info, info
        if flag == "1":
            assert "-DUCX_ISR_NESTING" in log.read_text()


@pytest.mark.parametrize("log,ref", [
    ("exp23/logs/D.events.txt", "exp23/reference_D.json"),
    ("exp23/logs/E.events.txt", "exp23/reference_E.json"),
    ("exp23/logs/F.events.txt", "exp23/reference_head.json"),
    ("exp23/logs/G.events.txt", "exp23/reference_G.json"),
    ("exp23/logs/H.events.txt", "exp23/reference_H.json"),
    ("car-v-rtl/logs/CV.events.txt", "car-v-rtl/reference_CV.json"),
    ("car-v-rtl/logs/CV2.events.txt", "car-v-rtl/reference_CV2.json"),
    ("multiapp/logs/MA.events.txt", "multiapp/reference_MA_CARV.json"),
    ("multiapp/logs/MA.events.txt", "multiapp/reference_MA_E.json"),
    ("wcet/logs/W1.events.txt", "wcet/reference_W1.json"),
    ("car-full/logs/CF.events.txt", "car-full/reference_CF.json"),
])
def test_stored_runs_are_of_the_previous_image(log, ref):
    """The stored runs have no isr line in the RUN_INFO (A to E: no
    RUN_INFO), the image of the kernel up to r11, and the reference of each
    states clock.isr = nesting (rtlapp.clock.isr for W1)."""
    path = exp23.run_info_path(os.path.join(EXP, log))
    assert exp23.isr_rule(exp23.read_run_info(path) if path else None) == "nesting"
    with open(os.path.join(EXP, ref)) as f:
        flat = exp23.flatten(json.load(f))
    assert [v for k, v in flat.items() if k.endswith("clock.isr")] == ["nesting"]


# ---------------------------------------------------------------- build


def disassembly(path, elf):
    r = subprocess.run(["riscv64-elf-objdump", "-d", "-Mno-aliases", str(elf)], capture_output=True, text=True,
                       env={**os.environ, "PATH": path})
    assert r.returncode == 0, r.stderr
    funcs, cur = {}, None
    for line in r.stdout.splitlines():
        m = re.match(r"^[0-9a-f]+ <(\w+)>:$", line)
        if m:
            cur = funcs.setdefault(m[1], [])
        elif cur is not None and line.strip():
            cur.append(line)
    return funcs


def calls(funcs, fname, target):
    return sum(1 for ln in funcs.get(fname, []) if re.search(rf"\bjal\b.*<{target}>", ln))


def make(ucx, path, target, cc=None):
    env = {**os.environ, "PATH": path}
    extra = [f"CC={cc}"] if cc else []
    for args in (["make", "-s", "ARCH=riscv/hf-riscv-e", "incl"], ["make", "-s", "clean"],
                 ["make", "-s", *extra, target, "F_CLK=434912000"]):
        r = subprocess.run(args, cwd=ucx, env=env, capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    return ucx / "build" / "target" / "image.elf"


def test_build_default_and_nesting(tmp_path):
    """Default image: no _interrupt_tick in dispatch, one interrupt write
    (_di) in irq2_handler and irq3_handler and none in the release handler,
    yield saves and restores the state, tasks start through _task_start.
    With -DUCX_ISR_NESTING: the handlers and dispatch of the kernel up to
    r11; weird_a_data is then the stored image of the data-driven code
    (experiments/wcet/images/tick/weird_a_data.elf) when the compiler is
    the one of that image."""
    from tests.test_ucxgen_carv import toolchain
    pytest.importorskip("elftools")
    path = toolchain(tmp_path)
    if path is None:
        pytest.skip("riscv64-elf toolchain ausente")
    ucx = tmp_path / "ucx-os"
    shutil.copytree(UCX, ucx, ignore=shutil.ignore_patterns("*.o", "*.pack", "image.*", "code.txt"))
    for app in ("weird_a", "weird_a_data"):
        f = disassembly(path, make(ucx, path, app))
        assert "_task_start" in f and calls(f, "_task_start", "_interrupt_set") == 1
        assert calls(f, "dispatch", "_interrupt_tick") == 0 and "_interrupt_tick" not in f
        assert calls(f, "irq2_handler", "_interrupt_set") == 1
        assert calls(f, "irq3_handler", "_interrupt_set") == 1
        assert calls(f, "irq4_handler", "_interrupt_set") == 0
        assert calls(f, "yield", "_interrupt_set") >= 2       # _di at the entry, restore at the return
    cc = "riscv64-elf-gcc -DUCX_ISR_NESTING"
    elf = make(ucx, path, "weird_a_data", cc)
    f = disassembly(path, elf)
    assert "_task_start" not in f and calls(f, "dispatch", "_interrupt_tick") == 1
    assert calls(f, "irq2_handler", "_interrupt_set") == 2 and calls(f, "irq3_handler", "_interrupt_set") == 2
    assert calls(f, "irq4_handler", "_interrupt_set") == 2 and calls(f, "yield", "_interrupt_set") == 0
    built = open(os.path.join(EXP, "wcet", "images", "tick", "BUILD.txt")).readline().split(" (container")[0]
    gcc = subprocess.run(["riscv64-elf-gcc", "--version"], capture_output=True, text=True,
                         env={**os.environ, "PATH": path}).stdout.splitlines()[0]
    # version text after the program name (riscv64-elf-gcc or riscv64-unknown-elf-gcc)
    if gcc.split(" ", 1)[-1].strip() != built.split(" ", 1)[-1].strip():
        pytest.skip(f"compiler {gcc!r} is not the one of images/tick ({built!r})")
    from elftools.elf.elffile import ELFFile

    def sections(p):
        with open(p, "rb") as fh:
            e = ELFFile(fh)
            return {s: e.get_section_by_name(s).data() for s in (".text", ".data")}
    assert sections(elf) == sections(os.path.join(EXP, "wcet", "images", "tick", "weird_a_data.elf"))
