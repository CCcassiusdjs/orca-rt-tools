"""Time-triggered UCX-OS application of rttools.ucxgen (CAR-full, several
release periods and cycles): manifest, stored files, input errors and the
build with the riscv64-elf toolchain."""
import json
import os
import re
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from rttools.ucxgen import __main__ as cli
from rttools.ucxgen import emit, memory, model

APP = os.path.join(REPO_ROOT, "apps", "car-full")
CSV = os.path.join(APP, "car-full.csv")
MAP = os.path.join(APP, "car-full-ONTO-hermes4x4.map")
UCX = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os")
APP_DIR = os.path.join(UCX, "app")


def manifest():
    return model.build(CSV, MAP, "car_full", mesh="4x4")


def test_manifest():
    m = manifest()
    assert m["model"] == "time_triggered" and m["phase_ns"] == 250000 and m["hyper_ticks"] == 50
    # release interrupt every phase on every PE with a task
    assert m["release"]["period_ns"] == 250000 and m["release"]["mask"] == 0xFFFF
    t = {x["name"]: x for x in m["tasks"]}
    assert t["OBMG"]["period_ticks"] == 50 and t["FBU1"]["period_ticks"] == 2 and t["NAVC"]["period_ticks"] == 5
    assert t["NAVC"]["workload"] == (151000 - 11000) // 10
    f = {(x["source"], x["target"]): x for x in m["flows"]}
    assert f[("NAVC", "OBDB")]["every"] == 5 and f[("STAC", "TPRC")]["every"] == 10
    assert f[("OBDB", "NAVC")]["feedback"] and f[("OBMG", "OBDB")]["feedback"]
    assert not f[("NAVC", "OBDB")]["feedback"]
    # creation order = order of the model (multirate.spec_from_graph)
    assert m["pe_dispatch"]["0-2"] == ["POSI", "NAVC", "DIRC"] and m["pe_dispatch"]["0-1"] == ["OBDB", "USOS", "OBMG"]
    assert m["pe_tasks"]["1-2"] == ["IDLE", "BFE3", "FDF1", "STPH"]
    assert len({x["iter_letter"] for x in m["tasks"]}) == 33


def test_stored_files_match():
    m = manifest()
    for name, text in cli.outputs(m).items():
        with open(os.path.join(APP_DIR, name)) as f:
            assert f.read() == text, name
    src = emit.c_source(m)
    assert "void ucx_app_tick(void)" in src and "READ_MARK" in src and "wait_release" in src
    assert "receive_one" not in src
    assert emit.sim_setup(m).endswith("MESH=4x4\nRELEASE_MASK=65535\n")


def test_heap_per_pe():
    with open(os.path.join(APP_DIR, "car_full.json")) as f:
        m = json.load(f)
    rows = memory.report(m, 48280, 2, (1, 2))
    assert rows[0]["worst_pe"] == 9 and rows[0]["fits"] and rows[0]["bytes"] == 39212


def test_errors(tmp_path):
    head = ("#tasks,,,,,\nTask,Period,Capacity,Deadline,Acronym,Description\n1,0.001,30000,0,S,S\n"
            "2,0.002,30000,0,X,X\n#flows,,,,,\nFlow,Period,Data,Deadline,Source,Target\n")
    par = "#parameters,,,,,\nParameter,Value,,,,\nrelease_model,phase,,,,\nscheduler_cycles,10000,,,,\n"
    mp = tmp_path / "a.map"
    mp.write_text("0:S\n1:X\n")
    csv = tmp_path / "a.csv"
    csv.write_text(head + "1,0.001,2,0.001,S,X\n" + par)
    with pytest.raises(model.GenError, match="4 bytes"):
        model.build(str(csv), str(mp), "a", mesh="2x1")
    csv.write_text(head + "1,0.0015,64,0.0015,S,X\n" + par)
    with pytest.raises(model.GenError, match="not a multiple"):
        model.build(str(csv), str(mp), "a", mesh="2x1")
    csv.write_text(head + "1,0.002,64,0.002,S,X\n" + par)
    m = model.build(str(csv), str(mp), "a", mesh="2x1")
    assert m["model"] == "time_triggered" and m["flows"][0]["every"] == 2


# ---------------------------------------------------------------- build


def toolchain(tmp_path):
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


def test_build_car_full_and_weird_a(tmp_path):
    path = toolchain(tmp_path)
    if path is None:
        pytest.skip("riscv64-elf toolchain ausente")
    ucx = tmp_path / "ucx-os"
    shutil.copytree(UCX, ucx, ignore=shutil.ignore_patterns("*.o", "*.pack", "image.*", "code.txt"))
    weird_a = build(ucx, "weird_a", path)
    build(ucx, "car_full", path)
    target = ucx / "build" / "target"
    env = {**os.environ, "PATH": path}
    syms = subprocess.run(["riscv64-elf-nm", str(target / "image.elf")], capture_output=True, text=True,
                          env=env).stdout
    # tick hook in dispatch and latest-value delivery in the driver
    assert re.search(r" T ucx_app_tick$", syms, re.M) and re.search(r" t pktdrv_put_latest$", syms, re.M)
    with open(os.path.join(APP_DIR, "car_full.json")) as f:
        m = json.load(f)
    rows = memory.report(m, memory.heap_size(str(target / "image.map")), 2, (1,))
    assert rows[0]["fits"], rows
    # weird_a after car_full: kernel and driver without the macros
    assert build(ucx, "weird_a", path) == weird_a
    syms = subprocess.run(["riscv64-elf-nm", str(target / "image.elf")], capture_output=True, text=True,
                          env=env).stdout
    assert "ucx_app_tick" not in syms and "pktdrv_put_latest" not in syms
