"""Scripts of the artifact (experiments/): source identification of a
simulation run (exp23/source_info.sh, simulate.sh REQUIRE_CLEAN), the
default log of exp23, and the zero-load latency testbench (zll)."""
import os
import shutil
import stat
import subprocess

import pytest

from tests.conftest import REPO_ROOT

EXP23 = os.path.join(REPO_ROOT, "experiments", "exp23")
ZLL = os.path.join(REPO_ROOT, "experiments", "zll")

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.org",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git ausente")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True, env={**os.environ, **GIT_ENV}).stdout.strip()


def make_repo(tmp_path, tag="v1"):
    """Minimal repository with the files that source_info.sh and simulate.sh read."""
    repo = tmp_path / "repo"
    e = repo / "experiments" / "exp23"
    (e / "rtl").mkdir(parents=True)
    (repo / "pkt-sim").mkdir()
    for f in ("source_info.sh", "simulate.sh", "build_sw.sh", "VERSION", ".gitattributes"):
        shutil.copy2(os.path.join(EXP23, f), e / f)
    (e / "rtl" / "mon.sv").write_text("module m; endmodule\n")
    (repo / "pkt-sim" / "a.v").write_text("// rtl\n")
    (repo / ".gitignore").write_text("build/\n")
    git(tmp_path, "init", "-q", str(repo))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    if tag:
        git(repo, "tag", tag)
    return repo


def info(repo, script=None):
    script = script or (repo / "experiments" / "exp23" / "source_info.sh")
    out = repo.parent / "RUN_INFO"
    r = subprocess.run(["bash", str(script), str(repo), str(out), str(repo.parent / "STATUS")],
                       capture_output=True, text=True, env={**os.environ, **GIT_ENV})
    assert r.returncode == 0, r.stderr
    return dict(line.split("=", 1) for line in out.read_text().splitlines())


@needs_git
def test_clean_checkout_at_tag(tmp_path):
    repo = make_repo(tmp_path)
    i = info(repo)
    assert i["repo_commit"] == git(repo, "rev-parse", "HEAD")
    assert i["repo_state"] == "clean"
    assert i["repo_tag"] == "v1"
    assert len(i["src_sha256"]) == 64


@needs_git
def test_dirty_checkout(tmp_path):
    repo = make_repo(tmp_path)
    clean = info(repo)
    (repo / "pkt-sim" / "a.v").write_text("// changed\n")
    (repo / "pkt-sim" / "new.v").write_text("// untracked\n")
    i = info(repo)
    assert i["repo_state"] == "dirty"
    assert i["src_sha256"] != clean["src_sha256"]
    status = (tmp_path / "STATUS").read_text()
    assert "pkt-sim/a.v" in status and "pkt-sim/new.v" in status
    # ignored outputs do not make the tree dirty
    git(repo, "checkout", "--", "pkt-sim/a.v")
    (repo / "pkt-sim" / "new.v").unlink()
    (repo / "build").mkdir()
    (repo / "build" / "out.txt").write_text("x")
    assert info(repo)["repo_state"] == "clean"


@needs_git
def test_untagged_commit(tmp_path):
    repo = make_repo(tmp_path, tag=None)
    i = info(repo)
    assert i["repo_state"] == "clean" and i["repo_tag"] == "none"


@needs_git
def test_git_archive_keeps_commit_and_digest(tmp_path):
    repo = make_repo(tmp_path)
    clean = info(repo)
    arch = tmp_path / "arch"
    arch.mkdir()
    tar = tmp_path / "a.tar"
    git(repo, "archive", "-o", str(tar), "v1")
    subprocess.run(["tar", "-xf", str(tar), "-C", str(arch)], check=True)
    i = info(arch)
    assert i["repo_commit"] == clean["repo_commit"]
    assert i["repo_state"] == "archive"
    assert i["repo_tag"] == "v1"
    assert i["src_sha256"] == clean["src_sha256"]


@needs_git
def test_copy_without_git(tmp_path):
    """Copy of a worktree whose .git file points to a missing directory
    (the copy that wrote repo_commit=unknown-dirty): no commit, state nogit."""
    repo = make_repo(tmp_path)
    clean = info(repo)
    copy = tmp_path / "copy"
    shutil.copytree(repo, copy, ignore=shutil.ignore_patterns(".git"))
    (copy / ".git").write_text("gitdir: /nonexistent/worktrees/x\n")
    i = info(copy)
    assert i["repo_commit"] == "unknown"
    assert i["repo_state"] == "nogit"
    assert i["src_sha256"] == clean["src_sha256"]


@needs_git
def test_copy_inside_other_repository(tmp_path):
    repo = make_repo(tmp_path)
    outer = tmp_path / "outer"
    outer.mkdir()
    git(tmp_path, "init", "-q", str(outer))
    copy = outer / "copy"
    shutil.copytree(repo, copy, ignore=shutil.ignore_patterns(".git"))
    assert info(copy)["repo_state"] == "nogit"


