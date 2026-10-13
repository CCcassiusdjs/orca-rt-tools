"""UCX-OS application generator (rttools.ucxgen): model of application E
against weird_a.c, order without sequence rows, input errors and the
heap size of an image map."""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.ucxgen import memory, model

APP_E = os.path.join(REPO_ROOT, "apps", "synthetic-app-e")
E_CSV = os.path.join(APP_E, "synthetic-app-e.csv")
E_MAP = os.path.join(APP_E, "synthetic-app-e-ONTO-hermes2x2.map")


def by_name(m):
    return {t["name"]: t for t in m["tasks"]}


# ---------------------------------------------------------------- model


def test_app_e_matches_weird_a():
    m = model.build(E_CSV, E_MAP, "app_e", mesh="2x2")
    t = by_name(m)
    assert m["warnings"] == []
    # PEs of weird_a.c (CPU_* defines)
    cpu = {"A": 0, "B": 0, "D": 0, "F": 0, "C": 1, "E": 2, "H": 2, "I": 2, "G": 3, "J": 3}
    assert {n: x["pe"] for n, x in t.items()} == cpu
    # one source (A), released on PE 0: mask 1, as the default of manycore_top.sv
    assert [n for n, x in t.items() if x["source"]] == ["A"]
    assert m["release"] == {"period_ns": 500000, "delay_ns": 3000000, "pes": [0],
                            "pe_labels": ["0-0"], "mask": 1}
    # creation order = sequence rows of the CSV (dispatch order of the model)
    assert m["pe_tasks"] == {"0-0": ["IDLE", "A", "B", "D", "F"], "1-0": ["IDLE", "C"],
                             "0-1": ["IDLE", "E", "I", "H"], "1-1": ["IDLE", "G", "J"]}
    # J joins three edges, in CSV order; ports unique and nonzero
    assert [m["flows"][i - 1]["source"] for i in t["J"]["inputs"]] == ["I", "H", "G"]
    ports = [x["port"] for x in m["tasks"]]
    assert 0 not in ports and len(set(ports)) == len(ports)
    # workload = (c(v) - scheduler_cycles) / 10
    assert t["B"]["workload"] == (58600 - 11000) // 10
    assert m["flows"][0]["tag_base"] == 1024 and m["flows"][-1]["tag_base"] == 11 * 1024


def test_order_without_sequence_rows(tmp_path):
    """Without sequence rows the order is the .map line, kept by local edges."""
    csv = tmp_path / "a.csv"
    csv.write_text("#tasks,,,,,\nTask,Period,Capacity,Deadline,Acronym,Description\n"
                   "1,0,30000,0,S,S\n2,0,30000,0,X,X\n3,0,30000,0,Y,Y\n"
                   "#flows,,,,,\nFlow,Period,Data,Deadline,Source,Target\n"
                   "1,0.001,64,0.001,S,Y\n2,0.001,64,0.001,Y,X\n"
                   "#parameters,,,,,\nParameter,Value,,,,\nscheduler_cycles,10000,,,,\n")
    mp = tmp_path / "a.map"
    mp.write_text("0:X,S,Y\n")
    m = model.build(str(csv), str(mp), "a", mesh="1x1")
    assert m["pe_tasks"] == {"0-0": ["IDLE", "S", "Y", "X"]}
    assert m["release"]["period_ns"] == 1000000
    assert any("manycore_pe.sv fires every 500000 ns" in w for w in m["warnings"])
    assert all(f["local"] for f in m["flows"])
    assert [t["workload"] for t in m["tasks"]] == [2000, 2000, 2000]


def test_errors(tmp_path):
    csv = tmp_path / "a.csv"
    head = "#tasks,,,,,\nTask,Period,Capacity,Deadline,Acronym,Description\n1,0,1000,0,S,S\n2,0,1000,0,X,X\n"
    flows = "#flows,,,,,\nFlow,Period,Data,Deadline,Source,Target\n"
    mp = tmp_path / "a.map"
    mp.write_text("0:S\n1:X\n")
    csv.write_text(head + flows + "1,0.001,64,0.001,S,X\n2,0.002,64,0.002,S,X\n")
    with pytest.raises(model.GenError, match="one release period"):
        model.build(str(csv), str(mp), "a", mesh="2x1")
    csv.write_text(head + flows + "1,0.001,70000,0.001,S,X\n")
    with pytest.raises(model.GenError, match="payload divisor"):
        model.build(str(csv), str(mp), "a", mesh="2x1")
    assert model.build(str(csv), str(mp), "a", mesh="2x1", payload_divisor=2)["flows"][0]["bytes"] == 35000
    csv.write_text(head + flows + "1,0.001,64,0.001,S,X\n")
    with pytest.raises(ValueError, match="not in the architecture"):
        model.build(str(csv), str(mp), "a", mesh="1x1")
    with pytest.raises(model.GenError, match="16-bit tag"):
        model.build(str(csv), str(mp), "a", mesh="2x1", tag_mod=40000)


# ---------------------------------------------------------------- memory


def test_heap_size_of_image_map(tmp_path):
    p = tmp_path / "image.map"
    p.write_text("                0x0000c644                        _heap_size = (_stack_end - _ebss)\n")
    assert memory.heap_size(str(p)) == 0xC644


