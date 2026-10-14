"""One UCX-OS image for several applications (rttools.ucxgen compose,
pkt-sim/software/ucx-os/app/carv_e.*, experiments/multiapp)."""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT, run_module
from tests.test_ucxgen_carv import build as build_image, toolchain
from rttools.ucxgen import memory, model

APPS = os.path.join(REPO_ROOT, "apps")
E_CSV = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv")
E_MAP2 = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map")
CARV_CSV = os.path.join(APPS, "car-v", "car-v.csv")
CARV_MAP4 = os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map")
EXP = os.path.join(REPO_ROOT, "experiments", "multiapp")
UCX = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os")
APP_DIR = os.path.join(UCX, "app")
PARTS = [("CARV", CARV_CSV, os.path.join(EXP, "maps", "CARV.map")),
         ("E", E_CSV, os.path.join(EXP, "maps", "E.map"))]


def test_composition_model():
    m = model.compose(PARTS, "carv_e", mesh="4x5")
    carv = model.build(CARV_CSV, PARTS[0][2], "carv_e", mesh="4x5")
    e = model.build(E_CSV, PARTS[1][2], "carv_e", mesh="4x5")
    assert [a["name"] for a in m["apps"]] == ["CARV", "E"]
    assert len(m["tasks"]) == 33 and len(m["flows"]) == 34
    # ports, flows, tags and letters numbered across the applications
    assert [t["port"] for t in m["tasks"]] == list(range(1, 34))
    assert [f["id"] for f in m["flows"]] == list(range(1, 35))
    assert [f["tag_base"] for f in m["flows"]] == [i * 1024 for i in range(1, 35)]
    assert len({t["iter_letter"] for t in m["tasks"]}) == 33
    assert m["apps"][1]["flows"] == list(range(24, 35))
    # E keeps its tasks, PEs, creation order and sources; flows shifted by 23
    for a, b in zip([t for t in m["tasks"] if t["app"] == "E"], e["tasks"]):
        assert (a["name"], a["pe"], a["order"], a["workload"], a["source"]) == \
            (b["name"], b["pe"], b["order"], b["workload"], b["source"])
        assert a["inputs"] == [i + 23 for i in b["inputs"]] and a["port"] == b["port"] + 23
    assert m["pe_dispatch"]["2-3"] == e["pe_dispatch"]["2-3"] == ["A", "B", "D", "F"]
    assert m["pe_tasks"]["1-2"] == ["IDLE", "J", "G"]
    assert m["release"]["pes"] == sorted(carv["release"]["pes"] + e["release"]["pes"]) == [1, 2, 3, 7, 8, 11, 12, 14, 16]
    assert m["release"]["mask"] == 88462


def test_composition_errors(tmp_path):
    over = tmp_path / "e.map"
    over.write_text("1:A,B,D,F\n9:C\n13:E,H,I\n10:G,J\n")
    with pytest.raises(model.GenError, match="PE 1 is mapped by applications CARV and E"):
        model.compose([PARTS[0], ("E", E_CSV, str(over))], "x", mesh="4x5")
    slow = tmp_path / "e1ms.csv"
    slow.write_text(open(E_CSV).read().replace("0.0005,", "0.001,"))
    with pytest.raises(model.GenError, match="one release period"):
        model.compose([PARTS[0], ("E", str(slow), PARTS[1][2])], "x", mesh="4x5")
    with pytest.raises(model.GenError, match="task A in applications E and E2"):
        e2 = tmp_path / "e2.map"
        e2.write_text("16:A,B,D,F\n17:C\n18:E,H,I\n19:G,J\n")
        model.compose([("E", E_CSV, PARTS[1][2]), ("E2", E_CSV, str(e2))], "x", mesh="4x5")
    with pytest.raises(model.GenError, match="repeated application name"):
        model.compose([PARTS[1], PARTS[1]], "x", mesh="4x5")


