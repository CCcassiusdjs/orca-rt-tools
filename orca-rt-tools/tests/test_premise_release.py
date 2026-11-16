"""Check of premise (ii) on a link schedule (rttools.paper.ttflow.premise_release) and the guard of AGS
(rttools.modules.routing.router.release_guard)."""
from rttools.modules.routing import router
from rttools.paper import ttflow

TERMS = {"kernel": {"send_isr": 622, "receive_isr_size": 3878, "receive_isr_end": 925, "release": 249},
         "sections": {"yield": 853, "send_local": 1191}}
P = 131520
NEED = router.ISR_ENTRY_CYCLES + 929 + 253


def row(s, o, period=P):
    return {"s": s, "occupancy": o, "period": period}


def test_reservation_before_the_request():
    r = ttflow.premise_release([row(117332, 15405)], 1621, TERMS)
    assert r["holds"] and r["required_margin_cycles"] == NEED
    assert r["margin_min_cycles"] == P - (117332 + 15405 - router.NI_RX_END_CYCLES)


def test_end_of_reception_before_the_release():
    # the last flit can come so late that the end-of-reception handler and the release handler reach the tick
    o = P - 117332 + router.NI_RX_END_CYCLES - NEED
    assert not ttflow.premise_release([row(117332, o)], 1621, TERMS)["holds"]
    assert ttflow.premise_release([row(117332, o - 1)], 1621, TERMS)["holds"]


def test_reservation_just_after_a_request():
    q = P - 1621
    assert not ttflow.premise_release([row(q + 500, 15405)], 1621, TERMS)["holds"]
    assert ttflow.premise_release([row(q + 1191 + 61, 15405)], 1621, TERMS)["holds"]


def test_long_activity_in_the_lead():
    assert not ttflow.premise_release([], 1200, TERMS)["holds"]


def test_guard_matches_the_check():
    g = router.release_guard(P)
    if g is None:          # no network-interface model
        return
    for s, o in ((117332, 15405), (117332, P - 117332 + router.NI_RX_END_CYCLES - NEED), (P - 1621 + 500, 15405),
                 (P - 1621 + 1252, 15405), (1000, 15405)):
        assert g(s, o) == (not ttflow.premise_release([row(s, o)], router.RELEASE_LEAD_CYCLES, TERMS)["holds"])


def test_ags_places_a_packet_after_the_guard(monkeypatch):
    # one packet on one link: the first candidates break the guard, AGS places it at a later candidate
    from rttools.modules.backend.ags import search3, heuristics
    p = {"min_start": [[P - 1621 - 100]], "occupancy": [[15405]], "deadline": [[3 * P]], "packets": [{"name": "f:0"}],
         "hyperperiod": 3 * P}
    search3.GUARD = router.release_guard(P) or (lambda k, o: False)
    try:
        sched, skipped = search3.search3(p, heuristics.lstf, 5, 100)
    finally:
        search3.GUARD = None
    k = sched[0][0]
    assert not skipped and k is not None
    if router.release_guard(P) is not None:
        assert ttflow.premise_release([row(k, 15405)], 1621, TERMS)["holds"] and k > P - 1621 - 100
