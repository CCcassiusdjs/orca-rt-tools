"""Frequency search extracted from rttools/__main__.py (same sequence of
attempts and same messages as the loop it replaces)."""
import os

from rttools.modules.frequency import search

LIMIT = 3000   # attempts at or above LIMIT Hz are feasible


def fake_schedule_at(app, noc, mapping, appname, frequency, cfg):
    ok = frequency >= LIMIT
    return {
        "frequency": frequency,
        "hyperperiod": int(frequency),
        "problem": {"hyperperiod": int(frequency), "packets": [], "links": [],
                    "occupancy": []},
        "schedule": [[0]] if ok else [[None]],
        "skipped": set() if ok else {0},
    }


CFG = {"frequency": 8000, "pruning_factor": 1, "fail_threshold": 1,
       "heuristic": None, "scaling_tolerance": 100}


def test_search_returns_problem_of_feasible_frequency(monkeypatch):
    monkeypatch.setattr(search, "schedule_at", fake_schedule_at)
    seen = []
    res = search.search_minimum_frequency(None, None, None, "x", CFG,
                                          on_attempt=lambda a, ok: seen.append((a["frequency"], ok)))
    assert res["frequency"] >= LIMIT
    assert res["problem"]["hyperperiod"] == int(res["frequency"])
    assert [(f, ok) for (f, ok, _) in res["attempts"]] == seen
    # the result is the LAST feasible attempt; an infeasible attempt sets
    # upper = 2 * center and discards the lower feasible bound, so an
    # earlier attempt can be feasible at a lower frequency (here 3000 Hz
    # against the reported ~3082 Hz). The TUI lists all attempts.
    feasible = [f for (f, ok) in seen if ok]
    assert res["frequency"] == feasible[-1]
    assert min(feasible) < res["frequency"]
    # an infeasible attempt sets upper = 2 * center, so the interval only
    # closes after a feasible attempt
    assert seen[-1][1] is True


def test_cli_svg_receives_found_frequency(monkeypatch, tmp_path):
    import rttools.__main__ as cli
    monkeypatch.setattr(search, "schedule_at", fake_schedule_at)
    monkeypatch.setattr(cli.appparser, "loadFromFile", lambda f: (None, "x"))
    monkeypatch.setattr(cli.nocparser, "loadFromFile", lambda f: None)
    monkeypatch.setattr(cli.mapparser, "loadFromFile", lambda f: None)
    calls = []
    monkeypatch.setattr(cli.svg, "saveSvg", lambda fn, res, problem, skipped, scale: calls.append(problem))
    monkeypatch.setattr(cli.sys, "argv", ["rttools", "a", "m", "n", "8000"])
    monkeypatch.setattr(cli, "RTTOOLS_SCALING_TOLERANCE", 100)
    monkeypatch.chdir(tmp_path)
    assert cli.main() == 0
    assert len(calls) == 1
    assert calls[0]["hyperperiod"] >= LIMIT


def test_fixed_frequency_without_schedule_returns_error(monkeypatch):
    import rttools.__main__ as cli
    monkeypatch.setattr(search, "schedule_at",
                        lambda *a: {"frequency": 1, "hyperperiod": 1, "problem": {},
                                    "schedule": None, "skipped": set()})
    monkeypatch.setattr(cli.appparser, "loadFromFile", lambda f: (None, "x"))
    monkeypatch.setattr(cli.nocparser, "loadFromFile", lambda f: None)
    monkeypatch.setattr(cli.mapparser, "loadFromFile", lambda f: None)
    monkeypatch.setattr(cli.sys, "argv", ["rttools", "a", "m", "n", "1", "1", "1", "False"])
    assert cli.main() == 1
