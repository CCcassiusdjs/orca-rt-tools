"""Workloads in which the contention of packets sets f_NoC
(rttools/paper/linkload.py, experiments/linkload): the run reproduces
reference.json, and with the task costs of E divided by 16 and 32 the flow
and the links alone need a clock above f_CPU and above the clock at which
each packet alone fits its window, with the same packets."""
import os

from rttools.paper import cputime, linkload
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments", "linkload")


def test_reference(tmp_path):
    m, _ = linkload.run(os.path.join(EXP, "config.json"), str(tmp_path))
    assert cputime.check(os.path.join(tmp_path, "metrics.json"), os.path.join(EXP, "reference.json"))
    for k in ("16", "32"):
        r = m["apps"]["E"][k]
        assert r["links_only"]["contention_binds"] and r["no_handlers"]["contention_binds"]
        assert r["flow"]["minimum_hz"] == r["no_handlers"]["minimum_hz"]
    assert not m["apps"]["E"]["1"]["links_only"]["contention_binds"]
    for rows in m["apps"].values():
        for r in rows.values():
            assert r["links_only"]["minimum_hz"] <= r["flow"]["minimum_hz"]
