"""Files of task costs t(v) for the analysis flow.

The flow reads t(v) from the Capacity (wcet) column of the application
CSV (the measured costs: rttools/bench_t/main.py, apps/synthetic-app-e).
A costs file of rttools.wcet (`python -m rttools.wcet analyze ... --out
costs.json`) gives the static values, which the flow combines with them
under the rule below (default max):

    python -m rttools <app.csv> <map|spiral> <arch.gml> [<freq> ...] --costs costs.json

| Field of costs.json | Use |
|---|---|
| tasks.<label>.t | static t(v) of the task (cycles), against the wcet of the node with that label |
| scheduler_cycles | cost of one scheduler event (the dispatch term of t(v)), against the scheduler_cycles parameter of the application (start of each task in its sequence, rttools/bench_t/estimate.py, sequence) |

Without --costs the flow keeps the values of the CSV.

Handlers file (`<costs>.handlers.json` next to the costs file, the same
analysis of the same image: rttools.paper.wcet, handlers_file): the cost
of the interrupt handlers of one packet event and, per task, the handler
cycles that t(v) holds (the terms send_isr and receive_isr of
rttools/wcet/ucx.py). The general phase model and the phase model of the
time-triggered images (rttools/bench_t/multirate.py, rttools/modules/
instances/release.py) charge to each job the handlers of the packet
events of its PE that can run inside it beyond what its t(v) holds.

| Field of <costs>.handlers.json | Use |
|---|---|
| image | the image of the costs file (sha256 must match) |
| inject | cycles of the injection of one packet (compare interrupt of TIMER1, lib/noc_tt.c) |
| receive | cycles of the reception of one packet (irq2_handler and irq3_handler with their entries) |
| tasks.<label>.isr | handler cycles in t(v): out-degree times inject plus in-degree times receive |

Rule of a costs file (`rule` of apply, RULES): "max" (default) sets t(v)
= max(t(v) of the CSV, t(v) of the file) and scheduler_cycles = the larger
of the two, so every cost that places a release or an instant bounds the
characterized and the static cost; "static" replaces the CSV values with
the values of the file (the comparison of rttools.paper.wcet between the
static and the characterized costs). apply records the source of each
cost ("csv" or "static"; "csv" when the two are equal).
"""
from __future__ import annotations

import json
import os

MEASURED = "measured"
STATIC = "static"
MAX = "max"
RULES = (MAX, STATIC)


class CostsError(ValueError):
    pass


def handlers_path(path):
    """Path of the handlers file of a costs file."""
    stem = path[:-5] if path.endswith(".json") else path
    return stem + ".handlers.json"


def load_handlers(path, image=None):
    """{"inject", "receive", "tasks": {label: isr}, "source"} of a handlers
    file; `image`: the image of the costs file, whose sha256 must match."""
    with open(path) as f:
        data = json.load(f)
    for k in ("inject", "receive"):
        if not isinstance(data.get(k), int) or data[k] < 0:
            raise CostsError(f"{path}: {k} must be a non-negative integer")
    tasks = {}
    for label, v in (data.get("tasks") or {}).items():
        isr = v.get("isr") if isinstance(v, dict) else v
        if not isinstance(isr, int) or isr < 0:
            raise CostsError(f"{path}: task {label}: isr must be a non-negative integer")
        tasks[str(label)] = isr
    if image is not None and (data.get("image") or {}).get("sha256") != image.get("sha256"):
        raise CostsError(f"{path}: image {(data.get('image') or {}).get('sha256')} differs from the image "
                         f"{image.get('sha256')} of the costs file")
    return {"inject": data["inject"], "receive": data["receive"], "tasks": tasks, "source": path}


def load(path):
    """{"tasks": {label: t}, "scheduler_cycles": int or None, "source": path,
    "handlers": load_handlers of the handlers file next to it, or None}."""
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
    hp = handlers_path(path)
    handlers = load_handlers(hp, data.get("image")) if os.path.exists(hp) else None
    return {"tasks": out, "scheduler_cycles": sc, "source": path, "handlers": handlers}


def merge(csv_cost, file_cost, rule=MAX):
    """(cost, source) of one task under `rule`."""
    if rule not in RULES:
        raise CostsError(f"cost rule must be one of {', '.join(RULES)}, got {rule!r}")
    if rule == STATIC or file_cost > csv_cost:
        return file_cost, STATIC
    return csv_cost, "csv"


def apply(app, costs, rule=MAX):
    """Sets the wcet of every node of the application graph (networkx, from
    rttools.modules.io.appparser) from t(v) of `costs` (load), by label,
    and the scheduler_cycles parameter, under `rule` (RULES). Every task of
    the graph needs a cost. Returns {label: (old, new)} and records the
    source of each cost in the attribute "cost_source" of the node."""
    if isinstance(costs, str):
        costs = load(costs)
    changes = {}
    missing = []
    for n, d in app.nodes(data=True):
        label = str(d.get("label", n))
        if label not in costs["tasks"]:
            missing.append(label)
            continue
        new, src = merge(int(float(d.get("wcet", 0))), costs["tasks"][label], rule)
        changes[label] = (d.get("wcet"), new)
        d["wcet"] = new
        d["cost_source"] = src
    if missing:
        raise CostsError(f"{costs['source']}: no cost for tasks {', '.join(sorted(missing))}")
    if costs.get("scheduler_cycles") is not None:
        old = app.graph.get("scheduler_cycles")
        sc = costs["scheduler_cycles"]
        app.graph["scheduler_cycles"] = sc if rule == STATIC or old is None else max(int(old), sc)
    h = costs.get("handlers")
    if h is not None:
        app.graph["handlers"] = graph_handlers(app, h)
    return changes


def graph_handlers(app, h):
    """Handlers attribute of an application graph (release.settings): the
    event costs and the handler cycles in t(v) of every node (by node id;
    0 for a label without a row)."""
    return {"inject": h["inject"], "receive": h["receive"],
            "budget": {n: h["tasks"].get(str(d.get("label", n)), 0) for n, d in app.nodes(data=True)}}


def sources(app):
    """{label: "csv" or "static"} of a graph after apply."""
    return {str(d.get("label", n)): d.get("cost_source", "csv") for n, d in app.nodes(data=True)}


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
