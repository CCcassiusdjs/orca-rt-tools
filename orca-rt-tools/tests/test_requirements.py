"""Dependency file (orca-rt-tools/requirements.txt).

Every third-party module imported by rttools (outside the legacy code) is
declared, numpy included (RGG). matplotlib 3.5.1 uses np.Inf, absent from
numpy 2, so the file pins numpy below 2.
"""
import ast
import os
import re
import sys

from tests.conftest import PKG_ROOT

SKIP_DIRS = {"__rt_tools_old", "porca", "__pycache__"}
REQ = os.path.join(PKG_ROOT, "requirements.txt")


def third_party_imports():
    found = set()
    local = {"rttools", "tests"}
    root = os.path.join(PKG_ROOT, "rttools")
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        local.update(f[:-3] for f in files if f.endswith(".py"))
        local.update(dirs)          # packages of the repository itself (e.g. gcm)
        for f in files:
            if not f.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(d, f)).read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    found.add(node.module.split(".")[0])
    return {m for m in found if m not in sys.stdlib_module_names and m not in local}


def requirements():
    reqs = {}
    for line in open(REQ):
        line = line.split("#")[0].strip()
        if line:
            name = re.split(r"[<>=!~;\[ ]", line, 1)[0].lower()
            reqs[name] = line
    return reqs


def test_every_import_is_declared():
    reqs = requirements()
    missing = sorted(m for m in third_party_imports() if m.lower() not in reqs)
    assert missing == []


def test_numpy_below_2_with_matplotlib_351():
    reqs = requirements()
    assert reqs["matplotlib"] == "matplotlib==3.5.1"
    assert "<2" in reqs["numpy"].replace(" ", "")
