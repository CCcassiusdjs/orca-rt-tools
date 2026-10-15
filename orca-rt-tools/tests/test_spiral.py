"""ORT/SM, Spiral Mapping (ORCA RT-Tools reference, Section 8.1.2, Table 8.1, Fig. 8.2).

The repository of the ORCA RT-Tools reference has no implementation of the Spiral
Mapping; rttools/modules/mapping/spiral.py implements the rule of
Fig. 8.2.
"""
import os

from tests.conftest import REPO_ROOT
from rttools.gff.orca import import_graph
from rttools.modules.io import appparser
from rttools.modules.mapping import spiral

APPS = os.path.join(REPO_ROOT, "apps")

# Table 8.1: number, cluster (as printed), network volume
TABLE_8_1 = [
    (1, "SPES", 15360), (2, "TPRC", 2048), (3, "THRC", 20480), (4, "FBU1:BFE1", 51200),
    (5, "FBU2:BFE2", 51200), (6, "FBU4:BFE4", 51200), (7, "FBU5:BFE5", 51200), (8, "FBU6:BFE6", 51200),
    (9, "FBU7:BFE7", 51200), (10, "FBU8:BFE8", 51200), (11, "BFE3:FDF1", 1164800), (12, "FDF2:STPH", 358400),
    (13, "POSI:NAVI:DIRC", 56832), (14, "FBU3:VOD1:VOD2", 972800), (15, "USOS:OBDB:OBMG", 141312),
    (16, "VIBS:TPMS:STAC", 22528),
]

# Fig. 8.2 (f), top row first: cluster numbers of Table 8.1
FIG_8_2_F = [
    [9, 8, 7, 6],
    [10, 11, 14, 5],
    [13, 15, 12, 4],
    [2, 1, 3, 16],
]


def grid_of(cluster_nodes, width, height):
    inv = {n: c for c, n in cluster_nodes.items()}
    return [[inv.get(y * width + x) for x in range(width)] for y in range(height - 1, -1, -1)]


def test_spiral_order_4x4():
    # bottom row, right column up, top row leftwards, left column down,
    # then the inner ring in the same way
    assert spiral.spiral_order(4, 4) == [0, 1, 2, 3, 7, 11, 15, 14, 13, 12, 8, 4, 5, 6, 10, 9]


def test_spiral_order_covers_rectangular_meshes():
    for w, h in [(1, 1), (2, 2), (2, 3), (3, 2), (5, 5), (8, 10), (1, 4), (4, 1)]:
        order = spiral.spiral_order(w, h)
        assert sorted(order) == list(range(w * h)), (w, h)
    assert spiral.spiral_order(2, 2) == [0, 1, 3, 2]
    assert spiral.spiral_order(3, 2) == [0, 1, 2, 5, 4, 3]


def test_fig_8_2_from_table_8_1():
    clusters = [n for n, _, _ in TABLE_8_1]
    volumes = {n: v for n, _, v in TABLE_8_1}
    cmap = spiral.spiral_map(clusters, volumes, 4, 4)
    assert grid_of(cmap, 4, 4) == FIG_8_2_F
    # steps (a) to (f): increasing volume; the tie at 51200 keeps the
    # numbering of Table 8.1
    placed = sorted(cmap, key=lambda c: spiral.spiral_order(4, 4).index(cmap[c]))
    assert placed == [2, 1, 3, 16, 4, 5, 6, 7, 8, 9, 10, 13, 15, 12, 14, 11]


def car_edges(fbu3_vod2=False):
    """Tasks and edges of apps/shi-2010/shi-2010.txt (edge FBU8->VOD2, as in
    SHI2010.csv and Shi et al.); fbu3_vod2=True replaces that edge by
    FBU3->VOD2."""
    tasks, edges = spiral.from_orca(import_graph(os.path.join(APPS, "shi-2010", "shi-2010.txt")))
    assert ("FBU8", "VOD2", 960000) in edges
    if fbu3_vod2:
        edges = [("FBU3", v, w) if (u, v) == ("FBU8", "VOD2") else (u, v, w) for u, v, w in edges]
    return tasks, edges


