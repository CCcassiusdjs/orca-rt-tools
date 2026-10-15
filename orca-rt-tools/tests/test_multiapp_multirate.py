"""Composition of applications (rttools.multiapp) with several release
periods or a cycle: the general phase model of rttools/bench_t/multirate.py
on the union of the applications, and the static costs of rttools.wcet
(--costs) in the composition."""
import json
import os

import pytest

from tests.conftest import REPO_ROOT, run_module
from rttools.bench_t import multirate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator
from rttools.modules.io import appparser, mapparser, nocparser
from rttools.modules.unwrapper import flowUnwrapper
from rttools.multiapp import compose
from rttools.paper.frequency import search_config
from rttools.tui.model import network
from rttools.wcet import __main__ as wcli

APPS = os.path.join(REPO_ROOT, "apps")
ARCH = os.path.join(REPO_ROOT, "arch")
E_CSV = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv")
CARV_CSV = os.path.join(APPS, "car-v", "car-v.csv")
CF_CSV = os.path.join(APPS, "car-full", "car-full.csv")
CF_MAP = os.path.join(APPS, "car-full", "car-full-ONTO-hermes4x4.map")
E_SPEC = os.path.join(REPO_ROOT, "experiments", "wcet", "specs", "weird_a_H.json")
F0 = 500_000_000


def load(tmp_path, apps, arch="hermes-4x5.gml"):
    p = tmp_path / "composition.json"
    p.write_text(json.dumps({"arch": os.path.join(ARCH, arch), "apps": apps}))
    with network.quiet():
        return compose.load(compose.read_spec(str(p)))


