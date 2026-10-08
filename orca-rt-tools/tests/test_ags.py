"""AGS backend (rttools/modules/backend/ags)."""
from rttools.modules.backend.ags import heuristics, search3


def single_link(occupancy, min_start, deadline):
    """Problem with one link and one packet per entry of the lists."""
    n = len(occupancy)
    return {
        "min_start": [list(min_start)],
        "occupancy": [list(occupancy)],
        "deadline": [list(deadline)],
        "packets": [{"name": "p%d" % i} for i in range(n)],
        "links": ["0-1"],
        "hyperperiod": max(deadline),
    }


def test_zero_slack_packet_is_scheduled():
    # release window [10, 10]: deadline - occupancy = min_start
    p = single_link([5], [10], [15])
    res = search3.search3(p, heuristics.lstf, 3, 1)
    assert res is not None
    sched, skipped = res
    assert skipped == set() and sched[0][0] == 10
