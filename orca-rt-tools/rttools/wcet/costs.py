"""Files of task costs t(v) for the analysis flow.

The flow reads t(v) from the Capacity (wcet) column of the application
CSV (the measured costs: rttools/bench_t/main.py, apps/synthetic-app-e).
A costs file of rttools.wcet (`python -m rttools.wcet analyze ... --out
costs.json`) replaces them with the static values:

    python -m rttools <app.csv> <map|spiral> <arch.gml> [<freq> ...] --costs costs.json

| Field of costs.json | Use |
|---|---|
| tasks.<label>.t | t(v) of the task (cycles); replaces the wcet of the node with that label |
| scheduler_cycles | cost of one scheduler event (the dispatch term of t(v)); replaces the scheduler_cycles parameter of the application (start of each task in its sequence, rttools/bench_t/estimate.py, sequence) |

Without --costs the flow keeps the values of the CSV.
"""
from __future__ import annotations

import json

MEASURED = "measured"
STATIC = "static"


class CostsError(ValueError):
    pass


def load(path):
    """{"tasks": {label: t}, "scheduler_cycles": int or None, "source": path}."""
    with open(path) as f:
        data = json.load(f)
    tasks = data.get("tasks")
    if not isinstance(tasks, dict) or not tasks:
        raise CostsError(f"{path}: no tasks")
    out = {}
    for label, v in tasks.items():
        t = v.get("t") if isinstance(v, dict) else v
        if not isinstance(t, int) or t < 0:
            raise CostsError(f"{path}: task {label}: t must be a non-negative integer, got {t!r}")
        out[str(label)] = t
    sc = data.get("scheduler_cycles")
    if sc is not None and (not isinstance(sc, int) or sc < 0):
        raise CostsError(f"{path}: scheduler_cycles must be a non-negative integer")
    return {"tasks": out, "scheduler_cycles": sc, "source": path}


def apply(app, costs):
    """Sets the wcet of every node of the application graph (networkx, from
    rttools.modules.io.appparser) to t(v) of `costs` (load), by label, and
    the scheduler_cycles parameter. Every task of the graph needs a cost.
    Returns {label: (old, new)}."""
    if isinstance(costs, str):
        costs = load(costs)
    changes = {}
    missing = []
    for n, d in app.nodes(data=True):
        label = str(d.get("label", n))
        if label not in costs["tasks"]:
            missing.append(label)
            continue
        changes[label] = (d.get("wcet"), costs["tasks"][label])
        d["wcet"] = costs["tasks"][label]
    if missing:
        raise CostsError(f"{costs['source']}: no cost for tasks {', '.join(sorted(missing))}")
    if costs.get("scheduler_cycles") is not None:
        app.graph["scheduler_cycles"] = costs["scheduler_cycles"]
    return changes


def split_flag(args, flag="--costs"):
    """(args without `flag FILE`, FILE or None)."""
    out, path = [], None
    i = 0
    while i < len(args):
        if args[i] == flag:
            if i + 1 >= len(args):
                raise CostsError(f"{flag} needs a file")
            path = args[i + 1]
            i += 2
            continue
        if args[i].startswith(flag + "="):
            path = args[i].split("=", 1)[1]
            i += 1
            continue
        out.append(args[i])
        i += 1
    return out, path
