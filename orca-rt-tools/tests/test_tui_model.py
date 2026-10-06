"""Model layer of the TUI (rttools/tui/model): no Textual needed."""
import copy
import os
import xml.etree.ElementTree as ET

import pytest

from tests.conftest import REPO_ROOT, run_module
from rttools.tui.model import (
    benchmodel, compare, export, graphs, metrics, network, parsers, schedtests,
)
from rttools.tui.model.timeunit import RTL_PRESETS, TimeUnit, format_value
from rttools.tui.model.trace import Mark, Slice, Trace

RTL_LOG = """\
# Time scale of (manycore_tb.pe0) is 100ps / 100ps
# 1000 0-0 scheduled 0
# 1200 0-0 scheduled 4
# 1300 0-0 -> TAG 1230
# 1400 0-0 scheduled 3
# 1500 0-1 <- TAG 1230
# 1600 0-0 scheduled 0
# 1700 0-1 scheduled 1
# 1900 0-1 scheduled 0
# 2000 0-0 scheduled 9
"""


def rtl_lines(text=RTL_LOG):
    return text.splitlines(True)


# ------------------------------------------------------------- units

def test_unit_conversion_100ps():
    u = RTL_PRESETS["100ps"]
    assert u.convert(20, "cycles") == pytest.approx(1)          # 2 ns cycle
    assert u.convert(2_878_000, "cycles") == pytest.approx(143_900)
    assert u.convert(5_000_000, "ms") == pytest.approx(0.5)
    assert u.from_display(0.5, "ms") == pytest.approx(5_000_000)
    assert format_value(1234567, "raw") == "1,234,567"
    assert format_value(0.50000, "ms") == "0.5 ms"


def test_unit_without_seconds_offers_raw_only():
    assert TimeUnit(None, "unit").available_modes() == ["raw"]


# ------------------------------------------------------------ parsers

def test_parse_rtl_slices_marks_and_timescale():
    tr = parsers.parse_rtl(rtl_lines())
    assert tr.unit.name == "100 ps" and not tr.unit.assumed
    assert tr.lanes[:2] == ["0-0", "0-1"]
    s = tr.lane_slices("0-0")
    assert [(x.start, x.end, x.label) for x in s] == [
        (1000, 1200, "IDLE"), (1200, 1400, "A"), (1400, 1600, "B"), (1600, 2000, "IDLE"),
        (2000, 2000, "T9")]
    pk = tr.meta["packets"]
    assert pk == [{"tag": "1230", "src": "0-0", "dst": "0-1", "send": 1300, "recv": 1500, "latency": 200}]


def test_parse_rtl_without_timescale_is_assumed_1ns():
    tr = parsers.parse_rtl([l for l in rtl_lines() if "Time scale" not in l])
    assert tr.unit.name == "1 ns" and tr.unit.assumed


def test_parse_rtl_swap_xy():
    tr = parsers.parse_rtl(rtl_lines(), swap_xy=True)
    assert "1-0" in tr.lanes and "0-1" not in tr.lanes


def test_detect_formats(tmp_path):
    assert parsers.detect_format(rtl_lines()) == "rtl"
    assert parsers.detect_format(["0 10 A\n", "10 15 B\n"]) == "bench"
    assert parsers.detect_format(["x\n"], "trace.sch") == "kprofiler"
    tr = parsers.parse_rtl(rtl_lines())
    p = tmp_path / "t.csv"
    export.write_csv(tr, str(p))
    assert parsers.detect_format(p.read_text().splitlines(True)) == "csv"
    with pytest.raises(parsers.TraceFormatError):
        parsers.detect_format(["hello\n", "world\n"])


def test_bench_output_matches_bench_cli():
    src = os.path.join(REPO_ROOT, "apps", "sample-graph-a", "sample_graph.txt")
    r = run_module("rttools.bench", src, "single", "RR", "100000")
    assert r.returncode == 0
    from_cli = parsers.parse_bench(r.stdout.splitlines(True))
    tasks = benchmodel.load_tasks(src)
    tr, misses, end, _ = benchmodel.simulate(tasks, "RR", 100000)
    key = lambda t: [(s.start, s.end, s.label) for s in t.lane_slices("CPU")]
    assert key(from_cli) == key(tr)
    assert end == 51030


