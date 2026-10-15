"""General phase model (rttools/bench_t/multirate.py): rates, feedback
edges, chains, reads, CPU test, packets and data age on a small graph;
equivalence with the model of estimate.py for application E and CAR-V."""
import os
from fractions import Fraction

import pytest

from tests.conftest import REPO_ROOT
from rttools.bench_t import estimate, multirate
from rttools.modules.instances import instantiator, release
from rttools.modules.io import appparser, nocparser
from rttools.modules.mapping import mapfile
from rttools.modules.unwrapper import flowUnwrapper
from rttools.tui.model import network

APPS = os.path.join(REPO_ROOT, "apps")
ARCH = os.path.join(REPO_ROOT, "arch")
APP_E = (os.path.join(APPS, "synthetic-app-e", "synthetic-app-e.csv"),
         os.path.join(APPS, "synthetic-app-e", "synthetic-app-e-ONTO-hermes2x2.map"),
         os.path.join(ARCH, "hermes-2x2.gml"))
CAR_V = (os.path.join(APPS, "car-v", "car-v.csv"), os.path.join(APPS, "car-v", "car-v-ONTO-hermes4x4.map"),
         os.path.join(ARCH, "hermes-4x4.gml"))


def load(paths):
    csv, mp, arch = paths
    with network.quiet():
        g, name = appparser.loadFromFile(csv)
        noc = nocparser.loadFromFile(arch)
    return g, name, noc, mapfile.read(mp)


def shi_flows():
    from rttools.paper import carv
    return carv.read_flows(os.path.join(APPS, "shi-2010", "SHI2010.csv"))


def shi_task_order():
    """Acronyms of the #tasks section of SHI2010.csv, in file order."""
    import csv
    out, mode = [], 0
    with open(os.path.join(APPS, "shi-2010", "SHI2010.csv"), newline="") as f:
        for row in csv.reader(f):
            if row and row[0].startswith("#"):
                mode = 1 if row[0] == "#tasks" else 0
            elif mode == 1:
                mode = 2
            elif mode == 2 and row:
                out.append(row[4])
    return out


# ---------------------------------------------------------------- rates and graph


def test_rates_of_car():
    fl = shi_flows()
    tasks = sorted({f["src"] for f in fl} | {f["dst"] for f in fl})
    r = multirate.rates(tasks, [(f["src"], f["dst"], f["period"]) for f in fl])
    assert r["phase_s"] == Fraction(1, 50) and r["hyper_s"] == 1 and r["hyper_ticks"] == 50
    T = r["task_period_s"]
    # smallest period of the flows that the task sends, else that it receives
    assert T["NAVC"] == Fraction(1, 10) and T["OBMG"] == 1 and T["OBDB"] == Fraction(1, 2)
    assert T["TPRC"] == 1 and T["DIRC"] == Fraction(1, 10) and T["FBU1"] == Fraction(1, 25)
    assert r["ticks"]["FBU1"] == 2 and r["ticks"]["OBMG"] == 50
    # NAVC -> OBDB (0.5 s) every 5 jobs of NAVC (0.1 s); STAC -> TPRC every 10
    m = dict(zip([(f["src"], f["dst"]) for f in fl], r["flow_jobs"]))
    assert m[("NAVC", "OBDB")] == 5 and m[("STAC", "TPRC")] == 10 and m[("FBU1", "BFE1")] == 1


def test_flow_period_must_be_multiple_of_source_period():
    with pytest.raises(multirate.MultirateError, match="not a multiple"):
        multirate.rates(["a", "b"], [("a", "b", "0.3"), ("a", "b", "0.2")])
    assert multirate.frac_gcd(["0.04", "0.1"]) == Fraction(1, 50)
    assert multirate.frac_lcm(["0.04", "0.1", "0.5"]) == 1 and multirate.frac_lcm(["0.04", "0.1"]) == Fraction(1, 5)


def test_feedback_edges_and_chains_of_car():
    fl = shi_flows()
    order = [t for t in shi_task_order() if any(t in (f["src"], f["dst"]) for f in fl)]
    edges = [(f["src"], f["dst"]) for f in fl]
    fb = multirate.feedback_edges(order, edges)
    assert fb == [("OBDB", "NAVC"), ("OBMG", "OBDB")]
    assert not multirate.is_cyclic(order, [e for e in edges if e not in fb])
    assert multirate.is_cyclic(order, edges)
    # a marked edge comes first and changes the back edges of the search
    fb2 = multirate.feedback_edges(order, edges, marked=[("NAVC", "OBDB")])
    assert fb2[0] == ("NAVC", "OBDB") and not multirate.is_cyclic(order, [e for e in edges if e not in fb2])
    with pytest.raises(multirate.MultirateError, match="not an edge"):
        multirate.feedback_edges(order, edges, marked=[("FBU1", "NAVC")])
    ch = multirate.chains(order, edges)
    assert len(ch) == 34
    assert ["POSI", "OBMG", "OBDB", "NAVC", "DIRC"] in ch          # crosses both feedback edges
    assert all(c[0] in {"TPMS", "VIBS", "SPES", "POSI", "USOS"} | {f"FBU{i}" for i in range(1, 9)} for c in ch)
    assert {c[-1] for c in ch} == {"TPRC", "DIRC", "THRC"}


