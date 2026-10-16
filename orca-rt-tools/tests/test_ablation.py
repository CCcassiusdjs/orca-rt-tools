"""Ablation of the terms of the flow and the event-triggered baseline
(rttools/paper/ablation.py, experiments/ablation): the run reproduces
reference.json; without contention the WCTT of a packet equals its
occupancy o_i; the bound sums the packets of each competing input port
(polling control unit of the Hermes router) and slows the flits of a
packet whose DDMA also receives; the time-triggered link schedule never
needs a higher clock than the event-triggered baseline; the WCTT covers the
measured latencies of the stored event-triggered runs."""
import os

from rttools.modules.routing import router, wctt
from rttools.paper import ablation, cputime
from tests.conftest import REPO_ROOT

EXP = os.path.join(REPO_ROOT, "experiments")


def _path(nodes):
    return [{"data": {"label": f"{a}-{b}"}} for a, b in zip(nodes, nodes[1:])]


def test_wctt_without_contention_is_the_occupancy():
    p = {"name": "q", "datasize": 1230, "path": _path(["L", "0", "1", "L"])}
    assert wctt.wctt([p]) == {"q": router.occupancy(1, 1230)}


HOLD = router.getPacketFlits(64) + 1 + router.NI_RX_SIZE_CYCLES + router.NI_RX_END_CYCLES


def test_wctt_blocking_of_one_packet():
    """Two packets from different input ports to one ejection port: each
    waits at most for the hold of the other (flits + 1 + receive handlers)
    and one header service of the control unit."""
    a = {"name": "a", "datasize": 64, "path": _path(["L", "0", "1", "L"])}
    b = {"name": "b", "datasize": 64, "path": _path(["L", "2", "1", "L"])}
    w = wctt.wctt([a, b])
    extra = HOLD + wctt.HEADER_SERVICE
    assert w["a"] == router.occupancy(1, 64) + extra and w["b"] == router.occupancy(1, 64) + extra


def test_wctt_polling_sums_the_packets_of_a_port():
    """Packets b1 and b2 enter router 1 by one port: the polling control
    unit can serve both before a, so a waits for both holds; the rule of a
    round-robin arbiter per output counts one of them."""
    a = {"name": "a", "datasize": 64, "path": _path(["L", "0", "1", "L"])}
    b1 = {"name": "b1", "datasize": 64, "path": _path(["L", "2", "1", "L"])}
    b2 = {"name": "b2", "datasize": 64, "path": _path(["L", "3", "2", "1", "L"])}
    poll = wctt.wctt([a, b1, b2], ni="off")["a"]
    rr = wctt.wctt([a, b1, b2], ni="off", arbitration="round_robin")["a"]
    hold = router.getPacketFlits(64) + 1 + wctt.HEADER_SERVICE
    assert poll - rr == hold


def test_wctt_ddma_interleaving():
    """A packet whose target PE also sends a packet moves its flits at the
    rate of the shared memory port of the DDMA."""
    a = {"name": "a", "datasize": 400, "path": _path(["L", "0", "1", "L"])}
    b = {"name": "b", "datasize": 400, "path": _path(["L", "1", "2", "L"])}
    p = router.getPacketFlits(400)
    w = wctt.wctt([a, b], ni="off")
    assert w["a"] == router.occupancy(1, 400, wait="bound", ni="off") - p + wctt.interleaved(p)


def test_wctt_least_fixed_point_adds_packets_whose_windows_meet():
    """Exact releases: a starts at 0, b at 20; b meets a only through the
    window of a without contention, so the least fixed point charges a to b
    and b to a, and a packet released after both windows meets neither."""
    a = {"name": "a", "datasize": 64, "path": _path(["L", "0", "1", "L"]), "min_start": 0}
    b = {"name": "b", "datasize": 64, "path": _path(["L", "2", "1", "L"]), "min_start": 20}
    c = {"name": "c", "datasize": 64, "path": _path(["L", "3", "1", "L"]), "min_start": 10 ** 6}
    w, sets = wctt.wctt([a, b, c], earliest={"a": 0, "b": 20, "c": 10 ** 6}, details=True)
    assert sets == {"a": ["b"], "b": ["a"], "c": []}


def test_wctt_offsets_remove_packets_that_cannot_meet():
    a = {"name": "a", "datasize": 64, "path": _path(["L", "0", "1", "L"]), "min_start": 0}
    b = {"name": "b", "datasize": 64, "path": _path(["L", "2", "1", "L"]), "min_start": 100000}
    w, sets = wctt.wctt([a, b], earliest={"a": 0, "b": 100000}, details=True)
    assert sets == {"a": [], "b": []} and w["a"] == router.occupancy(1, 64)


def test_reference(tmp_path):
    m = ablation.run(os.path.join(EXP, "ablation", "config.json"), str(tmp_path))
    assert cputime.check(os.path.join(tmp_path, "metrics.json"), os.path.join(EXP, "ablation", "reference.json"))
    for name, row in m["apps"].items():
        if "event_triggered" in row:
            assert row["flow"]["minimum_hz"] <= row["event_triggered"]["minimum_hz"], name
            # less release jitter, lower event-triggered clock
            seq = [row[k]["minimum_hz"] for k in ("event_triggered", "event_triggered_b50", "event_triggered_b90",
                                                   "event_triggered_b100")]
            assert seq == sorted(seq, reverse=True), name
        for r, v in row.get("et_runs", {}).items():
            assert v["measured_above_wctt"] == 0 and v["late_packets"] == 0, (name, r)
        assert row["links_only"]["minimum_hz"] <= row["flow"]["minimum_hz"], name
