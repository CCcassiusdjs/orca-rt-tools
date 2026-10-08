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
    assert res["steps"] == len(seen)


def test_search_returns_lowest_feasible_attempt(monkeypatch):
    # the previous search set upper = 2 * center after an infeasible
    # attempt and returned 3082.03 Hz with 3000 Hz already feasible
    monkeypatch.setattr(search, "schedule_at", fake_schedule_at)
    res = search.search_minimum_frequency(None, None, None, "x", CFG)
    feasible = [f for (f, ok, _) in res["attempts"] if ok]
    assert res["frequency"] == min(feasible) == 3000
    assert res["frequency"] - res["lower"] <= CFG["scaling_tolerance"]
    assert res["lower"] < LIMIT
    # 8000 (ok), 4000 (ok), 2000, 3000 (ok), 2500, 2750, 2875, 2937.5
    assert res["steps"] == 8


def limit_case(limit):
    def fake(app, noc, mapping, appname, frequency, cfg):
        res = fake_schedule_at(app, noc, mapping, appname, frequency * LIMIT / limit, cfg)
        res["frequency"] = frequency
        return res
    return fake


def test_search_brackets_from_infeasible_start(monkeypatch):
    for limit in (1234.5, 3000, 7999, 8000, 8001, 50000, 1e6):
        monkeypatch.setattr(search, "schedule_at", limit_case(limit))
        res = search.search_minimum_frequency(None, None, None, "x", CFG)
        feasible = [f for (f, ok, _) in res["attempts"] if ok]
        infeasible = [f for (f, ok, _) in res["attempts"] if not ok]
        assert res["frequency"] == min(feasible) >= limit
        assert res["frequency"] - CFG["scaling_tolerance"] <= res["lower"] < limit
        assert res["lower"] == max([0] + [f for f in infeasible if f < res["frequency"]])


def test_relative_tolerance(monkeypatch):
    monkeypatch.setattr(search, "schedule_at", limit_case(1e6))
    cfg = dict(CFG, scaling_tolerance=0, relative_tolerance=0.02)
    res = search.search_minimum_frequency(None, None, None, "x", cfg)
    assert res["frequency"] >= 1e6
    assert res["lower"] / res["frequency"] >= 0.98


def test_undefined_hyperperiod_keeps_feasible_bound(monkeypatch):
    # schedule_at returns None when the lcm of the periods fails; the
    # previous search stopped there and returned the last feasible attempt
    def fake(app, noc, mapping, appname, frequency, cfg):
        if 2000 < frequency < 2900:
            return None
        return fake_schedule_at(app, noc, mapping, appname, frequency, cfg)
    monkeypatch.setattr(search, "schedule_at", fake)
    res = search.search_minimum_frequency(None, None, None, "x", CFG)
    assert any(n is None for (_, _, n) in res["attempts"])
    assert res["frequency"] == 3000
    assert res["frequency"] - res["lower"] <= CFG["scaling_tolerance"]


def test_never_feasible_returns_none(monkeypatch):
    monkeypatch.setattr(search, "schedule_at", limit_case(float("inf")))
    cfg = dict(CFG, max_doublings=3)
    assert search.search_minimum_frequency(None, None, None, "x", cfg) is None


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
