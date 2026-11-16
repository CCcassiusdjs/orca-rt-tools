"""Constant propagation over the blocks of one function.

Abstract value of a register or of a stack slot:

| Value | Meaning |
|---|---|
| int | known 32-bit value (unsigned representation) |
| ("sp", d) | the stack pointer at the entry of the function plus d |
| ("spge", d) | an address at or above ("sp", d): ("sp", d) plus an unknown index |
| None | unknown |

The state holds the registers and the 32-bit stack slots that the
function stored at known offsets of its entry stack pointer. A load from
read-only data of the image (text, .rodata) at a known address gives the
stored value; a load from a stack slot gives the stored value. A store
through ("spge", d), or a call with an argument ("sp", d) or ("spge", d),
forgets the slots at offsets >= d: C code reaches an object of the frame
(an array, a struct) from its address with non-negative offsets. A call
forgets the registers that the ABI lets the callee change
(rttools.wcet.decode, CALLER_SAVED). A callee whose return value the
query sets (`returns`, e.g. setjmp returns 0 on the path that saves a
context) sets a0.

Assumption: a store through an address that the analysis does not relate
to the stack pointer (a global, the heap, a pointer loaded from memory)
does not write the frame of the analyzed function. The code of UCX-OS and
of the applications passes addresses of the frame only as call arguments
and to inlined code, which the rules above cover.

The results serve three purposes: the arguments of each call (the context
of the callee), the branches with a known outcome (an edge that the
program cannot take), and the counted loops (rttools.wcet.loopbound).
"""
from __future__ import annotations

from rttools.wcet.decode import A0, ARG_REGS, CALLER_SAVED, GP, SP, ZERO

MASK = 0xFFFFFFFF
NREGS = 32


def s32(v):
    return v - (1 << 32) if v & 0x80000000 else v


class State:
    __slots__ = ("regs", "slots")

    def __init__(self, regs=None, slots=None):
        self.regs = list(regs) if regs is not None else [None] * NREGS
        self.slots = dict(slots) if slots else {}
        self.regs[ZERO] = 0

    def copy(self):
        return State(self.regs, self.slots)

    def __eq__(self, other):
        return isinstance(other, State) and self.regs == other.regs and self.slots == other.slots

    def get(self, r):
        return 0 if r == ZERO else self.regs[r]

    def set(self, r, v):
        if r != ZERO:
            self.regs[r] = v & MASK if isinstance(v, int) else v


def join(a, b):
    if a is None:
        return b.copy()
    if b is None:
        return a.copy()
    regs = [x if x == y else None for x, y in zip(a.regs, b.regs)]
    slots = {k: v for k, v in a.slots.items() if b.slots.get(k, object()) == v}
    return State(regs, slots)


def entry_state(args=None, gp=None):
    """State at the entry of a function: sp = ("sp", 0), gp from the image,
    a0..a5 from `args` ({register: value})."""
    st = State()
    st.set(SP, None)
    st.regs[SP] = ("sp", 0)
    if gp is not None:
        st.set(GP, gp)
    for r, v in (args or {}).items():
        st.set(r, v) if isinstance(v, int) else None
    return st


def _alu(op, a, b):
    """Result of an ALU operation on two known values (unsigned 32-bit)."""
    if op in ("add", "addi"):
        return a + b
    if op == "sub":
        return a - b
    if op in ("and", "andi"):
        return a & b
    if op in ("or", "ori"):
        return a | b
    if op in ("xor", "xori"):
        return a ^ b
    if op in ("sll", "slli"):
        return a << (b & 31)
    if op in ("srl", "srli"):
        return (a & MASK) >> (b & 31)
    if op in ("sra", "srai"):
        return s32(a & MASK) >> (b & 31)
    if op in ("slt", "slti"):
        return int(s32(a & MASK) < s32(b & MASK))
    if op in ("sltu", "sltiu"):
        return int((a & MASK) < (b & MASK))
    raise ValueError(op)


