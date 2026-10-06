import os
import sys
import subprocess

PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(PKG_ROOT)


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
