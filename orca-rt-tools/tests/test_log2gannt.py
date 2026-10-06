"""Fix 13 (rttools/log2gannt/matplot.py and gantt-latex.py).

1. f2na: (addr & 0xFF00) >> 16 always yields 0; the DDMA address is
   (x << 8) | y, so x = (addr >> 8) & 0xFF.
2. Task map per PE and time scale hardcoded (application E
   at 1 GHz, "x / 1000000 ms"); fixed output gannt2.png in the current
   directory. They are now parameters, with the old values as defaults.
3. A PE without events in the log raised IndexError in bins[b][0].
"""
import importlib.util
import json
import os

import pytest

from tests.conftest import PKG_ROOT, REPO_ROOT
from rttools.log2gannt import matplot

LOG = os.path.join(REPO_ROOT, "pkt-sim", "schedule-periodic3.txt")


def load_latex_module():
    path = os.path.join(PKG_ROOT, "rttools", "log2gannt", "gantt-latex.py")
    spec = importlib.util.spec_from_file_location("gantt_latex", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("f2na", [matplot.f2na, load_latex_module().f2na])
def test_f2na(f2na):
    assert f2na("0x00000102") == "1-2"
    assert f2na("0x00000300") == "3-0"
    assert f2na("00000001") == "0-1"


def test_time_formatter_scale():
    assert matplot.make_time_formatter(1_000_000)(2_000_000, None) == "2.0 ms"
    assert matplot.make_time_formatter(100_000)(2_000_000, None) == "20.0 ms"


def test_parse_log_intervals():
    lines = [
        "# 100 0-0 scheduled 1",
        "# 300 0-0 scheduled 2",
        "# 700 0-0 scheduled 0",
        "# Elapsed 1M time units.",
    ]
    names = {"0-0": ["IDLE", "X", "Y"], "1-1": ["IDLE", "Z"]}
    bins = matplot.parse_log(lines, names)
    assert [(e["time"], e["time_e"], e["task"]) for e in bins["0-0"]] == \
        [(100, 300, "X"), (300, 700, "Y"), (700, 700, "IDLE")]
    assert bins["1-1"] == []


def test_main_with_map_and_output(tmp_path):
    names = {"0-0": ["IDLE", "F", "D", "B", "A"], "1-1": ["IDLE", "J", "G"],
             "0-1": ["IDLE", "C"], "1-0": ["IDLE", "H", "I", "E"]}
    mfile = tmp_path / "map.json"
    mfile.write_text(json.dumps(names))
    out = tmp_path / "g.png"
    matplot.l2g_main([LOG, "--map", str(mfile), "--out", str(out), "--units-per-ms", "100000"])
    assert out.exists() and out.stat().st_size > 1000


# --- independent review: logs from the fixed RTL carry X and Y in the correct
# --- order; the default map follows the swapped order of the versioned logs
def swap_line(line):
    parts = line.split(" ")
    for i, p in enumerate(parts):
        if "-" in p and p.replace("-", "").isdigit():
            a, b = p.split("-")
            parts[i] = b + "-" + a
    return " ".join(parts)


def test_swap_xy_reads_new_logs():
    lines = open(LOG).readlines()
    new = [swap_line(l) for l in lines]
    a = matplot.parse_log(lines, matplot.task_names)
    b = matplot.parse_log(new, matplot.task_names, swap_xy=True)
    assert a == b


def test_mismatched_map_gives_clear_error():
    new = [swap_line(l) for l in open(LOG).readlines()]
    with pytest.raises(ValueError, match="--swap-xy"):
        matplot.parse_log(new, matplot.task_names)
