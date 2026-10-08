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


def order(*first_to_last):
    """Criterion that allocates the packets in the given order."""
    return lambda space, m, o, d: list(reversed(first_to_last))


def test_truncation_at_maximum_release():
    # p0 holds [0, 10]; p1 (window [0, 16], PF 10) collides at 0 and 10
    # (closed intervals) and fits only at its maximum release 16
    p = single_link([10, 5], [0, 0], [10, 21])
    sched, skipped = search3.search3(p, order(0, 1), 1, 10)
    assert skipped == set() and sched[0] == [0, 16]
    assert search3.candidates(0, 16, 10) == [0, 10, 16]
    assert search3.candidates(0, 20, 10) == [0, 10, 20]
    assert search3.candidates(5, 4, 1) == []


def test_failed_packet_goes_first_after_reset():
    # p0 (window [0, 10]) goes first and takes 0; p1 (window [0, 0]) fails,
    # moves to the front of R, and the reset places p1 at 0 and p0 at 6
    p = single_link([10, 5], [0, 0], [20, 5])
    sched, skipped = search3.search3(p, order(0, 1), 2, 1)
    assert skipped == set() and sched[0] == [6, 0]
    assert search3.hsearch.resets == 1
    # with threshold 1 the first failure discards p1
    sched, skipped = search3.search3(p, order(0, 1), 1, 1)
    assert skipped == {1} and sched[0] == [0, None]
    assert search3.hsearch.resets == 0


def test_threshold_counts_failures_across_resets():
    # p1 never fits (deadline 4 < occupancy 5: empty window); it fails
    # G = 3 times (2 resets), leaves R, and p2 is still placed
    p = single_link([10, 5, 4], [0, 0, 0], [10, 4, 30])
    sched, skipped = search3.search3(p, order(0, 1, 2), 3, 1)
    assert skipped == {1}
    assert search3.hsearch.resets == 2
    assert sched[0][0] is not None and sched[0][2] is not None and sched[0][1] is None
    lo = sorted((sched[0][j], sched[0][j] + [10, 5, 4][j]) for j in (0, 2))
    assert lo[0][1] < lo[1][0]


def test_dct_verify_schedule_is_valid():
    from rttools.paper.ch6 import load_problem
    p = load_problem("problem_dctVerify")
    sched, skipped = search3.search3(p, heuristics.mbcf, 10, 10)
    assert skipped == set()
    for l, row in enumerate(p["occupancy"]):
        iv = sorted((sched[l][j], sched[l][j] + o) for j, o in enumerate(row) if o is not None)
        assert all(a[1] < b[0] for a, b in zip(iv, iv[1:]))
        for j, o in enumerate(row):
            if o is not None:
                assert p["min_start"][l][j] <= sched[l][j] <= p["deadline"][l][j] - o