def test_stored_composition_matches_generator():
    args = []
    for n, c, mp in PARTS:
        args += ["--app", f"{n}:{c}:{mp}"]
    r = run_module("rttools.ucxgen", "compose-check", *args, "--name", "carv_e", "--mesh", "4x5",
                   "--out", APP_DIR)
    assert r.returncode == 0, r.stdout + r.stderr
    src = open(os.path.join(APP_DIR, "carv_e.c")).read()
    assert src.count("add_task(task_") == 33 and "void irq4_handler(void)" in src
    case9 = src[src.index("  case 9:"):src.index("  case 10:")]
    assert case9.index("task_E_J") < case9.index("task_E_G")
    assert open(os.path.join(APP_DIR, "carv_e.sim")).read().endswith("MESH=4x5\nRELEASE_MASK=88462\n")
    mk = open(os.path.join(UCX, "Makefile")).read()
    assert re.search(r"^GEN_APPS \+= carv_e$", mk, re.M)


def test_composition_heap_model():
    m = json.load(open(os.path.join(APP_DIR, "carv_e.json")))
    one = memory.pe_demand(m, in_flight=1)
    two = memory.pe_demand(m, in_flight=2)
    # PE 9: G and J of E; inputs F->G (6780), H->J (8900), I->J (5670) from other PEs
    ins = sum(memory.block(12 + b) for b in (6780, 8900, 5670))
    assert two[9]["in_packets"] == 2 * ins and one[9]["in_packets"] == ins
    assert max(one.values(), key=lambda d: d["bytes"]) == one[13] and one[13]["bytes"] == 36224
    assert two[9]["bytes"] == 50808


def test_build_composition(tmp_path):
    path = toolchain(tmp_path)
    if path is None:
        pytest.skip("riscv64-elf toolchain ausente")
    ucx = tmp_path / "ucx-os"
    shutil.copytree(UCX, ucx, ignore=shutil.ignore_patterns("*.o", "*.pack", "image.*", "code.txt"))
    weird_a = build_image(ucx, "weird_a", path)
    build_image(ucx, "carv_e", path)
    target = ucx / "build" / "target"
    syms = subprocess.run(["riscv64-elf-nm", str(target / "image.elf")], capture_output=True, text=True,
                          env={**os.environ, "PATH": path}).stdout
    assert re.search(r" T irq4_handler$", syms, re.M) and " strcmp" not in syms
    assert re.search(r" t task_E_J$", syms, re.M) and re.search(r" t task_CARV_OBMG$", syms, re.M)
    m = json.load(open(os.path.join(APP_DIR, "carv_e.json")))
    rows = memory.report(m, memory.heap_size(str(target / "image.map")), 1, (1,))
    assert rows[0]["fits"], rows
    assert build_image(ucx, "weird_a", path) == weird_a


def test_simulate_composition_4x5(tmp_path):
    """experiments/multiapp `make sim`: simulate.sh with carv_e takes the
    mesh 4x5 and the mask of carv_e.sim and the clock of the platform."""
    from tests.test_simulate_options import run_do, stub_repo
    repo, env, log = stub_repo(tmp_path)
    shutil.copy2(os.path.join(APP_DIR, "carv_e.sim"),
                 repo / "pkt-sim" / "software" / "ucx-os" / "app" / "carv_e.sim")
    sh = str(repo / "experiments" / "exp23" / "simulate.sh")
    r = subprocess.run(["bash", sh, str(tmp_path / "o"), "11500000", "carv_e"], capture_output=True, text=True,
                       env={**env, "F_CLK": "434912000"})
    assert r.returncode == 0, r.stdout + r.stderr
    g = "-gCLOCK_HALF_PERIOD_FS=1149657 -gRELEASE_CYCLES=217456 -gWARMUP_CYCLES=1304736 " \
        "-gNOC_DIM_X=4 -gNOC_DIM_Y=5 -gRELEASE_MASK=88462"
    assert f"vsim -c work.manycore_top work.chk_binds +RUN_NS=11500000 {g}\n" in run_do(tmp_path / "o")
    assert "-s carv_e" in log.read_text()
    assert f"app=carv_e mesh=4x5 generics={g}\n" in (tmp_path / "o" / "RUN_INFO").read_text()