def cf_and_e(tmp_path, **e):
    return load(tmp_path, [{"name": "CF", "csv": CF_CSV, "map": CF_MAP},
                           dict({"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4}, **e)])


def e_with_period(tmp_path, period="0.001"):
    p = tmp_path / "e2.csv"
    p.write_text(open(E_CSV).read().replace("0.0005,", period + ","))
    return str(p)


@pytest.fixture(scope="module")
def e_costs(tmp_path_factory):
    out = tmp_path_factory.mktemp("wcet") / "e_costs.json"
    assert wcli.main(["analyze", "--spec", E_SPEC, "--out", str(out)]) == 0
    return str(out)


# ---------------------------------------------------------------- selection of the model


def test_general_model_selection(tmp_path):
    one = load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                          {"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4}])
    assert compose.general(one["apps"]) is False
    two = load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                          {"name": "E", "csv": e_with_period(tmp_path), "map": "spiral", "pes": 4}])
    assert compose.general(two["apps"]) is True
    assert compose.general(cf_and_e(tmp_path)["apps"]) is True


def test_union_graph(tmp_path):
    comp = cf_and_e(tmp_path)
    U, entries, flow_of, owner = compose.union_graph(comp["apps"])
    assert U.number_of_nodes() == 33 + 10 and U.number_of_edges() == 38 + 11
    assert flow_of["f1"] == ("CF", "f1") and flow_of["f39"] == ("E", "f1") and flow_of["f49"] == ("E", "f11")
    assert owner["NAVC"] == "CF" and owner["A"] == "E"
    assert U.graph["feedback"] == [("OBDB", "NAVC"), ("OBMG", "OBDB")]
    assert U.graph["creation"]["E/0"] == ["F", "D", "B", "A"]
    assert "scheduler_cycles_pe" not in U.graph
    assert len(entries) == 16 + 4


def test_union_graph_errors(tmp_path):
    cpa = tmp_path / "e-cpa.csv"
    cpa.write_text(open(E_CSV).read().replace("release_model,phase", "release_model,cpa"))
    comp = load(tmp_path, [{"name": "CF", "csv": CF_CSV, "map": CF_MAP},
                           {"name": "E", "csv": str(cpa), "map": "spiral", "pes": 4}])
    with pytest.raises(compose.CompositionError, match="CF follow the general phase model.*release_model phase"):
        compose.general(comp["apps"])
    comp = load(tmp_path, [{"name": "E1", "csv": E_CSV, "map": "spiral", "pes": 4},
                           {"name": "E2", "csv": e_with_period(tmp_path), "map": "spiral", "pes": 4}],
                arch="hermes-4x4.gml")
    with pytest.raises(compose.CompositionError, match="task A in applications E1 and E2"):
        compose.union_graph(comp["apps"])


# ---------------------------------------------------------------- one application of the general model


def test_car_full_alone_equals_the_flow(tmp_path):
    """CAR-full alone through the composition: the steps and the results of
    search.minimum_frequency for the general model (f_CPU, network check at
    f_CPU, frequency) and the largest data age of experiments/car-full."""
    comp = load(tmp_path, [{"name": "CF", "csv": CF_CSV, "map": CF_MAP}], arch="hermes-4x4.gml")
    a = comp["apps"][0]
    cfg = search_config(F0)
    with network.quiet():
        multi = compose.minimum_frequency(comp["apps"], comp["noc"], cfg)
        g, name = appparser.loadFromFile(CF_CSV)
        alone = search.minimum_frequency(g, comp["noc"], mapparser.loadFromFile(CF_MAP), name, cfg)
        rb = compose.response_bounds(comp["apps"], comp["noc"], multi["frequency_hz"])
    assert multi["model"] == "multirate" and alone["cpu"]["model"] == "multirate"
    assert multi["f_cpu_hz"] == alone["f_cpu_hz"] == 432_000_000
    assert multi["frequency_hz"] == alone["frequency_hz"]
    for k in ("feasible", "hyperperiod", "packets", "skipped"):
        assert multi["final_check"][k] == alone["final_check"][k]
    assert multi["final_check"]["packets"] == 347
    c = multi["cpu"]["CF"]
    assert c["phase_cycles"] == alone["cpu"]["phase_cycles"] == 108_000
    assert rb["CF"]["cycles"] == 15_552_000 and rb["CF"]["chain"] == ["POSI", "OBMG", "OBDB", "NAVC", "DIRC"]
    assert rb["CF"]["chains"] == 34
    assert a["placement"]["method"] == "file"


# ---------------------------------------------------------------- two applications


def test_car_full_and_e(tmp_path):
    """CAR-full (four periods, two cycles) and E (one period, 0.5 ms) on the
    4x5 mesh: phase 0.25 ms, H = 12.5 ms. The packets of CAR-full in the
    union are those of CAR-full alone (same phase, disjoint PEs); E sends
    on its five flows between PEs 25 times per H; f_CPU of E comes from
    the ORT/BENCH sequences with the tick of 0.25 ms (the tick preempts the
    job of G or J on PE 16: one more dispatch, sigma)."""
    comp = cf_and_e(tmp_path)
    cf, e = comp["apps"]
    cfg = search_config(F0)
    with network.quiet():
        r = compose.minimum_frequency(comp["apps"], comp["noc"], cfg)
        f = r["frequency_hz"]
        pk, H, _, info = compose.union_packets(comp["apps"], comp["noc"], f)
        alone = flowUnwrapper.unwrap(instantiator.createInstance(cf["graph"], comp["noc"], f), comp["noc"],
                                     cf["entries"])[0]
        rb = compose.response_bounds(comp["apps"], comp["noc"], f)
    assert r["f_cpu_by_app"]["CF"] == 432_000_000
    _, _, _, _, rates, spec = compose.union_spec(comp["apps"])
    sub = compose.app_spec(spec, set(e["graph"].nodes))
    P_e = multirate.cpu_test(sub)["phase_cycles"]
    G, J = sub.cost["G"], sub.cost["J"]
    assert P_e == (G + J + spec.sigma) // 2 + (G + J + spec.sigma) % 2
    assert r["f_cpu_by_app"]["E"] == multirate.frequency_of(P_e, rates["phase_s"])
    assert f == r["f_cpu_hz"] == max(r["f_cpu_by_app"].values()) and r["final_check"]["feasible"]
    assert H == math_floor(rates["phase_s"], f) * 50
    assert info["CF"]["packets_in_H"] == 347 and info["E"]["packets_in_H"] == 125
    assert info["E"]["hyperperiod"] == 2 * math_floor(rates["phase_s"], f)
    mine = {p["name"]: (p["min_start"], p["abs_deadline"]) for p in pk if p["app"] == "CF"}
    assert mine == {"CF/" + p["name"]: (p["min_start"], p["abs_deadline"]) for p in alone}
    assert rb["E"]["chain"][0] == "A" and rb["E"]["chain"][-1] == "J" and rb["E"]["chains"] == 3
    assert rb["CF"]["chains"] == 34


def math_floor(phase_s, f):
    from fractions import Fraction
    import math
    return math.floor(multirate.seconds(phase_s) * Fraction(f))


def test_two_periods_response_equals_r_bound(tmp_path):
    """CAR-V (T = 0.5 ms) and E with T = 1 ms: phase 0.5 ms, the general
    model; the largest data age of CAR-V equals its R_bound (one period)."""
    comp = load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                           {"name": "E", "csv": e_with_period(tmp_path), "map": "spiral", "pes": 4}])
    with network.quiet():
        r = compose.minimum_frequency(comp["apps"], comp["noc"], search_config(F0))
        f = r["frequency_hz"]
        rb = compose.response_bounds(comp["apps"], comp["noc"], f)
        alone = compose.response_bound(comp["apps"][0], comp["noc"], f)
    assert r["model"] == "multirate" and f == 380_000_000
    assert rb["CARV"]["cycles"] == alone["cycles"] == 855_000
    assert rb["CARV"]["v_last"] == alone["v_last"] == "OBMG"
    with pytest.raises(compose.CompositionError, match="R_bound needs one release period"):
        compose.app_period_s(dict(comp["apps"][0], graph=appparser.loadFromFile(CF_CSV)[0]))


# ---------------------------------------------------------------- static costs (--costs)


def test_costs_in_the_composition(tmp_path, e_costs):
    """Static t(v) of E in a composition with one period (rule static):
    f_CPU of E equals the f_CPU of the flow of E with --costs; CAR-V keeps
    its costs. The default rule max takes max(CSV, static) of each task."""
    d = json.load(open(e_costs))
    csv = {t: int(dd["wcet"]) for t, dd in appparser.loadFromFile(E_CSV)[0].nodes(data=True)}
    comp = load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                           {"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4, "costs": e_costs}])
    e = comp["apps"][1]
    assert {t: dd["wcet"] for t, dd in e["graph"].nodes(data=True)} == {t: max(csv[t], v["t"])
                                                                        for t, v in d["tasks"].items()}
    assert e["graph"].graph["scheduler_cycles"] == 11000
    comp = load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                           {"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4, "costs": e_costs,
                            "cost_rule": "static"}])
    e = comp["apps"][1]
    assert {t: dd["wcet"] for t, dd in e["graph"].nodes(data=True)} == {t: v["t"] for t, v in d["tasks"].items()}
    assert e["graph"].graph["scheduler_cycles"] == d["scheduler_cycles"]
    with network.quiet():
        cpu = compose.cpu_tests(comp["apps"])
        g, _ = appparser.loadFromFile(CARV_CSV)
    assert cpu["E"]["f_cpu_hz"] == search.cpu_check(e["graph"], e["entries"])["f_cpu_hz"]
    assert cpu["CARV"]["f_cpu_hz"] == search.cpu_check(g, comp["apps"][0]["entries"])["f_cpu_hz"] == 380_000_000


