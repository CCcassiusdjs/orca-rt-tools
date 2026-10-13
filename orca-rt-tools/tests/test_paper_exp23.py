"""Pipeline of Ch. 8 (rttools/paper/exp23.py) on the stored logs."""
import json
import math
import os
import shutil
import subprocess

import pytest

from tests.conftest import REPO_ROOT
from rttools.paper import exp23

EXP = os.path.join(REPO_ROOT, "experiments", "exp23")


def cfg():
    return exp23.load_config(os.path.join(EXP, "config.json"))


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
    # deadline = start of the target in the phase after the source phase; dispatch order of the
    # kernel rule: E, H, I (F5 leaves H at 98 000, F4 leaves I at 173 370) and J, G (J starts at 11 000)
    assert t82 == {"F1": (28530, 261000, 1230), "F2": (181930, 368570, 6780), "F3": (96330, 261000, 1200),
                   "F4": (173370, 261000, 5670), "F5": (98000, 261000, 8900)}
    assert m["monitor"]["errors"] == 0 and m["monitor"]["nodes"] == 4


def test_cpu_check_and_response_bound(run_f):
    m, _ = run_f
    assert m["cpu"]["demand_cycles"] == {"ABDF": 181930, "C": 96330, "EHI": 173370, "GJ": 217450}
    assert m["cpu"]["f_cpu_hz"] == 434900000 and m["cpu"]["meets_phase"] is True
    assert m["cpu"]["phase_percent"]["GJ"] == pytest.approx(86.98)
    rb = m["response_bound"]
    # J runs first on GJ: f^(J) = c^(J) = 107 570, R^ = 3 P + 107 570
    assert (rb["cycles"], rb["task"], rb["phase"]) == (3 * 250000 + 107570, "J", 3)
    assert rb["ms"] == pytest.approx(1.71514)
    # J of iteration k runs in phase 3 and G of iteration k in phase 1 (phi(J) comes from I and H)
    assert rb["phases"] == {"A": 0, "B": 0, "D": 0, "F": 0, "C": 1, "G": 1, "E": 2, "H": 2, "I": 2, "J": 3}
    assert m["sequences"] == {"ABDF": ["A", "B", "D", "F"], "C": ["C"], "EHI": ["E", "H", "I"], "GJ": ["J", "G"]}
    # the measured response of log F (1.861 ms) closes at the exit of J after the two iterations
    # that one slice of J serves; the bound of one iteration stays below it until the response
    # is measured per iteration (PR 102)
    assert rb["ms"] < m["iterations"]["max_ms"] <= m["iterations"]["deadline_ms"]


def test_sequence_comes_from_the_bench_engine(monkeypatch):
    """cpu_sequence calls ORT/BENCH (no closed form in the pipeline)."""
    calls = []
    real = exp23.cpu_estimate.sequence
    monkeypatch.setattr(exp23.cpu_estimate, "sequence", lambda *a: calls.append(a) or real(*a))
    seq = exp23.cpu_sequence(cfg())
    assert len(calls) == 4
    assert {t: (v["start"], v["finish"]) for t, v in seq.items() if v["cluster"] == "EHI"} == \
        {"E": (11000, 52700), "H": (63700, 98000), "I": (109000, 173370)}
    assert {t: (v["start"], v["finish"]) for t, v in seq.items() if v["cluster"] == "GJ"} == \
        {"J": (11000, 107570), "G": (118570, 217450)}


def test_phase_windows_come_from_the_release_model(monkeypatch):
    """The flow table takes release and deadline from the phase model of
    the analysis (release.phase_flows), equal to Tab. 8.2."""
    calls = []
    real = exp23.release.phase_flows
    monkeypatch.setattr(exp23.release, "phase_flows", lambda *a: calls.append(a) or real(*a))
    w = exp23.phase_windows(cfg())
    assert len(calls) == 1
    assert w == {"F1": (28530, 261000), "F2": (181930, 368570), "F3": (96330, 261000),
                 "F4": (173370, 261000), "F5": (98000, 261000)}


