"""Deadline model tick of the time-triggered platform (router.tick_deadline,
the default with the network-interface model tt): a packet between PEs
reaches its target by the tick of the release of the job that reads it, the
earliest start of that job, and each job carries the handlers of the packet
events of its PE wherever they run (rttools/modules/instances/release.py,
handler_windows; rttools/bench_t/multirate.py, handler_extra)."""
import os

from rttools.bench_t import multirate
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator, release
from rttools.modules.routing import router
from rttools.paper import ttflow
from rttools.paper.frequency import search_config
from tests.conftest import REPO_ROOT

APPS = os.path.join(REPO_ROOT, "apps")
ARCH = os.path.join(REPO_ROOT, "arch")
COSTS = os.path.join(REPO_ROOT, "experiments", "wcet", "costs", "tt")


def test_handler_of_another_task_in_the_slice():
    """PE 0 runs y1 then y2; the packet of z (PE 1) to y2 arrives inside
    [F(z), end of the flow] = [50, 300], so its receive handler (30 cycles)
    can run in the slice of y1. t(y2) holds that handler (budget 30) and
    t(y1) none: F(y1) = 100 + 30, and F(y2) stays 200, since the work up to
    the end of y2 is y1 + y2 with the handler once. The inject handler of z
    starts at F(z) or later and does not delay z."""
    instance = {"flows": [("z", "y2", {"period": 1000, "label": "f1"})],
                "release": {"handlers": {"inject": 20, "receive": 30, "budget": {"y2": 30, "z": 20}}}}
    base = {"y1": {"finish": 100, "node": "0"}, "y2": {"finish": 200, "node": "0"},
            "z": {"finish": 50, "node": "1"}}
    seqs = {"0": ["y1", "y2"], "1": ["z"]}
    fin = release.handler_windows(instance, None, base, seqs, {"f1": 300})
    assert fin == {"y1": 130, "y2": 200, "z": 50}
    # without the budget of y2, the handler delays y2 as well
    instance["release"]["handlers"]["budget"] = {"z": 20}
    assert release.handler_windows(instance, None, base, seqs, {"f1": 300}) == {"y1": 130, "y2": 230, "z": 50}


def test_single_period_windows_of_application_e():
    """Application E at 449.152 MHz with t(v) = max(CSV, static) and the
    handlers of its image: every finish with the handlers is at or after
    the finish of the sequence, at least one task moves, every task ends
    within the phase, and every flow between PEs ends at the tick of the
    phase of its target (d P, d = n(target) - n(source))."""
    e = os.path.join(APPS, "synthetic-app-e")
    g, _, noc, entries, _ = ttflow.load_app(os.path.join(e, "synthetic-app-e.csv"),
                                            os.path.join(e, "synthetic-app-e-ONTO-hermes2x2.map"),
                                            os.path.join(ARCH, "hermes-2x2.gml"), os.path.join(COSTS, "weird_a.json"))
    assert router.tick_deadline()
    inst = instantiator.createInstance(g, noc, 449152000)
    win = release.task_windows(inst, entries)
    assert all(w["finish"] >= w["sequence_finish"] for w in win.values())
    assert any(w["finish"] > w["sequence_finish"] for w in win.values())
    assert release.handlers_fit(inst, entries)
    P = inst["flows"][0][2]["period"]
    flows = release.phase_flows(inst, entries)
    for s, t, d in inst["flows"]:
        if win[s]["node"] != win[t]["node"]:
            end = flows[d["label"]][1]
            assert end % P == 0 and end <= P + win[t]["start"]


def test_multirate_deadlines_at_the_release_of_the_reader():
    """CAR-full at 526.08 MHz (run CF6) with the costs and handlers of its
    image: the link schedule of schedule_at is feasible, every packet
    between PEs has its deadline at the release tick of the job that reads
    it and fits its window with its occupancy, and the handlers of the
    packet events add cycles to the jobs."""
    c = os.path.join(APPS, "car-full")
    g, appname, noc, entries, _ = ttflow.load_app(os.path.join(c, "car-full.csv"),
                                                  os.path.join(c, "car-full-ONTO-hermes4x4.map"),
                                                  os.path.join(ARCH, "hermes-4x4.gml"),
                                                  os.path.join(COSTS, "car_full.json"))
    f = 526080000
    a = search.schedule_at(g, noc, entries, appname, f, search_config(f))
    assert a is not None and a["schedule"] is not None and not a["skipped"]
    inst = instantiator.createInstance(g, noc, f)
    spec = multirate.spec_from_instance(inst, entries, noc)
    assert spec.tick
    P = inst["rates"]["phase_cycles"]
    sched = multirate.schedule(spec, P, extra=a.get("handler_extra"))
    assert sched.feasible
    # the charges are cycles added to the jobs (the round robin with the tick table is not monotonic in
    # the costs, so a job may end earlier when another job grows; the platform follows the same table)
    extra = a.get("handler_extra") or {}
    assert extra and all(x >= 0 for xs in extra.values() for x in xs) and any(x > 0 for xs in extra.values() for x in xs)
    win = multirate.packet_windows(spec, sched)
    for label, u, v, m in spec.flows:
        if spec.node_of[u] == spec.node_of[v]:
            continue
        o = spec.occ(u, v)
        for _, rel, dl, local in win[label]:
            assert not local and dl % P == 0 and rel + o <= dl
