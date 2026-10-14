"""CAR-V application of rttools.ucxgen (pkt-sim/software/ucx-os/app/car_v.*,
inputs in experiments/car-v-rtl/input): model, stored files against a new
generation, heap model and the build with the RISC-V toolchain."""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT, run_module
from rttools.ucxgen import memory, model

CARV = os.path.join(REPO_ROOT, "experiments", "car-v-rtl")
# inputs of experiments/car-v-rtl/Makefile: the CAR-V analysis flow (apps/car-v)
# when present, otherwise the provisional files of input/
FLOW_CSV = os.path.join(REPO_ROOT, "apps", "car-v", "car-v.csv")
FLOW_MAP = os.path.join(REPO_ROOT, "apps", "car-v", "car-v-ONTO-hermes4x4.map")
CARV_CSV = FLOW_CSV if os.path.exists(FLOW_CSV) else os.path.join(CARV, "input", "car-v.csv")
CARV_MAP = FLOW_MAP if os.path.exists(FLOW_MAP) else os.path.join(CARV, "input", "car-v.map")
UCX = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os")
APP_DIR = os.path.join(UCX, "app")


def by_name(m):
    return {t["name"]: t for t in m["tasks"]}


def test_carv_model():
    m = model.build(CARV_CSV, CARV_MAP, "car_v", mesh="4x4")
    t = by_name(m)
    assert len(m["tasks"]) == 23 and len(m["flows"]) == 23
    assert sum(not f["local"] for f in m["flows"]) == 16
    assert sorted(n for n, x in t.items() if x["source"]) == [f"FBU{i}" for i in range(1, 9)]
    assert m["release"]["pes"] == [1, 2, 3, 4, 5, 7, 8, 11] and m["release"]["mask"] == 0x9BE
    assert {n: len(t[n]["inputs"]) for n in ("FDF1", "FDF2", "STPH", "NAVC", "OBMG")} == \
        {"FDF1": 4, "FDF2": 4, "STPH": 2, "NAVC": 2, "OBMG": 1}
    assert max(f["bytes"] for f in m["flows"]) == 9600
    assert m["pe_tasks"]["0-1"] == ["IDLE", "FBU3", "VOD1"]


# ---------------------------------------------------------------- stored application


def test_stored_carv_matches_generator():
    r = run_module("rttools.ucxgen", "check", CARV_CSV, CARV_MAP, "--name", "car_v",
                   "--mesh", "4x4", "--out", APP_DIR)
    assert r.returncode == 0, r.stdout + r.stderr


def test_carv_source():
    src = open(os.path.join(APP_DIR, "car_v.c")).read()
    sim = open(os.path.join(APP_DIR, "car_v.sim")).read()
    assert "void irq4_handler(void)" in src
    assert src.count("add_task(task_") == 23
    # PE 4 creates FBU3 before VOD1 (dispatch order of the model)
    case4 = src[src.index("  case 4:"):src.index("  case 5:")]
    assert case4.index("task_FBU3") < case4.index("task_VOD1")
    # release by tick: the release generator on the 16 PEs (2494 = PEs of the sources, --release data)
    assert sim.endswith("MESH=4x4\nRELEASE_MASK=65535\nTICK_RELEASE=1\n")


# ---------------------------------------------------------------- memory


def test_heap_model():
    m = json.load(open(os.path.join(APP_DIR, "car_v.json")))
    d = memory.pe_demand(m, in_flight=2)
    # PE 4: FBU3 and VOD1 (3 tasks with IDLE), packets FBU3->VOD1, FBU3->BFE3 (9600) and VOD1->NAVC (128)
    tasks = 3 * (120 + 20 + 2056) + 2 * (32 + 40)
    assert d[4]["tasks"] == tasks
    assert d[4]["out_packets"] == 2 * (12 + 9600 + 8) + (12 + 128 + 8)
    assert d[4]["in_packets"] == 0
    # PE 6: BFE3 receives FBU3->BFE3 from PE 4, two packets in flight
    assert d[6]["in_packets"] == 2 * (12 + 9600 + 8)
    rows = memory.report(m, 50756, 2, (1, 2))
    assert rows[0]["worst_pe"] == 4 and rows[0]["fits"] and rows[0]["margin"] == 50740 - d[4]["bytes"]


# ---------------------------------------------------------------- build


def toolchain(tmp_path):
    """PATH with riscv64-elf-* (the names of arch.mak), or None."""
    if shutil.which("riscv64-elf-gcc"):
        return os.environ["PATH"]
    if not shutil.which("riscv64-unknown-elf-gcc"):
        return None
    b = tmp_path / "rvbin"
    b.mkdir()
    for tool in ("gcc", "as", "ld", "ar", "objdump", "objcopy", "readelf", "size", "nm"):
        os.symlink(shutil.which(f"riscv64-unknown-elf-{tool}"), b / f"riscv64-elf-{tool}")
    return f"{b}:{os.environ['PATH']}"


def build(ucx, target, path):
    env = {**os.environ, "PATH": path}
    for args in (["make", "-s", "ARCH=riscv/hf-riscv-e", "incl"], ["make", "-s", target]):
        r = subprocess.run(args, cwd=ucx, env=env, capture_output=True, text=True, timeout=600)
        assert r.returncode == 0, (r.stdout + r.stderr)[-3000:]
    return open(os.path.join(ucx, "build", "target", "code.txt")).read()


def test_build_carv_and_weird_a(tmp_path):
    path = toolchain(tmp_path)
    if path is None:
        pytest.skip("riscv64-elf toolchain ausente")
    ucx = tmp_path / "ucx-os"
    shutil.copytree(UCX, ucx, ignore=shutil.ignore_patterns("*.o", "*.pack", "image.*", "code.txt"))
    weird_a = build(ucx, "weird_a", path)
    car_v = build(ucx, "car_v", path)
    target = ucx / "build" / "target"
    syms = subprocess.run(["riscv64-elf-nm", str(target / "image.elf")], capture_output=True, text=True,
                          env={**os.environ, "PATH": path}).stdout
    # irq4_handler of the application (no strcmp of the kernel handler of E)
    assert re.search(r" T irq4_handler$", syms, re.M) and " strcmp" not in syms
    m = json.load(open(os.path.join(APP_DIR, "car_v.json")))
    rows = memory.report(m, memory.heap_size(str(target / "image.map")), 2, (1,))
    assert rows[0]["fits"], rows
    # weird_a after car_v: the image of weird_a alone (kernel handler of E back)
    assert build(ucx, "weird_a", path) == weird_a
    assert build(ucx, "car_v", path) == car_v


