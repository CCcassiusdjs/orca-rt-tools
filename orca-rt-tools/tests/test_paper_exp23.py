"""Pipeline of Ch. 8 (rttools/paper/exp23.py) on the stored logs."""
import json
import os
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from rttools.paper import exp23

EXP = os.path.join(REPO_ROOT, "experiments", "exp23")


def cfg():
    with open(os.path.join(EXP, "config.json")) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    out = {}
    for r in "ABCDE":
        d = tmp_path_factory.mktemp(r)
        out[r] = (exp23.analyze(os.path.join(EXP, "logs", f"{r}.events.txt"), cfg(), str(d)), str(d))
    return out


def test_run_d_matches_reference(runs):
    m, d = runs["D"]
    assert exp23.check(os.path.join(d, "metrics.json"), os.path.join(EXP, "reference_D.json")) == []


def test_corrected_values_of_chapter_8(runs):
    m, _ = runs["A"]
    rows = {r["cluster"]: r for r in m["tab83"]["rows"]}
    assert {c: rows[c]["measured"] for c in rows} == {"ABDF": 143900, "C": 80929, "EHI": 119220, "GJ": 182977}
    assert {c: rows[c]["estimated"] for c in rows} == {"ABDF": 181930, "C": 96330, "EHI": 173370, "GJ": 217450}
    assert m["tab83"]["mean_difference_percent"] == pytest.approx(27.43, abs=0.005)
    assert all(v["equal_in_all_hyperperiods"] for v in m["tab83"]["per_cluster"].values())
    assert sorted(round(p["max_ms"], 3) for p in m["iterations"]["per_release_offset"]) == [1.179, 1.361, 1.414, 1.861]
    t82 = {r["flow"]: (r["min_release"], r["deadline"], r["volume_bytes"]) for r in m["tab82"]}
    assert t82 == {"F1": (28530, 11000, 1230), "F2": (181930, 11000, 6780), "F3": (96330, 11000, 1200),
                   "F4": (128070, 120880, 5670), "F5": (173370, 120880, 8900)}
    assert m["monitor"]["errors"] == 0 and m["monitor"]["nodes"] == 4


def test_cpu_check_and_response_bound(runs):
    m, _ = runs["E"]
    assert m["cpu"]["demand_cycles"] == {"ABDF": 181930, "C": 96330, "EHI": 173370, "GJ": 217450}
    assert m["cpu"]["f_cpu_hz"] == 434900000 and m["cpu"]["meets_phase"] is True
    assert m["cpu"]["phase_percent"]["GJ"] == pytest.approx(86.98)
    rb = m["response_bound"]
    assert (rb["cycles"], rb["task"], rb["phase"]) == (967450, "J", 3)
    assert rb["ms"] == pytest.approx(1.9349)
    assert rb["phases"] == {"A": 0, "B": 0, "D": 0, "F": 0, "C": 1, "G": 1, "E": 2, "H": 2, "I": 2, "J": 3}
    # the bound covers every measured response
    assert m["iterations"]["max_ms"] <= rb["ms"] <= m["iterations"]["deadline_ms"]


def test_sequence_comes_from_the_bench_engine(monkeypatch):
    """cpu_sequence calls ORT/BENCH (no closed form in the pipeline)."""
    calls = []
    real = exp23.cpu_estimate.sequence
    monkeypatch.setattr(exp23.cpu_estimate, "sequence", lambda *a: calls.append(a) or real(*a))
    seq = exp23.cpu_sequence(cfg())
    assert len(calls) == 4
    assert {t: (v["start"], v["finish"]) for t, v in seq.items() if v["cluster"] == "EHI"} == \
        {"E": (11000, 52700), "I": (63700, 128070), "H": (139070, 173370)}


def test_units_detected_and_runs_equal_in_cycles(runs):
    a, d = runs["A"][0], runs["D"][0]
    assert a["unit"]["name"] == "100 ps" and d["unit"]["name"] == "1 ns"
    assert a["unit"]["swap_xy"] is False and d["unit"]["swap_xy"] is True
    for key in ("tab83", "iterations", "tab82"):
        assert json.dumps(a[key], sort_keys=True) == json.dumps(d[key], sort_keys=True)


def test_run_e_matches_head_reference(runs):
    _, d = runs["E"]
    assert exp23.check(os.path.join(d, "metrics.json"), os.path.join(EXP, "reference_head.json")) == []


def test_run_e_close_to_run_c(runs):
    """E (this tree) against C (fixed RTL and software of b920605). The
    only change to the simulated software between them is the zero-size
    check of ddma.c (828835f)."""
    c, e = runs["C"][0], runs["E"][0]
    for rc, re_ in zip(c["tab83"]["rows"], e["tab83"]["rows"]):
        assert abs(rc["measured"] - re_["measured"]) <= 2
    for fc, fe in zip(c["tab82"], e["tab82"]):
        assert 0 <= fc["latency_min_cycles"] - fe["latency_min_cycles"] <= 6


def test_outputs_and_macros(runs):
    _, d = runs["A"]
    for f in ("tab83.tex", "tab83.csv", "iterations.tex", "tab82.tex", "thesis.tex", "values.tex",
              "fig812.svg", "fig812.pdf", "metrics.json"):
        assert os.path.getsize(os.path.join(d, f)) > 0, f
    values = open(os.path.join(d, "values.tex")).read()
    assert "\\newcommand{\\ExpAbdfMeasured}{143\\,900}" in values
    assert "\\newcommand{\\ExpMaxResponseMs}{1.861}" in values
    assert "\\newcommand{\\ExpResponseBoundMs}{1.935}" in values
    assert "\\newcommand{\\ExpResponseBoundCycles}{967\\,450}" in values
    assert "\\newcommand{\\ExpCpuFrequencyMhz}{434.9}" in values


def test_check_reports_differences(tmp_path, runs):
    _, d = runs["A"]
    ref = {"tab83": {"rows": [{"measured": 1}]}, "_doc": "x"}
    p = tmp_path / "ref.json"
    p.write_text(json.dumps(ref))
    assert exp23.check(os.path.join(d, "metrics.json"), str(p)) == ["tab83.rows.0.measured: expected 1, got 143900"]


@pytest.mark.skipif(shutil.which("pdflatex") is None, reason="pdflatex missing")
def test_latex_tables_compile(runs, tmp_path):
    _, d = runs["A"]
    doc = tmp_path / "t.tex"
    doc.write_text("\\documentclass{article}\\usepackage{booktabs}\\begin{document}\n"
                   + "".join(f"\\input{{{os.path.join(d, n)}}}\n" for n in
                             ("values.tex", "tab83.tex", "iterations.tex", "tab82.tex", "thesis.tex"))
                   + "\\ExpAbdfMeasured\\end{document}\n")
    r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", str(doc)],
                       cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:]
