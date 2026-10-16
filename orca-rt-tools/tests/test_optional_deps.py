"""Optional dependencies of rttools/modules/io/svg2.py.

svg2 does not import pygraphviz and imports matplotlib only where it draws,
so the path rttools -> minizinc -> svg2 of the AGS runs without both
libraries.
"""
import os
import shutil

from tests.conftest import run_module, REPO_ROOT

APP_DIR = os.path.join(REPO_ROOT, "apps", "sample-graph-a")


def test_cli_runs_without_pygraphviz_and_matplotlib(tmp_path):
    for f in ("SAMPLE_GRAPH.csv", "SAMPLE_GRAPH-ONTO-hermes2x2.map"):
        shutil.copy(os.path.join(APP_DIR, f), tmp_path)
    shutil.copy(os.path.join(REPO_ROOT, "arch", "hermes-2x2.gml"), tmp_path)
    r = run_module(
        "rttools", "SAMPLE_GRAPH.csv", "SAMPLE_GRAPH-ONTO-hermes2x2.map",
        "hermes-2x2.gml", "1000000", "1", "2000", "False",
        cwd=str(tmp_path), block=("pygraphviz", "matplotlib", "matplotlib.pyplot"),
    )
    assert r.returncode == 0, r.stderr[-2000:]
    assert (tmp_path / "results.svg").exists()
