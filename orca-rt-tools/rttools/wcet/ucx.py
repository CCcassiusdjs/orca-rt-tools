"""Task cost t(v) of a UCX-OS task on an HF-RISC PE from the static WCET of
its code and of the kernel.

The flow (paper, Section 6.1) takes t(v) per task: the demand c(v) plus the
kernel work of v on its PE (dispatch, driver calls of its sent and
received packets, payload transfer). The terms below compose t(v) for one
iteration of v under the phase model (one dispatch of each task per
phase; every task of a PE finishes within the phase, so the idle task
runs at the tick):

| Term | Static WCET of | Count per iteration |
|---|---|---|
| job | the code from the return of ucx_task_yield to its next call (rttools.wcet.analysis, job), with at most one iteration (task_cost), split into body (code of the task and its callees), send (calls of ucx_noc_send), receive (ucx_noc_probe, ucx_noc_receive, ucx_free) and the call instruction into ucx_task_yield | 1 |
| dispatch | ucx_task_yield up to the jump of longjmp (setjmp returns 0: krnl_delay_update, krnl_stack_check, krnl_schedule) plus the resume of the next task in yield (setjmp returns 1) | 1 |
| send_isr | IRQ_ENTRY + _isr with irq_handler -> irq1_handler (end of a DDMA send) | out-degree of v |
| receive_isr | 2 IRQ_ENTRY + _isr with irq2_handler (size flit: ucx_malloc) + _isr with irq3_handler (end of the packet: queue, enable_receiver) | in-degree of v |
| tick | IRQ_ENTRY + _isr with irq_handler -> irq0_handler -> timer1ctc_handler -> krnl_dispatcher -> dispatch, where dispatch costs its save path up to longjmp plus the resume of the preempted context (the idle task) | 1 |
| release | IRQ_ENTRY + _isr with irq_handler -> irq4_handler (release of a source task) | 1 for a task without input edge; 1 for every task of an image with the release by tick |

Time-triggered injection (image with ucx_noc_send_at, pkt-sim/software/
ucx-os/lib/noc_tt.c): the job hands each packet to the kernel, which
injects it at the instant of the link schedule from the compare interrupt
of TIMER1 (irq0_handler -> timer1ocr_handler) or from the tick routine; irq1
stays masked. The send_isr term of such an image is IRQ_ENTRY + _isr with
irq_handler -> irq0_handler -> timer1ocr_handler (the injection of one
packet), per output edge; kernel["send_ack_isr"] keeps the irq1 path of the
image. The tick term includes the tick routine ucx_noc_tt_tick.

Release by tick (image with ucx_phase_wait, pkt-sim/software/ucx-os/lib/
tick_release.c): the release generator fires on every PE with a task and
irq4_handler counts the phase, so the release term enters every t(v) (one
handler per phase and PE, charged to each task of the PE as the tick);
the tick term includes the tick hook ucx_app_tick that dispatch calls, the
dispatch term the interrupt state that yield keeps, and the job the wait
for the tick of the phase (ucx_phase_wait) up to the call of
ucx_task_yield. The number of dispatches per phase does not change: the
tick readies the task that the release of the data-driven code readied,
and a packet arrival does not wake a task that waits for its phase.

Interrupts (kernel without UCX_ISR_NESTING, pkt-sim/software/ucx-os/
kernel/sched.c): every handler runs with interrupts disabled up to the
return of _isr, so each term above holds one handler and no handler runs
inside another; the tick term has no _interrupt_tick in dispatch, the
dispatch term has the save and the restore of the interrupt state in
yield (every image, not only the release by tick), and the receive and
release terms have no _di/_ei in the handlers. The first entry of a task
(_task_start, hal.c) runs once per task, before its first phase, and is
not a term. The image of a run up to r11 (kernel with UCX_ISR_NESTING)
has _ei in irq2_handler, irq3_handler and irq4_handler and
_interrupt_tick in dispatch; the analysis reads the code of the image in
both cases (experiments/wcet/images/tick: previous kernel;
experiments/wcet/images/isr: this kernel with the crt0.s of tag
r11-rc3). The crt0.s of this tree (experiments/wcet/images/guard) adds
the return test to _isr, in every interrupt term, and the read back of
IRQ_STATUS to _interrupt_set(0), in the terms that disable interrupts
(dispatch; the _di at the entry of irq2_handler and irq3_handler in
receive); the read back repeats only after
an interrupt taken in its wait (bound 1 in wcet/ucx-os.json), and that
pass, 16 cycles per such interrupt, is not in the terms.

The flow composes t(v) before the mapping (step 1 clusters with t(v)), so
the terms do not depend on the mapping: every edge counts as an edge
between PEs (the driver path of ucx_noc_send is the maximum of its local
and remote branches), and each task carries one tick of its PE. On a PE
with k tasks, the sum of t(v) charges the tick k times, against one
handler per phase.
"""
from __future__ import annotations

