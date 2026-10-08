"""Pipelines of the visuals of the article: stored graphs of Table 7.1
(rttools/paper/graphs.py), CAR and criterion of application E
(rttools/paper/car.py), contraction example, Table 7.1 summary and the
figures of application E (rttools/paper/figures.py)."""
import json
import os

from tests.conftest import REPO_ROOT
from rttools.paper import car, ch7, figures, graphs
from rttools.paper.exp23 import check

EXP = os.path.join(REPO_ROOT, "experiments")
APPS = os.path.join(REPO_ROOT, "apps")
CH7 = os.path.join(EXP, "ch7")
FIG = os.path.join(EXP, "figures")


def load(path):
    with open(path) as f:
        return json.load(f)


def test_stored_graphs_extract_with_their_hashes(tmp_path):
    names = graphs.extract(os.path.join(CH7, "graphs"), str(tmp_path))
    sizes = load(os.path.join(CH7, "config.json"))["all_sizes"]
    assert names == sorted(f"10_{v}.txt" for v in sizes)
    assert graphs.verify(str(tmp_path), os.path.join(CH7, "graphs", graphs.SUMS)) == []


def test_verify_reports_a_changed_graph(tmp_path):
    src = os.path.join(CH7, "graphs")
    for v in (20, 30):
        with open(os.path.join(src, f"10_{v}.txt"), "rb") as f, open(tmp_path / f"10_{v}.txt", "wb") as g:
            g.write(f.read())
    sums = tmp_path / "SUMS"
    sums.write_text("".join(f"{graphs.sha256(os.path.join(src, f'10_{v}.txt'))}  10_{v}.txt\n" for v in (20, 30, 40)))
    with open(tmp_path / "10_30.txt", "a") as f:
        f.write("\n0 1 2\n")
    assert graphs.verify(str(tmp_path), str(sums)) == ["10_30.txt: sha256 differs", "10_40.txt: missing"]


def test_pack_is_deterministic_and_extract_inverts_it(tmp_path):
    src = os.path.join(CH7, "graphs")
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    graphs.pack(src, str(a / "x.tar.xz"), [20, 30])
    graphs.pack(src, str(b / "x.tar.xz"), [20, 30])
    assert (a / "x.tar.xz").read_bytes() == (b / "x.tar.xz").read_bytes()
    out = tmp_path / "out"
    assert graphs.extract(str(a), str(out)) == ["10_20.txt", "10_30.txt"]
    for v in (20, 30):
        assert graphs.sha256(out / f"10_{v}.txt") == graphs.sha256(os.path.join(src, f"10_{v}.txt"))


def test_car_and_criterion_of_application_e(tmp_path):
    cfg = load(os.path.join(CH7, "car.json"))
    m = car.write(str(tmp_path), car.run_car(cfg["car"], APPS), car.run_appe(cfg["appe"], APPS), cfg)
    assert check(str(tmp_path / "metrics.json"), os.path.join(CH7, "reference_car.json")) == []
    ref = m["car"]["rows"]["Reference"]
    assert (ref["E"], ref["intra_volume"], ref["noc_volume"]) == (38, 0, m["car"]["total_volume"])
    # the sum of the WCETs does not change under contraction
    for r in m["car"]["rows"].values():
        assert sum(c["load"] for c in r["clusters"]) == sum(c["load"] for c in m["car"]["input"]["clusters"])
    assert m["appe"]["chosen"] == "MAX_PROC"
    rows = (tmp_path / "tab-car-rows.tex").read_text().splitlines()[1:]
    assert rows[1] == r"MAX-PROC & 20 & 24.7 & 279,776 & 214,330 & 4.248 & 105.0 & 2 \\"
    assert rows[2] == r"MIN-COMM & 21 & 3.5 & 18,229 & 987,368 & 30.214 & 443.3 & 2 \\"


def test_car_graph_has_the_edges_of_the_source():
    """apps/shi-2010/shi-2010.txt has the edges of SHI2010.csv (Shi et al.
    2010), including FBU8->VOD2 (the file had FBU3->VOD2)."""
    from rttools.gff.orca import import_graph
    from rttools.modules.io import appparser
    g, _ = appparser.loadFromFile(os.path.join(APPS, "shi-2010", "SHI2010.csv"))
    txt = import_graph(os.path.join(APPS, "shi-2010", "shi-2010.txt"))
    edges = sorted((e._from._data["label"], e._to._data["label"]) for e in txt._edges)
    assert edges == sorted(g.edges())
    assert ("FBU8", "VOD2") in edges and ("FBU3", "VOD2") not in edges


