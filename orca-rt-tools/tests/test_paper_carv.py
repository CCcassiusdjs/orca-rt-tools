"""CAR-V: generation from apps/shi-2010 (selection and scale rules) and the
analysis flow on the 4x4 mesh (rttools/paper/carv.py, experiments/car-v)."""
import json
import os
from fractions import Fraction

import pytest

from tests.conftest import REPO_ROOT, run_module
from rttools.modules.io import appparser
from rttools.paper import carv, exp23, frequency

# reference.json of experiments/car-v: network-interface model off (NI ?= off)
pytestmark = pytest.mark.usefixtures("ni_off")

EXP = os.path.join(REPO_ROOT, "experiments", "car-v")
APPS = os.path.join(REPO_ROOT, "apps")
ARCH = os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml")
CAR_V = os.path.join(APPS, "car-v")


@pytest.fixture(scope="module")
def cfg():
    with open(os.path.join(EXP, "config.json")) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def metrics(cfg, tmp_path_factory, ni_off_module):
    out = tmp_path_factory.mktemp("carv")
    m = carv.run(cfg, APPS, ARCH, str(out))
    return m, out


def car():
    wcet, order = carv.read_wcet(os.path.join(APPS, "shi-2010", "shi-2010.txt"))
    flows = carv.read_flows(os.path.join(APPS, "shi-2010", "SHI2010.csv"))
    return wcet, order, flows


# ------------------------------------------------------------ selection

def test_selection_takes_the_flows_of_the_shortest_period():
    wcet, order, flows = car()
    assert len(order) == 33 and len(flows) == 38
    assert sorted({f["period"] for f in flows}) == [Fraction("0.04"), Fraction("0.1"), Fraction("0.5"), Fraction(1)]
    period, tasks, sel = carv.select(flows, order)
    assert period == Fraction("0.04")
    assert len(tasks) == 23 and len(sel) == 23
    assert {f["period"] for f in sel} == {Fraction("0.04")}
    assert set(tasks) == ({f"FBU{i}" for i in range(1, 9)} | {f"BFE{i}" for i in range(1, 9)}
                          | {"FDF1", "FDF2", "STPH", "VOD1", "VOD2", "NAVC", "OBMG"})
    # the tasks keep the order of shi-2010.txt, the flows the order of SHI2010.csv
    assert tasks == [t for t in order if t in tasks]
    assert [(f["src"], f["dst"]) for f in sel][:3] == [("FBU3", "VOD1"), ("FBU8", "VOD2"), ("VOD1", "NAVC")]
    # an explicit period selects the same flows
    assert carv.select(flows, order, 0.04)[2] == sel
    with pytest.raises(ValueError):
        carv.select(flows, order, 0.3)


def test_subgraph_is_acyclic_and_car_is_not():
    wcet, order, flows = car()
    _, tasks, sel = carv.select(flows, order)
    # FBU -> BFE -> FDF -> STPH -> OBMG
    assert carv.longest_path(tasks, [(f["src"], f["dst"]) for f in sel]) == 4
    with pytest.raises(ValueError):
        carv.longest_path(order, [(f["src"], f["dst"]) for f in flows])


# ------------------------------------------------------------ scale

def test_scale_rule(cfg):
    app = carv.build(cfg, APPS)
    cost = dict(app["tasks"])
    # w = 350 000 cycles per 1 s on the 1 MHz basis: 14 000 cycles per job of 0.04 s
    assert carv.job_cycles(350000, Fraction("0.04"), 1) == 14000
    assert cost["FBU1"] == 6 * 14000 + 11000 == 95000
    # FBU4: w = 233 334, round(9 333.36) = 9 333
    assert cost["FBU4"] == 6 * 9333 + 11000 == 66998
    assert app["period_s"] == Fraction("0.0005")
    assert app["longest_path"] == 4
    assert app["deadline_s"] == 5 * Fraction("0.0005")
    data = {(a, b): d for a, b, d in app["flows"]}
    assert data[("FBU1", "BFE1")] == 153600 // 16 == 9600
    assert data[("VOD1", "NAVC")] == 2048 // 16
    assert data[("STPH", "OBMG")] == 16384 // 16


