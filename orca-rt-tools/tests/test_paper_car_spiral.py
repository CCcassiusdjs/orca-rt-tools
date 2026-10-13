"""Spiral Mapping of CAR in the pipeline of the article
(rttools/paper/car.py, run_spiral; experiments/ch7, make car)."""
import csv
import json
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.mapping import spiral as sm
from rttools.paper import car
from rttools.paper.ch7 import load_graph

APPS = os.path.join(REPO_ROOT, "apps")
CH7 = os.path.join(REPO_ROOT, "experiments", "ch7")


def load(path):
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def cfg():
    return load(os.path.join(CH7, "car.json"))["spiral"]


@pytest.fixture(scope="module")
def run(cfg):
    return car.run_spiral(cfg, APPS)


def test_mean_xy_distance_on_small_meshes():
    # 2x2: every node has distances 1, 1, 2 to the others
    assert [car.mean_xy(n, 2, 2) for n in range(4)] == [4 / 3] * 4
    # 3x3: corner 1+1+2+2+2+3+3+4 = 18, center 4 x 1 + 4 x 2 = 12, over 8 nodes
    assert car.mean_xy(0, 3, 3) == 18 / 8
    assert car.mean_xy(4, 3, 3) == 12 / 8
    assert car.hops(0, 15, 4) == 6 and car.hops(5, 9, 4) == 1


def test_outer_ring_of_the_4x4_mesh():
    assert [n for n in range(16) if not car.outer_ring(n, 4, 4)] == [5, 6, 9, 10]


def test_placement_cost_counts_payload_times_hops():
    inter = [("a", "b", 10), ("b", "c", 3)]
    assert car.placement_cost(inter, {"a": 0, "b": 3, "c": 15}, 4) == 10 * 3 + 3 * 3


def test_spiral_of_car_follows_the_volume_order(run):
    rows = run["rows"]
    assert run["criterion"] == "MAX_PROC"
    assert [r["position"] for r in rows] == list(range(1, 17))
    assert [r["node"] for r in rows] == sm.spiral_order(4, 4)
    vols = [r["volume"] for r in rows]
    assert vols == sorted(vols)
    assert (rows[0]["cluster"], rows[0]["volume"]) == ("TPRC", 2048)
    assert (rows[-1]["cluster"], rows[-1]["volume"]) == ("BFE3:FDF1:STPH", 1420800)
    # each inter-cluster edge counts for both of its clusters
    assert run["volume_sum"] == 2 * run["w_noc"] == 5273600
    # inner ring: positions 13 to 16, 88.8 % of the volume
    assert run["inner_nodes"] == [5, 6, 9, 10]
    assert [r["position"] for r in rows if not r["outer_ring"]] == [13, 14, 15, 16]
    assert run["inner_volume"] == 4684800
    assert round(run["inner_volume_percent"], 1) == 88.8
    # mean XY distance: corner 48/15, other outer 40/15, inner 32/15
    assert {r["mean_xy"] for r in rows} == {48 / 15, 40 / 15, 32 / 15}
    assert run["mean_xy"]["inner"] == {"min": 32 / 15, "max": 32 / 15}


def test_payload_hops_equals_the_task_mapping(run, cfg):
    """The cost over the inter-cluster edges equals the cost over all edges
    of the task graph under the task -> node mapping (edges inside a cluster
    have 0 hops)."""
    tasks, edges = sm.from_orca(load_graph(os.path.join(APPS, cfg["graph"])))
    tmap = sm.map_application(tasks, edges, 4, 4)["mapping"]
    assert run["payload_hops"]["spiral"] == sum(p * car.hops(tmap[a], tmap[b], 4) for a, b, p in edges) == 3242496
    assert sum(e["payload"] * e["hops"] for e in run["edges"]) == 3242496
    assert sum(e["payload"] for e in run["edges"]) == run["w_noc"]
    big = sorted(run["edges"], key=lambda e: -e["payload"])[:2]
    assert [(e["payload"], e["hops"]) for e in big] == [(960000, 1), (960000, 1)]


def test_reverse_spiral_and_random_placements(run):
    ph = run["payload_hops"]
    assert ph["reverse_spiral"] == 5537280
    rnd = ph["random"]
    assert (rnd["permutations"], rnd["seed"]) == (10000, 1)
    assert (rnd["min"], rnd["median"], rnd["max"]) == (3166720, 6920192, 13508096)
    assert (rnd["below_spiral"], rnd["equal_spiral"]) == (5, 0)
    assert rnd["min"] < ph["spiral"] < ph["reverse_spiral"] < rnd["median"]


