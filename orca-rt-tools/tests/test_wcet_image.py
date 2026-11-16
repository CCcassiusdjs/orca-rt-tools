"""rttools.wcet.image: ELF files (pyelftools) and objdump listings; the
section .wcet_bounds of WCET_LOOP_BOUND (pkt-sim/software/ucx-os/include/lib/
wcet.h)."""
import os

from rttools.wcet import analysis, image
from tests.conftest import REPO_ROOT

IMAGES = os.path.join(REPO_ROOT, "experiments", "wcet", "images")
BODIES = os.path.join(REPO_ROOT, "pkt-sim", "tests", "rtl", "wcet_bodies.elf")


def test_elf_and_listing_of_the_same_build_agree():
    elf = image.load(os.path.join(IMAGES, "wcet_e.elf"))
    lst = image.load(os.path.join(IMAGES, "wcet_e.lst"))
    assert elf.kind == "elf" and lst.kind == "listing"
    for a, w in lst.words.items():
        assert elf.words[a] == w
    assert elf.function("run_task").start == lst.function("run_task").start
    # aliases of one function: yield and _yield (kernel/sched.c)
    assert elf.canonical("_yield") == "yield" and elf.function("_yield").name == "yield"
    # read-only data: the descriptor table of rttools.ucxgen
    assert elf.read(elf.symbols["TASKS"] + 14, 1) is not None
    assert lst.read(elf.symbols["TASKS"] + 14, 1) is None


def test_bounds_section():
    img = image.load(BODIES)
    assert img.bounds, "no .wcet_bounds entries"
    flags = sorted({n >> 31 for _, n in img.bounds})
    assert flags == [0, 1]                 # WCET_LOOP_BOUND and WCET_LOOP_TOTAL
    an = analysis.Analyzer(img)
    r = an.function("body_sort")
    srcs = {(b, s) for _, _, b, s in r.loops}
    assert (64 * 63 // 2 + 63, "source") in srcs
    r = an.function("body_count")
    assert {(b, s) for _, _, b, s in r.loops} == {(256, "source")}
