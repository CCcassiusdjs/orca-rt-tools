"""Network pane: application, mapping and NoC; flows; frequency search
with live progress; link schedule, link usage and validation."""
from __future__ import annotations

import os
import time

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import (
    Button, DataTable, Input, Label, RichLog, Select, Static, TabbedContent, TabPane,
)

from rttools.tui.model import network
from rttools.tui.model.timeunit import format_frequency
from rttools.tui.ui.dialogs import Field, FormDialog, guarded, parse_number
from rttools.tui.ui.gantt import GanttView
from rttools.tui.ui.tables import esc, fill

CELL_W = 16


def draw_mesh(m, usage=None):
    """Rich markup of the mesh, Y = 0 at the bottom. usage maps link
    labels ("a-b") to utilization (0..1)."""
    usage = usage or {}
    pos = {xy: n for n, xy in m["nodes"].items()}
    lines = []

    def link_text(a, b, horizontal):
        ua = usage.get(f"{a}-{b}")
        ub = usage.get(f"{b}-{a}")
        if ua is None and ub is None:
            return "──" if horizontal else "│"
        u = max(ua or 0, ub or 0)
        color = "green" if u < 0.5 else "yellow" if u < 0.8 else "red"
        return f"[{color}]{'══' if horizontal else '║'}[/]"

    for y in reversed(range(m["height"])):
        top, mid1, mid2, bot = [], [], [], []
        for x in range(m["width"]):
            n = pos.get((x, y))
            if n is None:
                for row in (top, mid1, mid2, bot):
                    row.append(" " * CELL_W)
                if x < m["width"] - 1:
                    for row in (top, mid1, mid2, bot):
                        row.append("  ")
                continue
            tasks = ",".join(m["tasks"].get(n, [])) or "-"
            head = f" {n} ({x},{y}) "
            top.append("┌" + esc(head.ljust(CELL_W - 2, "─")[:CELL_W - 2]) + "┐")
            t1 = tasks[:CELL_W - 4]
            t2 = tasks[CELL_W - 4:2 * (CELL_W - 4)]
            mid1.append("│ [b]" + esc(t1.ljust(CELL_W - 4)) + "[/b] │")
            mid2.append("│ " + esc(t2.ljust(CELL_W - 4)) + " │")
            bot.append("└" + "─" * (CELL_W - 2) + "┘")
            if x < m["width"] - 1:
                right = pos.get((x + 1, y))
                top.append("  ")
                mid1.append(link_text(n, right, True) if right is not None else "  ")
                mid2.append("  ")
                bot.append("  ")
        lines += ["".join(top), "".join(mid1), "".join(mid2), "".join(bot)]
        if y > 0:
            vert = []
            for x in range(m["width"]):
                a, b = pos.get((x, y)), pos.get((x, y - 1))
                cell = " " * (CELL_W // 2) + (link_text(a, b, False) if a is not None and b is not None else " ")
                vert.append(cell + " " * (CELL_W - CELL_W // 2 - 1) + "  ")
            lines.append("".join(vert))
    return "\n".join(lines)


class NetworkPane(Widget):
    DEFAULT_CSS = """
    NetworkPane { height: 1fr; }
    NetworkPane #net-files { height: auto; padding: 0 1; background: $panel; }
    NetworkPane #net-settings { height: 1; }
    NetworkPane #net-settings Label { width: auto; }
    NetworkPane #net-settings Input { width: 12; }
    NetworkPane #net-settings Select { width: 10; }
    NetworkPane #net-status { height: auto; padding: 0 1; }
    NetworkPane #net-main { height: 1fr; }
    NetworkPane #net-mesh { width: 40; max-width: 60%; padding: 0 1; border-right: solid $panel; }
    NetworkPane #net-settings #n-opt { width: 22; }
    NetworkPane #net-settings #n-example { width: 24; }
    NetworkPane TabbedContent { width: 1fr; }
    NetworkPane DataTable { height: 1fr; }
    NetworkPane RichLog { height: 1fr; }
    """

    BINDINGS = [
        Binding("ctrl+o", "open_case", "Open case"),
        Binding("ctrl+r", "run", "Run search"),
        Binding("ctrl+k", "cancel", "Cancel"),
        Binding("ctrl+t", "to_trace", "To trace tab"),
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self.case = None
        self.files = None
        self.proc = None
        self.result = None
        self.started = None
        self.attempt_no = 0
        self.last_progress = {}
        self.current_frequency = None
        self.examples = network.examples()
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Static("No case. ctrl+o opens application (CSV), mapping and NoC (GML), or pick an example.",
                     id="net-files")
        with Horizontal(id="net-settings"):
            yield Select([(name, i) for i, (name, *_r) in enumerate(self.examples)],
                         prompt="Example", id="n-example", compact=True)
            yield Label(" Freq Hz ")
            yield Input("2000000", id="n-freq", compact=True)
            yield Label(" PF ")
            yield Input("2000", id="n-pf", compact=True)
            yield Label(" Tries ")
            yield Input("500", id="n-tries", compact=True)
            yield Label(" Heuristic ")
            yield Select([(h, h) for h in network.HEURISTICS], value="mbcf", allow_blank=False,
                         id="n-heur", compact=True)
            yield Label(" Tolerance ")
            yield Input("5000", id="n-tol", compact=True)
            yield Label(" Mode ")
            yield Select([("frequency search", True), ("fixed frequency", False)], value=True,
                         allow_blank=False, id="n-opt", compact=True)
            yield Button("Run", id="n-run", variant="success", compact=True)
            yield Button("Cancel", id="n-cancel", variant="error", compact=True)
        yield Static("", id="net-status")
        with Horizontal(id="net-main"):
            with VerticalScroll(id="net-mesh"):
                yield Static("", id="n-mesh")
            with TabbedContent(id="net-tabs"):
                with TabPane("Flows", id="n-tab-flows"):
                    yield DataTable(id="n-flows", cursor_type="row", zebra_stripes=True)
                with TabPane("Attempts", id="n-tab-att"):
                    yield DataTable(id="n-att", cursor_type="row")
                with TabPane("Schedule", id="n-tab-sched"):
                    yield GanttView(id="n-gantt")
                with TabPane("Links", id="n-tab-links"):
                    yield DataTable(id="n-links", cursor_type="row")
                with TabPane("Packets", id="n-tab-pkts"):
                    yield DataTable(id="n-pkts", cursor_type="row", zebra_stripes=True)
                with TabPane("Validation", id="n-tab-val"):
                    yield Static("", id="n-val")
                with TabPane("Log", id="n-tab-log"):
                    yield RichLog(id="n-log", max_lines=5000)

    # ------------------------------------------------------------- case

    def load_case(self, app_file, map_file, noc_file):
        try:
            self.case = network.load_case(app_file, map_file, noc_file)
        except Exception as exc:   # noqa: BLE001
            self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)
            return False
        self.files = (app_file, map_file, noc_file)
        self.result = None
        root = network.repo_root()

        def short(p):
            p = os.path.abspath(p)
            return os.path.relpath(p, root) if p.startswith(root + os.sep) else p

        self.query_one("#net-files", Static).update(
            f"[b]{esc(self.case['appname'])}[/b]  app {esc(short(app_file))}  map {esc(short(map_file))}  "
            f"NoC {esc(short(noc_file))}")
        m = network.mesh(self.case)
        self.query_one("#net-mesh").styles.width = m["width"] * (CELL_W + 2) + 2
        self.query_one("#n-mesh", Static).update(draw_mesh(m))
        self.show_flows()
        return True

    def frequency(self):
        return parse_number(self.query_one("#n-freq", Input).value, 2000000)

    def show_flows(self):
        if self.case is None:
            return
        try:
            f = self.frequency()
            rows, hp, packets = network.flows_at(self.case, f)
        except Exception as exc:   # noqa: BLE001
            self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)
            return
        out = []
        for r in rows:
            nodes = f"{r['src_node']} to {r['dst_node']}" + (" (local)" if r["local"] else "")
            out.append([r["flow"], r["source"], r["target"], nodes, r["hops"], f"{r['datasize']:,}",
                        f"{r['flits']:,}", "-" if r["net_time"] is None else f"{r['net_time']:,}",
                        f"{r['period']:,}", f"{r['deadline']:,}", r["packets"]])
        fill(self.query_one("#n-flows", DataTable),
             ["Flow", "Source", "Target", "Nodes", "Hops", "Bytes", "Flits", "Net time", "Period",
              "Deadline", "Packets/HP"], out)
        self.query_one("#net-status", Static).update(
            f"at {format_frequency(f)}: hyperperiod {hp:,} cycles, {len(packets or [])} packets "
            f"(local flows produce no packets)" if hp else
            f"at {format_frequency(f)}: hyperperiod 0 (a period is shorter than one cycle)")

    def on_input_submitted(self, event):
        if event.input.id == "n-freq":
            self.show_flows()

    def on_select_changed(self, event):
        if event.select.id == "n-example" and isinstance(event.value, int):
            name, app_f, map_f, noc_f = self.examples[event.value]
            self.load_case(app_f, map_f, noc_f)

    def action_open_case(self):
        a, m, n = self.files or ("", "", "")

        def done(res):
            if res:
                self.load_case(res["app"], res["map"], res["noc"])

        self.app.push_screen(FormDialog("Open network case", [
            Field("app", "Application (CSV)", a, "path"),
            Field("map", "Mapping (.map)", m, "path"),
            Field("noc", "NoC (GML)", n, "path"),
        ], tree_root=network.repo_root()), guarded(self.app, done))

    # ----------------------------------------------------------- search

    def on_button_pressed(self, event):
        if event.button.id == "n-run":
            self.action_run()
        elif event.button.id == "n-cancel":
            self.action_cancel()

    def action_run(self):
        if self.case is None:
            self.app.notify("open a case first", severity="warning")
            return
        if self.running():
            self.app.notify("a search is running; ctrl+k cancels it", severity="warning")
            return
        try:
            params = {
                "app": self.files[0], "map": self.files[1], "noc": self.files[2],
                "frequency": self.frequency(),
                "pruning_factor": int(parse_number(self.query_one("#n-pf", Input).value, 2000)),
                "fail_threshold": int(parse_number(self.query_one("#n-tries", Input).value, 500)),
                "heuristic": self.query_one("#n-heur", Select).value,
                "scaling_tolerance": parse_number(self.query_one("#n-tol", Input).value, 5000),
                "optimize": bool(self.query_one("#n-opt", Select).value),
            }
        except ValueError:
            self.app.notify("frequency, PF, tries and tolerance are numbers", severity="error")
            return
        self.query_one("#n-log", RichLog).clear()
        att = self.query_one("#n-att", DataTable)
        att.clear(columns=True)
        for h, w in (("#", 3), ("Frequency", 18), ("Result", 10), ("Skipped", 7), ("Hyperperiod", 14),
                     ("Packets", 7), ("Elapsed", 10)):
            att.add_column(h, width=w)
        self.attempt_no = 0
        self.started = time.time()
        self.last_progress = {}
        self.current_frequency = params["frequency"]
        self.proc = network.start_worker(params)
        self.query_one("#net-tabs", TabbedContent).active = "n-tab-att"
        if self._timer is None:
            self._timer = self.set_interval(0.5, lambda: self.update_status())
        self.monitor(self.proc)

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @work(thread=True, group="net-search")
    def monitor(self, proc):
        finished = False
        for msg in network.read_messages(proc.stdout):
            if msg[0] in ("result", "error"):
                finished = True
            self.app.call_from_thread(self.on_worker_message, msg, proc)
        code = proc.wait()
        if not finished:
            self.app.call_from_thread(self.on_worker_message, ("ended", code), proc)

    def update_status(self, force=False):
        if self.started is None or (not force and not self.running()):
            return
        el = time.time() - self.started
        p = self.last_progress
        running = self.running()
        state = "running" if running else "stopped"
        self.query_one("#net-status", Static).update(
            f"{state}: attempt {self.attempt_no + 1 if running else self.attempt_no} at "
            f"{format_frequency(self.current_frequency or 0)}, search nodes entered {p.get('entered', 0):,}, "
            f"ignored {p.get('ignored', 0):,}, restarts {p.get('skipped', 0)}, elapsed {el:,.0f} s")

    def on_worker_message(self, msg, proc=None):
        if proc is not None and proc is not self.proc:
            return      # message of an earlier (cancelled) search
        kind, data = msg
        log = self.query_one("#n-log", RichLog)
        if kind == "log":
            log.write(data)
            if data.startswith("[info") and "Tentative frequency is" in data:
                try:
                    self.current_frequency = float(data.split("Tentative frequency is")[1].split("Hz")[0])
                except ValueError:
                    pass
        elif kind == "progress":
            self.last_progress = data
            self.update_status()
        elif kind == "attempt":
            self.attempt_no += 1
            self.query_one("#n-att", DataTable).add_row(
                str(self.attempt_no), format_frequency(data["frequency"]),
                "feasible" if data["ok"] else "infeasible", str(data["skipped"]),
                f"{data['hyperperiod']:,}", str(data["packets"]), f"{data['time'] - self.started:,.1f} s")
        elif kind == "result":
            self.proc = None
            self.update_status(True)
            if data is None:
                self.app.notify("no feasible schedule", severity="warning", timeout=8)
                return
            self.show_result(data)
        elif kind == "error":
            self.proc = None
            self.update_status(True)
            log.write(data)
            self.app.notify("search failed; see the Log tab", severity="error", timeout=8)
        elif kind == "ended":
            self.proc = None
            self.update_status(True)
            self.app.notify(f"search process ended without result (exit code {data})", severity="warning")

    def action_cancel(self):
        if self.running():
            self.proc.terminate()
            self.app.notify("search cancelled")

    # ----------------------------------------------------------- result

    def show_result(self, res):
        self.result = res
        att = res.get("attempts")
        best = res["frequency"]
        note = ""
        if att:
            feas = [f for (f, ok, _) in att if ok]
            if feas and min(feas) < best:
                note = (f"  [yellow]an earlier attempt was feasible at {format_frequency(min(feas))}; "
                        f"the search reports the last feasible attempt[/]")
        self.query_one("#net-status", Static).update(
            f"[b]schedule at {format_frequency(best)}[/b], hyperperiod {res['hyperperiod']:,} cycles, "
            f"{len(res['problem']['packets'])} packets, {len(res['skipped'])} skipped{note}")
        trace = network.schedule_trace(res)
        g = self.query_one("#n-gantt", GanttView)
        g.set_trace(trace)
        usage = network.link_usage(res)
        fill(self.query_one("#n-links", DataTable), ["Link", "Packets", "Busy (cycles)", "Utilization"],
             [[r["link"], r["packets"], f"{r['busy']:,}", f"{100 * r['utilization']:.2f}%"] for r in usage])
        prow = []
        for r in network.packet_rows(res):
            prow.append([r["packet"], r["flow"], r["source"], r["target"], f"{r['release']:,}",
                         "-" if r["start"] is None else f"{r['start']:,}",
                         "-" if r["end"] is None else f"{r['end']:,}", f"{r['deadline']:,}",
                         "-" if r["slack"] is None else f"{r['slack']:,}", r["path"]])
        fill(self.query_one("#n-pkts", DataTable),
             ["Packet", "Flow", "From", "To", "Release", "Start", "End", "Deadline", "Slack", "Path"], prow)
        issues = network.validate(res)
        self.query_one("#n-val", Static).update(
            "[green]Schedule valid[/]: no overlap on any link, every packet between release and deadline."
            if not issues else f"[red]{len(issues)} issues[/]\n" + "\n".join(esc(i) for i in issues[:200]))
        m = network.mesh(self.case) if self.case else None
        if m:
            self.query_one("#n-mesh", Static).update(draw_mesh(m, {r["link"]: r["utilization"] for r in usage}))
        self.query_one("#net-tabs", TabbedContent).active = "n-tab-sched"

    def action_to_trace(self):
        if self.result is None:
            self.app.notify("no schedule yet", severity="warning")
            return
        self.app.show_in_trace(network.schedule_trace(self.result))