def test_kprofiler_example():
    path = os.path.join(REPO_ROOT, "orca-rt-tools", "rttools", "porca", "old-ccp-migration",
                        "apps", "kprofiler", "examples", "hfos.sch")
    tr = parsers.load_trace(path)
    assert tr.meta["format"] == "kprofiler"
    assert tr.lanes[-1] == "Kernel"
    rows = [l for l in open(path).readlines()[1:] if len(l.split()) >= 7]
    assert len([s for s in tr.slices if s.kind == "task"]) == len(rows)
    assert all(s.end >= s.start for s in tr.slices)


def test_csv_roundtrip(tmp_path):
    tr = parsers.parse_rtl(rtl_lines())
    p = tmp_path / "t.csv"
    export.write_csv(tr, str(p))
    back = parsers.load_trace(str(p))
    key = lambda t: sorted((s.lane, s.start, s.end, s.label) for s in t.slices)
    assert key(back) == key(tr)
    assert sorted((m.lane, m.time, m.kind) for m in back.marks) == sorted((m.lane, m.time, m.kind) for m in tr.marks)
    assert back.unit.seconds == pytest.approx(tr.unit.seconds) and back.unit.clock_hz == tr.unit.clock_hz


def test_svg_export_is_valid_xml(tmp_path):
    tr = parsers.parse_rtl(rtl_lines())
    p = tmp_path / "t.svg"
    export.write_svg(tr, str(p), mode="ns")
    root = ET.parse(str(p)).getroot()
    rects = [e for e in root.iter() if e.tag.endswith("rect")]
    assert len(rects) == 1 + len(tr.slices)       # background + slices


# ------------------------------------------------------------ queries

def make_trace():
    sl = [Slice("L", 0, 10, "A"), Slice("L", 10, 30, "IDLE", "idle"), Slice("L", 30, 35, "B"),
          Slice("L", 35, 50, "C"), Slice("L", 50, 60, "IDLE", "idle")]
    return Trace("t", TimeUnit(1e-9, "1 ns"), [], sl, [Mark("L", 32, "send", "x")])


def test_queries():
    tr = make_trace()
    assert [s.label for s in tr.slices_between("L", 5, 31)] == ["A", "IDLE", "B"]
    assert tr.slice_at("L", 34).label == "B"
    assert tr.slice_at("L", 60) is None
    assert tr.next_event(30) == 32 and tr.prev_event(30) == 10
    assert [m.time for m in tr.marks_between("L", 0, 33)] == [32]


def test_lane_stats_and_bursts():
    tr = make_trace()
    st = metrics.lane_stats(tr, "L", 0, 60)
    assert (st.busy, st.idle, st.slices) == (30, 30, 3)
    assert st.utilization == pytest.approx(0.5)
    b = metrics.bursts(tr, "L", 0, 60)
    assert [(x["start"], x["end"], x["sequence"], x["partial"]) for x in b] == [
        (0, 10, "A", False), (30, 50, "BC", False)]
    b = metrics.bursts(tr, "L", 5, 60)
    assert b[0]["partial"] is True


def test_compare_with_scale():
    a = make_trace()
    # B in a unit 10 times larger (as a 1 ns log against a 100 ps log)
    b = Trace("b", a.unit, [], [Slice(s.lane, s.start / 10, s.end / 10, s.label, s.kind) for s in a.slices])
    b2 = Trace("b2", a.unit, [], [Slice(s.lane, s.start, s.end, s.label, s.kind) for s in a.slices])
    assert compare.identical(compare.compare(a, b2))
    res = compare.compare(a, b, scale_b=10)
    assert res["L"]["matched"] == 5 and res["L"]["equal_times"] == 5
    c = Trace("c", a.unit, [], [Slice("L", s.start + (1 if s.label == "C" else 0), s.end, s.label)
                               for s in a.slices])
    r = compare.compare(a, c)["L"]
    assert r["first_time_mismatch"][0] == 3 and r["max_delta"] == 1
    assert not compare.identical(compare.compare(a, c))


