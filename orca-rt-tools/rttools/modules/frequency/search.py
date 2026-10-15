"""Network schedule at a fixed frequency and minimum frequency search.

The command line tool (rttools/__main__.py) and the TUI (rttools/tui)
share these functions. The functions print the same log messages that
the command line tool printed before the extraction.
"""
from rttools.terminal.terminal import error, info, warn
from rttools.modules.instances import instantiator, release
from rttools.modules.unwrapper import flowUnwrapper
from rttools.modules.backend.ags import ags


HANDLER_ROUNDS = 64


def schedule_at(app, noc, mapping, appname, frequency, cfg):
    """Builds the problem at `frequency` and runs the AGS backend.

    Returns a dict with the keys frequency, hyperperiod, problem,
    schedule (link x packet start times or None), skipped (set of
    packet indices) and handler_extra. Returns None when the hyperperiod is 0.

    General phase model on the time-triggered platform with the handlers
    of the image (rttools/bench_t/multirate.py): the CPU schedule charges
    each job the handlers of the packet events of the link schedule
    (multirate.handler_extra), so the packet windows, the link schedule and
    the charges form a fixed point: from no charge, each round schedules
    the packets of the CPU schedule with the charges of the previous round
    and raises the charges to the events of its link schedule, until the
    charges stay (the link schedule of that round has the windows of the
    CPU schedule with those charges, and the charges cover its events);
    handler_extra is that charge ({task: [cycles per job position]}), which
    every user of the schedule at this frequency passes to
    multirate.schedule. No fixed point within HANDLER_ROUNDS rounds, or a
    CPU schedule that misses a deadline, gives no schedule."""
    extra = None
    for _ in range(HANDLER_ROUNDS):
        instance = instantiator.createInstance(app, noc, frequency)
        if extra is not None:
            instance["handler_extra"] = extra
        packets, hp, nlinks = flowUnwrapper.unwrap(instance, noc, mapping)
        if hp == 0:
            return None
        problem, result = ags.agsExport(
            packets,
            nlinks,
            hp,
            mapping,
            noc,
            appname,
            cfg["pruning_factor"],
            cfg["fail_threshold"],
            cfg["heuristic"],
        )
        sched, skipped = (None, set()) if result is None else result
        if sched is not None and not release.handlers_fit(instance, mapping):
            # phase model with the handlers of the packet events: a task ends after its phase
            sched = None
        new = _handler_round(instance, noc, mapping, problem, sched, skipped, extra)
        if new is None or new == extra:
            break
        extra = new
    else:
        sched = None
    return {
        "frequency": frequency,
        "hyperperiod": hp,
        "problem": problem,
        "schedule": sched,
        "skipped": skipped,
        "handler_extra": extra,
    }


def _handler_round(instance, noc, mapping, problem, sched, skipped, extra):
    """Charges of the next round of schedule_at, or None when the instance
    has no such fixed point (no general phase model, no handlers, not the
    time-triggered platform, or no complete link schedule)."""
    if instance.get("rates") is None or sched is None or skipped:
        return None
    from rttools.bench_t import multirate
    spec = multirate.spec_from_instance(instance, mapping, noc)
    if not (spec.tick and spec.handlers):
        return None
    ms = multirate.schedule(spec, instance["rates"]["phase_cycles"], extra=extra)
    if not ms.feasible:
        return None
    rows = multirate.attempt_rows(spec, ms, {"problem": problem, "schedule": sched})
    return multirate.handler_extra(spec, ms, multirate.link_events(spec, ms, rows), extra)


def feasible(attempt):
    return (attempt is not None and attempt["schedule"] is not None
            and len(attempt["skipped"]) == 0)


def _converged(lower, upper, cfg):
    """Stop rule: the interval (lower, upper] is narrower than the absolute
    tolerance cfg["scaling_tolerance"] (Hz) or, when the configuration has
    "relative_tolerance" r, narrower than r * upper (the stop rule of the
    thesis, lower / upper >= ITF = 0.98, is r = 1 - ITF = 0.02)."""
    width = upper - lower
    if width <= cfg["scaling_tolerance"]:
        return True
    rel = cfg.get("relative_tolerance")
    return rel is not None and width <= rel * upper