import csv
import hashlib

from rttools.wcet import timing
from rttools.wcet.analysis import ENV0, Analyzer, WcetError

CUT = ("ucx_task_yield",)
CATEGORIES = {
    "ucx_noc_send": "send",
    "ucx_noc_send_at": "send",
    "tt_send": "send",            # ucx_noc_send_at of the generated applications (rttools.ucxgen.emit)
    "ucx_noc_probe": "receive",
    "ucx_noc_receive": "receive",
    "ucx_free": "receive",
}
# calls per iteration of the tasks of weird_a.c and of rttools.ucxgen:
# ITER_BEGIN and ITER_END (include/device/cacc.h)
ITERATION_CALLS = {"set_iter_mark": 2}
HANDLERS = {"tick": "irq0_handler", "send": "irq1_handler", "rx_size": "irq2_handler",
            "rx_end": "irq3_handler", "release": "irq4_handler", "inject": "irq0_handler"}
# timer handlers that irq0_handler calls (arch/riscv/hf-riscv-e/interrupt.c,
# timer_vector): the tick (TIMER1 CTC) and the compare interrupt of the
# time-triggered injection (TIMER1 OCR, lib/noc_tt.c)
TIMER_HANDLERS = {"tick": "timer1ctc_handler", "inject": "timer1ocr_handler"}


def _resume_start(an, fname, setjmp="setjmp"):
    """Address of the block after the call of setjmp in `fname` (the
    return point of longjmp)."""
    cfg = an.cfg(fname)
    for b in sorted(cfg.blocks):
        blk = cfg.blocks[b]
        if blk.term == "call" and blk.callee == setjmp:
            return blk.end
    raise WcetError(f"{fname}: no call of {setjmp}")


def switch(an, fname):
    """(save, resume) cycles of a context switch in `fname` (yield or
    dispatch): save = the path where setjmp returns 0, up to the jump of
    longjmp; resume = the path from the return of setjmp with a0 = 1 to
    the return of `fname`."""
    env = ENV0.with_(returns={"setjmp": 0}, noreturn={"longjmp"})
    save = an.function(fname, env=env)
    resume = an.function(fname, start=_resume_start(an, fname), init={"a0": 1})
    return save, resume


def isr(an, handler, extra=None):
    """IRQ_ENTRY + the WCET of _isr when irq_handler calls `handler`."""
    icalls = {"irq_handler": ([handler], 1)}
    kw = dict(extra or {})
    icalls.update(kw.pop("icalls", {}))
    env = ENV0.with_(icalls=icalls, **kw)
    r = an.function("_isr", env=env)
    return timing.IRQ_ENTRY + r.cycles


