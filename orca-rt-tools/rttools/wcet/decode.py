"""Decoder of the RV32I/RV32E base instructions that the HF-RISC core of the
platform executes (pkt-sim/hw/cpu/core_rv32e, control.vhd).

The core implements RV32E without the M and C extensions: the compiler
(-march=rv32e -mabi=ilp32e) emits 32-bit instructions only and calls
software routines for multiplication and division (__mulsi3, __udivsi3
of arch/common/muldiv.c). `decode` rejects an M instruction, since the
control unit of the core has no decoding for it.

| Field | Meaning |
|---|---|
| op | mnemonic (addi, lw, beq, jal, ...) |
| kind | timing class of rttools.wcet.timing: alu, lui, load, store, branch, jal, jalr, system, fence |
| rd, rs1, rs2 | register numbers (x0 to x31; RV32E uses x0 to x15) |
| imm | sign-extended immediate (branch and jal: byte offset from pc) |
| width, signed | loads and stores: bytes accessed and sign extension of a load |
"""
from __future__ import annotations

from dataclasses import dataclass

REG_NAMES = ["zero", "ra", "sp", "gp", "tp", "t0", "t1", "t2", "s0", "s1",
             "a0", "a1", "a2", "a3", "a4", "a5", "a6", "a7", "s2", "s3", "s4", "s5",
             "s6", "s7", "s8", "s9", "s10", "s11", "t3", "t4", "t5", "t6"]
REG = {n: i for i, n in enumerate(REG_NAMES)}
REG["fp"] = 8

ZERO, RA, SP, GP = 0, 1, 2, 3
A0 = 10
# argument registers of the ilp32e ABI (a0 to a5)
ARG_REGS = tuple(range(10, 16))
# registers a call may change (ilp32e: ra, t0 to t2, a0 to a5)
CALLER_SAVED = (1, 5, 6, 7, 10, 11, 12, 13, 14, 15)


class DecodeError(ValueError):
    pass


@dataclass(frozen=True)
class Instr:
    addr: int
    word: int
    op: str
    kind: str
    rd: int = 0
    rs1: int = 0
    rs2: int = 0
    imm: int = 0
    width: int = 0
    signed: bool = False

    @property
    def target(self):
        """Branch or jal target address."""
        return (self.addr + self.imm) & 0xFFFFFFFF

    @property
    def is_call(self):
        """jal or jalr that writes the link register (a call)."""
        return self.kind in ("jal", "jalr") and self.rd == RA

    @property
    def is_return(self):
        return self.kind == "jalr" and self.rd == ZERO and self.rs1 == RA and self.imm == 0

    def __str__(self):
        r = REG_NAMES
        if self.kind == "alu" and self.op.endswith("i"):
            return f"{self.op} {r[self.rd]},{r[self.rs1]},{self.imm}"
        if self.kind == "alu":
            return f"{self.op} {r[self.rd]},{r[self.rs1]},{r[self.rs2]}"
        if self.kind == "lui":
            return f"{self.op} {r[self.rd]},0x{(self.imm >> 12) & 0xFFFFF:x}"
        if self.kind == "load":
            return f"{self.op} {r[self.rd]},{self.imm}({r[self.rs1]})"
        if self.kind == "store":
            return f"{self.op} {r[self.rs2]},{self.imm}({r[self.rs1]})"
        if self.kind == "branch":
            return f"{self.op} {r[self.rs1]},{r[self.rs2]},{self.target:x}"
        if self.kind == "jal":
            return f"jal {r[self.rd]},{self.target:x}"
        if self.kind == "jalr":
            return f"jalr {r[self.rd]},{self.imm}({r[self.rs1]})"
        return self.op


def sext(v, bits):
    m = 1 << (bits - 1)
    return (v & (m - 1)) - (v & m)


_BRANCH = {0: "beq", 1: "bne", 4: "blt", 5: "bge", 6: "bltu", 7: "bgeu"}
_LOAD = {0: ("lb", 1, True), 1: ("lh", 2, True), 2: ("lw", 4, True), 4: ("lbu", 1, False), 5: ("lhu", 2, False)}
_STORE = {0: ("sb", 1), 1: ("sh", 2), 2: ("sw", 4)}
_OPIMM = {0: "addi", 2: "slti", 3: "sltiu", 4: "xori", 6: "ori", 7: "andi"}
_OP = {(0, 0): "add", (0, 0x20): "sub", (1, 0): "sll", (2, 0): "slt", (3, 0): "sltu", (4, 0): "xor",
       (5, 0): "srl", (5, 0x20): "sra", (6, 0): "or", (7, 0): "and"}