# ------------------------------------------------- schedulability tests

CLASSIC = [{"name": "a", "wcet": 3, "period": 7}, {"name": "b", "wcet": 3, "period": 12},
           {"name": "c", "wcet": 5, "period": 20}]


def test_response_time_analysis_classic_example():
    # Burns and Wellings: R = 3, 6, 20
    assert [r["R"] for r in schedtests.response_times(CLASSIC, "RM")] == [3, 6, 20]
    assert schedtests.liu_layland_bound(3) == pytest.approx(0.7798, abs=1e-4)
    rows = dict((n, ok) for n, _, ok in schedtests.analyze(CLASSIC, "RM", 1))
    assert rows["RTA"] is True


def test_rta_matches_bench_simulation():
    tr, misses, end, _ = benchmodel.simulate(CLASSIC, "RM", 840, quantum=1)
    assert misses == []
    obs = schedtests.observed_responses(tr.lane_slices("CPU"), CLASSIC, 840)
    rta = {r["name"]: r["R"] for r in schedtests.response_times(CLASSIC, "RM")}
    for t in CLASSIC:
        assert obs[t["name"]][0] <= rta[t["name"]] + 1


def test_edf_demand():
    ok, x, _ = schedtests.edf_demand([{"name": "a", "wcet": 2, "period": 4, "deadline": 2},
                                      {"name": "b", "wcet": 2, "period": 6, "deadline": 3}])
    assert not ok and x == 3
    ok, x, _ = schedtests.edf_demand([{"name": "a", "wcet": 1, "period": 4, "deadline": 2},
                                      {"name": "b", "wcet": 1, "period": 6, "deadline": 3}])
    assert ok


def test_bench_save_load_roundtrip(tmp_path):
    tasks = [{"name": "A", "wcet": 2, "period": 10, "deadline": 8}, {"name": "B", "wcet": 5, "period": None,
                                                                     "deadline": None}]
    p = tmp_path / "t.txt"
    benchmodel.save_tasks(str(p), tasks)
    assert benchmodel.load_tasks(str(p)) == tasks
    assert benchmodel.validate(tasks + [{"name": "A", "wcet": -1, "period": 0, "deadline": None}])


# -------------------------------------------------------------- graphs

def test_gcpa_matches_versioned_output():
    g = graphs.load(os.path.join(REPO_ROOT, "apps", "sample-graph-b", "sample-graph-b.txt"))
    cost, path = graphs.gcpa(g)
    ref = {}
    for line in open(os.path.join(REPO_ROOT, "apps", "sample-graph-b", "sample-graph-b.gcpa.txt")):
        if line.strip():
            label = line.split("'label': '")[1].split("'")[0]
            ref[label] = int(line.split()[-1])
    assert cost == ref
    assert path[-1] == "J" and path[0] == "A"


def test_max_proc_clusters_of_chapter_8():
    g = graphs.load(os.path.join(REPO_ROOT, "apps", "sample-graph-b", "sample-graph-b.txt"))
    cg = graphs.cluster(g, 4, "MAX_PROC")
    members = sorted("".join(sorted(r["members"])) for r in graphs.cluster_rows(g, cg))
    assert members == ["ABDF", "C", "EHI", "GJ"]
    assert len(g._nodes) == 10          # the original graph is unchanged


# ------------------------------------------------------------- network

def dct_case():
    d = os.path.join(REPO_ROOT, "apps", "str2rts-dct-verify")
    return network.load_case(os.path.join(d, "DCT-Verify.csv"),
                             os.path.join(d, "STR2RST-DCT-verify-ONTO-hermes3x2.map"),
                             os.path.join(REPO_ROOT, "arch", "hermes-2x3.gml"))


def test_examples_found():
    names = [e[0] for e in network.examples()]
    assert "str2rts-dct-verify" in names and "shi-2010" in names


