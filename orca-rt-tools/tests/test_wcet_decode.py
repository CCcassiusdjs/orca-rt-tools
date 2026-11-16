"""rttools.wcet.decode against the objdump listing of run H (riscv64-elf-gcc
12.2.0, objdump -Mno-aliases): the mnemonic of every instruction line."""
import os
import re

import pytest

from rttools.wcet import decode
from tests.conftest import REPO_ROOT

LISTING = os.path.join(REPO_ROOT, "experiments", "exp23", "logs", "H.image.lst")


def listing_lines():
    pat = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*)$")
    for line in open(LISTING):
        m = pat.match(line)
        if m and m[3] != ".word":
            yield int(m[1], 16), int(m[2], 16), m[3], m[4]


def test_every_instruction_of_the_listing():
    n = 0
    for addr, word, op, _ in listing_lines():
        assert decode.decode(word, addr).op == op, f"{addr:08x} {word:08x} {op}"
        n += 1
    assert n > 2500


def test_operands():
    i = decode.decode(0xfe810113, 0x40000228)          # addi sp,sp,-24
    assert (i.op, i.rd, i.rs1, i.imm, i.kind) == ("addi", 2, 2, -24, "alu")
    i = decode.decode(0xfec718e3, 0x40000268)          # bne a4,a2,40000258
    assert (i.op, i.rs1, i.rs2, i.target, i.kind) == ("bne", 14, 12, 0x40000258, "branch")
    i = decode.decode(0x0e9010ef, 0x40000240)          # jal ra,40001b28
    assert i.is_call and i.target == 0x40001b28
    i = decode.decode(0x00008067, 0)                   # jalr zero,0(ra)
    assert i.is_return
    i = decode.decode(0x06d70323, 0)                   # sb a3,102(a4)
    assert (i.op, i.rs1, i.rs2, i.imm, i.width) == ("sb", 14, 13, 102, 1)
    i = decode.decode(0xff042703, 0)                   # lw a4,-16(s0)
    assert (i.op, i.rd, i.rs1, i.imm, i.width, i.signed) == ("lw", 14, 8, -16, 4, True)
    i = decode.decode(0x41000537, 0)                   # lui a0,0x41000
    assert (i.op, i.rd, i.imm & 0xFFFFFFFF) == ("lui", 10, 0x41000000)


def test_the_core_has_no_multiplier_and_no_compressed_instructions():
    with pytest.raises(decode.DecodeError, match="M extension"):
        decode.decode(0x02b50533)                      # mul a0,a0,a1
    with pytest.raises(decode.DecodeError, match="compressed"):
        decode.decode(0x00004501)                      # c.li a0,0