def search_minimum_frequency(app, noc, mapping, appname, cfg, on_attempt=None, floor=0, schedule=None):
    """Lowest frequency at which the AGS backend schedules every packet,
    within the tolerance of _converged.

    The search keeps an interval (lower, upper]: `upper` is the lowest
    frequency with a feasible attempt and `lower` the highest frequency
    below `upper` without one. It starts at f0 = cfg["frequency"] with
    lower = 0. While no attempt is feasible, the search doubles the
    candidate (lower = c, c = 2c), at most cfg.get("max_doublings", 32)
    times. Afterwards each step tries the midpoint c of the interval: a
    feasible attempt sets upper = c, any other attempt sets lower = c, so a
    feasible frequency is never discarded. The search stops when the
    interval converges and returns the attempt at `upper`.

    An attempt whose hyperperiod is undefined (lcm of the periods in cycles
    not found, schedule_at returns None) gives no schedule at c; the search
    records it with skipped count None and treats c as not feasible.

    `floor` (Hz) is the initial lower bound: the search never tries a
    frequency at or below it (minimum_frequency passes f_CPU when the
    network is not feasible at f_CPU).

    `on_attempt(attempt, ok)` receives each attempt with a hyperperiod.
    `schedule` replaces schedule_at (same arguments and result); the
    composition of several applications (rttools/multiapp) passes the
    schedule of the union of their packets.
    Returns None when no attempt is feasible; otherwise the attempt at
    `upper` (keys of schedule_at) plus "attempts" (list of (frequency, ok,
    number of skipped packets or None)), "steps" (number of attempts),
    "lower" (final lower bound, Hz)."""
    attempts = []
    best = None
    lower = floor
    upper = None

    def attempt_at(frequency):
        info("Tentative frequency is " + str(frequency) + "Hz")
        attempt = (schedule or schedule_at)(app, noc, mapping, appname, frequency, cfg)
        if attempt is None:
            error("No hyperperiod at " + str(frequency) + "Hz; the attempt counts as not feasible.")
            attempts.append((frequency, False, None))
            return None, False
        ok = feasible(attempt)
        nskipped = len(attempt["skipped"])
        attempts.append((frequency, ok, nskipped))
        if on_attempt is not None:
            on_attempt(attempt, ok)
        if ok:
            warn("Found a schedule at " + str(frequency) + "Hz. Scaling frequency down.")
        else:
            error("Could not find a schedule at " + str(frequency) + "Hz.")
            if attempt["schedule"] is not None:
                error("Skip list is not empty (" + str(nskipped) + ")!")
        return attempt, ok

    # bracket: find a feasible upper bound
    center = cfg["frequency"]
    for _ in range(cfg.get("max_doublings", 32) + 1):
        attempt, ok = attempt_at(center)
        if ok:
            best, upper = attempt, center
            break
        lower = center
        error("Scaling frequency up...")
        center = center * 2
    if best is None:
        return None

    # bisection on (lower, upper]
    while not _converged(lower, upper, cfg):
        center = (lower + upper) / 2
        if not lower < center < upper:
            break   # no representable midpoint (tolerance 0)
        attempt, ok = attempt_at(center)
        if ok:
            best, upper = attempt, center
        else:
            lower = center

    info("Converged: " + str(lower) + "Hz < f <= " + str(upper) + "Hz after "
         + str(len(attempts)) + " attempts")
    best = dict(best)
    best["attempts"] = attempts
    best["steps"] = len(attempts)
    best["lower"] = lower
    return best


def cpu_check(app, mapping, noc=None):
    """CPU test of the analysis flow (release.cpu_bound), computed once
    from the application and the mapping, before and outside the frequency
    search (it does not depend on the candidate frequency). Returns the
    result of release.cpu_bound, or None when the test does not apply (no
    application graph, or flows with different periods)."""
    if app is None or mapping is None:
        return None
    try:
        return release.cpu_bound(app, mapping, noc=noc)
    except ValueError as e:
        warn("CPU test skipped: " + str(e))
        return None