def decode(word, addr=0):
    """Decodes one 32-bit instruction word (little-endian value) at `addr`."""
    w = word & 0xFFFFFFFF
    if w & 3 != 3:
        raise DecodeError(f"{addr:08x}: compressed or invalid instruction {w:08x} (the core has no C extension)")
    opc = w & 0x7F
    rd = (w >> 7) & 0x1F
    f3 = (w >> 12) & 7
    rs1 = (w >> 15) & 0x1F
    rs2 = (w >> 20) & 0x1F
    f7 = (w >> 25) & 0x7F
    imm_i = sext(w >> 20, 12)
    if opc == 0x37:
        return Instr(addr, w, "lui", "lui", rd=rd, imm=sext(w & 0xFFFFF000, 32))
    if opc == 0x17:
        return Instr(addr, w, "auipc", "lui", rd=rd, imm=sext(w & 0xFFFFF000, 32))
    if opc == 0x6F:
        imm = ((w >> 31) << 20) | (((w >> 12) & 0xFF) << 12) | (((w >> 20) & 1) << 11) | (((w >> 21) & 0x3FF) << 1)
        return Instr(addr, w, "jal", "jal", rd=rd, imm=sext(imm, 21))
    if opc == 0x67:
        if f3 != 0:
            raise DecodeError(f"{addr:08x}: invalid jalr {w:08x}")
        return Instr(addr, w, "jalr", "jalr", rd=rd, rs1=rs1, imm=imm_i)
    if opc == 0x63:
        if f3 not in _BRANCH:
            raise DecodeError(f"{addr:08x}: invalid branch {w:08x}")
        imm = ((w >> 31) << 12) | (((w >> 7) & 1) << 11) | (((w >> 25) & 0x3F) << 5) | (((w >> 8) & 0xF) << 1)
        return Instr(addr, w, _BRANCH[f3], "branch", rs1=rs1, rs2=rs2, imm=sext(imm, 13))
    if opc == 0x03:
        if f3 not in _LOAD:
            raise DecodeError(f"{addr:08x}: invalid load {w:08x}")
        op, width, signed = _LOAD[f3]
        return Instr(addr, w, op, "load", rd=rd, rs1=rs1, imm=imm_i, width=width, signed=signed)
    if opc == 0x23:
        if f3 not in _STORE:
            raise DecodeError(f"{addr:08x}: invalid store {w:08x}")
        op, width = _STORE[f3]
        imm = sext(((w >> 25) << 5) | ((w >> 7) & 0x1F), 12)
        return Instr(addr, w, op, "store", rs1=rs1, rs2=rs2, imm=imm, width=width)
    if opc == 0x13:
        if f3 == 1:
            if f7 != 0:
                raise DecodeError(f"{addr:08x}: invalid slli {w:08x}")
            return Instr(addr, w, "slli", "alu", rd=rd, rs1=rs1, imm=rs2)
        if f3 == 5:
            if f7 not in (0, 0x20):
                raise DecodeError(f"{addr:08x}: invalid shift {w:08x}")
            return Instr(addr, w, "srai" if f7 else "srli", "alu", rd=rd, rs1=rs1, imm=rs2)
        return Instr(addr, w, _OPIMM[f3], "alu", rd=rd, rs1=rs1, imm=imm_i)
    if opc == 0x33:
        if f7 == 1:
            raise DecodeError(f"{addr:08x}: M extension instruction {w:08x} (the core has no multiplier)")
        if (f3, f7) not in _OP:
            raise DecodeError(f"{addr:08x}: invalid register operation {w:08x}")
        return Instr(addr, w, _OP[(f3, f7)], "alu", rd=rd, rs1=rs1, rs2=rs2)
    if opc == 0x0F:
        return Instr(addr, w, "fence", "fence")
    if opc == 0x73:
        return Instr(addr, w, {0x00000073: "ecall", 0x00100073: "ebreak"}.get(w, "system"), "system")
    raise DecodeError(f"{addr:08x}: unknown opcode {opc:#04x} in {w:08x}")
