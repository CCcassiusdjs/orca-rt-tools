"""Pipelines of the visuals of the article: stored graphs of Table 7.1
(rttools/paper/graphs.py), CAR and criterion of application E
(rttools/paper/car.py), contraction example, Table 7.1 summary and the
figures of application E (rttools/paper/figures.py)."""
import json
import os

from tests.conftest import REPO_ROOT
from rttools.paper import graphs

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
