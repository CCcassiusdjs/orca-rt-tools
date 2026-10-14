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
| release | IRQ_ENTRY + _isr with irq_handler -> irq4_handler (release of a source task) | 1 for a task without input edge |

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
    "ucx_noc_probe": "receive",
    "ucx_noc_receive": "receive",
    "ucx_free": "receive",
}
# calls per iteration of the tasks of weird_a.c and of rttools.ucxgen:
# ITER_BEGIN and ITER_END (include/device/cacc.h)
ITERATION_CALLS = {"set_iter_mark": 2}
HANDLERS = {"tick": "irq0_handler", "send": "irq1_handler", "rx_size": "irq2_handler",
            "rx_end": "irq3_handler", "release": "irq4_handler"}


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
    tick = isr(an, HANDLERS["tick"], {"overrides": {"dispatch": d_save.cycles + d_resume.cycles}})
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
    if source_tasks:
        out["release"] = isr(an, HANDLERS["release"])
    return out


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


def analyze(img, annotations, tasks, edges, functions, params=None, task_args=None, iteration_calls=None):
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
    kernel = kernel_terms(an, source_tasks=bool(sources))
    out = {}
    for t in tasks:
        out[t] = task_cost(an, functions[t], ins[t], outs[t], kernel, source=ins[t] == 0,
                           args=(task_args or {}).get(t), iteration_calls=iteration_calls)
    return {"kernel": kernel, "tasks": out, "params": an.params}


def write_csv(path, result):
    keys = ["body", "send", "receive", "dispatch", "send_isr", "receive_isr", "tick", "release"]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["task", "function", "t"] + keys)
        for t, r in result["tasks"].items():
            w.writerow([t, r["function"], r["t"]] + [r["terms"][k] for k in keys])
