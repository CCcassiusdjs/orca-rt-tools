"""Upper bound of the cycles that the instrumentation writes add to the
CPU time measured in the RTL simulation of exp-23.

The kernel writes the instrumentation registers of manycore_pe.sv in each
dispatch (kernel/sched.c, krnl_schedule: set_cacc, set_counter_1,
set_counter_2) and in each packet event (lib/noc.c: set_counter_3 in
ucx_noc_send, set_counter_4 in the receive interrupt and in the local
delivery of ucx_noc_send); the RTL prints one log line per write to
counter 2 (`scheduled`), 3 (`->`) and 4 (`<-`). The measured CPU time
contains these writes.

Input: two listings (objdump --disassemble -Mno-aliases) of the image that
experiments/exp23/build_sw.sh builds, one with the writes and one with
-DUCX_NO_INSTRUMENTATION. For each function that calls an
instrumentation function (config `instrumentation.callees`):

| Step | Rule |
|---|---|
| Unmatched instructions | difflib alignment of the mnemonic sequences of the function in both listings; the instructions of the instrumented listing outside the equal blocks are the cost of the instrumentation in the caller (argument setup, the 64-bit counter of sched.c, calls, the stack frame and the reloads that the calls require) |
| Loop check | no unmatched instruction lies on a cycle of the control-flow graph of the function, so each one runs at most once per call |
| Callee | every instruction of each called instrumentation function (straight-line code, checked) runs once per call site |
| Other functions | the remaining functions of both listings have equal mnemonic sequences (checked); the instrumentation functions exist only in the instrumented listing |
| Assumption | a matched pair of instructions runs as often in both images (the writes do not change the control flow of the kernel) |

Cycles per instruction class (config `instrumentation.cycles`) come from
pkt-sim/tests/rtl/tb_cpu_cycles.vhd (HF-RISC core on the bus of
manycore_pe.sv, stall_in = 0, no wait state on the instrumentation
registers). A branch costs the larger of taken and not taken.

Charge of each function to the logged events (config
`instrumentation.events`, kind -> function that writes the logged
register, in this order):

| Case | Charge |
|---|---|
| A call to a writer lies on every path from the entry to a return of the function (first such kind) | The whole cost of the function (all unmatched instructions, also those of paths that exclude each other, and all instrumentation calls) to each event of that kind: each call of the function that returns logs one such event |
| Every path from the entry to an exit passes through a call to a writer of a kind or ends with a tail call (jal zero) of a function charged whole to that kind (ucx_noc_send_at of lib/noc_tt.c: set_counter_3 for a remote target, the tail call of ucx_noc_send for a local one) | The whole cost of the function plus the largest charge of those tail-called functions to that kind: each call logs one such event, and an event of the tail-call path runs the instrumentation of both functions |
| Otherwise | Each unmatched instruction must lie in a basic block with a call to a writer (it runs if and only if that call runs); the cost of the unmatched instructions and calls of those blocks goes to each event of the kind of the writer |

The cost of an event kind is the largest charge of the functions to it. The
bound of a cluster in an iteration is the sum of event count times event
cost, from the events of its PE in each hyperperiod window divided by the
iterations of the window; the percent divides it by the measured CPU time
of the same window."""
from __future__ import annotations

import difflib
import os
import re

RE_FUNC = re.compile(r"^([0-9a-f]+) <([^>]+)>:\s*$")
RE_INSN = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(\S+)\s*(.*?)\s*$")
RE_TARGET = re.compile(r"(?:^|,)\s*([0-9a-f]+)(?:\s+<[^>]*>)?\s*$")

LOADS = {"lb", "lh", "lw", "lbu", "lhu"}
STORES = {"sb", "sh", "sw"}
BRANCHES = {"beq", "bne", "blt", "bge", "bltu", "bgeu",
            "beqz", "bnez", "blez", "bgez", "bltz", "bgtz", "bgt", "ble", "bgtu", "bleu"}
JUMPS = {"jal", "jalr", "j", "jr", "ret", "call", "tail"}
ALU = {"lui", "auipc", "addi", "slti", "sltiu", "xori", "ori", "andi", "slli", "srli", "srai",
       "add", "sub", "sll", "slt", "sltu", "xor", "srl", "sra", "or", "and",
       "li", "mv", "nop", "not", "neg", "seqz", "snez", "sltz", "sgtz"}