def step(st, ins, img=None, returns=None, callee=None):
    """Applies one instruction to the state `st` (in place)."""
    k = ins.kind
    if k == "lui":
        st.set(ins.rd, ins.imm if ins.op == "lui" else ins.addr + ins.imm)
    elif k == "alu":
        a = st.get(ins.rs1)
        if ins.op.endswith("i"):
            b = ins.imm & MASK if ins.op not in ("slli", "srli", "srai") else ins.imm
        else:
            b = st.get(ins.rs2)
        if isinstance(a, int) and isinstance(b, int):
            st.set(ins.rd, _alu(ins.op, a, b))
        elif ins.op in ("addi", "add") and isinstance(a, tuple) and isinstance(b, int):
            st.regs[ins.rd] = (a[0], s32((a[1] + b) & MASK)) if ins.rd != ZERO else None
        elif ins.op == "add" and isinstance(b, tuple) and isinstance(a, int):
            st.regs[ins.rd] = (b[0], s32((b[1] + a) & MASK)) if ins.rd != ZERO else None
        elif ins.op == "sub" and isinstance(a, tuple) and isinstance(b, int):
            st.regs[ins.rd] = (a[0], s32((a[1] - b) & MASK)) if ins.rd != ZERO else None
        elif ins.op == "add" and (isinstance(a, tuple) or isinstance(b, tuple)):
            p = a if isinstance(a, tuple) else b
            st.regs[ins.rd] = ("spge", p[1]) if ins.rd != ZERO else None
        else:
            st.set(ins.rd, None)
            if ins.rd != ZERO:
                st.regs[ins.rd] = None
    elif k == "load":
        base = st.get(ins.rs1)
        v = None
        if isinstance(base, int) and img is not None:
            v = img.read((base + ins.imm) & MASK, ins.width, ins.signed)
        elif isinstance(base, tuple) and base[0] == "sp" and ins.width == 4:
            v = st.slots.get(base[1] + ins.imm)
        st.regs[ins.rd] = v if ins.rd != ZERO else None
        if ins.rd == ZERO:
            st.regs[ZERO] = 0
    elif k == "store":
        base = st.get(ins.rs1)
        if isinstance(base, tuple) and base[0] == "sp":
            off = base[1] + ins.imm
            for s in [s for s in st.slots if s < off + ins.width and off < s + 4]:
                del st.slots[s]
            if ins.width == 4:
                v = st.get(ins.rs2)
                if v is not None:
                    st.slots[off] = v
        elif isinstance(base, tuple):
            _kill_from(st, base[1] + min(ins.imm, 0))
    elif k in ("jal", "jalr"):
        if ins.rd != ZERO:
            # a call: the callee may change the caller-saved registers
            for r in ARG_REGS:
                v = st.get(r)
                if isinstance(v, tuple):
                    _kill_from(st, v[1])
            for r in CALLER_SAVED:
                st.regs[r] = None
            if returns and callee in returns:
                st.set(A0, returns[callee])
    return st


def _kill_from(st, d):
    for s in [s for s in st.slots if s + 4 > d]:
        del st.slots[s]


def branch_outcome(st, ins):
    """True (taken), False (not taken) or None (unknown) for a branch."""
    a, b = st.get(ins.rs1), st.get(ins.rs2)
    if isinstance(a, tuple) and isinstance(b, tuple) and a[0] == b[0] == "sp" and ins.op in ("beq", "bne"):
        return (a == b) if ins.op == "beq" else (a != b)
    if not (isinstance(a, int) and isinstance(b, int)):
        return None
    return compare(ins.op, a, b)


def compare(op, a, b):
    a &= MASK
    b &= MASK
    if op == "beq":
        return a == b
    if op == "bne":
        return a != b
    if op == "blt":
        return s32(a) < s32(b)
    if op == "bge":
        return s32(a) >= s32(b)
    if op == "bltu":
        return a < b
    if op == "bgeu":
        return a >= b
    raise ValueError(op)


class Values:
    """Fixpoint of the constant propagation over a CFG (rttools.wcet.cfg).

    `start`: block where the analysis starts (default: the entry);
    `init`: State there. `returns`: {callee: value of a0 after the call}.
    Attributes: `inp` (State at the start of each reachable block),
    `dead_edges` (set of (u, v) that a known branch outcome excludes)."""

    def __init__(self, cfg, init, img=None, returns=None, start=None):
        self.cfg = cfg
        self.img = img
        self.returns = returns or {}
        self.inp = {}
        self.dead_edges = set()
        start = cfg.entry if start is None else start
        self.start = start
        self.inp[start] = init.copy()
        work = [start]
        while work:
            b = work.pop()
            out, live = self._out(b)
            for s in live:
                new = join(self.inp.get(s), out) if s in self.inp else out.copy()
                if self.inp.get(s) != new:
                    self.inp[s] = new
                    work.append(s)
        # dead edges from the final states
        for b in self.inp:
            _, live = self._out(b)
            for s, _k in self.cfg.blocks[b].succs:
                if s not in live:
                    self.dead_edges.add((b, s))

    def _callee(self, blk):
        return blk.callee if blk.term in ("call", "tailcall") else None

    def _out(self, b):
        blk = self.cfg.blocks[b]
        st = self.inp[b].copy()
        for ins in blk.instrs:
            step(st, ins, self.img, self.returns, self._callee(blk))
        live = [s for s, _ in blk.succs]
        if blk.term == "branch":
            pre = self.inp[b].copy()
            for ins in blk.instrs[:-1]:
                step(pre, ins, self.img, self.returns, None)
            o = branch_outcome(pre, blk.last)
            if o is True:
                live = [blk.last.target]
            elif o is False:
                live = [blk.end]
        return st, live

    def before(self, b, addr):
        """State before the instruction at `addr` of block `b`."""
        blk = self.cfg.blocks[b]
        st = self.inp[b].copy()
        for ins in blk.instrs:
            if ins.addr == addr:
                return st
            step(st, ins, self.img, self.returns, self._callee(blk))
        raise KeyError(addr)

    def out(self, b):
        return self._out(b)[0]

    def call_args(self, b):
        """{argument register: known value} before the call of block `b`."""
        st = self.before(b, self.cfg.blocks[b].last.addr)
        return {r: st.get(r) for r in ARG_REGS if isinstance(st.get(r), int)}
