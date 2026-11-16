
"""Several applications on one NoC (rttools.multiapp): union of the packet
instances, placement on disjoint PEs, equality with the flow of one
application, interference of the schedules of each application alone."""
import json
import os

import pytest

from tests.conftest import REPO_ROOT, run_module
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator
from rttools.modules.io import appparser, mapparser, nocparser
from rttools.modules.mapping import mapfile, spiral
from rttools.modules.unwrapper import flowUnwrapper
from rttools.multiapp import compose
from rttools.paper.frequency import search_config
from rttools.tui.model import network

# the stored references of experiments/exp23, car-v and multiapp: network-interface
# model off (NI ?= off in their Makefiles)
pytestmark = pytest.mark.usefixtures("ni_off")

APPS = os.path.join(REPO_ROOT, "apps")
ARCH = os.path.join(REPO_ROOT, "arch")
E_CSV = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv")
E_MAP = os.path.join(APPS, "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map")
CARV_CSV = os.path.join(APPS, "car-v", "car-v.csv")
CARV_MAP = os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map")
EXP = os.path.join(REPO_ROOT, "experiments", "multiapp")


def spec(tmp_path, apps, arch="hermes-4x5.gml"):
    p = tmp_path / "composition.json"
    p.write_text(json.dumps({"arch": os.path.join(ARCH, arch), "apps": apps}))
    return compose.read_spec(str(p))


def load(tmp_path, apps, arch="hermes-4x5.gml"):
    with network.quiet():
        return compose.load(spec(tmp_path, apps, arch))


def two_apps(tmp_path):
    return load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                           {"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4}])


# ---------------------------------------------------------------- placement


def test_spiral_sequence_on_disjoint_pes(tmp_path):
    comp = two_apps(tmp_path)
    order = spiral.spiral_order(4, 5)
    carv, e = comp["apps"]
    assert carv["placement"]["nodes"] == sorted(order[:16])
    assert e["placement"]["nodes"] == [9, 10, 13, 14] == sorted(order[16:])
    assert not compose.problems(comp["apps"])
    # clusters of each application: the same ORT/GCM result as on its own mesh
    assert sorted(map(sorted, (e["tasks"] for e in e["entries"]))) == \
        sorted(map(sorted, (x["tasks"] for x in mapparser.loadFromFile(E_MAP))))


def test_spiral_alone_equals_spiral_mapping(tmp_path):
    """One application with pes = W x H: the Spiral Mapping of the command line."""
    for csv, arch, n in ((E_CSV, "hermes-2x2.gml", 4), (CARV_CSV, "hermes-4x4.gml", 16)):
        comp = load(tmp_path, [{"name": "A", "csv": csv, "map": "spiral", "pes": n}], arch)
        with network.quiet():
            g, _ = appparser.loadFromFile(csv)
        tasks, edges = spiral.from_networkx(g)
        w = 2 if n == 4 else 4
        ref = spiral.map_application(tasks, edges, w, w)
        assert comp["apps"][0]["entries"] == mapfile.from_dict(ref["mapping"])


def test_overlapping_pes_is_an_error(tmp_path):
    bad = tmp_path / "e.map"
    bad.write_text("0:A,B,D,F\n16:C\n17:E,H,I\n18:G,J\n")
    with pytest.raises(compose.CompositionError) as ex:
        load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": CARV_MAP},
                        {"name": "E", "csv": E_CSV, "map": str(bad)}])
    msg = str(ex.value)
    assert "PE 0 is mapped by applications CARV (tasks NAVC) and E (tasks A, B, D, F)" in msg
    # a spiral application takes only the nodes that no .map file uses
    comp = load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": CARV_MAP},
                           {"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4}])
    assert comp["apps"][1]["placement"]["nodes"] == [16, 17, 18, 19]
    with pytest.raises(compose.CompositionError, match="0 free nodes"):
        load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                        {"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4}], "hermes-4x4.gml")
    with pytest.raises(compose.CompositionError, match="repeated application name"):
        load(tmp_path, [{"name": "E", "csv": E_CSV, "map": E_MAP}, {"name": "E", "csv": E_CSV, "map": E_MAP}])


def test_cli_reports_overlap(tmp_path):
    bad = tmp_path / "e.map"
    bad.write_text("3:A,B,D,F\n16:C\n17:E,H,I\n18:G,J\n")
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"arch": os.path.join(ARCH, "hermes-4x5.gml"),
                             "apps": [{"name": "CARV", "csv": CARV_CSV, "map": CARV_MAP},
                                      {"name": "E", "csv": E_CSV, "map": str(bad)}]}))
    r = run_module("rttools.multiapp", str(p))
    assert r.returncode == 1 and "PE 3 is mapped by applications CARV" in r.stderr