class Insn:
    __slots__ = ("addr", "mnemonic", "operands")

    def __init__(self, addr, mnemonic, operands):
        self.addr, self.mnemonic, self.operands = addr, mnemonic, operands

    def target(self):
        """Address of a direct branch or jal, else None."""
        if self.mnemonic in BRANCHES or self.mnemonic in ("jal", "j", "call", "tail"):
            m = RE_TARGET.search(self.operands.split("#")[0])
            return int(m.group(1), 16) if m else None
        return None

    def callee(self):
        """Symbol of a direct call (jal ra / call), else None."""
        if self.mnemonic == "call" or (self.mnemonic == "jal" and self.operands.startswith("ra,")):
            m = re.search(r"<([^>+]+)>", self.operands)
            return m.group(1) if m else None
        return None

    def text(self):
        return f"{self.addr:08x} {self.mnemonic} {self.operands}".rstrip()


def parse_listing(path):
    """{function: [Insn]} of an objdump listing (code sections)."""
    out = {}
    cur = None
    with open(path, errors="replace") as f:
        for line in f:
            m = RE_FUNC.match(line)
            if m:
                cur = m.group(2)
                out[cur] = []
                continue
            if line.startswith("Disassembly of section"):
                cur = None
                continue
            m = RE_INSN.match(line)
            if m and cur is not None:
                out[cur].append(Insn(int(m.group(1), 16), m.group(3), m.group(4)))
    return out


def insn_class(mnemonic):
    if mnemonic in LOADS:
        return "load"
    if mnemonic in STORES:
        return "store"
    if mnemonic in BRANCHES:
        return "branch"
    if mnemonic in JUMPS:
        return "jump"
    if mnemonic in ALU:
        return "alu"
    raise ValueError("instruction without a cycle class: " + mnemonic)


def class_cycles(table):
    """Cycles per class from config instrumentation.cycles (a branch costs
    the larger of taken and not taken)."""
    return {"alu": table["alu"], "load": table["load"], "store": table["store"], "jump": table["jump"],
            "branch": max(table["branch_taken"], table["branch_not_taken"])}


def cycles_of(insns, cyc):
    return sum(cyc[insn_class(i.mnemonic)] for i in insns)


def successors(insns, k):
    """Indices of the successors of instruction k in its function (calls
    return to the next instruction; ret and indirect jumps leave)."""
    i = insns[k]
    index = {x.addr: n for n, x in enumerate(insns)}
    nxt = [k + 1] if k + 1 < len(insns) else []
    mn = i.mnemonic
    if mn in BRANCHES:
        t = i.target()
        return nxt + ([index[t]] if t in index else [])
    if i.callee() is not None or (mn == "jalr" and i.operands.startswith("ra,")):
        return nxt
    if mn in ("jal", "j", "tail"):
        t = i.target()
        return [index[t]] if t in index else []
    if mn in ("jalr", "jr", "ret"):
        return []
    return nxt


def in_loop(insns):
    """Set of indices that lie on a cycle of the control-flow graph."""
    succ = [successors(insns, k) for k in range(len(insns))]
    loop = set()
    for k in range(len(insns)):
        seen, stack = set(), list(succ[k])
        while stack:
            n = stack.pop()
            if n == k:
                loop.add(k)
                break
            if n not in seen:
                seen.add(n)
                stack.extend(succ[n])
    return loop


def is_exit(i):
    """Return or indirect jump (leaves the function)."""
    return i.mnemonic in ("ret", "jr") or (i.mnemonic == "jalr" and not i.operands.startswith("ra,"))


def is_call(i):
    return i.callee() is not None or (i.mnemonic == "jalr" and i.operands.startswith("ra,"))


def blocks(insns):
    """Basic block index of each instruction (a call does not end a block:
    it returns to the next instruction)."""
    index = {x.addr: n for n, x in enumerate(insns)}
    leaders = {0}
    for k, i in enumerate(insns):
        t = i.target()
        if t in index and not is_call(i):
            leaders.add(index[t])
        if (i.mnemonic in BRANCHES or i.mnemonic in JUMPS) and not is_call(i) and k + 1 < len(insns):
            leaders.add(k + 1)
    out, b = [], -1
    for k in range(len(insns)):
        if k in leaders:
            b += 1
        out.append(b)
    return out


def on_every_return_path(insns, k):
    """True when every path from the entry to an exit passes through
    instruction k (no exit is reachable from the entry without k)."""
    return covers_every_exit(insns, {k})


def covers_every_exit(insns, ks):
    """True when every path from the entry to an exit (return, indirect
    jump or jump out of the function) passes through an instruction of
    `ks`."""
    if 0 in ks:
        return True
    seen, stack = {0}, [0]
    while stack:
        n = stack.pop()
        if is_exit(insns[n]) or not successors(insns, n):
            return False
        for s in successors(insns, n):
            if s not in ks and s not in seen:
                seen.add(s)
                stack.append(s)
    return True


