"""Bounds of loops: counted loops found by the analysis and bound
expressions of the annotations.

A loop bound is the largest number of executions of the loop header per
entry into the loop (header count <= bound x entry count), or per call of
the function (scope "function").

| Pattern (detected) | Condition | Bound |
|---|---|---|
| counted loop | one definition `addi r, r, c` (c != 0) of the induction register r in the loop, in a block of this loop (not of an inner loop) that dominates every latch; an exit branch that compares r with a limit whose value at the branch is the same in every iteration (a constant in the converged state of rttools.wcet.value, e.g. a field of a const descriptor that the loop loads again in each pass), in a block of this loop that dominates every latch; known r at the entry | first iteration at which the exit branch leaves the loop (the value of r at the branch follows from the position of the update before or after it), at most MAX_COUNT |
| shift loop | one definition `srli r, r, c` or `srai r, r, c` and an exit when r = 0 (beq r, zero out of the loop or bne r, zero into it), same dominance conditions | ceil(32 / c) + 1 |

An expression bound (annotation) may use the arguments a0 to a5 at the
entry of the function (known in the context of the call), integers, + - *
// ( ), min/max, and u8(x), u16(x), u32(x): the unsigned value at address x
of the read-only data of the image (a field of a const descriptor that an
argument points to, as the TASKS table of rttools.ucxgen).
"""
from __future__ import annotations

import ast
import math

from rttools.wcet.decode import REG
from rttools.wcet.value import MASK, compare

MAX_COUNT = 1 << 20


def _defs(cfg_blocks, body, reg):
    out = []
    for b in body:
        for ins in cfg_blocks[b].instrs:
            if ins.kind in ("alu", "lui", "load") and ins.rd == reg:
                out.append((b, ins))
            elif ins.kind in ("jal", "jalr") and ins.rd != 0 and reg in (1, 5, 6, 7, 10, 11, 12, 13, 14, 15):
                out.append((b, ins))
    return out


def counted(blocks, loop, inner_bodies, dom, values, entry_state):
    """Bound of a loop of one function by the patterns of the module
    docstring, or None. `blocks`: start -> Block; `loop`: rttools.wcet.cfg
    Loop; `inner_bodies`: bodies of the loops nested in it; `dom`:
    dominator sets; `values`: rttools.wcet.value.Values of the function;
    `entry_state`: State on the entry edges (join)."""
    if entry_state is None:
        return None
    latches = [u for u, _ in loop.back_edges]
    own = set(loop.body)
    for ib in inner_bodies:
        own -= ib

    def dominates_latches(b):
        return all(b in dom.get(u, ()) for u in latches)

    best = None
    for b in sorted(own):
        blk = blocks[b]
        if blk.term != "branch" or not dominates_latches(b):
            continue
        br = blk.last
        succ_in = [s for s, _ in blk.succs if s in loop.body]
        succ_out = [s for s, _ in blk.succs if s not in loop.body]
        if len(succ_in) != 1 or len(succ_out) != 1:
            continue
        exit_on_taken = br.target in succ_out
        for ind, lim_reg in ((br.rs1, br.rs2), (br.rs2, br.rs1)):
            if ind == 0:
                continue
            defs = _defs(blocks, loop.body, ind)
            if len(defs) != 1:
                continue
            ub, up = defs[0]
            if ub not in own or not dominates_latches(ub):
                continue
            init = entry_state.get(ind)
            if up.op == "addi" and up.rs1 == ind and up.imm != 0:
                if not isinstance(init, int):
                    continue
                # the converged state at the branch holds for every iteration
                lim = values.before(b, br.addr).get(lim_reg) if b in values.inp else None
                if not isinstance(lim, int):
                    continue
                # update before the branch in the same iteration?
                before = (ub != b and ub in dom.get(b, ())) or (ub == b)
                n = _iterate(br.op, ind == br.rs1, init, up.imm, lim, before, exit_on_taken)
            elif up.op in ("srli", "srai") and up.rs1 == ind and up.imm > 0 and lim_reg == 0 \
                    and br.op in ("beq", "bne") and ((br.op == "beq") == exit_on_taken):
                n = math.ceil(32 / up.imm) + 1
            else:
                continue
            if n is not None and (best is None or n < best):
                best = n
    return best


def _iterate(op, ind_first, init, step, lim, update_before, exit_on_taken):
    v = init
    for j in range(1, MAX_COUNT + 1):
        x = (v + step) & MASK if update_before else v
        a, b = (x, lim) if ind_first else (lim, x)
        taken = compare(op, a, b)
        if taken == exit_on_taken:
            return j
        v = (v + step) & MASK
    return None


_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Add, ast.Sub,
            ast.Mult, ast.FloorDiv, ast.USub, ast.Call, ast.Load)


def evaluate(expr, args, read=None):
    """Value of a bound expression; `args`: {register number: value} at
    the entry of the function; `read(address, width)`: read-only data of
    the image (None when unknown). Raises ValueError when the expression
    uses an argument or a datum without a known value."""
    if isinstance(expr, int):
        return expr
    tree = ast.parse(str(expr), mode="eval")
    funcs = ("min", "max", "u8", "u16", "u32")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED):
            raise ValueError(f"bound expression {expr!r}: {type(node).__name__} not allowed")
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in funcs):
            raise ValueError(f"bound expression {expr!r}: only {', '.join(funcs)} calls")

    def mem(width):
        def f(addr):
            v = read(addr & MASK, width) if read is not None else None
            if v is None:
                raise ValueError(f"bound expression {expr!r}: no read-only data at {addr & MASK:#x}")
            return v
        return f
    env = {"min": min, "max": max, "u8": mem(1), "u16": mem(2), "u32": mem(4)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in env:
            r = REG.get(node.id)
            if r is None:
                raise ValueError(f"bound expression {expr!r}: unknown name {node.id}")
            v = args.get(r)
            if not isinstance(v, int):
                raise ValueError(f"bound expression {expr!r}: {node.id} unknown in this context")
            # arguments are signed C integers
            env[node.id] = v - (1 << 32) if v & 0x80000000 else v
    return int(eval(compile(tree, "<bound>", "eval"), {"__builtins__": {}}, env))