def test_applies():
    assert not multirate.applies(["a", "b"], [("a", "b", "0.5")])
    assert multirate.applies(["a", "b"], [("a", "b", "0.5")], given={"b": "1"})
    assert multirate.applies(["a", "b"], [("a", "b", "0.5"), ("b", "a", "0.5")])           # cycle
    assert multirate.applies(["a", "b"], [("a", "b", "0.5")], marked=[("a", "b")])


# ---------------------------------------------------------------- toy application


def toy_spec():
    """S (2P) and A (P) on PE 0; B (4P) and C (2P) on PE 1; B -> A is a
    feedback edge."""
    return multirate.Spec(
        tasks=["S", "A", "B", "C"], cost={"S": 30, "A": 20, "B": 150, "C": 20},
        ticks={"S": 2, "A": 1, "B": 4, "C": 2}, phase_s=Fraction(1, 1000), hyper_ticks=4,
        flows=[("f1", "S", "A", 1), ("f2", "A", "B", 1), ("f3", "B", "A", 1), ("f4", "B", "C", 1),
               ("f5", "A", "C", 2)],
        node_of={"S": "0", "A": "0", "B": "1", "C": "1"}, orders={"0": ["S", "A"], "1": ["B", "C"]},
        sigma=5, feedback=[("B", "A")])


def test_toy_schedule_reads_packets_and_age():
    spec = toy_spec()
    s = multirate.schedule(spec, 100)
    assert s.feasible and s.h0 == 0 and s.H == 400
    # PE 1: B (150) spans two ticks, C runs after B in round robin
    assert s.job("B", 0) == (0, 5, 175)
    assert s.job("C", 0)[1:] == (105, 120)
    # same PE: A reads S of the same phase (S finished before A starts)
    assert multirate.read_index(spec, s, "S", "A", 1, 0) == 0
    assert multirate.read_index(spec, s, "S", "A", 1, 1) == 0
    # other PE: B of phase 0 reads the A job of a phase < 0: none; job 1 of B
    # (phase 4) reads A of phase 3
    assert multirate.read_index(spec, s, "A", "B", 1, 0) is None
    assert multirate.read_index(spec, s, "A", "B", 1, 1) == 3
    # A -> C every 2 jobs of A: C of phase 2 reads A job 0 (job 1 does not send)
    assert multirate.read_index(spec, s, "A", "C", 2, 1) == 0
    w = multirate.packet_windows(spec, s)
    assert [x[0] for x in w["f5"]] == [0, 2]
    # A job 0 ends at 50; the first C job released at or after 50 is C job 1 (phase 2)
    assert w["f2"][0] == (0, 50, s.job("B", 1)[1], False)
    assert w["f5"][0] == (0, 50, s.job("C", 1)[1], False)
    ages = {"-".join(a["chain"]): a for a in multirate.data_age(spec, s)}
    assert set(ages) == {"S-A-B-C", "S-A-C"}
    # S-A-C: C job c reads A (every 2) of a phase < its release; worst at C of phase 2k
    assert ages["S-A-C"]["max_cycles"] == max(
        s.job("C", c)[2] - s.job("S", multirate.read_index(spec, s, "S", "A", 1, multirate.read_index(
            spec, s, "A", "C", 2, c)))[0] for c in range(2, 6))


def test_cpu_test_threshold_and_phase_rule():
    spec = toy_spec()
    t = multirate.cpu_test(spec)
    P = t["phase_cycles"]
    assert multirate.schedule(spec, P).feasible and not multirate.schedule(spec, P - 1).feasible
    # utilization bound: PE 1: 150/4 + 20/2 = 47.5 -> 48
    assert t["utilization_cycles"] == 48 and P >= 48
    # every job inside its release phase: largest c(V_k, p) = 150 + 20 at phase 0 of PE 1
    assert t["f_cpu_phase_hz"] == pytest.approx(170 / 0.001)
    assert t["f_cpu_hz"] == multirate.frequency_of(P, spec.phase_s)


# ---------------------------------------------------------------- one period: model of estimate.py


@pytest.mark.parametrize("paths,clock", [(APP_E, 500e6), (CAR_V, 500e6)])
def test_one_period_matches_phase_model(paths, clock, deadline_start):
    g, _, noc, entries = load(paths)
    assert multirate.graph_rates(g) is None          # the flow keeps estimate.py
    old = release.cpu_bound(g, entries)
    spec = multirate.spec_from_graph(g, entries, multirate.graph_rates(g, force=True))
    t = multirate.cpu_test(spec)
    assert t["f_cpu_hz"] == old["f_cpu_hz"]
    P = int(0.0005 * clock)
    inst = instantiator.createInstance(g, noc, clock)
    win = release.task_windows(inst, entries)
    phi = estimate.phases([(a, b) for a, b, _ in inst["flows"]], {x: win[x]["node"] for x in win})
    rb, _ = estimate.response_bound(phi, {x: win[x]["finish"] for x in win}, P)
    s = multirate.schedule(spec, P)
    assert max(a["max_cycles"] for a in multirate.data_age(spec, s)) == rb
    with network.quiet():
        pk, hp, _ = flowUnwrapper.unwrap(inst, noc, entries)
        inst2 = dict(inst, rates=dict(multirate.graph_rates(g, force=True), phase_cycles=P, hyper_cycles=P))
        pk2, hp2, _ = flowUnwrapper.unwrap(inst2, noc, entries)

    def key(ps):
        return sorted((p["name"], p["min_start"], p["abs_deadline"], p["net_time"]) for p in ps)
    assert key(pk) == key(pk2) and hp == hp2 == P
