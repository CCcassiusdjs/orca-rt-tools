"""Anonymized export (tools/anonymize/export.sh) of HEAD: no identifying
string, no wording about changes to the code of the thesis, no
thesis-comparison material, markers applied, and the verification detects
a planted name and planted correction wording."""
import json
import os
import shutil
import subprocess
import sys

import pytest

from tests.conftest import REPO_ROOT

TOOL = os.path.join(REPO_ROOT, "tools", "anonymize")

pytestmark = [
    pytest.mark.skipif(not os.path.isdir(TOOL), reason="tools/anonymize is not in the anonymized copy"),
    pytest.mark.skipif(shutil.which("git") is None
                       or subprocess.run(["git", "-C", REPO_ROOT, "rev-parse", "HEAD"],
                                         capture_output=True).returncode != 0, reason="no git repository"),
]


@pytest.fixture(scope="module")
def export(tmp_path_factory):
    out = tmp_path_factory.mktemp("anon") / "copy"
    r = subprocess.run(["bash", os.path.join(TOOL, "export.sh"), str(out)], capture_output=True, text=True,
                       env={**os.environ, "PYTHON3": sys.executable}, timeout=600)
    return out, r


def test_export_has_no_identifying_string(export):
    out, r = export
    assert r.returncode == 0, r.stdout + r.stderr
    assert "identifying strings: 0 unexpected" in r.stdout
    assert "correction wording: 0 unexpected" in r.stdout
    assert "removed thesis-comparison material still present: 0" in r.stdout
    assert not (out / ".git").exists() and not (out / "tools" / "anonymize").exists()


def test_export_content(export):
    out, _ = export
    e = out / "experiments"
    assert not (e / "ch6").exists()
    assert sorted(os.listdir(e / "exp23" / "logs")) == ["F.RUN_INFO", "F.events.txt", "F.image.lst",
                                                         "F.noinstr.lst", "F.software.txt", "F.time.txt"] + [
        f"{r}.{x}" for r in "GH" for x in ("RUN_INFO", "events.txt", "image.lst", "noinstr.lst", "time.txt")]
    assert (e / "exp23" / "reference_G.json").exists() and (e / "exp23" / "reference_H.json").exists()
    assert not (e / "exp23" / "reference_D.json").exists() and not (e / "exp23" / "reference_E.json").exists()
    assert sorted(os.listdir(e / "car-v-rtl" / "logs")) == [
        f"{r}.{x}" for r in ("CV", "CV2") for x in ("RUN_INFO", "events.txt", "time.txt")]
    assert (e / "car-v-rtl" / "reference_CV.json").exists() and (e / "car-v-rtl" / "reference_CV2.json").exists()
    assert "thesis" not in json.loads((e / "exp23" / "config.json").read_text())
    assert "reference_rows" in json.loads((e / "ch7" / "config.json").read_text())
    exp23 = (out / "orca-rt-tools" / "rttools" / "paper" / "exp23.py").read_text()
    assert "thesis_comparison" not in exp23 and '"thesis"' not in exp23
    for f in ("ARTIFACT.md", "README.md", "experiments/README.md", "experiments/exp23/README.md",
              "experiments/exp23/Makefile", "experiments/Makefile"):
        text = (out / f).read_text()
        assert "anon:drop" not in text, f
    assert "runs:" not in (e / "exp23" / "Makefile").read_text()
    assert "ch6" not in (e / "Makefile").read_text()
    assert (e / "exp23" / "VERSION").read_text().startswith("commit=$Format:%H$")


def test_verify_detects_planted_name(export):
    out, _ = export
    p = out / "experiments" / "planted.txt"
    p.write_text("simulated on the paxos server\n")
    try:
        r = subprocess.run([sys.executable, "-I", os.path.join(TOOL, "anonymize.py"), "verify", str(out),
                            "--repo", REPO_ROOT], capture_output=True, text=True)
    finally:
        p.unlink()
    assert r.returncode == 1
    assert "UNEXPECTED experiments/planted.txt:1" in r.stdout


def test_verify_detects_correction_wording(export):
    out, _ = export
    p = out / "experiments" / "planted.c"
    p.write_text("/* the fix of the original RTL */\n")
    try:
        r = subprocess.run([sys.executable, "-I", os.path.join(TOOL, "anonymize.py"), "verify", str(out),
                            "--repo", REPO_ROOT], capture_output=True, text=True)
    finally:
        p.unlink()
    assert r.returncode == 1
    assert "correction wording: 1 unexpected" in r.stdout
    assert "UNEXPECTED experiments/planted.c:1" in r.stdout
