"""Application and mesh options of experiments/exp23/simulate.sh (stub
tools): the defaults give the vsim command of run F; car_v and 4x4 pass the
setup of app/car_v.sim to manycore_top with vsim -g."""
import os
import shutil
import stat
import subprocess

from tests.conftest import REPO_ROOT

APP_DIR = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app")


def stub_repo(tmp_path):
    repo = tmp_path / "repo"
    e = repo / "experiments" / "exp23"
    (e / "rtl").mkdir(parents=True)
    for f in ("source_info.sh", "simulate.sh", "VERSION"):
        shutil.copy2(os.path.join(REPO_ROOT, "experiments", "exp23", f), e / f)
    mc = repo / "pkt-sim" / "manycore_modelsim"
    mc.mkdir(parents=True)
    (mc / "sim.do").write_text("vlog x\nvsim work.manycore_top\nrun 1000ms\n")
    app = repo / "pkt-sim" / "software" / "ucx-os" / "app"
    app.mkdir(parents=True)
    (repo / "pkt-sim" / "software" / "hfrisc-software").mkdir()
    shutil.copy2(os.path.join(APP_DIR, "car_v.sim"), app / "car_v.sim")
    b = tmp_path / "bin"
    b.mkdir()
    log = tmp_path / "make.log"
    for name, body in {"vsim": 'echo "Questa stub"\n', "riscv64-elf-gcc": 'echo "gcc stub"\n',
                       "make": f'echo "$@" >> {log}\n'}.items():
        p = b / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return repo, {**os.environ, "PATH": f"{b}:{os.environ['PATH']}"}, log


def run_do(out):
    return (out / "pkt-sim" / "manycore_modelsim" / "run.do").read_text()


def test_simulate_default_is_run_f(tmp_path):
    repo, env, log = stub_repo(tmp_path)
    r = subprocess.run(["bash", str(repo / "experiments" / "exp23" / "simulate.sh"), str(tmp_path / "o"), "1000"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "vsim -c work.manycore_top work.chk_binds +RUN_NS=1000\n" in run_do(tmp_path / "o")
    assert "-s weird_a" in log.read_text()
    assert "app=weird_a mesh=2x2 generics=\n" in (tmp_path / "o" / "RUN_INFO").read_text()


def test_simulate_carv_4x4(tmp_path):
    repo, env, log = stub_repo(tmp_path)
    sh = str(repo / "experiments" / "exp23" / "simulate.sh")
    r = subprocess.run(["bash", sh, str(tmp_path / "o"), "11500000", "car_v", "4x4"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr
    g = "-gNOC_DIM_X=4 -gNOC_DIM_Y=4 -gRELEASE_MASK=2494"
    assert f"vsim -c work.manycore_top work.chk_binds +RUN_NS=11500000 {g}\n" in run_do(tmp_path / "o")
    assert "-s car_v" in log.read_text()
    assert f"app=car_v mesh=4x4 generics={g}\n" in (tmp_path / "o" / "RUN_INFO").read_text()
    # mesh from car_v.sim; environment overrides the release; monitor off
    r = subprocess.run(["bash", sh, str(tmp_path / "o2"), "1000", "car_v"], capture_output=True, text=True,
                       env={**env, "RELEASE_PERIOD_NS": "250000", "MONITOR": "0"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"vsim -c work.manycore_top {g} -gRELEASE_PERIOD_NS=250000\n" in run_do(tmp_path / "o2")
    r = subprocess.run(["bash", sh, str(tmp_path / "o3"), "1000", "car_v", "4by4"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "invalid mesh" in r.stderr