def test_dispatch_order_comes_from_the_creation_rows_of_the_csv():
    """The creation rows of the application CSV (config application) are
    the source of the order; the order of estimate.clusters is not read."""
    c = cfg()
    assert exp23.creation_order(c) == {"ABDF": ["F", "D", "B", "A"], "C": ["C"], "EHI": ["H", "I", "E"],
                                       "GJ": ["J", "G"]}
    c["estimate"]["clusters"]["EHI"] = list(reversed(c["estimate"]["clusters"]["EHI"]))
    assert exp23.dispatch_sequences(c)["EHI"] == ["E", "H", "I"]


def test_log_table_must_follow_the_creation_rows():
    c = cfg()
    c["pe_tasks"]["1-0"] = ["IDLE", "E", "I", "H"]
    with pytest.raises(ValueError):
        exp23.creation_order(c)
    c = cfg()
    c["application"] = "../../apps/synthetic-app-e/synthetic-app-e.csv"
    with pytest.raises(ValueError):
        exp23.creation_order(c)


def test_run_f_dispatch_follows_the_kernel_rule(run_f):
    """Log F: per phase, ABDF runs A, B, D, F and EHI runs E, H, I (never
    E, I, H). GJ runs J, G in the phases in which J is ready at the tick
    (J dispatched first) and G, J in the phases in which the packets of I
    reach J after the tick (one slice of I serves two iterations); in no
    phase with both ready at the tick does G run first."""
    c = cfg()
    tr = exp23.load(os.path.join(EXP, "logs", "F.events.txt"), c)
    clk = exp23.Clock(tr.unit, c["clock_hz"])
    p = clk.raw(c["release_period_s"])
    seen = {}
    for pe, cluster in c["clusters"].items():
        by = {}
        for sl in tr.lane_slices(pe):
            if sl.label != "IDLE":
                by.setdefault(int(sl.start // p), []).append(sl)
        for k, ss in by.items():
            if 8 <= k < 40:
                seen.setdefault(cluster, set()).add(" ".join(x.label for x in ss))
    assert seen == {"ABDF": {"A B D F"}, "C": {"C"}, "EHI": {"E H I"}, "GJ": {"G J", "J G"}}
    for sl in tr.lane_slices("1-1"):
        k = int(sl.start // p)
        if sl.label == "J" and 8 <= k < 40 and clk.cycles(sl.start - k * p) < 5000:
            rest = [x.label for x in tr.lane_slices("1-1") if int(x.start // p) == k and x.label != "IDLE"]
            assert rest == ["J", "G"]


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
    # one slice of J serves two iterations: the measured response exceeds the bound of one
    # iteration (PR 102 measures per iteration)
    assert m["response_bound"]["ms"] < m["iterations"]["max_ms"]
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
    assert "\\newcommand{\\ExpResponseBoundMs}{1.715}" in values
    assert "\\newcommand{\\ExpResponseBoundCycles}{857\\,570}" in values
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


# ------------------------------------------------- clock of the simulation

def test_half_period_and_flow_clock():
    """simulate.sh: half period floor(1e15 / (2 F_CLK)) fs, clock at or
    above F_CLK. The flow returns f_CPU = 434.9 MHz; with T = 0.5 ms the
    release period must be a whole number of TIMER1 steps of 16 cycles,
    so F_CLK is a multiple of 32 kHz: 434.912 MHz."""
    assert exp23.half_period_fs(500_000_000) == 1_000_000
    assert exp23.half_period_fs(435_200_000) == 1_148_897
    ck = exp23.flow_clock(434_900_000, 0.0005)
    assert (ck["f_clk_hz"], ck["grid_hz"], ck["half_period_fs"], ck["period_fs"]) == (434_912_000, 32_000, 1_149_657,
                                                                                      2_299_314)
    assert (ck["release_cycles"], ck["tick_steps"]) == (217_456, 13_591)
    assert ck["clock_hz_exact"] == pytest.approx(434_912_326.024, abs=1e-3)
    assert ck["clock_hz_exact"] >= ck["f_clk_hz"] >= 434_900_000
    # a frequency on the grid stays; 500 MHz and 435.2 MHz are on it
    assert exp23.flow_clock(434_912_000, 0.0005)["f_clk_hz"] == 434_912_000
    assert exp23.flow_clock(500_000_000, 0.0005)["half_period_fs"] == 1_000_000
    assert exp23.flow_clock(435_200_000, 0.0005)["clock_hz_exact"] == pytest.approx(435_200_022.282, abs=1e-3)
    # 1 ps precision: half period 1149 ps
    assert exp23.flow_clock(434_900_000, 0.0005, precision_fs=1000)["half_period_fs"] == 1_149_000


def test_clock_of_frequency_run_and_cli(capsys):
    """make flow-clock: the minimum frequency of the .map mapping of the
    frequency pipeline gives F_CLK."""
    ref = os.path.join(EXP, "reference_frequency.json")
    ck = exp23.clock_of_frequency_run(ref, cfg())
    assert ck["map"] == "synthetic-app-e-ONTO-hermes2x2.map" and ck["f_clk_hz"] == 434_912_000
    assert exp23.main(["clock", ref, "--config", os.path.join(EXP, "config.json"), "--field", "f_clk_hz"]) == 0
    assert capsys.readouterr().out.strip() == "434912000"


def write_run_info(path, f_clk, release_cycles=None):
    half = exp23.half_period_fs(f_clk)
    lines = ["repo_commit=unknown", "sim_ns=20000000 monitor=1", f"f_clk_hz={f_clk}",
             f"clock_half_period_fs={half}"]
    if release_cycles is not None:
        lines.append(f"release_cycles={release_cycles}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def test_simulation_clock_sources(tmp_path):
    """RUN_INFO with the clock keys wins over config clock_hz; RUN_INFO of
    run F (no clock keys) and no RUN_INFO fall back to the config; a
    release period in cycles different from the config stops."""
    c = cfg()
    f_info = exp23.run_info_path(os.path.join(EXP, "logs", "F.events.txt"))
    assert os.path.basename(f_info) == "F.RUN_INFO"
    assert exp23.simulation_clock(c, exp23.read_run_info(f_info))["source"] == "config"
    assert exp23.run_info_path(os.path.join(EXP, "logs", "A.events.txt")) is None
    p = tmp_path / "RUN_INFO"
    write_run_info(p, 435_200_000, 217_600)
    assert exp23.run_info_path(str(tmp_path / "events.txt")) == str(p)
    ck = exp23.simulation_clock(c, exp23.read_run_info(p))
    assert ck["source"] == "RUN_INFO" and ck["clock_hz"] == 435_200_000 and ck["half_period_fs"] == 1_148_897
    assert ck["cycle_hz"] == pytest.approx(1e15 / 2_297_794)
    write_run_info(p, 500_000_000, 250_000)
    ck = exp23.simulation_clock(c, exp23.read_run_info(p))
    assert ck["cycle_hz"] == 500_000_000 and ck["clock_hz"] == 500_000_000
    write_run_info(p, 435_200_000, 250_000)
    with pytest.raises(ValueError, match="release_cycles"):
        exp23.simulation_clock(c, exp23.read_run_info(p))


def test_run_f_with_run_info_at_500_mhz_matches_head_reference(tmp_path):
    """A new run at the default clock writes the clock keys to RUN_INFO;
    the analysis gives the numbers of run F (no edge restoration at 2 ns)."""
    d = tmp_path / "sim"
    d.mkdir()
    shutil.copy(os.path.join(EXP, "logs", "F.events.txt"), d / "events.txt")
    write_run_info(d / "RUN_INFO", 500_000_000, 250_000)
    m = exp23.analyze(str(d / "events.txt"), cfg(), str(tmp_path / "out"))
    assert m["clock"]["source"] == "RUN_INFO" and m["clock"]["edges_snapped"] is False
    assert exp23.check(str(tmp_path / "out" / "metrics.json"), os.path.join(EXP, "reference_head.json")) == []


F_SYNTH = 435_200_000


def synthetic_run(tmp_path):
    """Log of run F moved to a 435.2 MHz clock with the same events in
    cycles: event at rising edge n (2 n + 1 ns at 500 MHz) printed at
    round((2 n + 1) half) ns, half = 1 148 897 fs (manycore_top.sv with
    timescale 1ns/1fs prints integer ns). The config keeps the cycles of
    run F: T = 250 000 cycles, warm-up 1 500 000, first hyperperiod
    2 000 000, deadline 1 000 000."""
    import re
    half = exp23.half_period_fs(F_SYNTH)
    d = tmp_path / "synth"
    d.mkdir()
    out = []
    with open(os.path.join(EXP, "logs", "F.events.txt")) as f:
        for line in f:
            if "Time scale of" in line:
                out.append(line.replace("100ps", "1fs"))
                continue
            m = (re.match(r"(# TRIGGER: workflow iteration at )(\d+)(.*)", line, re.S)
                 or re.match(r"(# )(\d+)( .*)", line, re.S))
            if m:
                t = int(m.group(2))
                assert t % 2 == 1
                t = ((t * half) + 500_000) // 1_000_000
                line = m.group(1) + str(t) + m.group(3)
            out.append(line)
    (d / "events.txt").write_text("".join(out))
    write_run_info(d / "RUN_INFO", F_SYNTH, 250_000)
    c = cfg()
    for k, cyc in (("release_period_s", 250_000), ("warmup_s", 1_500_000), ("first_hyperperiod_s", 2_000_000),
                   ("response_deadline_s", 1_000_000)):
        c[k] = cyc / F_SYNTH
    return str(d / "events.txt"), c


def close(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6)
    return a == b


def test_cycles_at_another_clock_equal_run_f(run_f, tmp_path):
    """With a clock period that is not a whole number of ns, the analysis
    restores the rising edges and gives the cycles of run F: CPU time per
    iteration, responses, release to dispatch and packet latencies. The
    platform ms are cycles / F_CLK."""
    log, c = synthetic_run(tmp_path)
    m = exp23.analyze(log, c, str(tmp_path / "out"))
    a = run_f[0]
    assert m["clock"] == {"clock_hz": F_SYNTH, "cycle_hz": pytest.approx(1e15 / 2_297_794),
                          "half_period_fs": 1_148_897, "source": "RUN_INFO", "run_info": "RUN_INFO",
                          "edges_snapped": True}
    for r, s in zip(a["tab83"]["rows"], m["tab83"]["rows"]):
        assert (r["cluster"], r["estimated"]) == (s["cluster"], s["estimated"])
        assert close(r["measured"], s["measured"])
    for cl in a["tab83"]["per_cluster"]:
        assert all(close(x, y) for x, y in zip(a["tab83"]["per_cluster"][cl]["per_hyperperiod"],
                                              m["tab83"]["per_cluster"][cl]["per_hyperperiod"]))
    keys = ("iteration", "response_cycles", "release_to_dispatch_cycles", "response_from_release_cycles")
    assert [{k: p[k] for k in keys} for p in a["iterations"]["all"]] == \
        [{k: p[k] for k in keys} for p in m["iterations"]["all"]]
    assert m["iterations"]["release_to_dispatch_all_releases"] == a["iterations"]["release_to_dispatch_all_releases"]
    lat = ("flow", "latency_min_cycles", "latency_max_cycles", "packets", "min_release", "deadline")
    assert [{k: r[k] for k in lat} for r in a["tab82"]] == [{k: r[k] for k in lat} for r in m["tab82"]]
    assert m["iterations"]["max_cycles"] == 930_585
    assert m["iterations"]["max_ms"] == pytest.approx(930_585 / F_SYNTH * 1e3, abs=1e-9)
    assert m["parameters"]["release_period_cycles"] == 250_000
    assert "cycles at 435.2 MHz" in open(tmp_path / "out" / "tab83.tex").read()


def test_figures_at_another_clock_equal_run_f(tmp_path):
    """experiments/figures (rttools.paper.figures exp23) on the same log:
    the flow table and the Gantt busy times of reference_exp23.json."""
    from rttools.paper import figures
    log, c = synthetic_run(tmp_path)
    with open(os.path.join(REPO_ROOT, "experiments", "figures", "config.json")) as f:
        fcfg = json.load(f)
    with open(os.path.join(REPO_ROOT, "experiments", "figures", "reference_exp23.json")) as f:
        ref = json.load(f)
    m = figures.exp23_figures(log, c, fcfg, str(tmp_path / "fig"))
    cols = ("flow", "latency_min", "latency_max", "send_min", "send_max", "arrival_max", "release", "deadline")
    assert [{k: r[k] for k in cols} for r in m["flows"]] == [{k: r[k] for k in cols} for r in ref["flows"]]
    assert m["gantt"]["busy_equals_tab83"] is True
    assert m["iterations"]["max_cycles"] == ref["iterations"]["max_cycles"]


def test_snap_to_edges_rejects_a_time_off_the_clock(tmp_path):
    """A time farther than half a unit from every rising edge stops the
    analysis (wrong half period in RUN_INFO)."""
    log, c = synthetic_run(tmp_path)
    tr = exp23.load(log, dict(c, clock_hz=F_SYNTH), None, None)
    with pytest.raises(ValueError, match="rising edge"):
        exp23.snap_to_edges(tr, 1_100_000)


def test_reference_flow_is_the_model_at_the_flow_clock():
    """reference_flow.json (make paper-flow) holds the model at F_CLK of
    make flow-clock; recomputed from config.json."""
    with open(os.path.join(EXP, "reference_flow.json")) as f:
        ref = json.load(f)
    ck = exp23.clock_of_frequency_run(os.path.join(EXP, "reference_frequency.json"), cfg())
    c = dict(cfg(), clock_hz=ck["f_clk_hz"])
    assert ref["clock"]["clock_hz"] == ck["f_clk_hz"] and ref["clock"]["half_period_fs"] == ck["half_period_fs"]
    assert ref["parameters"]["release_period_cycles"] == ck["release_cycles"]
    cpu = exp23.cpu_check(c, exp23.estimates(c))
    assert {k: ref["cpu"][k] for k in ref["cpu"]} == {k: cpu[k] for k in ref["cpu"]}
    rb = exp23.response_bound(c)
    assert {k: ref["response_bound"][k] for k in ref["response_bound"]} == {k: rb[k] for k in ref["response_bound"]}
    assert rb["ms"] <= rb["deadline_ms"]


def test_no_500_mhz_constant_in_the_pipeline():
    """The exp23 pipeline takes the clock from RUN_INFO or config.json:
    no 500 MHz, 250000 or 250016 literal in rttools/paper and in the
    scripts of experiments/exp23 (the defaults of simulate.sh and of the
    Makefile are the clock of run F; F0 is the first frequency of the
    search of the flow)."""
    import re
    pat = re.compile(r"\b(500[_,]?000[_,]?000|5e8|500e6|250[_,]?000|250[_,]?016)\b|500 ?MHz")
    root = os.path.join(REPO_ROOT, "orca-rt-tools", "rttools", "paper")
    hits = []
    for name in sorted(os.listdir(root)):
        if name.endswith(".py"):
            with open(os.path.join(root, name)) as f:
                for i, line in enumerate(f, 1):
                    if pat.search(line) and "--f0" not in line:
                        hits.append(f"{name}:{i}: {line.strip()}")
    assert hits == []


@pytest.mark.parametrize("f_clk, rc, text", [
    ("435200000", 2, "clock: F_CLK 435200000 Hz, half period 1148897 fs (435200022.282 Hz), release every 217600 "
                     "cycles, first at cycle 1305600, F_TICK 2000 Hz"),
    ("434912000", 2, "half period 1149657 fs (434912326.024 Hz), release every 217456 cycles"),
    ("500000000", 2, "half period 1000000 fs (500000000.000 Hz), release every 250000 cycles, first at cycle 1500000"),
    ("434900000", 2, "not a multiple of 16"),
    ("1000000000", 2, "below 1 GHz"),
    ("4.352e8", 2, "positive integer"),
])
def test_simulate_sh_clock(tmp_path, f_clk, rc, text):
    """simulate.sh derives the clock of the run from F_CLK before any tool
    check; without vsim on PATH it stops after printing it."""
    path = "/usr/bin:/bin"
    if shutil.which("vsim", path=path):
        pytest.skip("vsim on " + path)
    r = subprocess.run([os.path.join(EXP, "simulate.sh"), str(tmp_path / "out"), "1000"],
                       env={"PATH": path, "F_CLK": f_clk}, capture_output=True, text=True, timeout=60)
    assert r.returncode == rc
    assert text in r.stdout + r.stderr
    assert not (tmp_path / "out").exists()