def network_check(app, noc, mapping, appname, frequency, cfg, schedule=None):
    """One evaluation of the network at `frequency` (instantiation with the
    release model of the application, unwrapping and AGS): {"frequency_hz",
    "feasible", "hyperperiod", "packets", "skipped"}; hyperperiod, packets
    and skipped are None when the hyperperiod is undefined. `schedule`
    replaces schedule_at (search_minimum_frequency)."""
    attempt = (schedule or schedule_at)(app, noc, mapping, appname, frequency, cfg)
    if attempt is None:
        return {"frequency_hz": frequency, "feasible": False, "hyperperiod": None, "packets": None,
                "skipped": None}
    return {"frequency_hz": frequency, "feasible": feasible(attempt), "hyperperiod": attempt["hyperperiod"],
            "packets": len(attempt["problem"]["packets"]), "skipped": len(attempt["skipped"])}


def minimum_frequency(app, noc, mapping, appname, cfg, on_attempt=None):
    """Minimum frequency of the analysis flow.

    1. The CPU test gives f_CPU once (cpu_check), outside the bisection.
    2. The bisection gives the lowest frequency f* at which the AGS backend
       schedules every packet (search_minimum_frequency).
    3. When f_CPU > f*, the network is evaluated once more at f_CPU
       (network_check): the release model ties the windows of the packets
       to the phase length T f, so feasibility at f* does not imply
       feasibility at f_CPU. Feasible: the result is f_CPU. Not feasible:
       the search continues upwards from f_CPU (doubling, then bisection
       on (f_CPU, upper], never below f_CPU) and the result is the first
       feasible frequency it finds.

    Returns {"cpu", "network", "f_star_hz", "f_cpu_hz", "final_check",
    "final_search", "frequency_hz"}: final_check is the evaluation at f_CPU
    (None when f_CPU <= f* or unknown), final_search the result of the
    search above f_CPU (None when not needed); a value is None when its
    part has no result.

    General phase model (cpu["model"] == "multirate", several periods or a
    cycle, rttools/bench_t/multirate.py): the packet windows come from the
    ORT/BENCH sequences over the hyperperiod, which exist only at f >=
    f_CPU. The network is evaluated at f_CPU first (final_check); when it
    is not feasible there, the search runs above f_CPU (final_search).
    f_star_hz is then the lowest frequency at or above f_CPU with a
    feasible link schedule (f_CPU itself when final_check is feasible) and
    network is None."""
    cpu = cpu_check(app, mapping, noc)
    f_cpu = cpu["f_cpu_hz"] if cpu is not None else None
    if f_cpu is not None:
        info("CPU test: f_CPU = " + str(f_cpu) + "Hz (largest CPU demand per release period)")
    if cpu is not None and cpu.get("model") == "multirate":
        info("Network check at f_CPU = " + str(f_cpu) + "Hz (general phase model)")
        check = network_check(app, noc, mapping, appname, f_cpu, cfg)
        above = None
        if check["feasible"]:
            final = f_cpu
        else:
            warn("No schedule at f_CPU; searching above f_CPU")
            up = dict(cfg)
            up["frequency"] = 2 * f_cpu
            above = search_minimum_frequency(app, noc, mapping, appname, up, on_attempt, floor=f_cpu)
            final = above["frequency"] if above is not None else None
        return {"cpu": cpu, "network": None, "f_star_hz": final, "f_cpu_hz": f_cpu, "final_check": check,
                "final_search": above, "frequency_hz": final}
    net = search_minimum_frequency(app, noc, mapping, appname, cfg, on_attempt)
    f_star = net["frequency"] if net is not None else None
    check = None
    above = None
    if f_star is None:
        final = None
    elif f_cpu is None or f_star >= f_cpu:
        final = f_star
    else:
        info("Network check at f_CPU = " + str(f_cpu) + "Hz")
        check = network_check(app, noc, mapping, appname, f_cpu, cfg)
        if check["feasible"]:
            final = f_cpu
        else:
            warn("No schedule at f_CPU; searching above f_CPU")
            up = dict(cfg)
            up["frequency"] = 2 * f_cpu
            above = search_minimum_frequency(app, noc, mapping, appname, up, on_attempt, floor=f_cpu)
            final = above["frequency"] if above is not None else None
    return {"cpu": cpu, "network": net, "f_star_hz": f_star, "f_cpu_hz": f_cpu, "final_check": check,
            "final_search": above, "frequency_hz": final}
