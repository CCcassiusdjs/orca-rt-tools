"""rttools.wcet.cfg (blocks, dominators, natural loops) and rttools.wcet.ipet."""
import os

import pytest

from rttools.wcet import cfg, image, ipet
from tests.conftest import REPO_ROOT

LISTING = os.path.join(REPO_ROOT, "experiments", "exp23", "logs", "H.image.lst")


def test_loops_of_a_small_graph():
    # 0 -> 1 -> 2 -> 1 (inner), 2 -> 3 -> 0? no: 3 -> 1 (outer), 3 -> 4
    succ = {0: [1], 1: [2], 2: [1, 3], 3: [1, 4], 4: []}
    lps = cfg.loops(succ, 0)
    assert len(lps) == 1                      # same header: one loop
    lp = lps[0]
    assert lp.header == 1 and lp.body == {1, 2, 3}
    assert sorted(lp.back_edges) == [(2, 1), (3, 1)] and lp.entries == [(0, 1)]
    succ = {0: [1], 1: [2], 2: [2, 3], 3: [1, 4], 4: []}
    lps = cfg.loops(succ, 0)
    inner = next(x for x in lps if x.header == 2)
    outer = next(x for x in lps if x.header == 1)
    assert inner.parent is outer and inner.body == {2}


def test_irreducible_flow_is_an_error():
    succ = {0: [1, 2], 1: [2], 2: [1, 3], 3: []}
    with pytest.raises(cfg.CFGError, match="irreducible"):
        cfg.loops(succ, 0)


def test_cfg_of_ucx_sleep():
    img = image.load(LISTING)
    g = cfg.build(img, "ucx_sleep")
    terms = sorted(b.term for b in g.blocks.values())
    assert "call" in terms and "return" in terms
    lps = cfg.loops(g.succ_map(), g.entry)
    assert sorted(lp.header for lp in lps) == [0x400023b8, 0x400023c4]


def test_indirect_jump_without_targets_is_an_error():
    img = image.load(LISTING)
    with pytest.raises(cfg.CFGError, match="indirect jump"):
        cfg.build(img, "irq0_handler")       # jump table: a listing has no .rodata


def test_ipet_loop_bound_and_branch_costs():
    # S -> h; h -> b (taken, 3) or h -> x (fall, 1); b -> h (back edge); x -> T
    p = ipet.Problem(node_cost={"h": 2, "b": 10, "x": 1})
    s = p.add_edge("S", "h")
    p.sources[s] = 1
    e_hb = p.add_edge("h", "b", 3)
    e_bh = p.add_edge("b", "h")
    p.add_edge("h", "x", 1)
    p.add_edge("x", "T")
    p.loops.append(([s, e_bh], [s], 5))       # the header runs at most 5 times
    sol = ipet.solve(p)
    # 5 header executions: 4 passes through b (3 + 10 + 2 each), entry 2, exit 1 + 1
    assert sol.cycles == 2 + 4 * (3 + 10 + 2) + 1 + 1
    assert sol.edge_counts[e_hb] == 4


def test_ipet_without_bound_is_unbounded():
    p = ipet.Problem(node_cost={"h": 1, "b": 1})
    s = p.add_edge("S", "h")
    p.sources[s] = 1
    p.add_edge("h", "b")
    p.add_edge("b", "h")
    p.add_edge("h", "T")
    with pytest.raises(ipet.IPETError, match="unbounded"):
        ipet.solve(p)