def test_costs_in_the_general_model(tmp_path, e_costs):
    """Static t(v) of E next to CAR-full (rule static): E keeps its
    scheduler cost on its PEs (scheduler_cycles_pe), so P_min of E is (t(G)
    + t(J) + sigma_E) / 2."""
    comp = cf_and_e(tmp_path, costs=e_costs, cost_rule="static")
    d = json.load(open(e_costs))
    U, _, _, _ = compose.union_graph(comp["apps"])
    e_pes = {str(x["node"]) for x in comp["apps"][1]["entries"] if x["tasks"]}
    assert U.graph["scheduler_cycles"] == 11000
    assert U.graph["scheduler_cycles_pe"] == {**{str(x["node"]): 11000 for x in comp["apps"][0]["entries"]},
                                              **{n: d["scheduler_cycles"] for n in e_pes}}
    with network.quiet():
        cpu = compose.cpu_tests(comp["apps"])
    GJ = d["tasks"]["G"]["t"] + d["tasks"]["J"]["t"] + d["scheduler_cycles"]
    assert cpu["E"]["phase_cycles"] == (GJ + 1) // 2
    assert cpu["CF"]["f_cpu_hz"] == 432_000_000


def test_costs_in_the_general_model_of_one_application(tmp_path):
    """Costs file (rule static) on an application of the general model
    (CAR-full): the CPU test takes the costs of the file, the same as a CSV
    with these capacities."""
    g, _ = appparser.loadFromFile(CF_CSV)
    entries = mapparser.loadFromFile(CF_MAP)
    tasks = {t: int(dd["wcet"]) // 2 for t, dd in g.nodes(data=True)}
    p = tmp_path / "costs.json"
    p.write_text(json.dumps({"tasks": {t: {"t": v} for t, v in tasks.items()}, "scheduler_cycles": 5500}))
    from rttools.wcet import costs
    costs.apply(g, str(p), costs.STATIC)
    with network.quiet():
        got = search.cpu_check(g, entries)
    text = open(CF_CSV).read()
    h, _ = appparser.loadFromFile(CF_CSV)
    for t, dd in h.nodes(data=True):
        dd["wcet"] = tasks[t]
    h.graph["scheduler_cycles"] = 5500
    with network.quiet():
        ref = search.cpu_check(h, entries)
    assert got["model"] == "multirate" and got["phase_cycles"] == ref["phase_cycles"] < 108_000
    assert "scheduler_cycles,11000" in text


def test_cli_with_costs(tmp_path, e_costs):
    comp = tmp_path / "c.json"
    comp.write_text(json.dumps({"arch": os.path.join(ARCH, "hermes-4x5.gml"), "apps": [
        {"name": "CF", "csv": CF_CSV, "map": CF_MAP},
        {"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4}]}))
    r = run_module("rttools.multiapp", str(comp), "--costs", "E=" + e_costs, timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert "general phase model: phase 0.25 ms, hyperperiod 12.5 ms" in r.stdout
    # rule max: f_CPU of E with max(CSV, static) sets the frequency
    assert "E: f_CPU = 456900000 Hz (456.900 MHz)" in r.stdout
    assert "frequency of the platform = 456900000 Hz (456.900 MHz)" in r.stdout
    assert "CF: largest data age = 16381950 cycles (35.855 ms)" in r.stdout
    assert "E: largest data age" in r.stdout
    r = run_module("rttools.multiapp", str(comp), "--costs", "X=" + e_costs, timeout=300)
    assert r.returncode == 1 and "application 'X' not in the composition" in r.stderr
