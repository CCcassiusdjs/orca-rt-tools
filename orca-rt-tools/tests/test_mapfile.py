"""Mapping files (rttools/modules/mapping/mapfile.py).

apps/synthetic-app-e/synthetic-app-e-ONTO-hermes2x2.map had `3:G,H`: task
H on nodes 2 and 3 and task J on no node. The application of exp-23
(pkt-sim/software/ucx-os/app/weird_a.c, CPU_G = CPU_J = 3) and Fig. 8.6a
of the ORCA RT-Tools reference run G and J on node 3.
"""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.io import appparser, nocparser
from rttools.modules.mapping import mapfile

APPS = os.path.join(REPO_ROOT, "apps")
ARCH = os.path.join(REPO_ROOT, "arch")

# application, mapping file, architecture
PAIRS = [
    ("sample-graph-a/SAMPLE_GRAPH.csv", "sample-graph-a/SAMPLE_GRAPH-ONTO-hermes2x2.map", "hermes-2x2"),
    ("sample-graph-b/sample-graph-b.csv", "sample-graph-b/hermes2x2.map", "hermes-2x2"),
    ("shi-2010/SHI2010.csv", "shi-2010/shi2010-ONTO-hermes4x4.map", "hermes-4x4"),
    ("str2rts-cfar/STR2RTS-CFAR.csv", "str2rts-cfar/STR2RTS-CFAR-ONTO-hermes2x2.map", "hermes-2x2"),
    ("str2rts-dct-verify/DCT-Verify.csv", "str2rts-dct-verify/STR2RST-DCT-verify-ONTO-hermes3x2.map", "hermes-2x3"),
    ("synthetic-flow-a/SyntheticA.csv", "synthetic-flow-a/Synthetic-Flow-A-ONTO-hermes2x2.map", "hermes-2x2"),
    ("synthetic-flow-d/SyntheticD.csv", "synthetic-flow-d/Synthetic-Flow-D-ONTO-hermes4x4.map", "hermes-4x4"),
    ("synthetic-app-e/synthetic-app-e.csv", "synthetic-app-e/synthetic-app-e-ONTO-hermes2x2.map", "hermes-2x2"),
]


def map_files():
    out = []
    for d in sorted(os.listdir(APPS)):
        p = os.path.join(APPS, d)
        if os.path.isdir(p):
            out += [os.path.join(d, f) for f in sorted(os.listdir(p)) if f.endswith(".map")]
    return out


@pytest.mark.parametrize("rel", map_files())
def test_every_task_appears_once_in_each_map(rel):
    entries = mapfile.read(os.path.join(APPS, rel))
    names = [t for e in entries for t in e["tasks"]]
    assert sorted(names) == sorted(set(names)), rel
    nodes = [e["node"] for e in entries]
    assert sorted(nodes) == sorted(set(nodes)), rel


@pytest.mark.parametrize("app, mapping, arch", PAIRS)
def test_every_task_of_the_application_is_mapped_once(app, mapping, arch):
    g, _ = appparser.loadFromFile(os.path.join(APPS, app))
    noc = nocparser.loadFromFile(os.path.join(ARCH, arch + ".gml"))
    entries = mapfile.read(os.path.join(APPS, mapping))
    assert mapfile.problems(entries, list(g.nodes), list(noc.nodes)) == []


def test_app_e_map_is_fig_8_6a():
    entries = mapfile.read(os.path.join(APPS, "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map"))
    assert {e["node"]: sorted(e["tasks"]) for e in entries} == {
        "0": ["A", "B", "D", "F"], "1": ["C"], "2": ["E", "H", "I"], "3": ["G", "J"]}


def test_problems_found():
    entries = mapfile.parse("0:A,B\n1:B\n2:C\n2:D\n7:E\n")
    p = mapfile.problems(entries, tasks=["A", "B", "C", "D", "E", "F"], nodes=["0", "1", "2", "3"])
    assert "task B mapped 2 times (nodes 0, 1)" in p
    assert "node 2 on more than one line" in p
    assert "node 7 is not in the architecture" in p
    assert "task F not mapped" in p
    with pytest.raises(mapfile.MappingError):
        mapfile.check(entries, tasks=["A"])


def test_unknown_tasks_only_with_flag():
    entries = mapfile.parse("0:A,X\n")
    assert mapfile.problems(entries, tasks=["A"]) == []
    assert mapfile.problems(entries, tasks=["A"], unknown=True) == ["task X is not in the application"]
    assert mapfile.unknown_tasks(entries, ["A"]) == ["X"]


def test_parse_skips_blank_lines_and_comments_and_rejects_bad_lines():
    entries = mapfile.parse("# mapping\n\n0:A, B  # node 0\n1:C\n")
    assert entries == [{"node": "0", "tasks": ["A", "B"]}, {"node": "1", "tasks": ["C"]}]
    with pytest.raises(mapfile.MappingError):
        mapfile.parse("0 A,B\n")
    with pytest.raises(mapfile.MappingError):
        mapfile.parse("x:A\n")


def test_write_and_read_back(tmp_path):
    p = str(tmp_path / "m.map")
    mapfile.write(p, {"C": 0, "A": 1, "B": 1, "G": 2, "J": 2})
    assert open(p).read() == "0:C\n1:A,B\n2:G,J\n"
    assert mapfile.read(p) == [{"node": "0", "tasks": ["C"]}, {"node": "1", "tasks": ["A", "B"]},
                               {"node": "2", "tasks": ["G", "J"]}]