def kernel_terms(an, source_tasks=True):
    """Kernel terms of t(v) (cycles) and their parts."""
    y_save, y_resume = switch(an, "yield")
    # ucx_task_yield is a jump to yield (kernel/sched.c, _yield alias)
    entry = an.function("ucx_task_yield", env=ENV0.with_(returns={"setjmp": 0}, noreturn={"longjmp"}))
    d_save, d_resume = switch(an, "dispatch")
    tt = tt_image(an.img)
    tick = isr(an, HANDLERS["tick"], {"overrides": {"dispatch": d_save.cycles + d_resume.cycles},
                                      "icalls": {"irq0_handler": ([TIMER_HANDLERS["tick"]], 1)}} if tt else
               {"overrides": {"dispatch": d_save.cycles + d_resume.cycles}})
    out = {
        "yield_save": entry.cycles,
        "yield_resume": y_resume.cycles,
        "dispatch": entry.cycles + y_resume.cycles,
        "tick_dispatch_save": d_save.cycles,
        "tick_dispatch_resume": d_resume.cycles,
        "tick": tick,
        "send_isr": isr(an, HANDLERS["send"]),
        "receive_isr_size": isr(an, HANDLERS["rx_size"]),
        "receive_isr_end": isr(an, HANDLERS["rx_end"]),
    }
    out["receive_isr"] = out["receive_isr_size"] + out["receive_isr_end"]
    if tt:
        out["send_ack_isr"] = out["send_isr"]
        out["send_isr"] = isr(an, HANDLERS["inject"], {"icalls": {"irq0_handler": ([TIMER_HANDLERS["inject"]], 1)}})
    if source_tasks:
        out["release"] = isr(an, HANDLERS["release"])
    return out


def tt_image(img):
    """True for an image with the time-triggered injection (lib/noc_tt.c:
    ucx_noc_send_at)."""
    return img.has_function("ucx_noc_send_at")


# cycles of the interrupt controller from the rise of a cause to the request
# to the core (pkt-sim/hw/cpu/core_rv32e/int_control.vhd: irq_done ->
# irq_idle after the return of _isr, then irq_idle -> irq_int -> irq); the
# entry of the core is IRQ_ENTRY of each handler term
IRQ_DECISION = 4
# step of TIMER1 (hal.c, prescaler 16): the injection instant of the table
# is the instant of the link schedule rounded up to a multiple of it
TIMER_STEP = 16


def _section_analyzer(an, functions):
    """Analyzer of `an` with one pass of the loops of `functions`: the
    loop that blocks in ucx_task_yield runs its test once on the path that
    ends at the call and once on the path from the return of the call."""
    from rttools.wcet.annotations import Annotations
    a = Annotations()
    a.params = dict(an.ann.params)
    a.exclude = set(an.ann.exclude)
    a.sections = list(an.ann.sections)
    a.funcs = {f: {k: list(v) for k, v in d.items()} for f, d in an.ann.funcs.items()}
    for f in functions:
        d = a.funcs.setdefault(f, {"loops": [], "indirect_jumps": [], "indirect_calls": []})
        d["loops"] = [{"select": "all", "bound": 1}]
    return Analyzer(an.img, a, model=an.model, params=an.params)


def _yield_section(an, fname, kernel):
    """Cycles with interrupts disabled of a function that disables them
    and blocks in ucx_task_yield (ucx_phase_wait, wait_release of a
    time-triggered application): the path from the entry to the call of
    ucx_task_yield, the switch (kernel["yield_switch"]) and the path from
    the return of the call to the return of the function."""
    an = _section_analyzer(an, [fname])
    # the path ends at the call; the switch is the yield_switch term
    env = ENV0.with_(noreturn={"ucx_task_yield"}, overrides={"ucx_task_yield": 0})
    head = an.function(fname, env=env)
    tail = an.function(fname, env=env, start=_resume_start(an, fname, "ucx_task_yield"))
    return {"head": head.cycles, "tail": tail.cycles, "cycles": head.cycles + kernel["yield_switch"] + tail.cycles}