def test_car_clustered_by_gcm_and_mapped():
    """Steps 1 and 2 on the CAR graph of Chapter 7 (apps/shi-2010/shi-2010.txt,
    edge FBU8->VOD2 as in SHI2010.csv): MAX_PROC wins. 12 clusters equal
    clusters of Table 8.1, 11 of them with the volume of the table
    (POSI:NAVC:DIRC: 79 872, table 56 832). VOD2 joins FBU8, so the other
    4 clusters differ from the table (FBU3:VOD1:VOD2, FBU8:BFE8, BFE3:FDF1,
    FDF2:STPH)."""
    res = spiral.map_application(*car_edges(), 4, 4)
    assert res["criterion"] == "MAX_PROC"
    by_set = {frozenset(c.split(":")): c for c in res["clusters"]}
    table = {frozenset(name.replace("NAVI", "NAVC").split(":")): vol for _, name, vol in TABLE_8_1}
    common = {by_set[k]: (res["volumes"][by_set[k]], v) for k, v in table.items() if k in by_set}
    assert len(common) == 12
    assert {c: vv for c, vv in common.items() if vv[0] != vv[1]} == {"POSI:NAVC:DIRC": (79872, 56832)}
    others = {c: res["volumes"][c] for c in res["clusters"] if c not in common}
    assert {frozenset(c.split(":")): v for c, v in others.items()} == {
        frozenset(["FBU3", "VOD1"]): 972800, frozenset(["FBU8", "VOD2"]): 972800,
        frozenset(["BFE8", "FDF2"]): 1318400, frozenset(["BFE3", "FDF1", "STPH"]): 1420800}
    # increasing volume along the spiral
    order = spiral.spiral_order(4, 4)
    vols = [res["volumes"][c] for c in sorted(res["clusters"], key=lambda c: order.index(res["cluster_nodes"][c]))]
    assert vols == sorted(vols)


def test_car_with_the_edge_fbu3_vod2_gives_the_clusters_of_table_8_1():
    """With the edge FBU3->VOD2 in place of FBU8->VOD2, MAX_PROC gives the
    16 clusters of Table 8.1; the volumes of 4 clusters exceed the table, so
    the edge does not explain the volumes."""
    res = spiral.map_application(*car_edges(fbu3_vod2=True), 4, 4)
    assert res["criterion"] == "MAX_PROC"
    by_set = {frozenset(c.split(":")): c for c in res["clusters"]}
    table = {frozenset(name.replace("NAVI", "NAVC").split(":")): vol for _, name, vol in TABLE_8_1}
    assert set(table) == set(by_set)
    differ = {by_set[k]: res["volumes"][by_set[k]] for k, v in table.items() if res["volumes"][by_set[k]] != v}
    assert differ == {"BFE3:FDF1": 1318400, "FDF2:STPH": 512000, "POSI:NAVC:DIRC": 79872,
                      "FBU3:VOD1:VOD2": 985600}


def test_app_e_spiral_mapping():
    """Application E (synthetic-app-e.txt) on the 2x2 mesh. ORT/GCM chooses
    MAX_PROC (clusters of Fig. 8.5). The Spiral Mapping gives C 0, ABDF 1,
    GJ 2, EHI 3; Fig. 8.6a (and weird_a.c) uses ABDF 0, C 1, EHI 2, GJ 3."""
    tasks, edges = spiral.from_orca(import_graph(os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.txt")))
    res = spiral.map_application(tasks, edges, 2, 2)
    sums = {r["criterion"]: sorted(r["wcet"]) for r in res["rows"]}
    # Fig. 8.5 at the scale of synthetic-app-e.txt (1/10)
    assert sums == {"MIN_COMM": [69900, 78900, 157900, 203600], "MAX_COMM": [56700, 79800, 179100, 194700],
                    "MIN_PROC": [12000, 12300, 45600, 440400], "MAX_PROC": [78900, 114600, 137700, 179100]}
    assert res["criterion"] == "MAX_PROC"
    assert round(min(r["sigma"] for r in res["rows"]), 3) == 36383.195
    assert res["volumes"] == {"C": 2430, "A:B:D:F": 8010, "E:H:I": 15770, "G:J": 21350}
    assert res["cluster_nodes"] == {"C": 0, "A:B:D:F": 1, "G:J": 2, "E:H:I": 3}
    fig_8_6a = {"A:B:D:F": 0, "C": 1, "E:H:I": 2, "G:J": 3}
    assert res["cluster_nodes"] != fig_8_6a


def test_app_e_csv_gives_the_same_mapping_as_the_graph():
    g, _ = appparser.loadFromFile(os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv"))
    res = spiral.map_application(*spiral.from_networkx(g), 2, 2)
    assert res["mapping"] == {"C": 0, "A": 1, "B": 1, "D": 1, "F": 1, "G": 2, "J": 2, "E": 3, "H": 3, "I": 3}


def test_volumes_ignore_edges_inside_a_cluster():
    vol = spiral.cluster_volumes({"X": ["a", "b"], "Y": ["c"]}, [("a", "b", 100), ("b", "c", 7), ("c", "a", 5)])
    assert vol == {"X": 12, "Y": 12}


def test_too_many_clusters():
    import pytest
    with pytest.raises(ValueError):
        spiral.spiral_map(["a", "b", "c"], {"a": 1, "b": 2, "c": 3}, 1, 2)
