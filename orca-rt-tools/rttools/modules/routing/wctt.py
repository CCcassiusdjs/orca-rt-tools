"""Worst-case traversal time (WCTT) of the packets of one phase under
event-triggered injection, for the baseline of experiments/ablation: the
recursive calculus of wormhole networks (Ferrandiz, Frances and Fraboul,
SIES 2009) with the arbitration of the Hermes router and the DDMA of the
ORCA2 PE.

Under event-triggered injection, the DDMA of a PE takes a packet when its job
sends it, so the packets of a phase can meet on any link.

| Property of the platform | Source | Term of the bound |
|---|---|---|
| One control unit per router polls the five input ports (states S1 to S3 and prox of Hermes_switchcontrol.vhd): when the requested output is busy it polls the next requesting port, so one input port can win the same output several times before a waiting header of another port | pkt-sim/hw/router/hermes/Hermes_switchcontrol.vhd | W(q, k) sums hold over every packet of every other input port that takes the output of q at router k (each packet of the phase passes each router once), plus the service of the four other ports by the control unit (4 x 5 cycles) per packet |
| A packet holds each link of its route until its tail passes; under back pressure the tail waits for the blocking of the packet further on its route | Hermes buffers of 8 flits per input port | hold(h, j): remaining route of h with its own blocking (the recursion of the calculus) |
| The DDMA of the target withholds the credit of the size flit until irq2_handler assigns a buffer (rx_size) and lets the next packet in after the end-of-reception handshake (rx_end) | pkt-sim/hw/ddma/ddma.sv, lib/noc.c | rx_size + rx_end in hold and in WCTT; rx_size of each earlier packet of the source PE in src(q), whose DDMA keeps the packet until the size flit passes |
| The DDMA shares one memory port between send and receive and switches the token every G = 10 cycles (INTERLEAVING_GRAIN of manycore_top.sv) with one cycle per switch | pkt-sim/hw/ddma/ddma.sv | a packet whose source PE receives or whose target PE sends another packet of the phase moves its p payload flits in kappa(p) = ceil(p / G) (2 G + 2) cycles, otherwise p |

Cycles, with the constants of router.py (t_r = 6 per router, w_h per router,
control unit 4 x 5 = 20 per blocking packet, p flits from getPacketFlits, inject,
rx_size and rx_end of the network-interface model):

    hold(h, j) = sum_{k = j}^{m_h} (t_r + w_h + W(h, k)) + kappa_h + 1 + rx_size + rx_end
    W(q, k)    = sum over the packets h != q of the interference set of q that take out(q, k)
                 from an input port other than in(q, k) of (hold(h, index of out(q, k) on h) + 20)
    src(q)     = sum over the other packets h of the source PE of q of
                 (inject + sum_{k = 0}^{m_h} (t_r + w_h + W(h, k)) + kappa_h + 1 + rx_size)
    WCTT(q)    = inject + src(q) + sum_{k = 0}^{m_q} (t_r + w_h + W(q, k)) + kappa_q + 1 + rx_size + rx_end

where the route of q has the links l_0 (local port of the source), l_1 to
l_m between routers and l_{m+1} (local port of the target), and router k
(k = 0..m) takes l_k in and l_{k+1} out. XY routing keeps the channel
dependency graph acyclic, so the recursion ends. Without contention,
WCTT(q) = L0 + w_h (m + 1) + inject + rx_size + rx_end, the occupancy o_i of
the link schedule (with w_NI = NI_WAIT_CYCLES).

Interference set. Packet i is sent between its earliest release e_i and its
release r_i = F(u) (min_start) and leaves the NoC by r_i + WCTT_i. Without
a lower bound on the execution times, e_i is the start of the phase of the
sending job, and the bound holds when every packet leaves the NoC within the
phase of its release (event_triggered_at checks r_i + WCTT_i <= end of that
phase), so the interference set of q is every other packet of its phase.
With `earliest` (offset-aware variant: e_i from a lower bound of the
execution times), h interferes with q only when [e_h, r_h + WCTT_h] meets
[e_q, r_q + WCTT_q]; as in holistic analysis, the bound starts from the
windows without contention and adds the packets whose windows meet until the
sets stay (least fixed point: at the first instant at which a packet would
exceed its bound, every packet has stayed within its window, so every packet
that meets it is in its set).
"""
import math

from rttools.modules.routing import router

# per blocking packet: after it frees the output, the control unit can serve the headers of the four
# other ports (5 cycles each) before it polls the port of the waiting packet again
HEADER_SERVICE = router.HEADER_SERVICE_CYCLES * router.MAX_COMPETING_HEADERS
INTERLEAVING_GRAIN = 10


def _links(packet):
    return [p["data"]["label"] for p in packet["path"]]


