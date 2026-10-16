"""Implicit path enumeration (IPET; Li and Malik, 1995) as an integer
linear program solved by scipy.optimize.milp (HiGHS).

The program has one variable x_e >= 0 per edge e = (u, v) of a graph with a
source "S" and a sink "T". The count of node v is the flow into v. With
c_v the cycles of node v and c_e the cycles of edge e (the taken or
not-taken cost of a branch), the WCET is

    max  sum_e (c_e + c_v) x_e      (v = target of e; c_T = 0)
    s.t. x_(S, entry) = 1 (or the given source flows)
         sum_(u, v) x_(u,v) = sum_(v, w) x_(v,w)        for every node v
         sum_(u, h) x_(u,h) <= N_L sum_(p, h), p not in L  x_(p,h)
                                                         for every loop L (header h, bound N_L;
                                                         a bound per call of the function takes
                                                         the entry edges of the function instead)
         x_e = 0                                         for the edges that cannot run
         extra linear constraints (cut counts, call counts)

The solution gives the counts of the worst-case path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


class IPETError(ValueError):
    pass


@dataclass
class Problem:
    node_cost: dict = field(default_factory=dict)     # node -> cycles
    edges: list = field(default_factory=list)          # (u, v, cycles)
    zero_edges: set = field(default_factory=set)       # indices of edges fixed at 0
    sources: dict = field(default_factory=dict)        # (S, v) edge index -> flow
    # (in-edge idx list of the header, reference idx list, bound):
    # sum of the in-edges <= bound x sum of the reference edges (the entry
    # edges of the loop, or the entry edges of the function for a bound
    # per call)
    loops: list = field(default_factory=list)
    extra: list = field(default_factory=list)          # ({edge idx: coef}, upper bound)

    def add_edge(self, u, v, cost=0):
        self.edges.append((u, v, cost))
        return len(self.edges) - 1


@dataclass
class Solution:
    cycles: int
    edge_counts: list
    node_counts: dict


def solve(p):
    try:
        from scipy.optimize import LinearConstraint, milp, Bounds
        from scipy.sparse import lil_matrix
    except ImportError as e:  # pragma: no cover
        raise IPETError("the IPET solver needs scipy (requirements.txt)") from e
    n = len(p.edges)
    if n == 0:
        raise IPETError("empty problem")
    c = np.zeros(n)
    into = {}
    out = {}
    for i, (u, v, ce) in enumerate(p.edges):
        c[i] = -(ce + (p.node_cost.get(v, 0) if v != "T" else 0))
        into.setdefault(v, []).append(i)
        out.setdefault(u, []).append(i)
    rows = []
    lo, hi = [], []
    nodes = [v for v in set(into) | set(out) if v not in ("S", "T")]
    for v in nodes:
        r = {}
        for i in into.get(v, ()):
            r[i] = r.get(i, 0) + 1
        for i in out.get(v, ()):
            r[i] = r.get(i, 0) - 1
        rows.append(r)
        lo.append(0)
        hi.append(0)
    for i, f in p.sources.items():
        rows.append({i: 1})
        lo.append(f)
        hi.append(f)
    for ins, refs, bound in p.loops:
        r = {}
        for i in ins:
            r[i] = r.get(i, 0) + 1
        for i in refs:
            r[i] = r.get(i, 0) - bound
        rows.append(r)
        lo.append(-np.inf)
        hi.append(0)
    for coefs, ub in p.extra:
        rows.append(dict(coefs))
        lo.append(-np.inf)
        hi.append(ub)
    A = lil_matrix((len(rows), n))
    for k, r in enumerate(rows):
        for i, v in r.items():
            A[k, i] = v
    ub = np.full(n, np.inf)
    for i in p.zero_edges:
        ub[i] = 0
    res = milp(c, constraints=LinearConstraint(A.tocsr(), np.array(lo), np.array(hi)),
               integrality=np.ones(n), bounds=Bounds(np.zeros(n), ub))
    if res.status == 3 or (res.status != 0 and "unbounded" in str(res.message).lower()):
        raise IPETError("unbounded path (a loop without a bound): " + str(res.message))
    if res.status == 2 or res.x is None:
        raise IPETError("no feasible path: " + str(res.message))
    if res.status != 0:
        raise IPETError("solver: " + str(res.message))
    x = [int(round(v)) for v in res.x]
    counts = {}
    for i, (u, v, _) in enumerate(p.edges):
        counts[v] = counts.get(v, 0) + x[i]
    total = int(round(-res.fun))
    return Solution(total, x, counts)