def test_contraction_example(tmp_path):
    m = figures.contraction(os.path.join(APPS, "sample-graph-a", "sample_graph.txt"), 4, str(tmp_path))
    assert check(str(tmp_path / "contraction.json"), os.path.join(FIG, "reference_contraction.json")) == []
    for c in m["criteria"].values():
        assert len(c["steps"]) == 10 - 4
        # payload between clusters = payload of the edges left in the collapsed graph
        assert c["w_noc"] == c["out_payload"]
    # MIN-COMM contracts the edges in decreasing payload order (Kruskal)
    mc = m["criteria"]["MIN_COMM"]["steps"]
    assert list(mc) == ["E-I", "H-J", "B-D", "F-G", "I-J", "A-B"]
    body = (tmp_path / "fig-contraction-body.tex").read_text()
    assert body.count("\\begin{scope}[xshift=") == 2


def test_table71_summary_and_cluster_sizes(tmp_path):
    cfg = load(os.path.join(CH7, "config.json"))
    ch7.run(cfg, os.path.join(CH7, "graphs"), str(tmp_path / "run"), sizes=[20, 30, 100])
    m = figures.table71(str(tmp_path / "run" / "metrics.json"), os.path.join(CH7, "graphs"), str(tmp_path / "s"))
    rows = {d["V"]: d for d in m["rows"]}
    # cluster sizes of the stored graphs
    assert rows[20]["mc"]["cluster_sizes"] == [1, 1, 1, 17]
    assert rows[20]["mp"]["cluster_sizes"] == [3, 5, 6, 6]
    assert rows[100]["mc"]["cluster_sizes"] == [1, 1, 4, 94]
    for d in m["rows"]:
        for p in ("mc", "mp"):
            assert sum(d[p]["cluster_sizes"]) == d["V"]
            # NoC payload share = M3_in / M3_out
            assert abs(d[p]["noc_percent"] - 100 * d["M3"] / d[p]["M3"]) < 1e-9
    assert rows[20]["mc"]["kept_percent"] == 100 * 55 / 228
    # rho: ordered pairs of distinct vertices, 1 - 17 * 16 / (20 * 19)
    assert abs(rows[20]["mc"]["rho_percent"] - 100 * (1 - 272 / 380)) < 1e-9
    s = m["summary"]
    assert s["cluster_sizes"]["min_comm_three_single_tasks"] == 2
    assert s["mc"]["kept_percent"]["max"] == rows[20]["mc"]["kept_percent"]
    lines = (tmp_path / "s" / "tab-table71-rows.tex").read_text().splitlines()
    assert len(lines) == 1 + 6 and lines[1].count("&") == 7


def test_figures_of_application_e(tmp_path):
    cfg = load(os.path.join(EXP, "exp23", "config.json"))
    fcfg = load(os.path.join(FIG, "config.json"))
    # run F (tag exp23-F), join rule per_producer (default of the config)
    m = figures.exp23_figures(os.path.join(EXP, "exp23", "logs", "F.events.txt"), cfg, fcfg, str(tmp_path))
    assert m["join_rule"] == "per_producer"
    assert check(str(tmp_path / "metrics.json"), os.path.join(FIG, "reference_exp23.json")) == []
    assert m["gantt"]["busy_equals_tab83"]
    assert all(r["latency_matches_tab82"] for r in m["flows"])
    f1 = m["flows"][0]
    # L0 = 6 (m + 1) + p + 1 with p = 3 + ceil(1230 / 4)
    assert (f1["hops"], f1["flits"], f1["L0"]) == (1, 311, 324)
    assert len((tmp_path / "fig-iterations-coords.tex").read_text().splitlines()) == 1 + 30 + 1


def test_pe_coordinates_follow_the_swapped_labels():
    assert figures.pe_xy("0-1") == (1, 0)
    assert figures.pe_xy("1-0") == (0, 1)
