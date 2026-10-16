"""Runs the UCX-OS host C tests (pkt-sim/software/ucx-os/tests/host)
with gcc, AddressSanitizer and UBSan: address conversions of device/ddma.c
(test_ddma.c) and reception and port handling of lib/noc.c (test_noc.c)."""
import os
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT

HOST = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "tests", "host")

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc ausente")


@pytest.mark.parametrize("name", sorted(
    f[:-2] for f in os.listdir(HOST) if f.startswith("test_") and f.endswith(".c")))
def test_host(name, tmp_path):
    r = subprocess.run(["sh", os.path.join(HOST, "run.sh"), name],
                       env={**os.environ, "OUT": str(tmp_path)},
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr[-4000:]
    assert "FAIL" not in r.stdout
