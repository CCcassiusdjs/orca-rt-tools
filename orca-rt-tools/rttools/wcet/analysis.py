"""Static WCET of functions, code segments and task jobs.

| Query | Result |
|---|---|
| Analyzer.function(f, args) | WCET of one call of f with the known argument values `args` (the context): IPET over the blocks of f, each call charged with the WCET of the callee in the context of its arguments (bottom-up over the call graph, which must have no cycle) |
| Analyzer.function(f, start=a, init=...) | WCET of the segment of f from the block at address a (the return address of a call) to the return, with the registers of `init` (the resume path after setjmp, for instance) |
| Analyzer.job(f, cut) | WCET of one job of the task function f: the paths from the return of a call to a function of `cut` (the kernel entry of the task, ucx_task_yield) to the next such call |

Env sets query options that change the paths of the kernel code:
`returns` (a callee returns a fixed value: setjmp returns 0 on the path
that saves a context), `noreturn` (a call ends the path: longjmp), extra
`exclude` calls, `icalls` (targets of the indirect calls of a function, as
the interrupt handler that serves one cause), `overrides` (fixed cycles of
a function, composed by the caller of the query) and `params` of the
bound expressions.

Job analysis. A task function runs `do { wait for the inputs; work; send }
while (...)` and blocks in calls to the cut function. The supergraph of
the task inlines every function that reaches a cut call (receive helpers,
run_task of the generated applications); every other call is a summary
(the WCET of the callee in the context of its arguments). The job starts
at the return point of any cut call (source) and ends at a cut call
(sink): one dispatch of the task. A cut call costs its call instruction
only; the kernel path behind it is the dispatch term of the caller
(rttools.wcet.ucx). The loops are the natural loops of the supergraph
from the entry of the task function; a job that starts inside a loop
counts as one entry into it. `limits` bound the calls of given functions
per job (the iteration markers and the receives of one iteration,
rttools.wcet.ucx); a loop needs no bound of its own when every cycle of
it in the job passes such a call, or when the cut calls break its
cycles (the wait loop of a receive).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rttools.wcet import cfg as cfgmod
from rttools.wcet import ipet, loopbound, timing
from rttools.wcet.annotations import Annotations
from rttools.wcet.decode import RA, REG
from rttools.wcet.value import Values, entry_state, join


class WcetError(ValueError):
    pass


@dataclass(frozen=True)
class Env:
    returns: tuple = ()      # ((function, a0), ...)
    noreturn: frozenset = frozenset()
    exclude: frozenset = frozenset()
    icalls: tuple = ()       # ((function, (target, ...), max_count), ...)
    overrides: tuple = ()    # ((function, cycles), ...)
    params: tuple = ()       # ((name, value), ...)

    def with_(self, **kw):
        d = dict(returns=self.returns, noreturn=self.noreturn, exclude=self.exclude, icalls=self.icalls,
                 overrides=self.overrides, params=self.params)
        for k, v in kw.items():
            if k in ("returns", "icalls", "overrides", "params") and isinstance(v, dict):
                v = tuple(sorted(v.items())) if k != "icalls" else tuple(
                    sorted((f, tuple(t), m) for f, (t, m) in v.items()))
            if k in ("noreturn", "exclude"):
                v = frozenset(v)
            d[k] = v
        return Env(**d)


ENV0 = Env()


@dataclass
class CallSite:
    block: int
    addr: int
    callee: str
    args: dict
    cycles: int          # per call, including the call instruction
    count: int = 0
    category: str = "body"


@dataclass
class Result:
    name: str
    cycles: int
    args: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)       # CallSite with counts of the worst-case path
    loops: list = field(default_factory=list)       # (function, header, bound, source)
    counts: dict = field(default_factory=dict)      # node -> count
    categories: dict = field(default_factory=dict)  # category -> cycles on the worst-case path


class Analyzer:
    def __init__(self, img, annotations=None, model=None, params=None):
        self.img = img
        self.ann = (annotations or Annotations()).canonical(img)
        self.model = model or timing.CYCLES
        self.params = dict(self.ann.params)
        self.params.update(params or {})
        self._cfg = {}
        self._memo = {}
        self._stack = []
        self._reach = {}

    # ------------------------------------------------------------ helpers
    def _icall_spec(self, fname, env):
        for f, targets, m in env.icalls:
            if f == fname:
                return [{"at": "all", "targets": list(targets), "max_count": m}]
        return self.ann.indirect_calls(fname)

    def _max_count(self, fname, env, blk):
        """max_count of the indirect-call annotation of a call block."""
        if blk.call_targets is None:
            return None
        m = None
        for c in self._icall_spec(fname, env):
            if c.get("at", "all") == "all" or self.img.address(c["at"], fname) == blk.last.addr:
                m = c.get("max_count")
        return m

    def _indirect(self, fname, env):
        img = self.img
        func = img.function(fname)
        specs = {}
        jumps = self.ann.indirect_jumps(fname)
        calls = self._icall_spec(fname, env)
        for a in range(func.start, func.end, 4):
            try:
                ins = img.instr(a)
            except Exception:
                continue
            if ins.kind != "jalr" or ins.is_return:
                continue
            if ins.rd == RA:
                for c in calls:
                    if c.get("at", "all") == "all" or img.address(c["at"], fname) == a:
                        specs[a] = {"targets": [img.address(t) for t in c["targets"]],
                                    "max_count": c.get("max_count")}
            elif ins.rd == 0:
                match = [j for j in jumps if j.get("at", "all") == "all" or img.address(j["at"], fname) == a]
                for j in match[-1:]:
                    if j.get("return"):
                        specs[a] = {"return": True}
                    elif "targets" in j:
                        specs[a] = {"targets": [img.address(t, fname) for t in j["targets"]],
                                    "edge_max": {img.address(t, fname): m for t, m in j.get("max", {}).items()}}
                    elif "indices" in j:
                        tbl = cfgmod.jump_table(img, func, ins)
                        if tbl is None:
                            raise WcetError(f"{fname}: no jump table at {a:08x} for the annotation `indices` "
                                            f"(a listing has no .rodata; give `targets`)")
                        specs[a] = {"targets": [tbl[i] for i in j["indices"]],
                                    "edge_max": {tbl[int(i)]: m for i, m in j.get("max", {}).items()}}
        return specs

    def cfg(self, fname, env=ENV0):
        key = (fname, tuple(x for x in env.icalls if x[0] == fname))
        if key not in self._cfg:
            try:
                self._cfg[key] = cfgmod.build(self.img, fname, self._indirect(fname, env))
            except cfgmod.CFGError as e:
                raise WcetError(str(e)) from None
        return self._cfg[key]

    def _excluded(self, env):
        return self.ann.exclude | set(env.exclude)

    def _params(self, env):
        p = dict(self.params)
        p.update(dict(env.params))
        return p

    def _callees(self, blk):
        if blk.call_targets:
            return list(blk.call_targets)
        return [blk.callee] if blk.callee else []

    def _evaluate(self, expr, args, env):
        if isinstance(expr, int):
            return expr
        p = self._params(env)
        text = str(expr)
        for k in sorted(p, key=len, reverse=True):
            text = text.replace(k, str(int(p[k])))
        try:
            return loopbound.evaluate(text, args, self.img.read)
        except ValueError as e:
            raise WcetError(str(e)) from None

    # ------------------------------------------------------------ loops
    def _selects(self, sel, fname, loop, all_loops, blocks):
        if sel == "all":
            return True
        if isinstance(sel, dict):
            if "header" in sel:
                return self.img.address(sel["header"], fname) == loop.header
            if "contains_call" in sel:
                g = sel["contains_call"]

                def has(body):
                    return any(g in self._callees(blocks[b]) for b in body if b in blocks
                               and blocks[b].term in ("call", "tailcall"))
                if not has(loop.body):
                    return False
                inner = [lp for lp in all_loops if lp is not loop and lp.body < loop.body]
                return not any(has(lp.body) for lp in inner)
            if "index" in sel:
                hs = sorted(lp.header for lp in all_loops)
                k = sel["index"]
                return -len(hs) <= k < len(hs) and hs[k] == loop.header
        raise WcetError(f"{fname}: unknown loop selector {sel!r}")

    def loop_bound(self, fname, args, env, cfg, loop, all_loops, dom, values, use_rest=True):
        """[(bound, scope, source)] of a loop of function `fname` (the
        smallest bound of each scope), or None; the annotation with the
        selector "rest" applies when `use_rest` and no other bound
        exists."""
        cands = []
        chosen = None
        rest = None
        for spec in self.ann.loops(fname):
            sel = spec.get("select", "all")
            if sel == "rest":
                rest = spec
            elif self._selects(sel, fname, loop, all_loops, cfg.blocks):
                chosen = spec
        if chosen is not None:
            cands.append((self._evaluate(chosen["bound"], args, env), chosen.get("scope", "loop"), "annotation"))
        # bounds of the source (.wcet_bounds): the innermost loop that holds the address
        for addr, n in self.img.bounds:
            blk = cfg.block_of(addr)
            if blk is None or blk.start not in loop.body:
                continue
            inner = [lp for lp in all_loops if lp is not loop and lp.body < loop.body and blk.start in lp.body]
            if not inner:
                # bit 31: WCET_LOOP_TOTAL (per call of the function)
                cands.append((n & 0x7FFFFFFF, "function" if n & 0x80000000 else "loop", "source"))
        inner_bodies = [lp.body for lp in all_loops if lp is not loop and lp.body < loop.body]
        est = None
        for p, _h in loop.entries:
            if p in values.inp:
                est = join(est, values.out(p))
        n = loopbound.counted(cfg.blocks, loop, inner_bodies, dom, values, est)
        if n is not None:
            cands.append((n, "loop", "counted"))
        if not cands and rest is not None and use_rest:
            cands.append((self._evaluate(rest["bound"], args, env), rest.get("scope", "loop"), "annotation"))
        if not cands:
            return None
        # every candidate is an upper bound: the smallest of each scope
        out = []
        for scope in ("loop", "function"):
            c = [x for x in cands if x[1] == scope]
            if c:
                out.append(min(c))
        return out

    # ------------------------------------------------------------ costs
    def _own_cost(self, blk):
        c = 0
        for ins in blk.instrs:
            if ins.kind == "branch" and ins is blk.last:
                continue
            c += timing.cost(ins, self.model)
        return c

    def _edge_cost(self, blk, succ_kind):
        if blk.term != "branch":
            return 0
        taken, fall = timing.branch_costs(self.model)
        return taken if succ_kind == "taken" else fall

    def _call_cost(self, fname, blk, values, env):
        """(cycles of the callee per call, [(callee, args)]) of a call or
        tail-call block (the call instruction is in the block cost)."""
        args = values.call_args(blk.start)
        best = 0
        sites = []
        over = dict(env.overrides)
        for g in self._callees(blk):
            if g in over:
                c = over[g]
            else:
                c = self.function(g, args, env).cycles
            sites.append((g, args, c))
            best = max(best, c)
        return best, sites

    # ------------------------------------------------------------ function
    def function(self, fname, args=None, env=ENV0, start=None, init=None):
        args = {r: v for r, v in (args or {}).items() if isinstance(v, int)}
        key = (fname, tuple(sorted(args.items())), env, start,
               None if init is None else tuple(sorted(init.items())))
        if key in self._memo:
            return self._memo[key]
        if fname in dict(env.overrides) and start is None:
            r = Result(fname, dict(env.overrides)[fname], args)
            self._memo[key] = r
            return r
        if fname in self._stack:
            raise WcetError("recursion: " + " -> ".join(self._stack + [fname]))
        self._stack.append(fname)
        try:
            r = self._function(fname, args, env, start, init)
        finally:
            self._stack.pop()
        self._memo[key] = r
        return r

    def _function(self, fname, args, env, start, init):
        cfg = self.cfg(fname, env)
        st = entry_state(args, self.img.gp)
        for k, v in (init or {}).items():
            st.set(REG[k] if isinstance(k, str) else k, v)
        s0 = cfg.entry if start is None else start
        if s0 not in cfg.blocks:
            raise WcetError(f"{fname}: segment start {s0:08x} is not a block")
        values = Values(cfg, st, self.img, dict(env.returns), start=s0)
        excl = self._excluded(env)
        blocks = cfg.blocks
        live = set(values.inp)
        zero = {b for b in live if blocks[b].term in ("call", "tailcall")
                and any(g in excl for g in self._callees(blocks[b]))}
        succ = {b: [s for s, _ in blocks[b].succs if (b, s) not in values.dead_edges and b not in zero]
                for b in live}
        try:
            all_loops = cfgmod.loops(succ, s0)
        except cfgmod.CFGError as e:
            raise WcetError(f"{fname}: {e}") from None
        dom = cfgmod.dominators(succ, s0)
        reach = set(dom)
        p = ipet.Problem()
        call_sites = {}
        for b in reach:
            blk = blocks[b]
            c = self._own_cost(blk)
            if blk.term in ("call", "tailcall") and b not in zero:
                cc, sites = self._call_cost(fname, blk, values, env)
                c += cc
                call_sites[b] = (cc, sites)
            p.node_cost[b] = c
        src = p.add_edge("S", s0)
        p.sources[src] = 1
        into = {}
        for b in reach:
            blk = blocks[b]
            exits = blk.term in ("return", "tailcall") or (
                blk.term == "call" and any(g in env.noreturn for g in self._callees(blk)))
            if b in zero:
                continue
            if exits:
                p.add_edge(b, "T")
                continue
            for s, kind in blk.succs:
                if s not in reach:
                    continue
                i = p.add_edge(b, s, self._edge_cost(blk, kind))
                into.setdefault(s, []).append(i)
                if (b, s) in values.dead_edges:
                    p.zero_edges.add(i)
        into.setdefault(s0, []).append(src)
        for i, (u, v, _) in enumerate(p.edges):
            if v in zero:
                p.zero_edges.add(i)
        loop_info = []
        for lp in all_loops:
            res = self.loop_bound(fname, args, env, cfg, lp, all_loops, dom, values)
            if res is None:
                raise WcetError(f"{fname}: loop at {lp.header:08x} has no bound (annotation `loops` of {fname}, "
                                f"WCET_LOOP_BOUND in the source, or a counted loop)")
            ins = [i for i in into.get(lp.header, [])]
            for n, scope, source in res:
                if scope == "function":
                    refs = [src]
                else:
                    refs = [i for i in ins if p.edges[i][0] not in lp.body]
                p.loops.append((ins, refs, n))
                loop_info.append((fname, lp.header, n, source))
        for b in reach:
            for t, m in blocks[b].edge_max.items():
                idx = [i for i, (u, v, _) in enumerate(p.edges) if u == b and v == t]
                if idx:
                    p.extra.append(({i: 1 for i in idx}, m))
        for b in call_sites:
            m = self._max_count(fname, env, blocks[b])
            if m is not None:
                p.extra.append(({i: 1 for i in into.get(b, [])}, m))
        try:
            sol = ipet.solve(p)
        except ipet.IPETError as e:
            raise WcetError(f"{fname}: {e}") from None
        counts = sol.node_counts
        calls = []
        for b, (cc, sites) in call_sites.items():
            n = counts.get(b, 0)
            for g, a, c in sites:
                calls.append(CallSite(b, blocks[b].last.addr, g, a, c + timing.cost(blocks[b].last, self.model), n))
        return Result(fname, sol.cycles, args, calls, loop_info, counts)

    # ------------------------------------------------------------ job
    def reaches(self, fname, cut, env=ENV0):
        """True when a call path from `fname` reaches a function of `cut`."""
        key = (fname, frozenset(cut))
        if key in self._reach:
            return self._reach[key]
        self._reach[key] = False
        cfg = self.cfg(fname, env)
        out = False
        for blk in cfg.blocks.values():
            for g in self._callees(blk) if blk.term in ("call", "tailcall") else ():
                if g in cut or (g not in self._excluded(env) and self.reaches(g, cut, env)):
                    out = True
        self._reach[key] = out
        return out

    def job(self, fname, cut, env=ENV0, categories=None, args=None, limits=None):
        """WCET of one job of task function `fname`: the paths from the
        return of a call to a function of `cut` to the next such call.
        `limits`: [(function names, n)]: the calls of these functions sum
        to at most n per job. `categories`: function -> category of the
        cycles (callee of a summary call, or the function of the code)."""
        cut = set(cut)
        cats = categories or {}
        excl = self._excluded(env)
        insts = []   # (function, args, cfg, values, continuation node or None)
        nodes = {}   # node -> cost
        node_cat = {}   # node -> [(category, cycles)]
        edges = []   # (u, v, cost, dead)
        cut_nodes = set()
        zero_nodes = set()
        call_sites = []   # (node, CallSite)
        node_callees = {}  # node -> names of the called functions

        def expand(f, a, cont, depth, parent=None):
            if depth > 32:
                raise WcetError(f"inlining depth above 32 at {f}")
            cfg = self.cfg(f, env)
            values = Values(cfg, entry_state(a, self.img.gp), self.img, dict(env.returns))
            i = len(insts)
            insts.append((f, a, cfg, values, cont, parent))
            blocks = cfg.blocks
            for b in values.inp:
                blk = blocks[b]
                n = (i, b)
                own = self._own_cost(blk)
                nodes[n] = own
                node_cat[n] = [(cats.get(f, "body"), own)]
                gs = self._callees(blk) if blk.term in ("call", "tailcall") else []
                if gs:
                    node_callees[n] = set(gs)
                nxt_cont = None
                if blk.term == "call":
                    nxt_cont = (i, blk.end)
                elif blk.term == "tailcall":
                    nxt_cont = cont
                if gs and any(g in excl for g in gs):
                    # kept in the graph (the init code of a task may print);
                    # the pass of the task loop leaves it out
                    zero_nodes.add(n)
                    if blk.term == "call":
                        edges.append((n, (i, blk.end), 0, False))
                    elif cont is not None:
                        edges.append((n, cont, 0, False))
                    continue
                if gs and any(g in cut for g in gs):
                    if len(gs) != 1:
                        raise WcetError(f"{f}: indirect call with a cut target at {blk.last.addr:08x}")
                    cut_nodes.add(n)
                    jal = timing.cost(blk.last, self.model)
                    node_cat[n] = [(cats.get(f, "body"), own - jal), ("dispatch", jal)]
                    if blk.term == "call":
                        edges.append((n, (i, blk.end), 0, False))
                    elif cont is not None:
                        edges.append((n, cont, 0, False))
                    continue
                if gs and len(gs) == 1 and self.reaches(gs[0], cut, env):
                    g = gs[0]
                    j_args = values.call_args(b)
                    j = expand(g, j_args, nxt_cont, depth + 1, i)
                    edges.append((n, (j, self.cfg(g, env).entry), 0, False))
                    continue
                if gs:
                    cc, sites = self._call_cost(f, blk, values, env)
                    nodes[n] += cc
                    jal = timing.cost(blk.last, self.model)
                    cat = cats.get(gs[0], "body")
                    node_cat[n] = [(cats.get(f, "body"), own - jal), (cat, cc + jal)]
                    for g, ga, c in sites:
                        call_sites.append((n, CallSite(b, blk.last.addr, g, ga, c + jal, 0, cats.get(g, "body"))))
                    if blk.term == "call":
                        edges.append((n, (i, blk.end), 0, (b, blk.end) in values.dead_edges))
                    elif cont is not None:
                        edges.append((n, cont, 0, False))
                    continue
                if blk.term == "return":
                    if cont is not None:
                        edges.append((n, cont, 0, False))
                    continue
                for s, kind in blk.succs:
                    if s in values.inp:
                        edges.append((n, (i, s), self._edge_cost(blk, kind), (b, s) in values.dead_edges))
            return i

        cfg0 = self.cfg(fname, env)
        expand(fname, {r: v for r, v in (args or {}).items() if isinstance(v, int)}, None, 0)
        if not cut_nodes:
            raise WcetError(f"{fname}: no call of {', '.join(sorted(cut))}")
        # loops of the task: natural loops of the supergraph from the entry
        # of the task function (the structure of the code)
        full = {}
        for u, v, _c, dead in edges:
            if not dead:
                full.setdefault(u, []).append(v)
        try:
            lps = cfgmod.loops(full, (0, cfg0.entry))
        except cfgmod.CFGError as e:
            raise WcetError(f"{fname}: {e}") from None
        # job: from the return of a cut call (resume) to the next cut call
        succ = {}
        for u, v, _c, dead in edges:
            if dead or u in cut_nodes or u in zero_nodes or v in zero_nodes:
                continue
            succ.setdefault(u, []).append(v)
        resume = []
        for u, v, _c, dead in edges:
            if u in cut_nodes and v not in resume:
                resume.append(v)
        if not resume:
            raise WcetError(f"{fname}: the cut calls have no return point")
        reach = cfgmod.reachable(succ, resume)
        p = ipet.Problem()
        for n in reach:
            p.node_cost[n] = nodes[n]
        src = p.add_edge("S", "S0")
        p.sources[src] = 1
        into = {}
        start_edges = {}
        for r in resume:
            i = p.add_edge("S0", r)
            into.setdefault(r, []).append(i)
            start_edges[r] = i
        for u, v, c, dead in edges:
            if u not in reach or u in cut_nodes or v not in reach:
                continue
            i = p.add_edge(u, v, c)
            into.setdefault(v, []).append(i)
            if dead or u in zero_nodes or v in zero_nodes:
                p.zero_edges.add(i)
        for n in cut_nodes & reach:
            p.add_edge(n, "T")
        # limits: calls of the functions of each set per job
        limited = set()
        for funcs, m in limits or ():
            ns = [n for n in reach if node_callees.get(n, set()) & set(funcs)]
            limited.update(ns)
            idx = [i for n in ns for i in into.get(n, [])]
            if idx:
                p.extra.append(({i: 1 for i in idx}, m))
        loop_info = []
        inst_loops = {}
        for lp in lps:
            body = lp.body & reach
            if lp.header not in reach:
                continue
            ii, hb = lp.header
            f, a, cfg_i, values_i, _c, _p = insts[ii]
            if ii not in inst_loops:
                fsucc = {b: [s for s, _ in cfg_i.blocks[b].succs if (b, s) not in values_i.dead_edges]
                         for b in values_i.inp}
                inst_loops[ii] = (cfgmod.loops(fsucc, cfg_i.entry), cfgmod.dominators(fsucc, cfg_i.entry))
            flps, fdom = inst_loops[ii]
            flp = next((x for x in flps if x.header == hb), None)
            bound = None
            if flp is not None:
                bound = self.loop_bound(f, a, env, cfg_i, flp, flps, fdom, values_i, use_rest=False)
            if bound is None:
                # a loop needs no bound when each of its cycles in the job
                # passes a limited call, or when the cut calls break its cycles
                free = {u: [v for v in succ.get(u, ()) if v in body and v not in limited]
                        for u in body if u not in limited}
                if not cfgmod.has_cycle(free):
                    loop_info.append((f, hb, "limits" if limited & body else "cut", "calls per job"))
                    continue
                if flp is not None:
                    bound = self.loop_bound(f, a, env, cfg_i, flp, flps, fdom, values_i)
            if bound is None:
                raise WcetError(f"{fname}: loop at {hb:08x} of {f} has no bound in the job "
                                f"(annotation `loops` of {f}, WCET_LOOP_BOUND, or a counted loop)")
            ins = into.get(lp.header, [])
            for n, scope, source in bound:
                if scope == "function":
                    refs = into.get((ii, cfg_i.entry), [])
                    starts = [start_edges[r] for r in resume if r[0] == ii or r in lp.body]
                else:
                    refs = [i for i in ins if p.edges[i][0] not in lp.body]
                    starts = [start_edges[r] for r in resume if r in lp.body]
                # the job may start inside the loop or the function (a resume point)
                refs = list(dict.fromkeys(refs + starts))
                p.loops.append((ins, refs, n))
                loop_info.append((f, hb, n, source))
        try:
            sol = ipet.solve(p)
        except ipet.IPETError as e:
            raise WcetError(f"{fname}: {e}") from None
        counts = sol.node_counts
        catsum = {}
        for n in reach:
            k = counts.get(n, 0)
            if not k:
                continue
            for c, cy in node_cat[n]:
                catsum[c] = catsum.get(c, 0) + k * cy
        for i, (u, v, ce) in enumerate(p.edges):
            if ce and sol.edge_counts[i] and u not in ("S", "S0"):
                f = insts[u[0]][0]
                c = cats.get(f, "body")
                catsum[c] = catsum.get(c, 0) + ce * sol.edge_counts[i]
        calls = []
        for n, cs in call_sites:
            if n in reach and counts.get(n, 0):
                cs.count = counts[n]
                calls.append(cs)
        res = Result(fname, sol.cycles, dict(args or {}), calls, loop_info, counts, catsum)
        res.call_counts = {}
        for n in reach:
            for g in node_callees.get(n, ()):
                res.call_counts[g] = res.call_counts.get(g, 0) + counts.get(n, 0)
        return res
