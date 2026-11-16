"""Cycles per instruction of the HF-RISC core of the platform.

The core (pkt-sim/hw/cpu/core_rv32e/datapath.vhd) has three stages
(fetch, decode, execute) and one memory port for fetch and data
(int_control.vhd: addr_mem selects the data address while
data_access_cpu = 1). The PE has no cache: code and data are in the local
RAM of manycore_pe.sv, which returns the read data one cycle after the
address, without a wait state, and stall_i = 0. The datapath gives:

| Class | Cycles | Source in datapath.vhd |
|---|---|---|
| ALU (register or immediate, shifts) | 1 | one cycle in execute; the barrel shifter (bshifter.vhd) is combinational |
| lui, auipc | 1 | ALU |
| load, store | 3 | data_access_s: pc_next = pc_last (the fetch repeats) and inst_in_s = 0 (bubble) for the two cycles of the data access |
| conditional branch, taken | 3 | branch_taken: inst_in_s = 0 and bds = 1 (two bubbles) |
| conditional branch, not taken | 1 | no bubble |
| jal, jalr | 3 | jump_taken: two bubbles, as a taken branch |
| ecall, ebreak | 3 | except: pc_next = irq_vector and the bubbles of a jump |
| fence | 1 | decoded as an operation without effect |

pkt-sim/tests/rtl/tb_cpu_cycles.vhd measures these values on the RTL of
the core (blocks of 16 equal instructions of cpu_cycles.s; EXPECTED:
alu 1, lui 1, lw/lhu/lbu 3, sw/sh/sb 3, store and load of the
instrumentation registers 3, taken branch 3, branch not taken 1, jal 3,
call and return 6, the body of set_cacc 13, the 64-bit increment of
disp_timer 16). The sum of the costs of a sequence is its cost: each
class above stalls only the instructions behind it (block call_body and
block inc64 of the testbench equal the sums).

The core has no multiplier and no divider (control.vhd decodes no M
instruction); the analysis charges the software routines that the
compiler calls (__mulsi3, __udivsi3, __umodsi3 of arch/common/muldiv.c)
as any other function.

Interrupt entry: when the core acknowledges an interrupt (irq_ack_s),
pc_next = irq_vector and inst_in_s = 0, the redirection of a jump. The
analysis charges IRQ_ENTRY = 3 cycles (one jump) per interrupt; the
instruction that the redirection discards runs again after the return
(int_control.vhd keeps its address in irq_epc_reg) and its cost is in
the code of the interrupted task.
"""
from __future__ import annotations

CYCLES = {
    "alu": 1,
    "lui": 1,
    "load": 3,
    "store": 3,
    "branch_taken": 3,
    "branch_not_taken": 1,
    "jal": 3,
    "jalr": 3,
    "system": 3,
    "fence": 1,
}

IRQ_ENTRY = 3


def cost(instr, model=None):
    """Cycles of one instruction; a conditional branch returns the cost of
    its not-taken direction (edge costs: branch_costs)."""
    m = model or CYCLES
    if instr.kind == "branch":
        return m["branch_not_taken"]
    return m[instr.kind]


def branch_costs(model=None):
    """(taken, not taken) cycles of a conditional branch."""
    m = model or CYCLES
    return m["branch_taken"], m["branch_not_taken"]


def from_config(cycles):
    """Cost model from a mapping with the keys of the instrumentation
    section of experiments/exp23/config.json (alu, load, store, jump,
    branch_taken, branch_not_taken); missing classes keep CYCLES."""
    m = dict(CYCLES)
    for k, v in cycles.items():
        if k == "jump":
            m["jal"] = m["jalr"] = int(v)
        elif k in m:
            m[k] = int(v)
    return m
