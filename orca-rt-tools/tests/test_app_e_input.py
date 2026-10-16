"""Command line input of application E (apps/synthetic-app-e/synthetic-app-e.csv).

The file holds application E for the analysis flow of the paper: the graph of
synthetic-app-e.txt, release period 0.5 ms, end-to-end deadline 2 ms
(task rows), the payloads of the exp-23 application (pkt-sim/software/
ucx-os/app/weird_a.c, E->I with 9010 bytes), the characterized costs
c^(v) of rttools/bench_t/main.py (scale of the ORCA RT-Tools reference / 10) as task capacity and
the #parameters section of the phase model (scheduler cost and the
creation order of each PE, the source of the dispatch order of the
analysis; weird_a.c and the log table of experiments/exp23/config.json
must follow it).
"""
import json
import os
import re

from tests.conftest import REPO_ROOT
from rttools.bench_t import main as bench_t
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
    assert sorted(n._data["label"] for n in txt._nodes) == sorted(g.nodes)
    assert sorted((e._from._data["label"], e._to._data["label"], int(e._data["payload"])) for e in txt._edges) == \
        sorted((a, b, int(d["datasize"])) for a, b, d in g.edges(data=True))


def test_csv_costs_are_the_characterized_costs():
    """Task capacity = c^(v) of rttools/bench_t/main.py / 10 (cycles of
    the RTL), scheduler cost / 10, one creation row per cluster and no
    sequence row (the kernel rule gives the dispatch order)."""
    g, _ = appparser.loadFromFile(CSV)
    costs = {t: c // 10 for ts in bench_t.TASK_SETS.values() for t, c in ts}
    assert {n: int(d["wcet"]) for n, d in g.nodes(data=True)} == costs
    assert g.graph["release_model"] == "phase"
    assert g.graph["scheduler_cycles"] == bench_t.SCHEDULER_CYCLES // 10
    assert "sequences" not in g.graph
    assert sorted(sorted(ts) for ts in g.graph["creation"].values()) == \
        sorted(sorted(t for t, _ in ts) for ts in bench_t.TASK_SETS.values())


def weird_a_creation():
    """{cpu id: [task, ...]} of the ucx_task_add calls of app_main, in
    call order, and the tasks added before the switch (every PE)."""
    text = open(WEIRD_A).read()
    body = text[text.index("int32_t app_main(void)"):]
    body = body[:body.index("return 1;")]
    head, cases = body.split("switch (cpu_id)")
    common = re.findall(r'ucx_task_add\(\w+,\s*"(\w+)"', head)
    out, cur = {}, []
    for line in cases.splitlines():
        m = re.match(r"\s*case\s+(\d+):", line)
        if m:
            cur = out.setdefault(m.group(1), [])
            continue
        m = re.search(r'ucx_task_add\(\w+,\s*"(\w+)"', line)
        if m:
            cur.append(m.group(1))
    return common, out


def test_creation_rows_are_app_main_of_weird_a():
    """The creation rows of the CSV are the source of the order; app_main
    adds the idle task first and then the tasks of each PE in the order of
    its row (weird_a.c:401-422)."""
    common, cases = weird_a_creation()
    g, _ = appparser.loadFromFile(CSV)
    assert common == ["IDLE"]
    assert cases == g.graph["creation"]


def test_log_table_of_exp23_is_the_creation_order():
    """experiments/exp23/config.json pe_tasks decodes the task ids of the
    log (id 0 = IDLE, then the creation order); it equals the creation row
    of the cluster of each PE."""
    with open(os.path.join(REPO_ROOT, "experiments", "exp23", "config.json")) as f:
        cfg = json.load(f)
    g, _ = appparser.loadFromFile(CSV)
    rows = {"".join(sorted(ts)): ts for ts in g.graph["creation"].values()}
    for pe, cluster in cfg["clusters"].items():
        assert cfg["pe_tasks"][pe] == ["IDLE"] + rows["".join(sorted(cluster))], pe


def test_csv_matches_weird_a():
    d = weird_a_defines()
    g, _ = appparser.loadFromFile(CSV)
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