def tail_callee(insns, k):
    """Symbol of a jump out of the function (jal zero, j, tail) at
    instruction k, else None."""
    i = insns[k]
    if not (i.mnemonic in ("j", "tail") or (i.mnemonic == "jal" and i.operands.startswith("zero,"))):
        return None
    if i.target() in {x.addr for x in insns}:
        return None
    m = re.search(r"<([^>+]+)>", i.operands)
    return m.group(1) if m else None


def unmatched(on, off):
    """Indices of the instructions of `on` outside the equal blocks of the
    alignment of the mnemonic sequences of `on` and `off`."""
    sm = difflib.SequenceMatcher(None, [i.mnemonic for i in on], [i.mnemonic for i in off], autojunk=False)
    out = []
    for tag, i1, i2, _, _ in sm.get_opcodes():
        if tag in ("replace", "delete"):
            out.extend(range(i1, i2))
    return out


def callee_cost(name, funcs, cyc):
    body = funcs[name]
    for k, i in enumerate(body):
        if i.mnemonic in BRANCHES or (i.mnemonic in JUMPS and k != len(body) - 1):
            raise ValueError(f"instrumentation function {name} is not straight-line code ({i.text()})")
    return {"instructions": len(body), "cycles": cycles_of(body, cyc), "code": [i.text() for i in body]}


def function_costs(on_funcs, off_funcs, callees, writers, cyc):
    """Cost of the instrumentation in each function of `on_funcs` that
    calls a function of `callees`, and its charge to the event kinds
    (`writers`: kind -> writer function, in charge order); checks of the
    module doc."""
    missing = [c for c in callees if c not in on_funcs]
    if missing:
        raise ValueError("instrumentation functions missing in the listing: " + ", ".join(missing))
    left = [c for c in callees if c in off_funcs]
    if left:
        raise ValueError("instrumentation functions in the listing without instrumentation: " + ", ".join(left))
    cal = {c: callee_cost(c, on_funcs, cyc) for c in callees}
    kind_of = {w: k for k, w in writers.items()}
    callers = {n: insns for n, insns in on_funcs.items() if any(i.callee() in callees for i in insns)}
    changed = sorted(n for n in on_funcs if n not in callers and n not in callees
                     and (n not in off_funcs or [i.mnemonic for i in on_funcs[n]] != [i.mnemonic for i in off_funcs[n]]))
    changed += sorted(n for n in off_funcs if n not in on_funcs)
    if changed:
        raise ValueError("functions without instrumentation calls differ between the listings: " + ", ".join(changed))

    def cost(insns):
        """(instructions, cycles) of unmatched instructions plus the bodies
        of the instrumentation functions they call."""
        n = len(insns) + sum(cal[i.callee()]["instructions"] for i in insns if i.callee() in cal)
        c = cycles_of(insns, cyc) + sum(cal[i.callee()]["cycles"] for i in insns if i.callee() in cal)
        return n, c

    out = {}
    # the functions whose paths end in a tail call of another caller come
    # after it (their charge adds the charge of the tail-called function)
    tails = {n: {tail_callee(on, k) for k in range(len(on))} & set(callers) - {n} for n, on in callers.items()}
    order = sorted(callers, key=lambda n: (bool(tails[n]), n))
    for name in order:
        on = callers[name]
        if name not in off_funcs:
            raise ValueError(f"function {name} missing in the listing without instrumentation")
        off = off_funcs[name]
        um = unmatched(on, off)
        loops = in_loop(on)
        bad = [on[k].text() for k in um if k in loops]
        if bad:
            raise ValueError(f"{name}: instrumentation instructions inside a loop: " + "; ".join(bad))
        calls = [k for k, i in enumerate(on) if i.callee() in callees]
        missed = [on[k].text() for k in calls if k not in um]
        if missed:
            raise ValueError(f"{name}: instrumentation calls matched to the listing without instrumentation: "
                             + "; ".join(missed))
        caller = [on[k] for k in um]
        n_all, c_all = cost(caller)
        charges = {}
        whole = next((kind for kind, w in writers.items()
                      if any(on[k].callee() == w and on_every_return_path(on, k) for k in calls)), None)
        tail = None
        if whole is None:
            for kind, w in writers.items():
                via = {k: tail_callee(on, k) for k in range(len(on))}
                via = {k: t for k, t in via.items() if t in out and out[t]["rule"].startswith("every_return_path")
                       and kind in out[t]["charges"]}
                ks = {k for k in calls if on[k].callee() == w} | set(via)
                if via and covers_every_exit(on, ks):
                    tail = (kind, sorted(set(via.values())))
                    break
        if whole is not None:
            rule = "every_return_path"
            charges[whole] = {"instructions": n_all, "cycles": c_all}
        elif tail is not None:
            kind, targets = tail
            rule = "every_return_path_with_tail_call"
            worst = max(targets, key=lambda t: (out[t]["charges"][kind]["cycles"], t))
            charges[kind] = {"instructions": n_all + out[worst]["charges"][kind]["instructions"],
                             "cycles": c_all + out[worst]["charges"][kind]["cycles"]}
        else:
            rule = "block"
            blk = blocks(on)
            kinds_of_block = {}
            for k in calls:
                if on[k].callee() in kind_of:
                    kinds_of_block.setdefault(blk[k], set()).add(kind_of[on[k].callee()])
            alone = [on[k].text() for k in um if blk[k] not in kinds_of_block]
            if alone:
                raise ValueError(f"{name}: instrumentation instructions outside the blocks of the logged writes: "
                                 + "; ".join(alone))
            for kind in writers:
                sel = [on[k] for k in um if kind in kinds_of_block[blk[k]]]
                if sel:
                    ni, ci = cost(sel)
                    charges[kind] = {"instructions": ni, "cycles": ci}
        out[name] = {
            "calls": [on[k].callee() for k in calls],
            "caller_instructions": len(caller),
            "caller_cycles": cycles_of(caller, cyc),
            "instructions": n_all,
            "cycles": c_all,
            "instructions_with": len(on),
            "instructions_without": len(off),
            "rule": rule,
            "tail_calls": tail[1] if tail is not None else [],
            "charges": charges,
            "caller_code": [i.text() for i in caller],
        }
    return out, cal


