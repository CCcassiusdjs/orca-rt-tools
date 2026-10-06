"""Network schedule at a fixed frequency and minimum frequency search.

The command line tool (rttools/__main__.py) and the TUI (rttools/tui)
share these functions. The functions print the same log messages that
the command line tool printed before the extraction.
"""
from rttools.terminal.terminal import error, info, warn
from rttools.modules.instances import instantiator
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


def search_minimum_frequency(app, noc, mapping, appname, cfg, on_attempt=None):
    """Bisection on the frequency, starting at cfg["frequency"].

    A feasible attempt lowers the upper bound; an infeasible attempt
    doubles the upper bound. The search stops when the interval is
    narrower than cfg["scaling_tolerance"] or when the hyperperiod is 0.

    `on_attempt(attempt, ok)` receives each attempt. Returns the last
    feasible attempt (same keys as schedule_at, plus "attempts", the list
    of (frequency, ok, number of skipped packets)) or None."""
    low_frequency = 0
    center_frequency = cfg["frequency"]
    upper_frequency = cfg["frequency"] * 10

    last = None
    attempts = []

    while True:
        info("Tentative frequency is " + str(center_frequency) + "Hz")
        attempt = schedule_at(app, noc, mapping, appname, center_frequency, cfg)
        if attempt is None:
            break

        ok = feasible(attempt)
        nskipped = len(attempt["skipped"])
        attempts.append((center_frequency, ok, nskipped))
        if on_attempt is not None:
            on_attempt(attempt, ok)

        if ok:
            warn("Found a schedule at " + str(center_frequency) + "Hz. Scaling frequency down.")
            last = attempt
            upper_frequency = center_frequency
            center_frequency = (upper_frequency + low_frequency) / 2
        else:
            error("Could not find a schedule at " + str(center_frequency) + "Hz.")
            if attempt["schedule"] is not None:
                error("Skip list is not empty (" + str(nskipped) + ")!")
            error("Scaling frequency up...")
            upper_frequency = center_frequency * 2
            low_frequency = center_frequency
            center_frequency = (upper_frequency + low_frequency) / 2

        if (upper_frequency - low_frequency) < cfg["scaling_tolerance"]:
            break

    if last is not None:
        last = dict(last)
        last["attempts"] = attempts
    return last
