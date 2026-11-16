import os
import sys
import subprocess

import pytest

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PKG_ROOT)


@pytest.fixture(autouse=True)
def _default_header_wait(monkeypatch):
    """Every test starts with the default link occupancy o_i = L0 +
    20 (m + 1) + w_NI: no RTTOOLS_HEADER_WAIT, RTTOOLS_NI or
    RTTOOLS_DEADLINE in the environment (also for child processes) and no
    selection by router.set_header_wait, router.set_ni or
    router.set_deadline (network-interface model tt, w_NI = NI_WAIT_CYCLES,
    deadline model tick)."""
    from rttools.modules.routing import router
    monkeypatch.delenv(router.HEADER_WAIT_ENV, raising=False)
    monkeypatch.delenv(router.NI_ENV, raising=False)
    monkeypatch.delenv(router.DEADLINE_ENV, raising=False)
    router.set_header_wait(None)
    router.set_ni(None)
    router.set_deadline(None)
    yield
    router.set_header_wait(None)
    router.set_ni(None)
    router.set_deadline(None)


@pytest.fixture
def deadline_start(monkeypatch):
    """Deadline model start (RTTOOLS_DEADLINE=start, also for child
    processes): the deadline of a packet at the modeled start of the job
    that reads it and no handlers of the packet events, the model of the
    ORCA RT-Tools reference (Tab. 8.2 and the windows of the phase model) and of the tables
    up to tag r11-rc8 (router.tick_deadline)."""
    from rttools.modules.routing import router
    monkeypatch.setenv(router.DEADLINE_ENV, "start")
    router.set_deadline(None)
    yield


@pytest.fixture
def ni_off(monkeypatch):
    """Network-interface model off (RTTOOLS_NI=off, also for child
    processes): the model of the stored references of the runs up to tag
    r11-rc5, which their targets select (NI ?= off in the Makefiles of
    experiments/)."""
    from rttools.modules.routing import router
    monkeypatch.setenv(router.NI_ENV, router.NI_OFF)
    router.set_ni(None)
    yield


@pytest.fixture(scope="module")
def ni_off_module():
    """ni_off with scope module: the outputs of a target with a stored
    reference that a module builds once for its tests."""
    from rttools.modules.routing import router
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv(router.NI_ENV, router.NI_OFF)
        router.set_ni(None)
        yield


def run_module(module, *args, cwd=None, block=(), timeout=120):
    """Runs `python -m module args` in an isolated process.

    `block` lists modules that the child process treats as missing
    (simulates an installation without the dependency)."""
    pre = ""
    if block:
        pre = "import sys\n" + "".join(f"sys.modules[{m!r}] = None\n" for m in block)
    code = (
        pre
        + f"import sys, runpy\nsys.path.insert(0, {PKG_ROOT!r})\n"
        + f"sys.argv = [{module!r}] + {list(args)!r}\n"
        + f"runpy.run_module({module!r}, run_name='__main__', alter_sys=True)\n"
    )
    return subprocess.run(
        [sys.executable, "-I", "-c", code],
        cwd=cwd or PKG_ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
