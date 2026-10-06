"""Fix 12 (rttools/rgg/__main__.py and rttools/modules/io/svg.py).

1. RGG used the global numpy.random and random, without a seed: the graphs of
   Table 7.1 cannot be regenerated. It now accepts an optional seed.
2. svg.py drew colors at random on each run: two SVGs of the same scale
   differed byte by byte. The colors now use a generator with a fixed seed.
"""
import os
import shutil

from tests.conftest import run_module, REPO_ROOT
from rttools.rgg.__main__ import generate_random_graph


def dump(g):
    return ([(n._id, n._data) for n in g._nodes],
            [(e._from._id, e._to._id, e._data) for e in g._edges])


def test_rgg_same_seed_same_graph():
    a = generate_random_graph(10, [200, 2000], 3, [2000, 20000], seed=42)
    b = generate_random_graph(10, [200, 2000], 3, [2000, 20000], seed=42)
    c = generate_random_graph(10, [200, 2000], 3, [2000, 20000], seed=43)
    assert dump(a) == dump(b)
    assert dump(a) != dump(c)


def test_rgg_cli_seed(tmp_path):
    outs = []
    for name in ("a.txt", "b.txt"):
        r = run_module("rttools.rgg", "10", "200", "2000", "3", "2000", "20000",
                       str(tmp_path / name), "7")
        assert r.returncode == 0, r.stderr[-2000:]
        outs.append((tmp_path / name).read_text())
    assert outs[0] == outs[1]


def test_rgg_cli_without_seed_still_works(tmp_path):
    r = run_module("rttools.rgg", "10", "200", "2000", "3", "2000", "20000",
                   str(tmp_path / "x.txt"))
    assert r.returncode == 0, r.stderr[-2000:]


def test_svg_is_deterministic(tmp_path):
    app = os.path.join(REPO_ROOT, "apps", "sample-graph-a")
    svgs = []
    for k in ("r1", "r2"):
        d = tmp_path / k
        d.mkdir()
        for f in ("SAMPLE_GRAPH.csv", "SAMPLE_GRAPH-ONTO-hermes2x2.map"):
            shutil.copy(os.path.join(app, f), d)
        shutil.copy(os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"), d)
        r = run_module("rttools", "SAMPLE_GRAPH.csv", "SAMPLE_GRAPH-ONTO-hermes2x2.map",
                       "hermes-2x2.gml", "1000000", "1", "2000", "False", cwd=str(d))
        assert r.returncode == 0, r.stderr[-2000:]
        svgs.append((d / "results.svg").read_bytes())
    assert svgs[0] == svgs[1]
