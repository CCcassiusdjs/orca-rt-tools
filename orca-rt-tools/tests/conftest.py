import os
import sys
import subprocess

import pytest

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PKG_ROOT)


@pytest.fixture(autouse=True)
def _default_header_wait(monkeypatch):
    """Every test starts with the default link occupancy o_i = L0: no
    RTTOOLS_HEADER_WAIT in the environment (also for child processes) and
    no selection by router.set_header_wait."""
    from rttools.modules.routing import router
    monkeypatch.delenv(router.HEADER_WAIT_ENV, raising=False)
    router.set_header_wait(None)
    yield
    router.set_header_wait(None)


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