def test_random_placements_depend_only_on_the_seed(cfg):
    small = dict(cfg, permutations=200)
    a = car.run_spiral(small, APPS)["payload_hops"]["random"]
    b = car.run_spiral(small, APPS)["payload_hops"]["random"]
    c = car.run_spiral(dict(small, seed=2), APPS)["payload_hops"]["random"]
    assert a == b
    assert a != c


def test_make_car_writes_spiral_csv_and_values(tmp_path):
    out = tmp_path / "car"
    assert car.main(["--config", os.path.join(CH7, "car.json"), "--apps", APPS, "--out", str(out)]) == 0
    from rttools.paper.exp23 import check
    assert check(str(out / "metrics.json"), os.path.join(CH7, "reference_car.json")) == []
    with open(out / "spiral.csv") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 16 and rows[12]["cluster"] == "FBU3:VOD1" and rows[12]["tasks"] == "FBU3 VOD1"
    with open(out / "spiral-edges.csv") as f:
        assert len(list(csv.DictReader(f))) == 20
    values = (out / "values.tex").read_text()
    for line in (r"\newcommand{\ExpCarSpiralCriterion}{MAX-PROC}",
                 r"\newcommand{\ExpCarSpiralPayloadHops}{3\,242\,496}",
                 r"\newcommand{\ExpCarSpiralReversePayloadHops}{5\,537\,280}",
                 r"\newcommand{\ExpCarSpiralRandomMedian}{6\,920\,192}",
                 r"\newcommand{\ExpCarSpiralRandomBelow}{5}",
                 r"\newcommand{\ExpCarSpiralInnerVolumePercent}{88.8}",
                 r"\newcommand{\ExpCarSpiralMeanXyOuterMax}{3.20}",
                 r"\newcommand{\ExpCarSpiralMeanXyOuterMin}{2.67}",
                 r"\newcommand{\ExpCarSpiralMeanXyInnerMax}{2.13}",
                 r"\newcommand{\ExpCarSpiralMesh}{\ensuremath{4\times4}}"):
        assert line in values.splitlines()


def test_figure_body_of_the_spiral_mapping(tmp_path, run):
    from rttools.paper import figures
    from rttools.paper.exp23 import check
    with open(tmp_path / "metrics.json", "w") as f:
        json.dump({"spiral": run}, f)
    m = figures.spiral_figure(str(tmp_path / "metrics.json"), str(tmp_path))
    assert check(str(tmp_path / "fig-spiral.json"), os.path.join(CH7, "reference_spiral_fig.json")) == []
    tiles = m["tiles"]
    # shading 3 at the smallest volume, 60 at the largest; labels in 10^3 flits, half up
    assert (tiles[0]["shade"], tiles[-1]["shade"]) == (3, 60)
    assert [t["volume_kflits"] for t in tiles] == [2, 15, 20, 23, 51, 51, 51, 51, 51, 51, 80, 141, 973, 973,
                                                   1318, 1421]
    assert m["frame"] == [0.5, 0.5, 2.5, 2.5] and m["arrows"] == 15
    body = (tmp_path / "fig-spiral-body.tex").read_text().splitlines()
    assert body[0].startswith("% generated by python -m rttools.paper.figures")
    assert sum(1 for line in body if line.startswith("\\node[sqt=")) == 16
    assert sum(1 for line in body if line.startswith("\\draw[sqar]")) == 15
    assert r"\node[sqc] at ([xshift=0.8mm]t16.center) {BFE3\\FDF1\\STPH\\[0.6pt]\textbf{1421}};" in body
    assert r"\draw[thick] (0.750,0.625) rectangle (3.750,3.125); % nodes off the outer ring [5, 6, 9, 10]" in body


def test_figure_command_line(tmp_path):
    from rttools.paper import figures
    out = tmp_path / "car"
    car.main(["--config", os.path.join(CH7, "car.json"), "--apps", APPS, "--out", str(out)])
    assert figures.main(["spiral", str(out / "metrics.json"), "--out", str(out)]) == 0
    assert (out / "fig-spiral-body.tex").exists() and (out / "fig-spiral.json").exists()
