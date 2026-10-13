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
        # the stored logs come from weird_a.c before the per-producer join of J
        out[r] = (exp23.analyze(os.path.join(EXP, "logs", f"{r}.events.txt"), cfg(), str(d), join="any3"), str(d))
    return out


@pytest.fixture(scope="module")
def run_f(tmp_path_factory):
    d = tmp_path_factory.mktemp("F")
    # run F (tag exp23-F): this tree, join rule per_producer of the config;
    # listings of its image for the bound of the instrumentation writes
    return exp23.analyze(os.path.join(EXP, "logs", "F.events.txt"), cfg(), str(d),
                         listing=os.path.join(EXP, "logs", "F.image.lst"),
                         listing_without=os.path.join(EXP, "logs", "F.noinstr.lst")), str(d)


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
    # deadline = start of the target in the phase after the source phase
    assert t82 == {"F1": (28530, 261000, 1230), "F2": (181930, 261000, 6780), "F3": (96330, 261000, 1200),
                   "F4": (128070, 370880, 5670), "F5": (173370, 370880, 8900)}
    assert m["monitor"]["errors"] == 0 and m["monitor"]["nodes"] == 4


def test_cpu_check_and_response_bound(run_f):
    m, _ = run_f
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


def test_phase_windows_come_from_the_release_model(monkeypatch):
    """The flow table takes release and deadline from the phase model of
    the analysis (release.phase_flows), equal to Tab. 8.2."""
    calls = []
    real = exp23.release.phase_flows
    monkeypatch.setattr(exp23.release, "phase_flows", lambda *a: calls.append(a) or real(*a))
    w = exp23.phase_windows(cfg())
    assert len(calls) == 1
    assert w == {"F1": (28530, 261000), "F2": (181930, 261000), "F3": (96330, 261000),
                 "F4": (128070, 370880), "F5": (173370, 370880)}


def test_units_detected_and_runs_equal_in_cycles(runs):
    a, d = runs["A"][0], runs["D"][0]
    assert a["unit"]["name"] == "100 ps" and d["unit"]["name"] == "1 ns"
    assert a["unit"]["swap_xy"] is False and d["unit"]["swap_xy"] is True
    for key in ("tab83", "iterations", "tab82"):
        assert json.dumps(a[key], sort_keys=True) == json.dumps(d[key], sort_keys=True)


def test_run_e_matches_its_reference(runs):
    _, d = runs["E"]
    assert exp23.check(os.path.join(d, "metrics.json"), os.path.join(EXP, "reference_E.json")) == []


def test_run_f_matches_head_reference(run_f):
    """Run F (tag exp23-F): the per-producer join of J, the default rule of
    the config; the pairing of the tags stays consistent."""
    m, d = run_f
    assert exp23.check(os.path.join(d, "metrics.json"), os.path.join(EXP, "reference_head.json")) == []
    assert m["join_rule"] == "per_producer" and m["packet_pairs"] == {"unexpected": 0}
    assert m["monitor"]["errors"] == 0 and m["monitor"]["send_pkts"] == m["monitor"]["recv_pkts"] == 166
    # GJ: mean of 7 hyperperiods; the first one differs (start-up of PE 1-1)
    gj = m["tab83"]["per_cluster"]["GJ"]
    assert gj["equal_in_all_hyperperiods"] is False
    assert gj["per_hyperperiod"][1:] == [182647.75, 182647.75, 182648.5, 182647.75, 182647.75, 182648.5]
    assert round(gj["mean"], 1) == 181763.6
    assert m["iterations"]["max_ms"] <= m["response_bound"]["ms"]
    run_info = open(os.path.join(EXP, "logs", "F.RUN_INFO")).read()
    assert "repo_state=archive\n" in run_info and "repo_tag=exp23-F\n" in run_info


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


def test_outputs_and_macros_of_run_f(run_f):
    _, d = run_f
    for f in ("tab83.tex", "tab83.csv", "iterations.tex", "tab82.tex", "values.tex", "fig812.svg", "fig812.pdf",
              "metrics.json"):
        assert os.path.getsize(os.path.join(d, f)) > 0, f
    values = open(os.path.join(d, "values.tex")).read()
    assert "\\newcommand{\\ExpGjMeasured}{181\\,763.6}" in values
    assert "\\newcommand{\\ExpMeanOverestimation}{27.53}" in values
    assert "\\newcommand{\\ExpMaxResponseMs}{1.861}" in values
    assert "GJ & 181\\,763.6 &" in open(os.path.join(d, "tab83.tex")).read()


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