def stub_tools(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    for name, body in {"vsim": 'echo "Questa stub"\n', "riscv64-elf-gcc": 'echo "gcc stub"\n',
                       "make": "exit 0\n"}.items():
        p = b / name
        p.write_text("#!/bin/sh\n" + body)
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return {**os.environ, **GIT_ENV, "PATH": f"{b}:{os.environ['PATH']}"}


def simulate(repo, out, env, **extra):
    return subprocess.run(["bash", str(repo / "experiments" / "exp23" / "simulate.sh"), str(out), "1000"],
                          capture_output=True, text=True, env={**env, **extra})


@needs_git
def test_simulate_require_clean(tmp_path):
    env = stub_tools(tmp_path)
    repo = make_repo(tmp_path)
    git(repo, "tag", "-d", "v1")
    sim_do = repo / "pkt-sim" / "manycore_modelsim" / "sim.do"
    sim_do.parent.mkdir()
    sim_do.write_text("vlog x\nvsim -c top\n")
    for d in ("ucx-os", "hfrisc-software"):
        (repo / "pkt-sim" / "software" / d).mkdir(parents=True)
        (repo / "pkt-sim" / "software" / d / "Makefile").write_text("all:\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "sim.do")
    # untagged: refused with REQUIRE_CLEAN=1, accepted without it
    r = simulate(repo, tmp_path / "o1", env, REQUIRE_CLEAN="1")
    assert r.returncode == 3, r.stdout + r.stderr
    git(repo, "tag", "v2")
    (repo / "pkt-sim" / "a.v").write_text("// changed\n")
    r = simulate(repo, tmp_path / "o2", env, REQUIRE_CLEAN="1")
    assert r.returncode == 3 and "dirty" in r.stderr
    git(repo, "checkout", "--", "pkt-sim/a.v")
    r = simulate(repo, tmp_path / "o3", env, REQUIRE_CLEAN="1")
    assert r.returncode == 0, r.stdout + r.stderr
    run_info = (tmp_path / "o3" / "RUN_INFO").read_text()
    assert f"repo_commit={git(repo, 'rev-parse', 'HEAD')}\n" in run_info
    assert "repo_state=clean\n" in run_info and "repo_tag=v2\n" in run_info
    assert "sim_ns=1000 monitor=1\n" in run_info and "vsim=Questa stub\n" in run_info


def test_exp23_default_is_run_f():
    r = subprocess.run(["make", "-n", "-C", EXP23, "PYTHON=python3"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "analyze logs/F.events.txt --config config.json --join per_producer" in r.stdout
    assert "reference_head.json" in r.stdout
    r = subprocess.run(["make", "-n", "-C", EXP23, "PYTHON=python3", "LOG=logs/D.events.txt",
                        "REF=reference_D.json"], capture_output=True, text=True)
    assert "analyze logs/D.events.txt" in r.stdout and "reference_D.json" in r.stdout


@needs_git
def test_simulate_builds_with_the_writes(tmp_path):
    """simulate.sh builds through build_sw.sh with UCX_CFLAGS empty, also
    when the environment sets it."""
    env = stub_tools(tmp_path)
    log = tmp_path / "make.log"
    (tmp_path / "bin" / "make").write_text(f'#!/bin/sh\necho "$PWD $*" >> {log}\n')
    repo = make_repo(tmp_path)
    sim_do = repo / "pkt-sim" / "manycore_modelsim" / "sim.do"
    sim_do.parent.mkdir()
    sim_do.write_text("vlog x\nvsim -c top\n")
    for d in ("ucx-os", "hfrisc-software"):
        (repo / "pkt-sim" / "software" / d).mkdir(parents=True)
    r = simulate(repo, tmp_path / "o", env, UCX_CFLAGS="-DUCX_NO_INSTRUMENTATION")
    assert r.returncode == 0, r.stdout + r.stderr
    calls = log.read_text()
    assert "ARCH=riscv/hf-riscv-e incl" in calls and "weird_a" in calls and "boot_sim" in calls
    assert "UCX_NO_INSTRUMENTATION" not in calls
    assert (tmp_path / "o" / "gcc.txt").read_text() == "gcc stub\n"


@pytest.mark.skipif(shutil.which("ghdl") is None, reason="ghdl ausente")
def test_zll_2x2(tmp_path):
    r = subprocess.run(["sh", os.path.join(ZLL, "run.sh"), str(tmp_path)],
                       env={**os.environ, "XR": "2", "YR": "2", "SRCS": "0 3", "PS": "1 4"},
                       capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, (r.stdout + r.stderr)[-4000:]
    assert "zll: 16 of 16 points satisfy L0 = 6(m+1) + p + 1" in r.stdout
    rows = (tmp_path / "zll.csv").read_text().splitlines()
    assert rows[0] == "src_x,src_y,dst_x,dst_y,m,p,latency,model,match"
    assert len(rows) == 17 and all(r.endswith(",yes") for r in rows[1:])
    # (0,0) -> (1,1): m = 2, p = 4: 6 * 3 + 4 + 1
    assert "0,0,1,1,2,4,23,23,yes" in rows
