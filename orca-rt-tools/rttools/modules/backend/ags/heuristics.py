"""Criteria of the AGS (Sec. 6.3.4 of the thesis; ICECS 2022).

Each criterion takes the problem (tables link x packet min_start,
occupancy and deadline, list of packets, hyperperiod) and returns the
packet indices in allocation order: the first index is allocated first.
Ties keep the order of the packets in the problem.

Quantities per packet i:
  o_i   occupancy of each link of the path (cycles), the size of the
        packet in the unit of the period (the thesis uses "size" with
        the period in Eq. 6.2, so both are in cycles);
  T_i   period of the flow of i, in cycles: the "period" key of the packet
        when present, otherwise HP / n_f, with n_f the number of packets
        of the flow of i in the hyperperiod HP (the flow unwrapper emits
        one packet per period, so n_f = HP / T_i). The flow of a packet is
        its "flow" key, or the name before ":" ("f10:3" is packet 3 of
        flow f10); a packet without either is the only packet of its
        flow (T_i = HP).
"""


def _flow(pkt):
    if isinstance(pkt, dict):
        if "flow" in pkt:
            return pkt["flow"]
        name = pkt.get("name", "")
    else:
        name = str(pkt)
    return name.split(":")[0] if ":" in name else None


def _occupancy(problem):
    occ = problem["occupancy"]
    n = len(occ[0]) if occ else 0
    out = [0] * n
    for j in range(n):
        for row in occ:
            if row[j] is not None:
                out[j] = row[j]
                break
    return out


def _periods(problem):
    pkts = problem["packets"]
    hp = problem["hyperperiod"]
    count = {}
    for k in pkts:
        f = _flow(k)
        if f is not None:
            count[f] = count.get(f, 0) + 1
    out = []
    for k in pkts:
        if isinstance(k, dict) and "period" in k:
            out.append(k["period"])
            continue
        f = _flow(k)
        out.append(hp if f is None else hp / count[f])
    return out


def lstf(problem):
    """Least Slack-Time First, Eq. 6.2: LSTF(i) = T_i - o_i, smallest
    first (packets with fewer alternatives first)."""
    o = _occupancy(problem)
    t = _periods(problem)
    return sorted(range(len(o)), key=lambda i: t[i] - o[i])


def mbcf(problem):
    """Most Bandwidth Consuming First, Eq. 6.3: MBCF(i) = o_i * HP / T_i,
    largest first."""
    o = _occupancy(problem)
    t = _periods(problem)
    hp = problem["hyperperiod"]
    return sorted(range(len(o)), key=lambda i: -(o[i] * hp / t[i]))


def mcpf(problem):
    """Most Critical Path First (Sec. 6.3.4, no equation in the thesis):
    the usage of link l is the time it is occupied in the hyperperiod,
    u(l) = sum of o_k over the packets k that use l; the score of packet i
    is the sum of u(l) over the links of its path. Largest score (path
    through the most used links) first."""
    occ = problem["occupancy"]
    n = len(occ[0]) if occ else 0
    usage = [sum(v for v in row if v is not None) for row in occ]
    score = [0] * n
    for l, row in enumerate(occ):
        for j in range(n):
            if row[j] is not None:
                score[j] += usage[l]
    return sorted(range(n), key=lambda i: -score[i])