def test_flows_and_validation():
    from rttools.modules.frequency import search
    case = dct_case()
    rows, hp, packets = network.flows_at(case, 2000000)
    assert hp == 78651 and len(rows) == 7
    cfg = {"pruning_factor": 500, "fail_threshold": 500, "heuristic": network.HEURISTICS["mbcf"]}
    res = search.schedule_at(case["app"], case["noc"], case["mapping"], case["appname"], 2000000, cfg)
    assert network.validate(res) == []
    tr = network.schedule_trace(res)
    assert set(tr.lanes) == {d["label"] for (_, _, d) in res["problem"]["links"]}
    # an overlap injected on one link is reported
    bad = copy.deepcopy(res)
    l = next(i for i, row in enumerate(bad["problem"]["occupancy"]) if sum(o is not None for o in row) >= 2)
    ks = [k for k, o in enumerate(bad["problem"]["occupancy"][l]) if o is not None][:2]
    bad["schedule"][l][ks[1]] = bad["schedule"][l][ks[0]]
    assert any("overlap" in i for i in network.validate(bad))


def test_worker_process_fixed_frequency():
    d = os.path.join(REPO_ROOT, "apps", "str2rts-dct-verify")
    params = {"app": os.path.join(d, "DCT-Verify.csv"),
              "map": os.path.join(d, "STR2RST-DCT-verify-ONTO-hermes3x2.map"),
              "noc": os.path.join(REPO_ROOT, "arch", "hermes-2x3.gml"),
              "frequency": 2000000, "pruning_factor": 500, "fail_threshold": 500,
              "heuristic": "mbcf", "scaling_tolerance": 5000, "optimize": False}
    proc = network.start_worker(params)
    msgs = list(network.read_messages(proc.stdout))
    assert proc.wait(timeout=120) == 0
    kinds = [k for k, _ in msgs]
    assert "log" in kinds and kinds[-1] == "result"
    res = msgs[-1][1]
    assert res["frequency"] == 2000000 and network.validate(res) == []


# ----------------------------------------------------------------- CLI

def test_cli_stats_export_compare(tmp_path):
    p = tmp_path / "log.txt"
    p.write_text(RTL_LOG)
    r = run_module("rttools.tui", "stats", str(p), "--display", "cycles")
    assert r.returncode == 0, r.stderr
    assert "| 0-0 |" in r.stdout and "AB" in r.stdout
    out = tmp_path / "o.svg"
    r = run_module("rttools.tui", "export", str(p), str(out))
    assert r.returncode == 0 and out.exists()
    r = run_module("rttools.tui", "compare", str(p), str(p))
    assert r.returncode == 0 and "identical" in r.stdout
    q = tmp_path / "log2.txt"
    q.write_text(RTL_LOG.replace("1400 0-0", "1401 0-0"))
    r = run_module("rttools.tui", "compare", str(p), str(q))
    assert r.returncode == 1


# ------------------------------------------------- real logs (exp-23)

def exp23_log(run):
    return os.path.join(REPO_ROOT, "experiments", "exp23", "logs", f"{run}.events.txt")


def test_real_logs_unit_trigger_and_swap():
    a = parsers.load_trace(exp23_log("A"), swap_xy="auto")
    d = parsers.load_trace(exp23_log("D"), swap_xy="auto")
    # "Time scale of (manycore_top.pe_x[0].pe_y[0].pe_mod) is 100ps / 100ps"
    assert a.unit.name == "100 ps" and not a.unit.assumed
    assert d.unit.name == "1 ns" and not d.unit.assumed
    # the fixed RTL prints X and Y in the other order
    assert a.meta["swap_xy"] is False and d.meta["swap_xy"] is True
    assert [s.label for s in a.lane_slices("0-1") if s.label != "IDLE"][:1] == ["C"]
    assert [s.label for s in d.lane_slices("0-1") if s.label != "IDLE"][:1] == ["C"]
    # TRIGGER lines: release of A every 0.5 ms from 3 ms
    rel = [m.time for m in a.lane_marks("TRIGGER")]
    assert rel[0] == 30007530 and rel[1] - rel[0] == 5000020
