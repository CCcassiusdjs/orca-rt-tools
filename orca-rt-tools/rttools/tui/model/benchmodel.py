"""Task sets for ORT/BENCH: load, save and simulate."""
from __future__ import annotations

import contextlib
import io

from rttools.bench.engine import SingleCoreEngine
from rttools.bench.scheduling import (
    DeadlineMonotonicSchedule, EarliestDeadlineFirst, RateMonotonicScheduling,
    RoundRobinSchedule,
)
from rttools.gff.orca import import_graph
from rttools.gsl.graph import Graph, GraphNode
from rttools.tui.model.timeunit import cycle_unit
from rttools.tui.model.trace import Mark, Slice, Trace

ALGORITHMS = {
    "RM": RateMonotonicScheduling,
    "DM": DeadlineMonotonicSchedule,
    "EDF": EarliestDeadlineFirst,
    "RR": RoundRobinSchedule,
}


def load_tasks(path):
    """Reads an ORCA graph file (`label wcet [period [deadline]]`). Edges
    are ignored by the bench."""
    g = import_graph(path)
    tasks = []
    for n in g._nodes:
        d = n._data
        tasks.append({
            "name": d["label"],
            "wcet": int(d["wcet"]),
            "period": int(d["period"]) if "period" in d else None,
            "deadline": int(d["deadline"]) if "deadline" in d else None,
        })
    return tasks


def save_tasks(path, tasks):
    with open(path, "w") as f:
        f.write("# nodes\n")
        for t in tasks:
            fields = [t["name"], str(t["wcet"])]
            if t.get("period"):
                fields.append(str(t["period"]))
                if t.get("deadline"):
                    fields.append(str(t["deadline"]))
            f.write(" ".join(fields) + "\n")
        f.write("\n# edges\n")


def validate(tasks):
    """List of error messages (empty when the task set is valid)."""
    errors = []
    names = set()
    for t in tasks:
        if not t["name"] or " " in t["name"]:
            errors.append(f"task name {t['name']!r}: empty or with spaces")
        if t["name"] in names:
            errors.append(f"task {t['name']}: duplicated name")
        names.add(t["name"])
        if t["wcet"] < 0:
            errors.append(f"task {t['name']}: wcet < 0")
        if t.get("period") is not None and t["period"] <= 0:
            errors.append(f"task {t['name']}: period <= 0")
        if t.get("deadline") is not None and t.get("period") is None:
            errors.append(f"task {t['name']}: deadline without period is not supported by the bench file format")
    return errors


def to_graph(tasks):
    g = Graph()
    for t in tasks:
        data = {"label": t["name"], "wcet": str(t["wcet"])}
        if t.get("period"):
            data["period"] = str(t["period"])
            if t.get("deadline"):
                data["deadline"] = str(t["deadline"])
        g._nodes.append(GraphNode(g.get_new_id(), data))
    return g


def simulate(tasks, algorithm, horizon, quantum=None, clock_hz=None):
    """Runs SingleCoreEngine. Returns (trace, misses, end time, log text).
    The trace has the lane CPU and one lane per task, release marks at
    k*T and deadline marks at k*T + D for periodic tasks, and miss marks."""
    engine = SingleCoreEngine(to_graph(tasks), ALGORITHMS[algorithm], quantum)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        end = engine.simulate(horizon, False)
    merged = engine.merged_trace()
    slices = []
    for b, e, n in merged:
        slices.append(Slice("CPU", b, e, n))
        slices.append(Slice(n, b, e, n))
    marks = []
    for t in tasks:
        if t.get("period"):
            d = t.get("deadline") or t["period"]
            k = 0
            while k * t["period"] <= horizon:
                marks.append(Mark(t["name"], k * t["period"], "release", f"{t['name']} job {k}"))
                if k * t["period"] + d <= horizon:
                    marks.append(Mark(t["name"], k * t["period"] + d, "deadline", f"{t['name']} job {k}"))
                k += 1
    for name, deadline, completion in engine._misses:
        marks.append(Mark(name, deadline, "miss",
                          f"{name} missed {deadline}" + ("" if completion is None else f", done {completion}")))
    lanes = ["CPU"] + [t["name"] for t in tasks]
    trace = Trace(f"bench {algorithm}", cycle_unit(clock_hz), lanes, slices, marks,
                  {"format": "bench", "algorithm": algorithm, "quantum": engine._quantum})
    return trace, list(engine._misses), end, buf.getvalue()