# ---------------------------------------------------------------- union of the packet instances


def packets_of(csv, map_path, arch, f):
    with network.quiet():
        g, _ = appparser.loadFromFile(csv)
        noc = nocparser.loadFromFile(arch)
        inst = instantiator.createInstance(g, noc, f)
        return flowUnwrapper.unwrap(inst, noc, mapparser.loadFromFile(map_path)), g, noc


def test_union_of_instances(tmp_path):
    comp = two_apps(tmp_path)
    f = 434_900_000
    with network.quiet():
        pk, H, links, info = compose.union_packets(comp["apps"], comp["noc"], f)
    assert H == 217_450 and info == {"CARV": {"hyperperiod": H, "packets": 16, "packets_in_H": 16},
                                     "E": {"hyperperiod": H, "packets": 5, "packets_in_H": 5}}
    assert len(pk) == 21 and {p["app"] for p in pk} == {"CARV", "E"}
    assert all(p["name"].startswith(p["app"] + "/f") and p["flow"].startswith(p["app"] + "/") for p in pk)
    assert len({p["name"] for p in pk}) == 21
    assert len(links) == 2 * 31 + 2 * 20


def test_union_over_the_lcm_of_the_periods(tmp_path):
    """Application E with T = 1 ms and CAR-V with T = 0.5 ms: H = 2 P(CAR-V);
    CAR-V packet j + 1 of each flow is packet j shifted by its hyperperiod,
    as flowUnwrapper.getPacketsFromFlows gives over H."""
    text = open(E_CSV).read().replace("0.0005,", "0.001,")
    e2 = tmp_path / "e2.csv"
    e2.write_text(text)
    comp = load(tmp_path, [{"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16},
                           {"name": "E", "csv": str(e2), "map": "spiral", "pes": 4}])
    f = 400_000_000
    with network.quiet():
        pk, H, _, info = compose.union_packets(comp["apps"], comp["noc"], f)
        carv = compose.app_packets(comp["apps"][0], comp["noc"], f)[0]
        inst = instantiator.createInstance(comp["apps"][0]["graph"], comp["noc"], f)
        direct = flowUnwrapper.getPacketsFromFlows(flowUnwrapper.extractFlows(inst["flows"]), H, inst["tasks"],
                                                   inst, comp["apps"][0]["entries"])
    assert H == 400_000 and info["CARV"]["hyperperiod"] == 200_000 and info["E"]["hyperperiod"] == 400_000
    assert info["CARV"]["packets_in_H"] == 32 and info["E"]["packets_in_H"] == 5
    mine = {p["name"]: (p["min_start"], p["abs_deadline"]) for p in pk if p["app"] == "CARV"}
    remote = {p["flow"] for p in carv}
    ref = {"CARV/" + p["name"]: (p["min_start"], p["abs_deadline"]) for p in direct if p["flow"] in remote}
    assert mine == ref


def test_union_schedule_covers_every_packet(tmp_path):
    comp = two_apps(tmp_path)
    f = 434_900_000
    with network.quiet():
        u = compose.schedule_union(comp["apps"], comp["noc"], f, search_config(f))
    assert search.feasible(u) and len(u["problem"]["packets"]) == 21
    # every packet has a reservation on every link of its path, disjoint per link
    iv = compose.link_intervals(u)
    assert len({j for _, _, _, j in iv}) == 21
    by = {}
    for label, a, b, _ in iv:
        by.setdefault(label, []).append((a, b))
    for ivs in by.values():
        ivs.sort()
        assert all(b1 < a2 for (_, b1), (a2, _) in zip(ivs, ivs[1:]))
    assert compose.periodic_overlaps(u) == {"pairs": 0, "links": []}


# ---------------------------------------------------------------- equality with one application


@pytest.mark.parametrize("csv,map_path,arch,f_star,f_cpu", [
    (E_CSV, E_MAP, "hermes-2x2.gml", 327690124.51171875, 434_900_000.0),
    (CARV_CSV, CARV_MAP, "hermes-4x4.gml", 359001159.66796875, 380_000_000.0),
])
def test_one_application_equals_the_flow(tmp_path, csv, map_path, arch, f_star, f_cpu):
    """E and CAR-V alone: the same search (every attempt), f_NoC, f_CPU,
    network check and minimum as search.minimum_frequency, the numbers of
    experiments/exp23 (reference_frequency.json) and experiments/car-v."""
    comp = load(tmp_path, [{"name": "A", "csv": csv, "map": map_path}], arch)
    a = comp["apps"][0]
    cfg = search_config(500_000_000)
    with network.quiet():
        multi = compose.minimum_frequency(comp["apps"], comp["noc"], cfg)
        one = search.minimum_frequency(a["graph"], comp["noc"], mapparser.loadFromFile(map_path), a["appname"], cfg)
    assert multi["network"]["attempts"] == one["network"]["attempts"]
    for k in ("f_star_hz", "f_cpu_hz", "frequency_hz", "final_check"):
        assert multi[k] == one[k]
    assert multi["f_star_hz"] == f_star and multi["f_cpu_hz"] == f_cpu == multi["frequency_hz"]
    assert multi["f_cpu_by_app"] == {"A": f_cpu}
    # same packets and schedule at the minimum frequency (names with the prefix A/)
    f = multi["frequency_hz"]
    with network.quiet():
        u = compose.schedule_union(comp["apps"], comp["noc"], f, cfg)
        s = search.schedule_at(a["graph"], comp["noc"], a["entries"], a["appname"], f, cfg)
    assert u["schedule"] == s["schedule"] and u["skipped"] == s["skipped"]
    assert [p["name"] for p in u["problem"]["packets"]] == ["A/" + p["name"] for p in s["problem"]["packets"]]


def test_response_bound_per_application(tmp_path):
    """R_bound of E at 434.912 MHz (run H: 759,938 cycles) and of CAR-V at
    380 MHz (runs CV and CV2: 855,000 cycles), on the composition."""
    comp = two_apps(tmp_path)
    carv, e = comp["apps"]
    rb = compose.response_bound(e, comp["noc"], 434_912_000)
    assert (rb["v_last"], rb["phase"], rb["finish_cycles"], rb["cycles"]) == ("J", 3, 107_570, 759_938)
    rb = compose.response_bound(carv, comp["noc"], 380_000_000)
    assert (rb["v_last"], rb["phase"], rb["cycles"]) == ("OBMG", 4, 855_000)


# ---------------------------------------------------------------- interference


def attempt(links, rows, hp):
    """Minimal attempt: links [(label)], rows [[start or None per packet]] with occupancy 10."""
    return {"hyperperiod": hp, "schedule": rows,
            "problem": {"links": [(0, 0, {"label": l}) for l in links],
                        "occupancy": [[10 if v is not None else None for v in r] for r in rows],
                        "packets": [{} for _ in rows[0]]}}


def test_collisions_of_schedules_alone():
    a = attempt(["1-2", "2-3"], [[0, 50], [0, None]], 100)
    b = attempt(["2-3"], [[5, 95]], 200)
    c = compose.collisions({"A": a, "B": b}, 200)
    # A repeats at 100: on 2-3, A [0, 10] meets B [5, 15]; A [100, 110] meets B [95, 105]
    assert c["pairs"] == 2 and c["links"] == ["2-3"]
    assert c["packets"] == {"A": 2, "B": 2} and c["packets_total"] == {"A": 4, "B": 2}
    # closed intervals: [0, 10] and [10, 20] overlap (search3.overleap)
    c = compose.collisions({"A": attempt(["x"], [[0]], 100), "B": attempt(["x"], [[10]], 100)}, 100)
    assert c["pairs"] == 1
    c = compose.collisions({"A": attempt(["x"], [[0]], 100), "B": attempt(["x"], [[11]], 100)}, 100)
    assert c["pairs"] == 0


def test_periodic_overlaps():
    # a reservation [95, 105] of hyperperiod 100 meets [0, 10] of the next one
    assert compose.periodic_overlaps(attempt(["x"], [[0, 95]], 100)) == {"pairs": 1, "links": ["x"]}
    assert compose.periodic_overlaps(attempt(["x"], [[0, 80]], 100)) == {"pairs": 0, "links": []}


def test_shared_links_of_the_composition(tmp_path):
    comp = two_apps(tmp_path)
    with network.quiet():
        pk, _, _, _ = compose.union_packets(comp["apps"], comp["noc"], 434_900_000)
    assert compose.shared_links(pk) == ["13-9"]
    rev = load(tmp_path, [{"name": "E", "csv": E_CSV, "map": "spiral", "pes": 4},
                          {"name": "CARV", "csv": CARV_CSV, "map": "spiral", "pes": 16}])
    with network.quiet():
        pk, _, _, _ = compose.union_packets(rev["apps"], rev["noc"], 434_900_000)
    assert rev["apps"][0]["placement"]["nodes"] == [0, 1, 2, 3]
    assert compose.shared_links(pk) == []


# ---------------------------------------------------------------- pipeline


def test_pipeline_matches_reference(tmp_path):
    """make -C experiments/multiapp run check, with 50 random placements
    instead of 1,000 (the other values do not depend on them)."""
    from rttools.paper import exp23, multiapp
    cfg = multiapp.read_config(os.path.join(EXP, "config.json"))
    cfg["random"] = {"placements": 50, "seed": 1}
    m = multiapp.run(cfg, str(tmp_path))
    ref = json.load(open(os.path.join(EXP, "reference.json")))
    ref.pop("random")
    (tmp_path / "ref.json").write_text(json.dumps(ref))
    assert exp23.check(str(tmp_path / "metrics.json"), str(tmp_path / "ref.json")) == []
    assert m["main"]["frequency_hz"] == 434_900_000 and m["main"]["binding"] == "cpu"
    assert all(s["equal"] and s["mapping_equal"] for s in m["single"])
    assert m["random"]["union_feasible"] == 50
    tex = (tmp_path / "values.tex").read_text()
    assert "\\newcommand{\\ExpMultiappMinimumMhz}{434.9}" in tex
    assert "\\newcommand{\\ExpMultiappCarvResponseBoundMs}{2.218}" in tex


def test_stored_maps_match_the_placement():
    r = run_module("rttools.paper.multiapp", "maps", "--config", os.path.join(EXP, "config.json"), "--check")
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------- run MA (RTL)


@pytest.mark.parametrize("app,csv", [("CARV", CARV_CSV), ("E", E_CSV)])
def test_run_ma_matches_reference(tmp_path, app, csv):
    """make -C experiments/multiapp analyze check-run: the stored run MA
    (carv_e, 4x5, 434.912 MHz) analyzed per application."""
    from rttools.paper import exp23, rtlapp
    out = tmp_path / app
    m = rtlapp.analyze(os.path.join(EXP, "logs", "MA.events.txt"),
                       os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app", "carv_e.json"), csv,
                       os.path.join(EXP, "maps", app + ".map"), str(out), app_name=app,
                       composition=os.path.join(EXP, "composition.json"))
    assert exp23.check(str(out / "metrics.json"), os.path.join(EXP, f"reference_MA_{app}.json")) == []
    r = m["responses"]
    assert m["releases"]["count"] == 17 and m["tags"]["unknown_tags"] == 0 and m["tags"]["other_app_tags"] > 0
    assert m["network"]["header_waits_with_other_app_contender"] == 0
    if app == "CARV":
        # BFE3 stops after iteration 6: iterations 1 to 6, all below R_bound
        assert (r["complete"], r["above_bound"], r["margin_bound_all_cycles"]) == (6, 0, 9047)
        assert m["tasks"]["BFE3"]["iterations"] == 6 and m["packets"]["late"] == 0
    else:
        # two runs of C, E, H, I in one phase: every response above R_bound, below the deadline
        assert (r["complete"], r["above_bound"], r["above_deadline"]) == (14, 14, 0)
        assert r["max_cycles"] == 854855 and m["model"]["response_bound"]["cycles"] == 759938
        assert {t for t, d in m["tasks"].items() if d["max_iterations_per_run"] == 2} == {"C", "E", "H", "I"}
