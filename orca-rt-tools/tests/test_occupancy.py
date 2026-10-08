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
    assert router.occupancy(m, payload) == l0


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