def test_scale_parameters():
    """Cost factor 8 gives the values of the r9 variant vscaled (cost x 8 +
    11 000, payload / 16); the parameters must be positive integers."""
    wcet, order, flows = car()
    period, tasks, sel = carv.select(flows, order)
    sc = {"period_s": 0.0005, "hyperperiod_s": 1, "cost_factor": 6, "payload_divisor": 16,
          "scheduler_cycles": 11000}
    app = carv.scale(wcet, tasks, sel, period, sc, cost_factor=8)
    assert dict(app["tasks"])["FBU1"] == 123000 and dict(app["tasks"])["FBU4"] == 85664
    app = carv.scale(wcet, tasks, sel, period, sc, payload_divisor=8)
    assert max(d for _, _, d in app["flows"]) == 19200
    for bad in ({"cost_factor": 0}, {"payload_divisor": 2.5}):
        with pytest.raises(ValueError):
            carv.scale(wcet, tasks, sel, period, sc, **bad)


def test_utilization_preserving_factor(metrics):
    """k = f_clk T / (f_base T_src) = 500 MHz 0.5 ms / (1 MHz 0.04 s) keeps the
    share of the period of each job of CAR; 6 lies below it, 8 above."""
    m, _ = metrics
    assert m["scale"]["utilization_preserving_factor"] == 6.25


# ------------------------------------------------------------ generated files

def test_committed_csv_is_the_generator_output(cfg):
    with open(os.path.join(CAR_V, "car-v.csv")) as f:
        assert f.read() == carv.csv_text(carv.build(cfg, APPS), cfg)


def test_csv_reads_as_the_cli_input():
    app, name = appparser.loadFromFile(os.path.join(CAR_V, "car-v.csv"))
    assert name == "car-v"
    assert app.number_of_nodes() == 23 and app.number_of_edges() == 23
    assert app.graph["release_model"] == "phase"
    assert int(app.graph["scheduler_cycles"]) == 11000
    assert {float(d["period"]) for _, _, d in app.edges(data=True)} == {0.0005}
    assert int(app.nodes["FBU4"]["wcet"]) == 66998