def interleaved(p, grain=INTERLEAVING_GRAIN):
    """Cycles of p payload flits through a DDMA that alternates its memory
    token between send and receive every `grain` cycles."""
    return math.ceil(p / grain) * (2 * grain + 2)


def phase_of(packet, period):
    return packet["min_start"] // period


def wctt(packets, period=None, wait=None, ni=None, earliest=None, details=False, arbitration="polling"):
    """{packet name: WCTT in cycles} of `packets` (flowUnwrapper.unwrap: one
    hyperperiod of a single-period application or of a composition).
    `period`: cycles of a phase (None: one phase holds every packet).
    `wait` and `ni` select w_h and the network-interface terms as
    router.occupancy does. `earliest`: {packet name: earliest release in
    cycles} for the offset-aware variant. details=True also returns the
    interference set of each packet. arbitration "round_robin": the rule of
    the calculus for one round-robin arbiter per output (at most one packet
    per other input port, the largest hold), which the Hermes control unit
    does not implement (experiments/zll, make polling)."""
    w_h = router.header_wait() if wait is None else router.parse_header_wait(wait)
    resource, w_ni = router.ni_model() if ni is None else router.parse_ni(ni)
    if w_ni:
        scale = w_ni / router.NI_WAIT_CYCLES
        inj, rxs, rxe = (router.NI_INJECT_CYCLES * scale, router.NI_RX_SIZE_CYCLES * scale,
                         router.NI_RX_END_CYCLES * scale)
    else:
        inj = rxs = rxe = 0
    t_r = router.getRoutingTime()
    pk = [p for p in packets if len(p["path"]) >= 2]
    n = len(pk)
    links = [_links(p) for p in pk]
    flits = [p["flits"] if "flits" in p else router.getPacketFlits(p["datasize"]) for p in pk]
    phase = [0 if period is None else phase_of(p, period) for p in pk]
    src_pe = [ls[0].split("-")[-1] for ls in links]     # local link "L-<node>"
    dst_pe = [ls[-1].split("-")[0] for ls in links]     # local link "<node>-L"
    sets = [frozenset(h for h in range(n) if h != q and phase[h] == phase[q]) for q in range(n)]

    def solve(sets):
        def kappa(h, others):
            # the source PE of h receives, or its target PE sends, another packet that can meet h
            busy = any(dst_pe[g] == src_pe[h] or src_pe[g] == dst_pe[h] for g in others)
            return interleaved(flits[h]) if busy else flits[h]
        kap = [kappa(h, sets[h]) for h in range(n)]
        users = {}
        for i, ls in enumerate(links):
            for j, l in enumerate(ls):
                users.setdefault(l, []).append((i, j))
        memo_w, memo_r, memo_h = {}, {}, {}

        def W(q, k):
            key = (q, k)
            if key not in memo_w:
                out_l, in_l = links[q][k + 1], links[q][k]
                per_port = {}
                for h, j in users.get(out_l, []):
                    if h == q or j == 0 or h not in sets[q] or links[h][j - 1] == in_l:
                        continue
                    c = hold(h, j) + HEADER_SERVICE
                    port = links[h][j - 1]
                    per_port[port] = (per_port.get(port, 0) + c if arbitration == "polling"
                                      else max(per_port.get(port, 0), c))
                memo_w[key] = sum(per_port.values())
            return memo_w[key]

        def route(h, j):
            key = (h, j)
            if key not in memo_r:
                m = len(links[h]) - 2
                memo_r[key] = sum(t_r + w_h + W(h, k) for k in range(j - 1, m + 1))
            return memo_r[key]

        def hold(h, j):
            key = (h, j)
            if key not in memo_h:
                tail = kap[h] + 1 + rxs + rxe
                memo_h[key] = route(h, j + 1) + tail if j < len(links[h]) - 1 else tail
            return memo_h[key]

        out = []
        for q in range(n):
            src = sum(inj + route(h, 1) + kap[h] + 1 + rxs for h, j in users.get(links[q][0], [])
                      if h != q and j == 0 and h in sets[q])
            out.append(inj + src + route(q, 1) + kap[q] + 1 + rxs + rxe)
        return out

    if earliest is None:
        bound = solve(sets)
    else:
        # least fixed point: from the windows without contention, add the packets whose windows meet
        full, sets = sets, [frozenset()] * n
        bound = solve(sets)
        while True:
            win = [(earliest[pk[i]["name"]], pk[i]["min_start"] + bound[i]) for i in range(n)]
            new = [sets[q] | frozenset(h for h in full[q] if win[h][0] <= win[q][1] and win[q][0] <= win[h][1])
                   for q in range(n)]
            if new == sets:
                break
            sets = new
            bound = solve(sets)
    out = {p["name"]: bound[i] for i, p in enumerate(pk)}
    if details:
        return out, {p["name"]: sorted(pk[h]["name"] for h in sets[i]) for i, p in enumerate(pk)}
    return out
