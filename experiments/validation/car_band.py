"""Validation of Section 6.6 (16/10/2026): for CAR (experiments/tt, CAR-FULL), the flow
is infeasible from 615 to 670 MHz and feasible at 610 and 675 MHz, and the read rule
assigns a packet of one flow to an earlier reader job in that band.
Usage: python3 val_car.py <repo root> <out.json>"""
import json
import math
import os
import sys
from fractions import Fraction

ROOT = os.path.abspath(sys.argv[1])
sys.path.insert(0, os.path.join(ROOT, "orca-rt-tools"))
os.chdir(os.path.join(ROOT, "experiments", "tt"))
from rttools.bench_t import multirate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator
from rttools.modules.unwrapper import flowUnwrapper
from rttools.paper import ttflow
from rttools.paper.frequency import search_config
from rttools.tui.model import network as tnet

cfg = ttflow.load_config("config.json")
a = cfg["apps"]["CAR-FULL"]
g, appname, noc, entries, _ = ttflow.load_app(a["csv"], a["map"], a["arch"], a["costs"])
spec = multirate.spec_from_graph(g, entries, multirate.graph_rates(g), noc)


def deadline_phases(f):
    """Phase index of the deadline (start of the reader job) of every packet, first
    round of the fixed point (no handler charge), and the period P in cycles."""
    P = math.floor(spec.phase_s * Fraction(f))
    with tnet.quiet():
        inst = instantiator.createInstance(g, noc, f)
        packets, _, _ = flowUnwrapper.unwrap(inst, noc, entries)
    return P, {p["name"]: p["abs_deadline"] // P for p in packets}


def diag(f):
    P = math.floor(spec.phase_s * Fraction(f))
    with tnet.quiet():
        at = search.schedule_at(g, noc, entries, appname, f, search_config(f))
    if at is None:
        return {"mhz": f / 1e6, "P": P, "schedule_at": None}
    return {"mhz": f / 1e6, "P": P, "skipped": len(at["skipped"]),
            "charge": at.get("handler_extra") is not None, "feasible": bool(search.feasible(at))}


out = {"grid": [], "reader_change": {}}
for mhz in range(600, 685, 5):
    r = diag(mhz * 1e6)
    out["grid"].append(r)
    print(r, flush=True)
_, base = deadline_phases(610e6)
for mhz in (615, 640, 670, 675):
    _, d = deadline_phases(mhz * 1e6)
    diff = {k: [base[k], d[k]] for k in base if k in d and d[k] != base[k]}
    out["reader_change"][str(mhz)] = diff
    print(mhz, "packets whose reader phase differs from 610 MHz:", diff, flush=True)
json.dump(out, open(sys.argv[2], "w"), indent=1)
