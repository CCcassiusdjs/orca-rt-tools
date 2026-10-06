"""Regression tests for the defects found in the review of the TUI."""
import asyncio
import subprocess
import sys
import time

import pytest

from rttools.tui.model import benchmodel, export, metrics, network, parsers, schedtests
from rttools.tui.model.timeunit import RTL_PRESETS, TimeUnit
from rttools.tui.model.trace import Slice, Trace


def test_ticks_terminate_at_large_times():
    tr = Trace("t", RTL_PRESETS["100ps"], [], [Slice("L", 10**17, 10**17 + 5, "A")])
    t0 = time.time()
    out = export.ticks(tr, 10**17, 10**17 + 5, "ns")
    assert time.time() - t0 < 1 and len(out) <= 33


def test_csv_quotes_commas_and_keeps_unit_name(tmp_path):
    tr = Trace("t", TimeUnit(1e-6, "1 us_x", 5e6), [], [Slice("Q,1", 0, 9, "A,B")])
    p = tmp_path / "t.csv"
    export.write_csv(tr, str(p))
    back = parsers.load_trace(str(p))
    assert [(s.lane, s.label) for s in back.slices] == [("Q,1", "A,B")]
    assert back.unit.name == "1 us_x"


@pytest.mark.parametrize("tasks", [
    [(4, 25), (5, 17), (5, 17)],
    [(4, 30), (1, 10), (10, 30)],
])
def test_rta_bounds_simulation_with_equal_priorities(tasks):
    ts = [{"name": f"t{i}", "wcet": c, "period": t} for i, (c, t) in enumerate(tasks)]
    hp = schedtests.lcm(t for _, t in tasks)
    tr, misses, _, _ = benchmodel.simulate(ts, "RM", 2 * hp, quantum=1)
    obs = schedtests.observed_responses(tr.lane_slices("CPU"), ts, 2 * hp)
    for r in schedtests.response_times(ts, "RM", jitter=1):
        assert obs[r["name"]][0] <= r["R"], (r, obs[r["name"]])


def test_edf_demand_truncated_is_inconclusive():
    ts = [{"name": "a", "wcet": 1, "period": 2, "deadline": 2},
          {"name": "b", "wcet": 3, "period": 100, "deadline": 4}]
    assert schedtests.edf_demand(ts)[:2] == (False, 4)
    assert schedtests.edf_demand(ts, max_points=1)[0] is None
    rows = dict((n, t) for n, t, _ in schedtests.analyze(
        [{"name": "a", "wcet": 3, "period": 2, "deadline": 1}], "EDF"))
    assert rows["EDF demand"] == "fail (U > 1)"


def test_burst_partial_at_window_boundary():
    tr = Trace("t", TimeUnit(1e-9, "1 ns"), [],
               [Slice("L", 0, 10, "A"), Slice("L", 10, 20, "B"), Slice("L", 20, 30, "C")])
    b = metrics.bursts(tr, "L", 10, 20)
    assert len(b) == 1 and b[0]["partial"] is True
    assert metrics.bursts(tr, "L", 0, 30)[0]["partial"] is False


def test_timescale_only_from_pe_path():
    log = ["# Time scale of (top_pipeline) is 1ns / 1ps\n", "# 10 0-0 scheduled 1\n"]
    assert parsers.parse_rtl(log).unit.assumed
    log = ["# Time scale of (tb.manycore_top.pe0) is 100ps / 100ps\n", "# 10 0-0 scheduled 1\n"]
    assert parsers.parse_rtl(log).unit.name == "100 ps"


def test_validate_lists_all_overlaps():
    res = {"problem": {"links": [(0, 1, {"label": "0-1"})],
                       "packets": [{"name": n, "min_start": 0, "abs_deadline": 100} for n in "ABC"],
                       "occupancy": [[10, 1, 3]], "hyperperiod": 100},
           "schedule": [[0, 2, 5]], "skipped": set(), "frequency": 1}
    issues = network.validate(res)
    assert len([i for i in issues if "overlap" in i]) == 2


