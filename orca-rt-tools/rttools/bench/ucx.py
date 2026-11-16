"""ORT/BENCH: one PE under the UCX-OS kernel with a periodic tick and
time-triggered tasks (several release periods).

The engine of rttools/bench/engine.py runs one job per task with a
quantum that restarts at each event; this module follows the rules of the
UCX-OS kernel (pkt-sim/software/ucx-os) instead, so the sequence of a PE
over a hyperperiod can contain jobs that span several ticks.

| Rule | Kernel source |
|---|---|
| The tasks of the PE form a circular list in creation order after the idle task (position 0) | kernel/ucx.c, ucx_task_add |
| The tick interrupt fires every P cycles at absolute instants 0, P, 2P, ... and calls the scheduler; the running task becomes ready | arch/riscv/hf-riscv-e/hal.c (timer1ctc_handler), kernel/sched.c (dispatch, krnl_schedule(0)) |
| The scheduler advances from the current position to the next ready task other than the idle task; it returns to the current task when no other task is ready, and runs the idle task when no task is ready | kernel/sched.c, krnl_schedule |
| A task that finishes its job blocks and yields; the scheduler then advances from its position | kernel/sched.c, yield (krnl_schedule(1)) |
| The jobs of the tick are released before the scheduler of that tick runs (tick hook of the generated application) | kernel/sched.c, dispatch (UCX_APP_TICK) |
| A task with a pending release when its job finishes starts the next job without a scheduler event | run loop of the generated application (rttools/ucxgen/emit.py) |

Task v has the cost c^(v) in cycles (it includes the scheduler event that
dispatches the job), a period of k_v ticks and an offset o_v (0 <= o_v <
k_v): it releases job j at tick o_v + j k_v. Each scheduler event costs
`sigma` cycles of the dispatched task: the first dispatch of a job is part
of c^(v), each later dispatch of the same job (after a preemption, or
the tick that lets it continue) adds sigma to its remaining work. The
start S of a job is its first dispatch plus sigma (the instant at which
the job reads its inputs, as estimate.sequence); the finish F is the end
of its last slice.

Platform accounting (`tick_sigma`, for the check of the bound): each tick
costs its event to the job that it dispatches (the tick interrupt, the
save of the running context and the resume of the dispatched one: tick
term of rttools/wcet/ucx.py), and each job carries its own work and the
switch at its end (its yield and the resume of the next task: dispatch
term), so a dispatch at the end of a job costs nothing more and a job
that starts there reads its inputs at once. The model (default
accounting) charges c^(v) with one dispatch and sigma per later dispatch;
with c^(v) >= work + dispatch term + tick term (the static t(v) holds the
three) and sigma >= tick term, a simulation with the platform accounting
and the table of the model ends every job at or before its F
(tests/test_tick_owner.py; the hook in C: pkt-sim/software/ucx-os/tests/host/
test_car_full_tt.c); without the table, a job that ends early can
move a later job by a whole phase.

When a completion and a tick fall on the same cycle, the completion is
handled first (the released jobs of the tick are not ready yet), and the
tick then schedules from the position that the completion left.

The position that each tick dispatches (`owners`: 0 for the idle task)
is the table of the time-triggered applications (rttools.ucxgen tt,
TT_TICK of app/<app>_tt.h): their tick hook starts the search of the
scheduler at that position, so a job that ends before its F does not
change the task of a later tick. With jobs that end before their
modeled finish, the round robin of the kernel without the table can give
a later tick to another task than the simulation does (the task started
after the early end holds the CPU at the tick and the search starts after
it); with the table, the tasks of each phase run in the circular order
from the position of the simulation, each with at most its remaining
work, so no job ends after its F.

With one period (k_v = 1 for every task) and c^(V_k) <= P, every phase
starts with the idle task and the jobs run in creation order without
preemption: S and F equal the values of rttools/bench_t/estimate.py,
sequence.
"""
from __future__ import annotations

from collections import deque


class Job:
    __slots__ = ("task", "index", "release", "deadline", "first", "start", "finish", "left", "started",
                 "dispatches", "slices")

    def __init__(self, task, index, release, deadline, cost):
        self.task = task
        self.index = index
        self.release = release
        self.deadline = deadline
        self.first = None      # first dispatch (cycles)
        self.start = None      # first dispatch + sigma: reading point
        self.finish = None
        self.left = cost
        self.started = False
        self.dispatches = 0
        self.slices = []

    def as_dict(self):
        return {"task": self.task, "index": self.index, "release": self.release, "deadline": self.deadline,
                "first": self.first, "start": self.start, "finish": self.finish, "dispatches": self.dispatches}


def released(task, phase):
    """True when `task` ({"period", "offset"} in ticks) releases a job at
    tick `phase`."""
    return phase >= task["offset"] and (phase - task["offset"]) % task["period"] == 0


