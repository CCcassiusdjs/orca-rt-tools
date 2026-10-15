"""Workloads in which the links set f_NoC (rttools/paper/linkload.py,
experiments/linkload): the run reproduces reference.json, and with payloads
16 times those of E the links alone need a clock above f_CPU and above the
clock at which each packet alone fits its window."""
import os

from rttools.paper import cputime, linkload
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments", "linkload")


def test_reference(tmp_path):
    m, _ = linkload.run(os.path.join(EXP, "config.json"), str(tmp_path))
    assert cputime.check(os.path.join(tmp_path, "metrics.json"), os.path.join(EXP, "reference.json"))
    assert m["apps"]["E"]["16"]["links_bind"] and not m["apps"]["E"]["1"]["links_bind"]
    for rows in m["apps"].values():
        for r in rows.values():
            assert r["links_only"]["minimum_hz"] <= r["flow"]["minimum_hz"]