def test_parse_number_rejects_non_finite():
    from rttools.tui.ui.dialogs import parse_number
    for v in ("inf", "1e400", "nan"):
        with pytest.raises(ValueError):
            parse_number(v)


# ------------------------------------------------------------------ UI

pytest.importorskip("textual")


def run(coro):
    return asyncio.run(coro)


def test_gantt_no_partial_mark_after_slice_end():
    from rttools.tui.ui.app import RTToolsApp
    tr = Trace("t", TimeUnit(1e-9, "1 ns"), [], [Slice("L", 0, 10, "A"), Slice("L", 20, 30, "A")])

    async def body():
        app = RTToolsApp()
        async with app.run_test(size=(120, 30)) as pilot:
            app.show_in_trace(tr)
            await pilot.pause()
            g = app.query_one("#gantt")
            g.set_view(0, g.plot_width)          # one raw unit per column
            g._layout()
            from rttools.tui.ui.gantt import EMPTY_BG
            cols = [(ch, seg.style) for seg in g._rows[2] for ch in seg.text][g.label_width:]
            empty = [ch == " " and st.bgcolor.name == EMPTY_BG for ch, st in cols]
            assert empty[10] and empty[30]          # no partial glyph after the end of a slice
            assert not empty[9] and not empty[20] and not empty[29]
    run(body())


def test_gantt_click_column_and_zoom_limits():
    from rttools.tui.ui.app import RTToolsApp
    tr = Trace("t", TimeUnit(1e-9, "1 ns"), [], [Slice("L", 0, 1000, "A")])

    async def body():
        app = RTToolsApp()
        async with app.run_test(size=(120, 30)) as pilot:
            app.show_in_trace(tr)
            await pilot.pause()
            g = app.query_one("#gantt")
            g.focus()
            await pilot.pause()
            g.set_view(0, g.plot_width)
            await pilot.click(g, offset=(g.label_width + 10 + g.content_region.x - g.region.x, 2))
            assert g.cursor == 10
            for _ in range(200):
                g.action_zoom(2)
            lo, hi = g.span_limits()
            assert g.view_span == hi
            for _ in range(200):
                g.action_zoom(0.5)
            assert g.view_span == lo
            g._layout()
    run(body())


def test_dialog_errors_do_not_end_the_app(tmp_path):
    from rttools.tui.ui.app import RTToolsApp
    from rttools.tui.ui.trace_pane import TracePane
    log = tmp_path / "log.txt"
    log.write_text("# 10 0-0 scheduled 1\n# 20 0-0 scheduled 0\n")

    async def body():
        app = RTToolsApp()
        async with app.run_test(size=(120, 40)) as pilot:
            tp = app.query_one(TracePane)
            tp.action_open()
            await pilot.pause()
            dlg = app.screen
            dlg.query_one("#f_path").value = str(log)
            dlg.query_one("#f_map").value = str(tmp_path / "missing.json")
            dlg.action_ok()
            await pilot.pause()
            assert app.is_running and tp.gantt.trace is None
            tp.load_file(str(log))
            tp.action_unit()
            await pilot.pause()
            dlg = app.screen
            dlg.query_one("#f_custom").value = "0ps"
            dlg.action_ok()
            await pilot.pause()
            assert tp.gantt.trace.unit.seconds > 0
    run(body())


def test_old_search_messages_are_ignored():
    from rttools.tui.ui.app import RTToolsApp
    from rttools.tui.ui.network_pane import NetworkPane

    async def body():
        app = RTToolsApp(tab="network")
        async with app.run_test(size=(150, 45)) as pilot:
            npn = app.query_one(NetworkPane)
            old = object()
            npn.proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(5)"])
            npn.started = time.time()
            npn.on_worker_message(("ended", -15), old)
            assert npn.proc is not None and npn.running()
            npn.on_worker_message(("attempt", {"frequency": 1, "ok": True, "skipped": 0,
                                               "hyperperiod": 1, "packets": 1, "time": time.time()}), old)
            assert npn.attempt_no == 0
            npn.proc.terminate()
            npn.proc.wait()
    run(body())
