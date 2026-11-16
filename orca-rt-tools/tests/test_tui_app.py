"""TUI in headless mode (Textual App.run_test)."""
import asyncio
import os
import time

import pytest

pytest.importorskip("textual")

from tests.conftest import REPO_ROOT                              # noqa: E402
from tests.test_tui_model import RTL_LOG, CLASSIC                 # noqa: E402
from rttools.tui.model import benchmodel                          # noqa: E402
from rttools.tui.model.timeunit import RTL_PRESETS                # noqa: E402
from rttools.tui.ui.app import RTToolsApp                         # noqa: E402
from rttools.tui.ui.bench_pane import BenchPane                   # noqa: E402
from rttools.tui.ui.dialogs import FormDialog, parse_number       # noqa: E402
from rttools.tui.ui.gantt import GanttView                        # noqa: E402
from rttools.tui.ui.graph_pane import GraphPane                   # noqa: E402
from rttools.tui.ui.network_pane import NetworkPane, draw_mesh    # noqa: E402
from rttools.tui.ui.trace_pane import TracePane                   # noqa: E402

SIZE = (150, 45)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def rtl_file(tmp_path):
    p = tmp_path / "log.txt"
    p.write_text(RTL_LOG)
    return str(p)


def test_parse_number():
    assert parse_number("2M") == 2000000
    assert parse_number("1_000") == 1000
    assert parse_number("", 7) == 7
    assert parse_number("0.5") == 0.5


def test_trace_keys_cursor_zoom_units(rtl_file):
    async def body():
        app = RTToolsApp(rtl_file, "trace", {})
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            g = app.query_one("#gantt", GanttView)
            assert g.trace is not None and g.trace.unit.name == "100 ps"
            g.focus()
            span = g.view_span
            await pilot.press("plus")
            assert g.view_span < span
            await pilot.press("f")
            assert g.view_span == g.trace.t1 - g.trace.t0
            await pilot.press("n")
            assert g.cursor == 1200            # next event of lane 0-0
            await pilot.press("m", "n")
            assert g.mark == 1200 and g.cursor == 1300
            await pilot.press("down")
            assert g.selected_lane == "0-1"
            await pilot.press("u")
            assert g.mode == "cycles"
            text = str(app.query_one("#trace-cursor").render())
            assert "Δ" in text and "5 cyc" in text          # 100 units of 100 ps = 5 cycles
            await pilot.press("home")
            assert g.cursor == g.trace.t0
    run(body())


