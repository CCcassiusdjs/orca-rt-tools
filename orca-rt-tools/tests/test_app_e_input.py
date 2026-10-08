"""Command line input of application E (apps/synthetic-app-e/synthetic-app-e.csv).

The file was a copy of apps/shi-2010/SHI2010.csv (CAR application of Shi,
Burns and Indrusiak 2010), added in commit 4c299fc. It now holds
application E: the graph of synthetic-app-e.txt, release period 0.5 ms,
end-to-end deadline 2 ms (task rows) and the payloads of the exp-23
application (pkt-sim/software/ucx-os/app/weird_a.c), except E->I, which
weird_a.c sends with COMM_DF_WORKLOAD (3450 bytes) and the graph gives as
9010 bytes.
"""
import os
import re

from tests.conftest import REPO_ROOT
from rttools.gff.orca import import_graph
from rttools.modules.io import appparser

APP_E = os.path.join(REPO_ROOT, "apps", "synthetic-app-e")
CSV = os.path.join(APP_E, "synthetic-app-e.csv")
WEIRD_A = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app", "weird_a.c")


def weird_a_defines():
    out = {}
    with open(WEIRD_A) as f:
        for line in f:
            m = re.match(r"#define\s+(\w+)\s+(\d+)", line)
            if m:
                out[m.group(1)] = int(m.group(2))
    return out


def test_csv_is_application_e():
    g, name = appparser.loadFromFile(CSV)
    assert name == "synthetic-app-e"
    assert sorted(g.nodes) == list("ABCDEFGHIJ")
    assert g.number_of_edges() == 11


def test_csv_matches_the_graph_file():
    g, _ = appparser.loadFromFile(CSV)
    txt = import_graph(os.path.join(APP_E, "synthetic-app-e.txt"))
    assert {n._data["label"]: int(n._data["wcet"]) for n in txt._nodes} == \
        {n: int(d["wcet"]) for n, d in g.nodes(data=True)}
    assert sorted((e._from._data["label"], e._to._data["label"], int(e._data["payload"])) for e in txt._edges) == \
        sorted((a, b, int(d["datasize"])) for a, b, d in g.edges(data=True))


def test_csv_matches_weird_a():
    d = weird_a_defines()
    g, _ = appparser.loadFromFile(CSV)
    for n, data in g.nodes(data=True):
        # WCET in cycles = 10 x the sleep argument of weird_a.c
        assert int(data["wcet"]) == 10 * d[f"TASK_{n}_WORKLOAD"], n
    for a, b, data in g.edges(data=True):
        if (a, b) == ("E", "I"):
            assert int(data["datasize"]) == 9010 == d["COMM_EI_WORKLOAD"]
        else:
            assert int(data["datasize"]) == d[f"COMM_{a}{b}_WORKLOAD"], (a, b)


def test_csv_periods_and_deadlines():
    g, _ = appparser.loadFromFile(CSV)
    for _, _, data in g.edges(data=True):
        assert float(data["period"]) == 0.0005
        assert float(data["deadline"]) == 0.0005
    rows = [r.split(",") for r in open(CSV).read().splitlines()]
    start = rows.index(["Task", "Period", "Capacity", "Deadline", "Acronym", "Description"])
    tasks = rows[start + 1:start + 11]
    assert [r[4] for r in tasks] == list("ABCDEFGHIJ")
    assert all(float(r[1]) == 0.0005 and float(r[3]) == 0.002 for r in tasks)


def test_car_keeps_its_own_file():
    g, _ = appparser.loadFromFile(os.path.join(REPO_ROOT, "apps", "shi-2010", "SHI2010.csv"))
    assert "NAVC" in g.nodes and g.number_of_edges() == 38
