"""Network schedule at a fixed frequency and minimum frequency search.

The command line tool (rttools/__main__.py) and the TUI (rttools/tui)
share these functions. The functions print the same log messages that
the command line tool printed before the extraction.
"""
from rttools.terminal.terminal import error, info, warn
from rttools.modules.instances import instantiator, release
from rttools.modules.unwrapper import flowUnwrapper
from rttools.modules.backend.ags import ags


def schedule_at(app, noc, mapping, appname, frequency, cfg):
    """Builds the problem at `frequency` and runs the AGS backend.

    Returns a dict with the keys frequency, hyperperiod, problem,
    schedule (link x packet start times or None) and skipped (set of
    packet indices). Returns None when the hyperperiod is 0."""
    instance = instantiator.createInstance(app, noc, frequency)
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
    return {
        "frequency": frequency,
        "hyperperiod": hp,
        "problem": problem,
        "schedule": sched,
        "skipped": skipped,
    }


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


def search_minimum_frequency(app, noc, mapping, appname, cfg, on_attempt=None):
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

    `on_attempt(attempt, ok)` receives each attempt with a hyperperiod.
    Returns None when no attempt is feasible; otherwise the attempt at
    `upper` (keys of schedule_at) plus "attempts" (list of (frequency, ok,
    number of skipped packets or None)), "steps" (number of attempts),
    "lower" (final lower bound, Hz)."""
    attempts = []
    best = None
    lower = 0
    upper = None

    def attempt_at(frequency):
        info("Tentative frequency is " + str(frequency) + "Hz")
        attempt = schedule_at(app, noc, mapping, appname, frequency, cfg)
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


def cpu_check(app, mapping):
    """CPU test of the analysis flow (release.cpu_bound), computed once
    from the application and the mapping, before and outside the frequency
    search (it does not depend on the candidate frequency). Returns the
    result of release.cpu_bound, or None when the test does not apply (no
    application graph, or flows with different periods)."""
    if app is None or mapping is None:
        return None
    try:
        return release.cpu_bound(app, mapping)
    except ValueError as e:
        warn("CPU test skipped: " + str(e))
        return None


def minimum_frequency(app, noc, mapping, appname, cfg, on_attempt=None):
    """Minimum frequency of the analysis flow: the CPU test gives f_CPU
    once (cpu_check), the bisection gives the lowest frequency f* at which
    the AGS backend schedules every packet (search_minimum_frequency), and
    the result is max(f*, f_CPU).

    Returns {"cpu": cpu_check result or None, "network": result of
    search_minimum_frequency or None, "f_star_hz", "f_cpu_hz",
    "frequency_hz"}; a value is None when its part has no result."""
    cpu = cpu_check(app, mapping)
    f_cpu = cpu["f_cpu_hz"] if cpu is not None else None
    if f_cpu is not None:
        info("CPU test: f_CPU = " + str(f_cpu) + "Hz (largest CPU demand per release period)")
    net = search_minimum_frequency(app, noc, mapping, appname, cfg, on_attempt)
    f_star = net["frequency"] if net is not None else None
    if f_star is None:
        final = None
    elif f_cpu is None:
        final = f_star
    else:
        final = max(f_star, f_cpu)
    return {"cpu": cpu, "network": net, "f_star_hz": f_star, "f_cpu_hz": f_cpu, "frequency_hz": final}