def test_trace_unit_preset_and_compare(rtl_file, tmp_path):
    other = tmp_path / "b.txt"
    # B: same events in units of 1 ns (times / 10)
    lines = []
    for l in RTL_LOG.splitlines():
        parts = l.lstrip("# ").split()
        if parts and parts[0].isdigit():
            parts[0] = str(int(parts[0]) // 10)
            lines.append(" ".join(parts))
    other.write_text("\n".join(lines) + "\n")

    async def body():
        app = RTToolsApp(rtl_file, "trace", {"unit": RTL_PRESETS["100ps"]})
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            tp = app.query_one(TracePane)
            from rttools.tui.model import parsers
            tp.show_comparison(parsers.load_trace(str(other)), 10)
            await pilot.pause()
            assert all(r["equal_times"] == r["count_a"] == r["count_b"] for r in tp.compare_result.values())
            assert tp.gantt.trace.lanes[:2] == ["A:0-0", "B:0-0"]
    run(body())


def test_open_dialog_loads_file(rtl_file):
    async def body():
        app = RTToolsApp()
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            tp = app.query_one(TracePane)
            tp.focus()
            tp.action_open()
            await pilot.pause()
            dlg = app.screen
            assert isinstance(dlg, FormDialog)
            dlg.query_one("#f_path").value = rtl_file
            dlg.query_one("#f_unit").value = "1ns"
            dlg.action_ok()
            await pilot.pause()
            assert tp.gantt.trace is not None and tp.gantt.trace.unit.name == "1 ns"
    run(body())


def test_bench_pane_run():
    async def body():
        app = RTToolsApp(tab="bench")
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            bp = app.query_one(BenchPane)
            bp.set_tasks([dict(t, deadline=None) for t in CLASSIC])
            bp.query_one("#b-quantum").value = "1"
            bp.action_run()
            await pilot.pause()
            assert bp.last_trace is not None
            rta = bp.query_one("#b-rta")
            assert rta.row_count == 3
            assert str(rta.get_row_at(2)[4]) == "20"
            tests = bp.query_one("#b-tests")
            assert tests.row_count >= 3
            # form: add a task and delete it
            bp.query_one("#b-name").value = "X"
            bp.query_one("#b-wcet").value = "1"
            bp.add_from_form()
            assert [t["name"] for t in bp.tasks][-1] == "X"
    run(body())


def test_graph_pane_cluster():
    async def body():
        app = RTToolsApp(os.path.join(REPO_ROOT, "apps", "sample-graph-b", "sample-graph-b.txt"), "graphs")
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            gp = app.query_one(GraphPane)
            assert gp.graph is not None
            gp.action_cluster()
            await pilot.pause()
            t = gp.query_one("#g-clusters")
            names = sorted("".join(sorted(str(t.get_row_at(i)[0]).split(":"))) for i in range(t.row_count))
            assert names == ["ABDF", "C", "EHI", "GJ"]
    run(body())


def dct_expected_search(header_wait):
    """Minimum frequency and number of attempts of the bisection of
    rttools.modules.frequency.search for the str2rts-dct-verify example with
    the settings of the network pane (start 2 MHz, PF 500, 500 tries, MBCF,
    tolerance 5 kHz) and the link occupancy o_i = L0 + w_h (m + 1) + w_NI of
    router.occupancy for the given header wait w_h and the network-interface
    model of the environment (RTTOOLS_NI). The pane runs the same
    search in a child process (rttools.tui.worker)."""
    from rttools.modules.frequency import search
    from rttools.modules.routing import router
    from rttools.tui.model import network
    from tests.test_tui_model import dct_case
    case = dct_case()
    cfg = {"frequency": 2000000, "pruning_factor": 500, "fail_threshold": 500,
           "heuristic": network.HEURISTICS["mbcf"], "scaling_tolerance": 5000}
    attempts = []
    prev = router.set_header_wait(header_wait)
    try:
        res = search.search_minimum_frequency(case["app"], case["noc"], case["mapping"], case["appname"],
                                              cfg, on_attempt=lambda a, ok: attempts.append(ok))
    finally:
        router.set_header_wait(prev)
    return res["frequency"], len(attempts)


def ch6_dct_reference_hz():
    """run_hz of dct_verify in experiments/ch6/reference.json (all criteria
    and pruning factors give the same value), computed with o_i = L0."""
    import json
    path = os.path.join(REPO_ROOT, "experiments", "ch6", "reference.json")
    if not os.path.exists(path):
        pytest.skip("experiments/ch6 is not part of this copy of the artifact")
    with open(path) as f:
        ref = json.load(f)

    def rows(node):
        if isinstance(node, dict):
            if node.get("app") == "dct_verify" and "run_hz" in node:
                yield node["run_hz"]
            for v in node.values():
                yield from rows(v)
        elif isinstance(node, list):
            for v in node:
                yield from rows(v)
    values = set(rows(ref))
    assert len(values) == 1
    return values.pop()


@pytest.mark.parametrize("header_wait", [None, "off"])
def test_network_pane_example_and_search(monkeypatch, header_wait):
    """The pane reports the minimum of the in-process search with the same
    settings and the same link occupancy. With the defaults (w_h = 20
    cycles per router and the network-interface model tt, o_i = L0 + 20
    (m + 1) + w_NI) the search ends at 1.6875 MHz after 10 attempts. With
    w_h = 0 and the network-interface model off (o_i = L0,
    RTTOOLS_HEADER_WAIT=off and RTTOOLS_NI=off) the bisection halves 2 MHz
    down to 62.5 kHz (infeasible), bisects [62.5, 125] kHz until the
    interval is below the 5 kHz tolerance and ends at 78.125 kHz, the
    value of Table 6.7 in experiments/ch6/reference.json."""
    from rttools.modules.routing import router
    if header_wait is not None:
        monkeypatch.setenv(router.HEADER_WAIT_ENV, header_wait)   # read by the child process
    if header_wait == "off":
        monkeypatch.setenv(router.NI_ENV, router.NI_OFF)
    expected_hz, expected_attempts = dct_expected_search(header_wait)
    if header_wait == "off":
        assert expected_hz == pytest.approx(ch6_dct_reference_hz())

    async def body():
        app = RTToolsApp(tab="network")
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            npn = app.query_one(NetworkPane)
            ex = [i for i, e in enumerate(npn.examples) if e[0] == "str2rts-dct-verify"][0]
            npn.query_one("#n-example").value = ex
            await pilot.pause()
            assert npn.case is not None
            assert npn.query_one("#n-flows").row_count == 7
            npn.query_one("#n-pf").value = "500"
            npn.action_run()
            t0 = time.time()
            while npn.result is None and time.time() - t0 < 120:
                await pilot.pause(0.2)
            assert npn.result is not None
            assert npn.result["frequency"] == pytest.approx(expected_hz)
            assert "valid" in str(npn.query_one("#n-val").render())
            assert npn.query_one("#n-att").row_count == expected_attempts
    run(body())


def test_network_cancel():
    async def body():
        app = RTToolsApp(tab="network")
        async with app.run_test(size=SIZE) as pilot:
            await pilot.pause()
            npn = app.query_one(NetworkPane)
            ex = [i for i, e in enumerate(npn.examples) if e[0] == "shi-2010"][0]
            npn.query_one("#n-example").value = ex
            await pilot.pause()
            npn.action_run()
            await pilot.pause(1.0)
            assert npn.running()
            npn.action_cancel()
            t0 = time.time()
            while npn.proc is not None and time.time() - t0 < 20:
                await pilot.pause(0.2)
            assert npn.proc is None
    run(body())


def test_mesh_drawing():
    m = {"nodes": {"0": (0, 0), "1": (1, 0), "2": (0, 1), "3": (1, 1)},
         "tasks": {"0": ["A"], "1": [], "2": ["B", "C"], "3": []}, "width": 2, "height": 2}
    text = draw_mesh(m, {"0-1": 0.9})
    assert "B,C" in text and "[red]" in text