def simulate(tasks, tick, phases, sigma=0, tail=None, boundary=None, owner_of=None, tick_sigma=False):
    """Simulates one PE.

    `tasks`: creation order, [{"name", "cost", "period" (ticks), "offset"
    (ticks, default 0), "extra" (optional: cycles added to job j, list
    indexed by j modulo its length)}]; `tick`: P in cycles; `phases`: releases happen at
    ticks 0 .. phases - 1; the simulation continues with ticks and no new
    release until every job finishes, at most `tail` more ticks (default:
    phases). `boundary`: tick period (in ticks) at which the state of the
    PE is recorded before the tick is handled (hyperperiod H / P).
    `owner_of`: the kernel with the table of the time-triggered applications
    (TT_TICK): at tick t with owner_of(t) = p > 0, the search of the
    scheduler starts at position p (the task of p when it has a pending
    job, else the next one after it), whatever task runs; None: the round
    robin from the position of the running task. `tick_sigma`: the
    platform accounting (see above); False: the accounting of the model
    (the first dispatch of a job is part of c^(v)).

    Returns {"jobs": {name: [Job]}, "slices": [(begin, end, name)],
    "states": {tick index: state tuple}, "owners": [position that each
    tick dispatches, 0: idle task], "complete": bool}."""
    if tick <= 0:
        raise ValueError("tick must be positive")
    names = [t["name"] for t in tasks]
    if len(set(names)) != len(names):
        raise ValueError("repeated task on the PE: " + ", ".join(names))
    spec = {}
    for t in tasks:
        c, k, o = int(t["cost"]), int(t["period"]), int(t.get("offset", 0))
        if c < 0 or k < 1 or not 0 <= o < k:
            raise ValueError(f"task {t['name']}: cost >= 0, period >= 1 and 0 <= offset < period required")
        spec[t["name"]] = {"cost": c, "period": k, "offset": o, "extra": list(t.get("extra") or [])}
    order = [None] + names
    pending = {n: deque() for n in names}
    jobs = {n: [] for n in names}
    count = {n: 0 for n in names}
    slices = []
    states = {}
    owners = []
    cur = 0          # position of the current task (0: idle)
    running = None   # name of the running task, None: idle
    time = 0
    nxt = 0          # index of the next tick
    tail = phases if tail is None else tail
    last_tick = phases + tail

    def next_ready(frm):
        n = len(order)
        for step in range(1, n + 1):
            p = (frm + step) % n
            if p != 0 and pending[order[p]]:
                return p
        return None

    def dispatch(name, now, at_tick=False):
        job = pending[name][0]
        job.dispatches += 1
        if tick_sigma:
            if at_tick:
                job.left += sigma
            if not job.started:
                job.started = True
                job.first = now
                job.start = now + sigma if at_tick else now
            return job
        if not job.started:
            job.started = True
            job.first = now
            job.start = now + sigma
        else:
            job.left += sigma
        return job

    def state(now):
        q = tuple((n, tuple((j.left, j.started, None if j.first is None else j.first - now,
                              j.release - now) for j in pending[n])) for n in names)
        return (cur, running, q)

    while True:
        busy = any(pending.values())
        if nxt > last_tick or (nxt >= phases and not busy):
            break
        t_tick = nxt * tick
        job = pending[running][0] if running is not None else None
        t_done = time + job.left if job is not None else None
        t = t_tick if t_done is None or t_tick < t_done else t_done
        if job is not None and t > time:
            job.left -= t - time
            if job.slices and job.slices[-1][1] == time:
                job.slices[-1] = (job.slices[-1][0], t)
            else:
                job.slices.append((time, t))
            if slices and slices[-1][2] == running and slices[-1][1] == time:
                slices[-1] = (slices[-1][0], t, running)
            else:
                slices.append((time, t, running))
        time = t
        at_tick = time == t_tick
        if job is not None and job.left == 0:
            job.finish = time
            pending[running].popleft()
            if pending[running]:
                nj = pending[running][0]       # pending release: next job without a scheduler event
                nj.started = True
                nj.first = time
                nj.start = time
            else:
                p = next_ready(cur)
                if p is None:
                    cur, running = 0, None
                elif at_tick:
                    cur, running = p, None    # dispatch replaced by the tick below
                else:
                    cur, running = p, order[p]
                    dispatch(running, time)
        if at_tick:
            if boundary and nxt % boundary == 0:
                states[nxt] = state(time)
            if nxt < phases:
                for n in names:
                    s = spec[n]
                    if released(s, nxt):
                        x = s["extra"][count[n] % len(s["extra"])] if s["extra"] else 0
                        j = Job(n, count[n], time, time + s["period"] * tick, s["cost"] + x)
                        count[n] += 1
                        jobs[n].append(j)
                        pending[n].append(j)
            prev = running
            o = owner_of(nxt) if owner_of is not None else 0
            p = next_ready((o - 1) % len(order)) if o else next_ready(cur)
            if p is None:
                cur, running = 0, None
            else:
                cur, running = p, order[p]
                if running == prev:
                    pending[running][0].left += sigma   # the tick lets the same job continue
                    pending[running][0].dispatches += 1
                else:
                    dispatch(running, time, True)
            owners.append(cur)
            nxt += 1
    complete = not any(pending.values())
    return {"jobs": jobs, "slices": slices, "states": states, "owners": owners, "complete": complete}


def busy_per_phase(slices, tick, phases):
    """Busy cycles of the PE (non-idle slices) in each tick interval
    [p P, (p + 1) P), p = 0 .. phases - 1."""
    out = [0] * phases
    for b, e, _ in slices:
        p = b // tick
        while b < e and p < phases:
            end = min(e, (p + 1) * tick)
            out[p] += end - b
            b = end
            p += 1
    return out