class FakeTrace:
    """Receives at the PE of J, the slices of J and the end of the log."""

    def __init__(self, recvs, j_runs, t1):
        from rttools.tui.model.trace import Mark, Slice
        self.marks = [Mark("1-1", t, "recv", "TAG " + tag) for t, tag in recvs]
        self.slices = [Slice("1-1", a, b, "J") for a, b in j_runs]
        self.t1 = t1

    def lane_marks(self, lane):
        return [m for m in self.marks if m.lane == lane]

    def lane_slices(self, lane):
        return [s for s in self.slices if s.lane == lane]


def test_join_rules_differ_when_a_producer_is_ahead():
    """G sends the packets of iterations 1 and 2 before H and I send the
    packet of iteration 1: any3 completes iteration 1 at the third packet
    (the second packet of G); per_producer waits for H and I."""
    recvs = [(10, "1230"), (20, "1230"), (30, "8900"), (40, "5670"), (50, "8900"), (60, "5670")]
    tr = FakeTrace(recvs, [(35, 36), (45, 46), (65, 66)], 100)
    c = cfg()
    assert exp23.join_arrivals(tr, c, 0, "any3") == [30, 60]
    assert exp23.join_arrivals(tr, c, 0, "per_producer") == [40, 60]


def test_join_rule_selection():
    c = cfg()
    assert c["join"]["rule"] == "per_producer"
    assert exp23.join_rule(c) == "per_producer" and exp23.join_rule(c, "any3") == "any3"
    del c["join"]["rule"]
    assert exp23.join_rule(c) == "per_producer"
    with pytest.raises(ValueError):
        exp23.join_rule(c, "x")


@pytest.mark.parametrize("run", "ABCDE")
def test_stored_runs_same_response_with_both_rules_and_consistent_pairs(runs, run, tmp_path):
    m, _ = runs[run]
    assert m["join_rule"] == "any3"
    assert m["packet_pairs"] == {"unexpected": 0}
    p = exp23.analyze(os.path.join(EXP, "logs", f"{run}.events.txt"), cfg(), str(tmp_path), join="per_producer")
    assert p["iterations"]["all"] == m["iterations"]["all"]


def test_cycles_text():
    assert exp23.cycles_text(80968.50000000001) == "80,968.5"
    assert exp23.cycles_text(144098) == "144,098"
    assert exp23.cycles_text(144098.0) == "144,098"


class SliceTrace:
    def __init__(self, slices, t1):
        from rttools.tui.model.trace import Slice
        self.slices = [Slice("1-1", a, b, n) for a, b, n in slices]
        self.t1 = t1

    def lane_slices(self, lane):
        return [s for s in self.slices if s.lane == lane]


def test_closed_runs_keep_a_slice_closed_at_the_end_of_the_log():
    """A `scheduled` event at the last instant of the log closes the slice
    of J: the slice counts; the open slice that event starts leaves."""
    tr = SliceTrace([(10, 35, "G"), (35, 100, "J"), (100, 100, "G")], 100)
    assert exp23.closed_runs(tr, "1-1", "J") == [(35, 100)]


def test_closed_runs_leave_the_open_slice_cut_by_the_end_of_the_log():
    """No event closes the last slice of a lane: J may still run after the
    end of the log, so its slice leaves."""
    tr = SliceTrace([(10, 35, "G"), (35, 100, "J")], 100)
    assert exp23.closed_runs(tr, "1-1", "J") == []


def test_run_f_last_iterations_end_at_the_last_event(run_f):
    """Run F: J leaves the CPU at 19 865 063 ns ("1-1 scheduled 2", the last
    event of the log); iterations 31 and 32 end there."""
    m, _ = run_f
    it = m["iterations"]["all"]
    assert len(it) == 32
    assert [p["count"] for p in m["iterations"]["per_release_offset"]] == [8, 8, 8, 8]


def test_release_to_dispatch_and_response_from_release(run_f):
    """Run F: release (TRIGGER) to the first dispatch of A, over the complete
    iterations and over every release; maximum response counted from the
    release."""
    it, _ = run_f[0]["iterations"], run_f[1]
    assert it["complete"] == 32 and it["max_cycles"] == 930585
    assert it["release_to_dispatch"] == {"min_cycles": 1396, "max_cycles": 1891}
    assert it["release_to_dispatch_all_releases"] == {"releases": 34, "min_cycles": 1396, "max_cycles": 1924}
    assert it["response_from_release_max"]["cycles"] == 932143
    values = open(os.path.join(run_f[1], "values.tex")).read()
    assert "\\newcommand{\\ExpResponseFromReleaseMaxCycles}{932\\,143}" in values
    assert "\\newcommand{\\ExpReleaseToDispatchAllMaxCycles}{1\\,924}" in values
    assert "\\newcommand{\\ExpCompleteIterations}{32}" in values
