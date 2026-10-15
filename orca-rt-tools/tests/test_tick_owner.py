"""Tick owners of the time-triggered applications (rttools/bench/ucx.py,
owners and owner_of; TT_TICK of app/car_full_tt.h; the tick hook of
rttools.ucxgen). The round robin of UCX-OS searches at each tick from the
task that holds the CPU: a job that ends before its modeled finish lets
the next task start in the rest of the phase, and the tick then passes
over it (run CF5, USOS on PE 0-1). With the table, the tick hook starts
the search at the position that the model dispatches, so every job ends
at or before its F when its work and the events of the platform stay
within the charges of the model."""
import os
import random
import re

import pytest

from rttools.bench import ucx
from rttools.bench_t import multirate
from rttools.paper import ttflow
from tests.conftest import REPO_ROOT

APP = os.path.join(REPO_ROOT, "apps", "car-full")
CSV = os.path.join(APP, "car-full.csv")
MAP = os.path.join(APP, "car-full-ONTO-hermes4x4.map")
ARCH = os.path.join(REPO_ROOT, "arch", "hermes-4x4.gml")
COSTS = os.path.join(REPO_ROOT, "experiments", "wcet", "costs", "tt")
APP_DIR = os.path.join(REPO_ROOT, "pkt-sim", "software", "ucx-os", "app")
TICK, DISPATCH = 1852, 515      # tick + release and dispatch terms of car_full (rttools.wcet), cycles


def model(costs, P):
    g, _, _, entries, _ = ttflow.load_app(CSV, MAP, ARCH, costs)
    spec = multirate.spec_from_graph(g, entries, multirate.graph_rates(g))
    return spec, multirate.schedule(spec, P)


def platform(spec, sched, node, work, table):
    """Jobs of PE `node` with the work `work` (cycles of each task, without
    its events) and the events of the platform: each tick costs TICK to
    the job that it dispatches, the switch at the end of a job is part of
    the job (rttools/bench/ucx.py, tick_sigma)."""
    ts = spec.orders[node]
    own = sched.tick_owners()[node]
    loop = sched.h0 * spec.hyper_ticks

    def owner_of(t):
        return own[t] if t < len(own) else own[loop + (t - loop) % (len(own) - loop)]
    tasks = [{"name": t, "cost": work[t] + DISPATCH, "period": spec.ticks[t], "offset": spec.offsets[t]} for t in ts]
    return ucx.simulate(tasks, sched.P, 3 * spec.hyper_ticks, TICK, tail=3 * spec.hyper_ticks, tick_sigma=True,
                        owner_of=owner_of if table else None)


def late(sched, node, run):
    out = []
    for t, js in run["jobs"].items():
        for j, mj in zip(js, sched.sims[node]["jobs"][t]):
            if j.finish is not None and mj.finish is not None and j.finish > mj.finish:
                out.append((t, j.index + 1, j.release // sched.P, j.finish - mj.finish))
    return out


def test_round_robin_moves_usos_by_a_phase():
    """The model of run CF5 (costs of the image of r11-rc7, 478.336 MHz, P =
    119,584) and the work of car_full.c (the costs of the CSV): without the
    table, job 3 of USOS (phase 10 of each hyperperiod) ends a phase after
    its F, as in run CF5; with the table, no job ends after its F."""
    spec, sched = model(os.path.join(COSTS, "previous", "car_full-8f4b212f68a0.json"), 119584)
    node = next(n for n, ts in spec.orders.items() if "USOS" in ts)
    assert spec.orders[node] == ["OBDB", "USOS", "OBMG"]
    assert sched.tick_owners()[node][10:12] == [1, 2]          # OBDB holds phase 10, USOS gets the tick of 11
    csv = {"OBDB": 711000, "USOS": 104330, "OBMG": 1411000}
    work = {t: c - spec.sigma - TICK - DISPATCH for t, c in csv.items()}
    rr = late(sched, node, platform(spec, sched, node, work, False))
    assert [(t, j, q) for t, j, q, _ in rr] == [("USOS", 3, 10), ("USOS", 13, 60), ("USOS", 23, 110)]
    assert all(d > 90000 for *_, d in rr)
    assert late(sched, node, platform(spec, sched, node, work, True)) == []


def test_table_bounds_every_job():
    """CAR-full with the costs of the image of this tree at P = 119,488 (run
    CF6): for random work of every task (30 to 100 % of c(v) less its
    events) on every PE, no job ends after its F with the table; without
    it, jobs do."""
    spec, sched = model(os.path.join(COSTS, "car_full.json"), 119488)
    assert sched.feasible
    rr = table = 0
    for node, ts in spec.orders.items():
        for trial in range(40):
            rnd = random.Random(1000 * int(node) + trial)
            work = {t: max(0, int(spec.cost[t] * rnd.uniform(0.3, 1.0)) - TICK - DISPATCH) for t in ts}
            rr += len(late(sched, node, platform(spec, sched, node, work, False)))
            table += len(late(sched, node, platform(spec, sched, node, work, True)))
    assert table == 0 and rr > 0


def test_tick_table_of_the_image():
    """TT_TICK of app/car_full_tt.h: the position that the model dispatches
    at each tick (bits 0-1) and the releases of the tick (bit 2 + i), at the
    clock of the table; the tick hook of car_full.c reads it."""
    with open(os.path.join(APP_DIR, "car_full_tt.h")) as f:
        text = f.read()
    clock = int(re.search(r"#if F_CPU == (\d+)", text).group(1))
    P = int(re.search(r"(\d+) cycles per tick", text).group(1))
    assert (clock, P) == (477952000, 119488)
    rows = re.findall(r"\{([0-9, ]+)\},   /\* node (\d+) \*/", text)
    spec, sched = model(os.path.join(COSTS, "car_full.json"), P)
    own = sched.tick_owners()
    assert len(rows) == 16
    for vals, node in rows:
        vals = [int(x) for x in vals.split(",")]
        ts = spec.orders.get(node, [])
        assert [v & 3 for v in vals] == own.get(node, [0] * len(vals))
        for t, v in enumerate(vals):
            assert [(v >> (2 + i)) & 1 for i in range(len(ts))] == [
                int(t >= spec.offsets[x] and (t - spec.offsets[x]) % spec.ticks[x] == 0) for x in ts]
    with open(os.path.join(APP_DIR, "car_full.c")) as f:
        code = f.read()
    assert "tick_row = TT_TICK[ucx_noc_cpu_id()];" in code and "kcb_p->tcb_p = owner_pred[p];" in code
    assert "countdown" not in code