def sections(an, kernel, extra=()):
    """Sections with interrupts disabled outside the interrupt handlers
    (cycles of the longest path of each):

    | Section | Path |
    |---|---|
    | yield | ucx_task_yield up to the jump of longjmp (yield_save) and the longest resume of the next task: its return from yield (yield_resume) or, for a task that the tick preempted, the return through dispatch, irq0_handler, irq_handler and _isr (at most tick - tick_dispatch_save) |
    | ucx_phase_wait | lib/tick_release.c: _di, the test of the phase, the yield, and the test after the return up to _ei (_yield_section) |
    | tt_insert | lib/noc_tt.c (ucx_noc_send_at between _di and _ei): the insertion into the queue, the injection when the instant has passed, and the calls of _interrupt_set around it |
    | `extra` | functions of the application (`{"function": f, "yield": bool}`): with yield as ucx_phase_wait, else the whole function |

    Returns {"yield_switch", "sections": {name: cycles}, "parts", "max", "tail"}:
    "tail" is the longest path after the return of a yield of a section
    (the code that a task resumed by the tick runs before it enables
    interrupts)."""
    k = dict(kernel)
    k["yield_switch"] = kernel["yield_save"] + max(kernel["yield_resume"],
                                                   kernel["tick"] - kernel["tick_dispatch_save"])
    out = {"yield": k["yield_switch"]}
    parts = {}
    tail = 0
    img = an.img
    yields = ["ucx_phase_wait"] if img.has_function("ucx_phase_wait") else []
    whole = ["tt_insert"] if img.has_function("tt_insert") else []
    for e in extra:
        (yields if e.get("yield") else whole).append(e["function"])
    for f in yields:
        r = _yield_section(an, f, k)
        out[f] = r["cycles"]
        parts[f] = r
        tail = max(tail, r["tail"])
    di = an.function("_interrupt_set").cycles
    for f in whole:
        out[f] = an.function(f).cycles + (2 * di if f == "tt_insert" else 0)
    return {"yield_switch": k["yield_switch"], "sections": out, "parts": parts, "max": max(out.values()),
            "tail": tail}


def ni_terms(kernel, secs):
    """Bounds of the work of the network interface of one packet between
    PEs in an image with the time-triggered injection (cycles):

    | Term | Bound | Interval |
    |---|---|---|
    | inject | TIMER_STEP - 1 + IRQ_DECISION + B + send_isr | from the instant s of the link schedule to the return of the injection handler (the DDMA takes the header before) |
    | rx_size | IRQ_DECISION + B + receive_isr_size | from the size flit at the target DDMA to the return of irq2_handler, after it gives the buffer to the DDMA (credit withheld meanwhile) |
    | rx_end | IRQ_DECISION + B + receive_isr_end | from the last flit to the return of irq3_handler, after the DDMA handshake that lets the next packet in |
    | ni_wait | inject + rx_size + rx_end | the term of the occupancy o_i beyond ZLL + w_h (m + 1) |

    B = max(section) + release + tick + resume bounds what the CPU of a PE
    runs with interrupts disabled before it starts the handler of a cause
    of the packet. The handlers are not nested; a cause waits for the
    activity with interrupts disabled in progress (a section, or an _isr),
    then the CPU enters _isr and serves the pending causes in the order of
    their bits (irq_handler), the timer (bit 0) first: when that is the
    tick, dispatch switches to another task, which runs at most `resume`
    (the return of yield and the rest of the section that called it, or
    _task_start) before it enables interrupts. The network interface of a
    PE serves one packet at a time in the link schedule (rttools/modules/
    routing/router.py, NI resource), and each term below ends with the
    return of its handler, so the handlers of the other packets of the PE
    complete outside the interval of this packet; in that interval the
    other causes of the PE are one tick and one release interrupt (each
    interval is shorter than the tick period). resume = yield_resume +
    the longest path of a yield section after its call (sections, "tail").
    rx_end counts from the later of the last flit and the return of
    irq2_handler of the packet, which is at most rx_size + p + 1 cycles
    after the size flit, so the occupancy takes rx_size + rx_end."""
    resume = kernel["yield_resume"] + secs["tail"]
    b = secs["max"] + kernel.get("release", 0) + kernel["tick"] + resume
    inject = TIMER_STEP - 1 + IRQ_DECISION + b + kernel["send_isr"]
    rx_size = IRQ_DECISION + b + kernel["receive_isr_size"]
    rx_end = IRQ_DECISION + b + kernel["receive_isr_end"]
    return {"blocking": b, "resume": resume, "inject": inject, "rx_size": rx_size, "rx_end": rx_end,
            "ni_wait": inject + rx_size + rx_end, "timer_step": TIMER_STEP, "irq_decision": IRQ_DECISION}


