"""Check of premise (ii) on a link schedule (rttools.paper.ttflow.premise_release)."""
from rttools.modules.routing import router
from rttools.paper import ttflow

TERMS = {"kernel": {"send_isr": 622, "receive_isr_size": 3878, "receive_isr_end": 925},
         "sections": {"yield": 853, "send_local": 1191}}


def row(s, o, period=131520):
    return {"s": s, "occupancy": o, "period": period}


def test_size_handler_before_the_tick():
    # the size-flit handler ends by s + o - NI_RX_END_CYCLES, 2,940 cycles before the tick
    r = ttflow.premise_release([row(117332, 15405)], 1621, TERMS)
    assert r["holds"] and r["violations"] == 0 and r["longer_than_lead"] == ["rx_size"]
    assert r["margin_min_cycles"] == 131520 - (117332 + 15405 - router.NI_RX_END_CYCLES)


def test_size_handler_across_the_tick():
    # a reservation that starts before the request and whose size-flit handler can end after the tick
    s = 131520 - 1621 - 100
    r = ttflow.premise_release([row(s, 15405 + router.NI_RX_END_CYCLES)], 1621, TERMS)
    assert not r["holds"] and r["violations"] == 1 and r["margin_min_cycles"] <= 0


def test_reservation_after_the_request():
    # a reservation that starts after the request of a tick is checked against the next tick
    s = 131520 - 1000
    r = ttflow.premise_release([row(s, 15405)], 1621, TERMS)
    assert r["holds"] and r["margin_min_cycles"] == 2 * 131520 - (s + 15405 - router.NI_RX_END_CYCLES)


def test_long_section():
    r = ttflow.premise_release([], 1000, TERMS)
    assert not r["holds"]
