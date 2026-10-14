"""Control-flow graph of one function and natural loops of a graph.

`build` walks the instructions of a function from its entry and splits
them into basic blocks. A block ends at a conditional branch, a jump, a
call, a return or before the target of another branch. Each block ends
with one terminator:

| Terminator | Instruction | Successors |
|---|---|---|
| branch | beq, bne, blt, bge, bltu, bgeu | target (edge "taken") and next instruction (edge "fall") |
| jump | jal zero to an address of the same function | target |
| call | jal ra (direct) or jalr ra (indirect) | next instruction, after the callee returns |
| tailcall | jal zero to the entry of another function | none: the callee returns to the caller of this function |
| return | jalr zero, 0(ra) | none |
| ijump | jalr zero to a register other than ra | the targets of an annotation or of a jump table; none when the annotation marks it as a return |
| fall | the next instruction starts another block | next instruction |

Calls to the entry of another function are calls; a branch or jump into
the middle of another function is an error. An indirect jump or call
without targets (annotation or jump table) is an error, since the
analysis cannot bound its paths.

`loops` finds the natural loops of any graph (blocks of one function or
the supergraph of a task, rttools.wcet.analysis) from its dominators: the
target h of an edge u -> h that dominates u is a loop header, and the
loop holds the nodes that reach u without passing h. A cycle without such
a header (irreducible flow) is an error.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from rttools.wcet.decode import RA, ZERO


class CFGError(ValueError):
    pass


@dataclass
class Block:
    start: int
    instrs: list
    term: str = "fall"
    succs: list = field(default_factory=list)   # (address, "taken" | "fall")
    callee: str | None = None                   # direct call or tail call
    call_targets: list | None = None            # indirect call: annotation targets
    edge_max: dict = field(default_factory=dict)  # indirect jump: target -> most executions per call

    @property
    def last(self):
        return self.instrs[-1]

    @property
    def end(self):
        return self.instrs[-1].addr + 4


@dataclass
class CFG:
    func: str
    entry: int
    blocks: dict  # start -> Block

    def succ_map(self):
        return {b: [s for s, _ in blk.succs] for b, blk in self.blocks.items()}

    def block_of(self, addr):
        for b in self.blocks.values():
            if b.start <= addr < b.end:
                return b
        return None


def jump_table(img, func, jalr):
    """Targets of the jump table of a switch compiled by gcc, from the
    instructions before `jalr` in the same function: the bound check
    (bltu/bgeu of the index against a constant), the base address
    (lui + addi), the scaled index (slli 2, add) and the load (lw) that
    gives the target. Needs the read-only data of an ELF image; returns
    (targets by index) or None when the pattern does not match."""
    instrs = []
    a = jalr.addr - 4
    while a >= func.start and len(instrs) < 12:
        try:
            instrs.append(img.instr(a))
        except Exception:
            break
        a -= 4
    # instrs[0] is the instruction right before jalr
    want = jalr.rs1
    lw = next((i for i in instrs if i.kind == "load" and i.op == "lw" and i.rd == want), None)
    if lw is None or lw.imm != 0:
        return None
    add = next((i for i in instrs if i.addr < lw.addr and i.op == "add" and i.rd == lw.rs1), None)
    if add is None:
        return None
    base = None
    idx_reg = None
    for r_base, r_idx in ((add.rs1, add.rs2), (add.rs2, add.rs1)):
        hi = next((i for i in instrs if i.addr < add.addr and i.op == "lui" and i.rd == r_base), None)
        lo = next((i for i in instrs if hi is not None and hi.addr < i.addr < add.addr and i.op == "addi"
                   and i.rd == r_base and i.rs1 == r_base), None)
        if hi is not None and lo is not None:
            base = (hi.imm + lo.imm) & 0xFFFFFFFF
            idx_reg = r_idx
            break
    if base is None:
        return None
    sl = next((i for i in instrs if i.addr < add.addr and i.op == "slli" and i.rd == idx_reg and i.imm == 2), None)
    if sl is None:
        return None
    idx = sl.rs1
    n = None
    for i in instrs:
        if i.addr >= sl.addr or i.kind != "branch" or i.op not in ("bltu", "bgeu"):
            continue
        # bltu k, idx -> default when idx > k: entries 0..k
        lim_reg = i.rs1 if i.op == "bltu" and i.rs2 == idx else (i.rs2 if i.op == "bgeu" and i.rs1 == idx else None)
        if lim_reg is None:
            continue
        li = next((j for j in instrs if j.addr < i.addr and j.op == "addi" and j.rd == lim_reg and j.rs1 == ZERO), None)
        if li is not None:
            n = li.imm + 1 if i.op == "bltu" else li.imm
            break
    if n is None or n <= 0 or n > 4096:
        return None
    targets = []
    for k in range(n):
        t = img.read(base + 4 * k, 4)
        if t is None:
            return None
        targets.append(t)
    return targets


def build(img, name, indirect=None):
    """CFG of function `name`. `indirect`: {jalr address: spec} for the
    indirect jumps and calls of the function, spec = {"targets": [address,
    ...]} (jump targets in the function, or call targets: function
    entries; for a jump, "edge_max": {target: n} limits the jumps to a
    target per call of the function) or {"return": True} (the jump leaves
    the function, as the jalr of _isr that returns to the interrupted
    code)."""
    func = img.function(name)
    indirect = indirect or {}
    seen = {}
    leaders = {func.start}
    work = [func.start]
    while work:
        pc = work.pop()
        while pc not in seen:
            if not func.contains(pc):
                raise CFGError(f"{name}: control flow leaves the function at {pc:08x}")
            ins = img.instr(pc)
            seen[pc] = ins
            nxt = pc + 4
            if ins.kind == "branch":
                t = ins.target
                if not func.contains(t):
                    raise CFGError(f"{name}: branch at {pc:08x} to {t:08x} outside the function")
                leaders.update((t, nxt))
                work.append(t)
                pc = nxt
                continue
            if ins.kind == "jal":
                t = ins.target
                if ins.rd == RA:
                    leaders.add(nxt)
                    pc = nxt
                    continue
                if ins.rd != ZERO:
                    raise CFGError(f"{name}: jal with link register {ins.rd} at {pc:08x}")
                if func.contains(t) and t != func.start:
                    leaders.add(t)
                    work.append(t)
                    break
                if img.function_starting_at(t) is None:
                    raise CFGError(f"{name}: jump at {pc:08x} into the middle of a function ({t:08x})")
                break  # tail call
            if ins.kind == "jalr":
                if ins.rd == RA:
                    leaders.add(nxt)
                    pc = nxt
                    continue
                if ins.rd != ZERO:
                    raise CFGError(f"{name}: jalr with link register {ins.rd} at {pc:08x}")
                if ins.is_return:
                    break
                spec = indirect.get(pc)
                if spec is None:
                    tbl = jump_table(img, func, ins)
                    spec = {"targets": tbl} if tbl else None
                if spec is None:
                    raise CFGError(f"{name}: indirect jump at {pc:08x} without targets "
                                   f"(annotation `indirect_jumps` of {name})")
                if spec.get("return"):
                    break
                for t in spec["targets"]:
                    if not func.contains(t):
                        raise CFGError(f"{name}: indirect jump at {pc:08x} to {t:08x} outside the function")
                    leaders.add(t)
                    work.append(t)
                break
            if ins.kind == "system":
                raise CFGError(f"{name}: {ins.op} at {pc:08x} (exception) on an analyzed path")
            pc = nxt

    blocks = {}
    addrs = sorted(seen)
    cur = None
    for a in addrs:
        if cur is None or a in leaders or a != cur.end:
            cur = Block(a, [])
            blocks[a] = cur
        cur.instrs.append(seen[a])
        ins = seen[a]
        if ins.kind in ("branch", "jal", "jalr") or (a + 4) in leaders:
            cur = None
    for b in blocks.values():
        ins = b.last
        nxt = b.end
        if ins.kind == "branch":
            b.term = "branch"
            b.succs = [(ins.target, "taken"), (nxt, "fall")]
        elif ins.kind == "jal" and ins.rd == RA:
            b.term = "call"
            f = img.function_starting_at(ins.target)
            if f is None:
                raise CFGError(f"{name}: call at {ins.addr:08x} to {ins.target:08x}, not a function entry")
            b.callee = f.name
            b.succs = [(nxt, "fall")]
        elif ins.kind == "jal":
            t = ins.target
            if func.contains(t) and t != func.start:
                b.term = "jump"
                b.succs = [(t, "taken")]
            else:
                b.term = "tailcall"
                b.callee = img.function_starting_at(t).name
        elif ins.kind == "jalr" and ins.rd == RA:
            b.term = "call"
            spec = indirect.get(ins.addr)
            if not spec or not spec.get("targets"):
                raise CFGError(f"{name}: indirect call at {ins.addr:08x} without targets "
                               f"(annotation `indirect_calls` of {name})")
            names = []
            for t in spec["targets"]:
                f = img.function_starting_at(t)
                if f is None:
                    raise CFGError(f"{name}: indirect call target {t:08x} is not a function entry")
                names.append(f.name)
            b.call_targets = names
            b.succs = [(nxt, "fall")]
        elif ins.is_return:
            b.term = "return"
        elif ins.kind == "jalr":
            spec = indirect.get(ins.addr)
            if spec is None:
                tbl = jump_table(img, func, ins)
                spec = {"targets": tbl}
            if spec.get("return"):
                b.term = "return"
            else:
                b.term = "ijump"
                b.succs = [(t, "taken") for t in dict.fromkeys(spec["targets"])]
                b.edge_max = dict(spec.get("edge_max", {}))
        else:
            b.term = "fall"
            b.succs = [(nxt, "fall")]
        for s, _ in b.succs:
            if s not in blocks:
                raise CFGError(f"{name}: successor {s:08x} of block {b.start:08x} is not a block")
    return CFG(name, func.start, blocks)


# ---------------------------------------------------------------- graphs

def reachable(succ, roots):
    seen = set()
    work = list(roots)
    while work:
        n = work.pop()
        if n in seen:
            continue
        seen.add(n)
        work.extend(succ.get(n, ()))
    return seen


def dominators(succ, entry):
    """Dominator sets of the nodes reachable from `entry` (iterative
    data-flow; the graphs of one function or task are small)."""
    nodes = reachable(succ, [entry])
    preds = {n: [] for n in nodes}
    for n in nodes:
        for s in succ.get(n, ()):
            if s in nodes:
                preds[s].append(n)
    order = _rpo(succ, entry, nodes)
    dom = {n: set(nodes) for n in nodes}
    dom[entry] = {entry}
    changed = True
    while changed:
        changed = False
        for n in order:
            if n == entry:
                continue
            ps = [dom[p] for p in preds[n]]
            new = set.intersection(*ps) if ps else set()
            new = new | {n}
            if new != dom[n]:
                dom[n] = new
                changed = True
    return dom


def _rpo(succ, entry, nodes):
    out, seen = [], set()
    stack = [(entry, iter(succ.get(entry, ())))]
    seen.add(entry)
    while stack:
        n, it = stack[-1]
        for s in it:
            if s in nodes and s not in seen:
                seen.add(s)
                stack.append((s, iter(succ.get(s, ()))))
                break
        else:
            stack.pop()
            out.append(n)
    return out[::-1]


@dataclass
class Loop:
    header: object
    body: set
    back_edges: list   # (u, header)
    entries: list      # (u, header), u outside the loop
    parent: object = None

    @property
    def depth(self):
        d, p = 0, self.parent
        while p is not None:
            d, p = d + 1, p.parent
        return d


def loops(succ, entry):
    """Natural loops of the graph, outermost first. Raises CFGError on a
    cycle without a dominating header."""
    dom = dominators(succ, entry)
    nodes = set(dom)
    preds = {n: [] for n in nodes}
    for n in nodes:
        for s in succ.get(n, ()):
            if s in nodes:
                preds[s].append(n)
    by_header = {}
    for u in nodes:
        for h in succ.get(u, ()):
            if h in nodes and h in dom[u]:
                by_header.setdefault(h, []).append(u)
    out = []
    for h, latches in by_header.items():
        body = {h}
        work = [u for u in latches if u != h]
        body.update(work)
        while work:
            n = work.pop()
            for p in preds[n]:
                if p not in body:
                    body.add(p)
                    work.append(p)
        entries = [(p, h) for p in preds[h] if p not in body]
        out.append(Loop(h, body, [(u, h) for u in latches], entries))
    # irreducible flow: a cycle left after removing the back edges
    back = {(u, h) for lp in out for (u, h) in lp.back_edges}
    acyc = {n: [s for s in succ.get(n, ()) if s in nodes and (n, s) not in back] for n in nodes}
    if has_cycle(acyc):
        raise CFGError("irreducible control flow (a cycle without a dominating header)")
    out.sort(key=lambda lp: -len(lp.body))
    for i, lp in enumerate(out):
        best = None
        for other in out[:i]:
            if lp.header in other.body and lp.body <= other.body and other is not lp:
                if best is None or len(other.body) < len(best.body):
                    best = other
        lp.parent = best
    return out


def has_cycle(succ):
    """True when the graph `succ` (node -> successors) has a cycle."""
    color = {}
    for root in succ:
        if root in color:
            continue
        stack = [(root, iter(succ[root]))]
        color[root] = 1
        while stack:
            n, it = stack[-1]
            for s in it:
                c = color.get(s)
                if c == 1:
                    return True
                if c is None:
                    color[s] = 1
                    stack.append((s, iter(succ.get(s, ()))))
                    break
            else:
                color[n] = 2
                stack.pop()
    return False
