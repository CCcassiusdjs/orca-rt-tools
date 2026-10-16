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
    for f in ("source_info.sh", "simulate.sh", "build_sw.sh", "VERSION"):
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
    # car_v.sim of the release by tick: the release generator on the 16 PEs
    g = "-gNOC_DIM_X=4 -gNOC_DIM_Y=4 -gRELEASE_MASK=65535"
    assert f"vsim -c work.manycore_top work.chk_binds +RUN_NS=11500000 {g}\n" in run_do(tmp_path / "o")
    assert "-s car_v" in log.read_text()
    assert f"app=car_v mesh=4x4 generics={g}\n" in (tmp_path / "o" / "RUN_INFO").read_text()
    # mesh from car_v.sim; the environment overrides the mask; monitor off
    r = subprocess.run(["bash", sh, str(tmp_path / "o2"), "1000", "car_v"], capture_output=True, text=True,
                       env={**env, "RELEASE_MASK": "3", "MONITOR": "0"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "vsim -c work.manycore_top -gNOC_DIM_X=4 -gNOC_DIM_Y=4 -gRELEASE_MASK=3\n" in run_do(tmp_path / "o2")
    r = subprocess.run(["bash", sh, str(tmp_path / "o4"), "1000", "car_v"], capture_output=True, text=True,
                       env={**env, "RELEASE_MASK": "0x9be"})
    assert r.returncode == 2 and "invalid RELEASE_MASK" in r.stderr
    r = subprocess.run(["bash", sh, str(tmp_path / "o3"), "1000", "car_v", "4by4"],
                       capture_output=True, text=True, env=env)
    assert r.returncode == 2 and "invalid mesh" in r.stderr


def test_simulate_clock_generics(tmp_path):
    """At a clock other than 500 MHz (make paper-flow: 434.912 MHz) the clock
    of the run goes to vsim -g and to the build; at 500 MHz the command has
    no clock option (test_simulate_default_is_run_f)."""
    repo, env, log = stub_repo(tmp_path)
    sh = str(repo / "experiments" / "exp23" / "simulate.sh")
    r = subprocess.run(["bash", sh, str(tmp_path / "o"), "1000"], capture_output=True, text=True,
                       env={**env, "F_CLK": "434912000"})
    assert r.returncode == 0, r.stdout + r.stderr
    g = "-gCLOCK_HALF_PERIOD_FS=1149657 -gRELEASE_CYCLES=217456 -gWARMUP_CYCLES=1304736"
    assert f"vsim -c work.manycore_top work.chk_binds +RUN_NS=1000 {g}\n" in run_do(tmp_path / "o")
    assert "-s weird_a F_CLK=434912000 F_TICK=2000" in log.read_text()
    info = (tmp_path / "o" / "RUN_INFO").read_text()
    assert f"app=weird_a mesh=2x2 generics={g}\n" in info and "f_clk_hz=434912000\n" in info
    # CAR-V at the clock of its flow (380 MHz): clock and mesh options together
    r = subprocess.run(["bash", sh, str(tmp_path / "o2"), "1000", "car_v", "4x4"], capture_output=True, text=True,
                       env={**env, "F_CLK": "380000000"})
    assert r.returncode == 0, r.stdout + r.stderr
    assert ("+RUN_NS=1000 -gCLOCK_HALF_PERIOD_FS=1315789 -gRELEASE_CYCLES=190000 -gWARMUP_CYCLES=1140000 "
            "-gNOC_DIM_X=4 -gNOC_DIM_Y=4 -gRELEASE_MASK=65535\n") in run_do(tmp_path / "o2")
