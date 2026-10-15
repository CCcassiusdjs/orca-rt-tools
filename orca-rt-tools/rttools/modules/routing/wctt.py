"""Worst-case traversal time (WCTT) of the packets of one phase under
event-triggered injection, by the recursive calculus of round-robin wormhole
networks (Ferrandiz, Frances and Fraboul, SIES 2009), for the baseline of
experiments/ablation.

Under event-triggered injection, the DDMA of a PE takes a packet when its job
sends it, so the packets of a phase can meet on any link. The Hermes router
serves its input ports in round-robin order (router.py, header wait): before
the header of packet q takes the output port of a router, each other input
port that requests the same output can send one packet through it. A packet
h that takes an output link holds it until its tail passes; under back
pressure the tail of h can wait for the blocking of h further on its route,
so the time h holds a link is the remaining route of h with its own blocking
(the recursion), the flits of h, and, at the ejection port of its target, the
receive handlers: the DDMA of the target withholds the credit of the size flit
until the handler assigns the buffer (rx_size) and lets the next packet in
only after the end-of-reception handshake (rx_end).

Cycles, with the constants of router.py (t_r = 6 per router, w_h per router,
p flits from getPacketFlits, inject, rx_size and rx_end of the network-
interface model):

    hold(h, j) = sum_{k = j}^{m_h} (t_r + w_h + W(h, k)) + p_h + 1 + rx_size + rx_end
    W(q, k)    = sum over the input ports i != in(q, k) of router k of
                 max over the packets h from i to out(q, k) of hold(h, index of out(q, k) on h)
    src(q)     = sum over the other packets h of the source PE of q of
                 (inject + sum_{k = 0}^{m_h} (t_r + w_h + W(h, k)) + p_h + 1)
    WCTT(q)    = inject + src(q) + sum_{k = 0}^{m_q} (t_r + w_h + W(q, k)) + p_q + 1 + rx_size + rx_end

where the route of q has the links l_0 (local port of the source), l_1 to
l_m between routers and l_{m+1} (local port of the target), and router k
(k = 0..m) takes l_k in and l_{k+1} out. XY routing keeps the channel
dependency graph acyclic, so the recursion ends. Without contention,
WCTT(q) = L0 + w_h (m + 1) + inject + rx_size + rx_end, the occupancy o_i of
the link schedule (with w_NI = NI_WAIT_CYCLES).
"""
from functools import lru_cache

from rttools.modules.routing import router


def _links(packet):
    return [p["data"]["label"] for p in packet["path"]]


def wctt(packets, wait=None, ni=None):
    """{packet name: WCTT in cycles} of `packets` (flowUnwrapper.unwrap: one
    phase of a single-period application). `wait` and `ni` select w_h and
    the network-interface terms as router.occupancy does; ni "off" drops the
    three handler terms."""
    w_h = router.header_wait() if wait is None else router.parse_header_wait(wait)
    resource, w_ni = router.ni_model() if ni is None else router.parse_ni(ni)
    if w_ni:
        inj, rxs, rxe = router.NI_INJECT_CYCLES, router.NI_RX_SIZE_CYCLES, router.NI_RX_END_CYCLES
        scale = w_ni / router.NI_WAIT_CYCLES
        inj, rxs, rxe = inj * scale, rxs * scale, rxe * scale
    else:
        inj = rxs = rxe = 0
    t_r = router.getRoutingTime()
    pk = [p for p in packets if len(p["path"]) >= 2]
    links = [_links(p) for p in pk]
    flits = [router.getPacketFlits(p["datasize"]) for p in pk]
    users = {}
    for i, ls in enumerate(links):
        for j, l in enumerate(ls):
            users.setdefault(l, []).append((i, j))

    @lru_cache(maxsize=None)
    def W(q, k):
        """Blocking of q at router k (output l_{k+1}, input l_k)."""
        out_l, in_l = links[q][k + 1], links[q][k]
        per_port = {}
        for h, j in users.get(out_l, []):
            if h == q or j == 0:
                continue
            port = links[h][j - 1]
            if port == in_l:
                continue
            per_port[port] = max(per_port.get(port, 0), hold(h, j))
        return sum(per_port.values())

    @lru_cache(maxsize=None)
    def route(h, j):
        """sum_{k = j - 1}^{m_h} (t_r + w_h + W(h, k)) for the output link j."""
        m = len(links[h]) - 2
        return sum(t_r + w_h + W(h, k) for k in range(j - 1, m + 1))

    @lru_cache(maxsize=None)
    def hold(h, j):
        return route(h, j + 1) + flits[h] + 1 + rxs + rxe if j < len(links[h]) - 1 else flits[h] + 1 + rxs + rxe

    out = {}
    for q, p in enumerate(pk):
        src_l = links[q][0]
        src = sum(inj + route(h, 1) + flits[h] + 1 for h, j in users.get(src_l, []) if h != q and j == 0)
        out[p["name"]] = inj + src + route(q, 1) + flits[q] + 1 + rxs + rxe
    return out
