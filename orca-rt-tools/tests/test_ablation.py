"""Ablation of the terms of the flow and the event-triggered baseline
(rttools/paper/ablation.py, experiments/ablation): the run reproduces
reference.json; without contention the WCTT of a packet equals its
occupancy o_i; the time-triggered link schedule never needs a higher clock
than the event-triggered baseline."""
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


def test_wctt_round_robin_blocking():
    """Two packets from different input ports to one ejection port: each
    waits at most for the hold of the other (flits + 1 + receive handlers)."""
    a = {"name": "a", "datasize": 64, "path": _path(["L", "0", "1", "L"])}
    b = {"name": "b", "datasize": 64, "path": _path(["L", "2", "1", "L"])}
    w = wctt.wctt([a, b])
    hold = router.getPacketFlits(64) + 1 + router.NI_RX_SIZE_CYCLES + router.NI_RX_END_CYCLES
    assert w["a"] == router.occupancy(1, 64) + hold and w["b"] == router.occupancy(1, 64) + hold


def test_reference(tmp_path):
    m = ablation.run(os.path.join(EXP, "ablation", "config.json"), str(tmp_path))
    assert cputime.check(os.path.join(tmp_path, "metrics.json"), os.path.join(EXP, "ablation", "reference.json"))
    for name, row in m["apps"].items():
        if "event_triggered" in row:
            assert row["flow"]["minimum_hz"] <= row["event_triggered"]["minimum_hz"], name
        assert row["links_only"]["minimum_hz"] <= row["flow"]["minimum_hz"], name