def task_cost(an, fname, n_in, n_out, kernel, source=False, args=None, iteration_calls=None):
    """t(v) of the task whose function is `fname` (dict of terms).

    The job runs from the return of ucx_task_yield to the next call of
    ucx_task_yield (one dispatch). One job serves one iteration: the
    calls of `iteration_calls` (default ITERATION_CALLS: the two
    iteration markers of the iteration) and the receives (one packet per
    input edge, n_in calls of ucx_noc_receive) bound the job. A job that
    takes a packet of the next iteration leaves that packet out of the
    next job, so n_in receives per job bound the receives of an
    iteration on average."""
    limits = [({g}, n) for g, n in (iteration_calls or ITERATION_CALLS).items()]
    limits.append(({"ucx_noc_receive"}, n_in))
    job = an.job(fname, CUT, categories=CATEGORIES, args=args, limits=limits)
    cat = job.categories
    terms = {
        "body": cat.get("body", 0),
        "send": cat.get("send", 0),
        "receive": cat.get("receive", 0),
        "dispatch": cat.get("dispatch", 0) + kernel["dispatch"],
        "send_isr": n_out * kernel["send_isr"],
        "receive_isr": n_in * kernel["receive_isr"],
        "tick": kernel["tick"],
        "release": kernel.get("release", 0) if source else 0,
    }
    other = sum(v for k, v in cat.items() if k not in ("body", "send", "receive", "dispatch"))
    if other:
        terms["body"] += other
    if sum(cat.values()) != job.cycles:
        raise WcetError(f"{fname}: categories {sum(cat.values())} differ from the job WCET {job.cycles}")
    sends = [{"addr": f"{c.addr:08x}", "args": {f"a{r - 10}": v for r, v in sorted(c.args.items())},
              "cycles": c.cycles, "count": c.count} for c in job.calls if c.callee == "ucx_noc_send"]
    return {
        "function": fname,
        "t": sum(terms.values()),
        "job": job.cycles,
        "terms": terms,
        "in_edges": n_in,
        "out_edges": n_out,
        "source": source,
        "calls": {g: n for g, n in sorted(job.call_counts.items()) if n},
        "send_calls": sends,
        "loops": [{"function": f, "header": f"{h:08x}", "bound": b, "source": s} for f, h, b, s in job.loops],
    }


def read_graph(csv_path):
    """(tasks in file order, edges) of an application CSV."""
    from rttools.ucxgen.model import read_csv
    tasks, flows, _ = read_csv(csv_path)
    return [t["label"] for t in tasks], [(f["source"], f["target"]) for f in flows]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def analyze(img, annotations, tasks, edges, functions, params=None, task_args=None, iteration_calls=None,
            sections_extra=()):
    """t(v) of every task. `tasks`: labels; `edges`: (u, v); `functions`:
    label -> task function of the image; `task_args`: label -> {register:
    value} at the entry of the task function (none for UCX-OS tasks)."""
    an = Analyzer(img, annotations, params=params)
    ins = {t: 0 for t in tasks}
    outs = {t: 0 for t in tasks}
    for u, v in edges:
        outs[u] += 1
        ins[v] += 1
    sources = [t for t in tasks if ins[t] == 0]
    tick_release = tick_release_image(img)
    kernel = kernel_terms(an, source_tasks=bool(sources) or tick_release)
    out = {}
    for t in tasks:
        out[t] = task_cost(an, functions[t], ins[t], outs[t], kernel, source=ins[t] == 0 or tick_release,
                           args=(task_args or {}).get(t), iteration_calls=iteration_calls)
    res = {"kernel": kernel, "tasks": out, "params": an.params, "release_rule": "tick" if tick_release else "data"}
    if tt_image(img):
        secs = sections(an, kernel, list(an.ann.sections) + list(sections_extra))
        res["injection"] = "tt"
        res["sections"] = secs
        # the release interrupt reaches every PE of the release mask, also
        # the PEs without a source task: B counts it
        k = kernel if "release" in kernel else dict(kernel, release=isr(an, HANDLERS["release"]))
        res["ni"] = ni_terms(k, secs)
    else:
        res["injection"] = "finish"
    return res


def tick_release_image(img):
    """True for an image built with the release by tick (lib/tick_release.c:
    ucx_phase_wait)."""
    return img.has_function("ucx_phase_wait")


def write_csv(path, result):
    keys = ["body", "send", "receive", "dispatch", "send_isr", "receive_isr", "tick", "release"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task", "function", "t"] + keys)
        for t, r in result["tasks"].items():
            w.writerow([t, r["function"], r["t"]] + [r["terms"][k] for k in keys])