def event_costs(on_path, off_path, cfg_instr):
    """Cost of each event kind (config instrumentation.events: kind ->
    function that writes the logged register): the largest charge of the
    functions to it (0 when no function charges it)."""
    cyc = class_cycles(cfg_instr["cycles"])
    on_funcs, off_funcs = parse_listing(on_path), parse_listing(off_path)
    writers = cfg_instr["events"]
    funcs, callees = function_costs(on_funcs, off_funcs, cfg_instr["callees"], writers, cyc)
    events = {}
    for kind, writer in writers.items():
        users = sorted(n for n, f in funcs.items() if kind in f["charges"])
        worst = max(users, key=lambda n: (funcs[n]["charges"][kind]["cycles"], n)) if users else None
        events[kind] = {"writer": writer, "functions": users, "worst_function": worst,
                        "instructions": funcs[worst]["charges"][kind]["instructions"] if worst else 0,
                        "cycles": funcs[worst]["charges"][kind]["cycles"] if worst else 0}
    return {"cycles_per_class": cyc, "events": events, "functions": funcs, "callees": callees}


def event_counts(tr, pe, a, b):
    """Dispatches (`scheduled` lines), sends (`->`) and receives (`<-`) of
    PE `pe` in [a, b) (raw units of the trace)."""
    return {"dispatch": sum(1 for s in tr.lane_slices(pe) if a <= s.start < b),
            "send": sum(1 for m in tr.lane_marks(pe) if m.kind == "send" and a <= m.time < b),
            "receive": sum(1 for m in tr.lane_marks(pe) if m.kind == "recv" and a <= m.time < b)}


def bound(tr, cfg, windows, measured, costs):
    """Bound of each cluster: events per iteration, cycles per iteration
    and percent of the measured CPU time per iteration, per hyperperiod
    window and maximum (measured = exp23.cpu_per_iteration)."""
    n = cfg["iterations_per_hyperperiod"]
    ev = costs["events"]
    out = {}
    for pe, cluster in cfg["clusters"].items():
        per = []
        for w, (a, b) in enumerate(windows):
            c = event_counts(tr, pe, a, b)
            cyc = sum(c[k] * ev[k]["cycles"] for k in ev) / n
            m = measured[cluster]["per_hyperperiod"][w]
            per.append({"events_per_iteration": {k: c[k] / n for k in ev}, "cycles": cyc,
                        "percent": 100 * cyc / m})
        worst = max(per, key=lambda p: p["percent"])
        out[cluster] = {"per_hyperperiod": per, "max_cycles": max(p["cycles"] for p in per),
                        "max_percent": worst["percent"],
                        "events_per_iteration_at_max": worst["events_per_iteration"]}
    return out


def analyze(tr, cfg, windows, measured, on_path, off_path):
    """metrics.json block `instrumentation`."""
    costs = event_costs(on_path, off_path, cfg["instrumentation"])
    clusters = bound(tr, cfg, windows, measured, costs)
    worst = max(clusters, key=lambda c: clusters[c]["max_percent"])
    return {"listing": os.path.basename(on_path), "listing_without": os.path.basename(off_path),
            "cycles_per_class": costs["cycles_per_class"],
            "events": costs["events"], "functions": costs["functions"],
            "callees": {k: {"instructions": v["instructions"], "cycles": v["cycles"]}
                        for k, v in costs["callees"].items()},
            "clusters": clusters, "max_percent": clusters[worst]["max_percent"], "max_cluster": worst}
