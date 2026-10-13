"""Link occupancy of a packet (ORT/FNS) against the measured zero-load
latency of the Hermes router, L0 = 6 (m + 1) + p + 1."""
import os

import pytest

from tests.conftest import REPO_ROOT
from rttools.modules.routing import router

# GHDL simulation of the Hermes of the repository (8 x 3 mesh, source
# (0,0), ideal injector and sink at the LOCAL ports): hops m, payload flits
# p (size flit value) and cycles from the acceptance of the header at the
# source to the consumption of the last flit at the target.
MEASURED = [
    (1, 1, 14), (1, 4, 17), (1, 16, 29), (1, 311, 324),
    (2, 1, 20), (2, 4, 23), (2, 16, 35), (2, 311, 330),
    (3, 1, 26), (3, 4, 29), (3, 16, 41), (3, 311, 336),
    (4, 1, 32), (4, 4, 35), (4, 16, 47), (4, 311, 342),
    (6, 1, 44), (6, 4, 47), (6, 16, 59), (6, 311, 354),
    (7, 1, 50), (7, 4, 53), (7, 16, 65), (7, 311, 360),
    (8, 1, 56), (8, 4, 59), (8, 16, 71), (8, 311, 366),
    (9, 1, 62), (9, 4, 65), (9, 16, 77), (9, 311, 372),
]

# flows of application E (exp-23): hops, payload bytes, flits p with the
# 12-byte kernel header, and L0
FLOWS_E = [
    (1, 1230, 311, 324),
    (2, 6780, 1698, 1717),
    (2, 1200, 303, 322),
    (1, 5670, 1421, 1434),
    (1, 8900, 2228, 2241),
]


@pytest.mark.parametrize("m,p,cycles", MEASURED)
def test_routing_time_matches_measured_latency(m, p, cycles):
    assert router.getRoutingTime() * (m + 1) + p + 1 == cycles


@pytest.mark.parametrize("m,payload,p,l0", FLOWS_E)
def test_occupancy_counts_kernel_header(m, payload, p, l0):
    assert router.getPacketFlits(payload) == p
    assert router.occupancy(m, payload, "off") == l0


def test_packet_flits_round_payload_to_words():
    # 1 byte of payload occupies one word; the header adds 3 flits
    assert router.getPacketFlits(0) == 3
    assert router.getPacketFlits(1) == 4
    assert router.getPacketFlits(4) == 4
    assert router.getPacketFlits(5) == 5
    # payload-only flits keep their meaning (MiniZinc backend)
    assert router.getNumFlits(5) == 2


def test_unwrapper_uses_occupancy():
    from rttools.tui.model import network
    d = os.path.join(REPO_ROOT, "apps", "str2rts-dct-verify")
    case = network.load_case(os.path.join(d, "DCT-Verify.csv"),
                             os.path.join(d, "STR2RST-DCT-verify-ONTO-hermes3x2.map"),
                             os.path.join(REPO_ROOT, "arch", "hermes-2x3.gml"))
    rows, hp, packets = network.flows_at(case, 2000000)
    assert packets
    by_flow = {r["flow"]: r for r in rows}
    for pkt in packets:
        r = by_flow[pkt["flow"]]
        assert pkt["net_time"] == router.occupancy(r["hops"], pkt["datasize"]) == r["net_time"]


# header wait at the SwitchControl (make -C experiments/zll contention)
CONTENTION_REF = os.path.join(REPO_ROOT, "experiments", "zll", "reference_contention.json")


def l0(m, payload):
    return router.getRoutingTime() * (m + 1) + router.getPacketFlits(payload) + 1


def test_header_wait_constants_come_from_ghdl_reference():
    import json
    with open(CONTENTION_REF) as f:
        ref = json.load(f)
    assert router.HEADER_SERVICE_CYCLES == ref["service_cycles_per_header"] == 5
    assert router.MAX_COMPETING_HEADERS == ref["competing_headers_max"] == 4
    assert router.HEADER_WAIT_CYCLES == ref["largest_wait_cycles"] == 20
    assert ref["flits_with_error"] == 0 and ref["lost_or_timeout"] == 0
    # one service time per competing header, 0 for a header alone
    for n, w in ref["largest_wait_by_headers"].items():
        assert w == router.HEADER_SERVICE_CYCLES * (int(n) - 1)


def test_default_occupancy_is_the_header_wait_bound():
    """Default o_i = L0 + 20 (m + 1): the header wait bound of the Hermes."""
    assert router.header_wait() == router.HEADER_WAIT_DEFAULT == router.HEADER_WAIT_CYCLES == 20
    for m, payload, p, lat in FLOWS_E:
        assert lat == l0(m, payload)
        assert router.occupancy(m, payload) == lat + 20 * (m + 1)


@pytest.mark.parametrize("m,payload,p,lat", FLOWS_E)
def test_occupancy_with_header_wait_bound(m, payload, p, lat):
    assert router.occupancy(m, payload, "bound") == lat + 20 * (m + 1)
    assert router.occupancy(m, payload, 20) == lat + 20 * (m + 1)
    assert router.occupancy(m, payload, "off") == lat
    assert router.occupancy(m, payload, 0) == lat


def test_header_wait_from_environment(monkeypatch):
    for value, w in (("bound", 20), ("BOUND", 20), ("7", 7), ("0", 0), ("off", 0), ("OFF", 0), ("", 20)):
        monkeypatch.setenv(router.HEADER_WAIT_ENV, value)
        assert router.header_wait() == w
        assert router.occupancy(2, 6780) == 1717 + w * 3
    monkeypatch.delenv(router.HEADER_WAIT_ENV)
    assert router.occupancy(2, 6780) == 1717 + 20 * 3


def test_set_header_wait_overrides_environment(monkeypatch):
    monkeypatch.setenv(router.HEADER_WAIT_ENV, "7")
    assert router.set_header_wait("bound") is None
    assert router.header_wait() == 20
    assert router.set_header_wait(None) == 20
    assert router.header_wait() == 7


@pytest.mark.parametrize("value", ["-1", -5, "twenty", "1.5", True])
def test_header_wait_rejects_bad_values(value, monkeypatch):
    with pytest.raises(ValueError):
        router.parse_header_wait(value)
    if isinstance(value, str):
        monkeypatch.setenv(router.HEADER_WAIT_ENV, value)
        with pytest.raises(ValueError):
            router.occupancy(1, 1230)


def test_unwrapper_uses_header_wait():
    from rttools.tui.model import network
    d = os.path.join(REPO_ROOT, "apps", "str2rts-dct-verify")
    files = (os.path.join(d, "DCT-Verify.csv"), os.path.join(d, "STR2RST-DCT-verify-ONTO-hermes3x2.map"),
             os.path.join(REPO_ROOT, "arch", "hermes-2x3.gml"))
    router.set_header_wait("off")
    _, _, base = network.flows_at(network.load_case(*files), 2000000)
    router.set_header_wait("bound")
    rows, _, packets = network.flows_at(network.load_case(*files), 2000000)
    hops = {r["flow"]: r["hops"] for r in rows}
    assert [p["name"] for p in packets] == [p["name"] for p in base]
    for p, b in zip(packets, base):
        assert p["net_time"] == b["net_time"] + 20 * (hops[p["flow"]] + 1)