def test_generate_cli_check_and_write(tmp_path):
    cfgp = os.path.join(EXP, "config.json")
    r = run_module("rttools.paper.carv", "generate", "--config", cfgp, "--apps", APPS, "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "up to date" in r.stdout
    out = tmp_path / "x.csv"
    r = run_module("rttools.paper.carv", "generate", "--config", cfgp, "--apps", APPS, "--out", str(out))
    assert r.returncode == 0, r.stderr
    assert out.read_text() == open(os.path.join(CAR_V, "car-v.csv")).read()
    out.write_text("changed\n")
    r = run_module("rttools.paper.carv", "generate", "--config", cfgp, "--apps", APPS, "--out", str(out), "--check")
    assert r.returncode == 1


# ------------------------------------------------------------ flow

def test_pipeline_matches_reference(metrics):
    m, out = metrics
    assert exp23.check(str(out / "metrics.json"), os.path.join(EXP, "reference.json")) == []
    assert m["app"]["csv_matches_repo"] and m["app"]["map_matches_repo"]
    for name in ("clustering.csv", "factors.csv", "flows.csv", "pes.csv", "values.tex", "car-v.csv", "car-v.map"):
        assert (out / name).exists()
    values = (out / "values.tex").read_text()
    assert "\\ExpCarvMinimumMhz}{380.0}" in values
    assert "\\ExpCarvFactorEightDivisorSixteenUtilizationPercent}{98.4}" in values


def test_clustering_chooses_the_smallest_m2(metrics):
    c = metrics[0]["chosen"]
    rows = c["clustering"]["rows"]
    assert [r["criterion"] for r in rows] == ["MIN_COMM", "MAX_COMM", "MIN_PROC", "MAX_PROC"]
    best = min(rows, key=lambda r: r["M2"])
    assert best["chosen"] and best["criterion"] == c["clustering"]["chosen"] == "MAX_PROC"
    assert all(r["clusters"] == 16 for r in rows)
    assert len(c["mapping"]) == 16


def test_cost_factor_rule(metrics, cfg):
    m, _ = metrics
    k6, k8 = m["candidates"]["k6_q16"], m["candidates"]["k8_q16"]
    assert k6["utilization_at_clock"] == pytest.approx(2 * 95000 / 250000)
    assert k8["utilization_at_clock"] == pytest.approx(2 * 123000 / 250000)
    assert k6["utilization_at_clock"] <= cfg["platform"]["max_utilization"] < k8["utilization_at_clock"]
    assert m["rule"]["chosen_cost_factor"] == 6 and m["rule"]["config_matches_rule"]
    assert carv.choose([], cfg["platform"]) is None


def test_cpu_bound_and_response_bound(metrics):
    c = metrics[0]["chosen"]
    T, clk = 0.0005, 500000000
    assert c["cpu"]["f_cpu_hz"] == pytest.approx(max(c["cpu"]["demand_cycles"].values()) / T)
    assert c["search"]["frequency_hz"] == c["cpu"]["f_cpu_hz"] and c["search"]["binding"] == "cpu"
    assert c["search"]["f_star_lower_hz"] < c["search"]["f_star_hz"] < c["cpu"]["f_cpu_hz"]
    rb = c["response_bound"]
    assert rb["v_last"] == "OBMG" and rb["phase"] == c["phase_max"] == 4
    assert rb["cycles_at_clock"] == 4 * T * clk + rb["finish_cycles"]
    # D = (n(v_last) + 1) T for the chosen mapping, and R_bound <= D
    assert rb["deadline_equals_phase_rule"]
    assert rb["ms_at_clock"] < rb["deadline_ms"] == 2.5
    assert c["largest_cost_below_tick"]


def test_network_frequency_is_set_by_the_tightest_window(metrics):
    """f* T >= f^(u) - s^(v) + o(u -> v) for every flow on the NoC. The
    tightest flows are BFE2 -> FDF1 and BFE5 -> FDF2 (both released at the
    finish of the second task of their PE): each shares the local link of
    its target with BFE1 -> FDF1 or BFE6 -> FDF2 (same release), so f* T
    exceeds the isolated requirement by less than the occupancy of one of
    these packets."""
    c = metrics[0]["chosen"]
    T, P = 0.0005, 0.0005 * 500000000
    req = {f["flow"]: f["offset_cycles"] - (f["end_cycles"] - P) + f["net_time_cycles"]
           for f in c["flow_windows"] if f["on_noc"]}
    top = max(req.values())
    tight = sorted(k for k, v in req.items() if v == top)
    fw = {f["flow"]: f for f in c["flow_windows"]}
    assert [(fw[k]["source"], fw[k]["target"]) for k in tight] == [("BFE2", "FDF1"), ("BFE5", "FDF2")]
    for k in tight:
        same = [f for f in fw.values() if f["target"] == fw[k]["target"] and f["flow"] != k
                and f["offset_cycles"] == fw[k]["offset_cycles"]]
        assert len(same) == 1
    f_star = c["search"]["f_star_hz"]
    assert top / T <= f_star
    assert 0 < f_star * T - top < min(fw[k]["net_time_cycles"] for k in tight)


def test_flows_and_packets(metrics):
    c = metrics[0]["chosen"]
    fw = c["flow_windows"]
    assert len(fw) == 23
    assert c["packets_per_period"] == sum(f["on_noc"] for f in fw) == 16
    assert c["local_flows"] == 7
    assert c["network_at_clock"] == {"frequency_hz": 500000000, "feasible": True, "hyperperiod": 250000,
                                     "packets": 16, "skipped": 0}
    for f in fw:
        assert f["window_cycles"] == f["end_cycles"] - f["offset_cycles"] > 0
        if f["on_noc"]:
            assert f["slack_cycles"] == f["window_cycles"] - f["net_time_cycles"] > 0
        else:
            assert f["src_pe"] == f["dst_pe"] and f["net_time_cycles"] is None


def test_cli_on_the_map_file_gives_the_same_frequency(metrics):
    c = metrics[0]["chosen"]
    r = frequency.run_one(os.path.join(CAR_V, "car-v.csv"), os.path.join(CAR_V, "car-v-ONTO-hermes4x4.map"),
                          ARCH, 500000000)
    assert r["f_cpu_hz"] == c["cpu"]["f_cpu_hz"]
    assert r["f_star_hz"] == c["search"]["f_star_hz"]
    assert r["frequency_hz"] == c["search"]["frequency_hz"]
    s = frequency.run_one(os.path.join(CAR_V, "car-v.csv"), "spiral", ARCH, 500000000)
    assert s["mapping"] == r["mapping"] and s["criterion"] == "MAX_PROC"


# ------------------------------------------------------------ memory

MEM = {"heap_bytes": 10000, "tcb_bytes": 112, "rt_bytes": 12, "stack_bytes": 2048, "queue_bytes": 24,
       "queue_slots": 8, "block_header_bytes": 8, "packet_header_bytes": 12, "receive_buffers": 2,
       "max_payload_bytes": 65535, "max_tasks": 16}


def test_memory_model_counts():
    app = {"tasks": [("A", 1), ("B", 1), ("C", 1)], "flows": [("A", "B", 10), ("A", "C", 100), ("B", "C", 4)]}
    r = carv.memory(app, {"A": 0, "B": 0, "C": 1}, MEM)
    task = (112 + 8) + (12 + 8) + (2048 + 8)
    comm = (24 + 8) + (32 + 8)
    pkt = lambda d: 12 + (d + 3) // 4 * 4 + 8  # noqa: E731
    pe0 = r["pes"]["0"]
    # A -> B is local: the target reads the buffer of the sender
    assert pe0["tasks"] == 3 * task and pe0["comm"] == 2 * comm
    assert pe0["send"] == pkt(10) + pkt(100) + pkt(4) and pe0["receive"] == 0
    pe1 = r["pes"]["1"]
    assert pe1["send"] == 0 and pe1["receive"] == 2 * (pkt(100) + pkt(4))
    assert pe1["queue_slots_used"] == 4
    assert r["worst_pe"] == "0" and r["worst_bytes"] == pe0["total"]
    assert r["fits"] is (pe0["total"] <= 10000)


def test_memory_of_car_v(metrics, cfg):
    m, _ = metrics
    mem = m["chosen"]["memory"]
    assert mem["fits"] and mem["payload_fits"] and mem["tasks_fit"] and mem["queue_fits"]
    assert mem["heap_bytes"] == 0xC62C
    assert mem["worst_bytes"] == 26120 and mem["largest_payload"] == 9600
    # FDF1 and FDF2 take 4 inputs each: 8 queue slots with two buffers per flow
    assert max(p["queue_slots_used"] for p in mem["pes"].values()) == 8
    assert m["candidates"]["k6_q8"]["memory_fits"] and m["candidates"]["k6_q8"]["memory_free_bytes"] == 5284
    # the payload of CAR (153 600 bytes) does not fit a uint16 payload_size
    app = carv.build(cfg, APPS, payload_divisor=1)
    tmap = {t: int(n) for n, ts in m["chosen"]["mapping"].items() for t in ts}
    full = carv.memory(app, tmap, cfg["memory"])
    assert not full["fits"] and not full["payload_fits"]
