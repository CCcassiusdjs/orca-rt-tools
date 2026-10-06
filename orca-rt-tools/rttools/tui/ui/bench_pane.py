"""ORT/BENCH front end: task set editor, simulation and schedulability
tests."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, Select, Static, TabbedContent, TabPane

from rttools.tui.model import benchmodel, schedtests
from rttools.tui.model.timeunit import format_value
from rttools.tui.ui.dialogs import Field, FormDialog, parse_number
from rttools.tui.ui.gantt import GanttView
from rttools.tui.ui.tables import fill


def hyperperiod(tasks):
    ps = [t["period"] for t in tasks if t.get("period")]
    return schedtests.lcm(ps) if ps else None


class BenchPane(Widget):
    DEFAULT_CSS = """
    BenchPane { height: 1fr; }
    BenchPane #bench-top { height: 15; }
    BenchPane #bench-tasks { width: 1fr; }
    BenchPane #bench-tasks DataTable { height: 1fr; }
    BenchPane #bench-form { width: 46; padding: 0 1; height: auto; }
    BenchPane #bench-form Horizontal { height: auto; }
    BenchPane #bench-form Input { width: 1fr; }
    BenchPane #bench-form Label { width: 10; padding: 1 0 0 0; }
    BenchPane #bench-form Select { width: 1fr; }
    BenchPane #bench-buttons { height: auto; }
    BenchPane #bench-buttons Button { min-width: 8; margin-right: 1; }
    BenchPane #bench-settings { height: 1; }
    BenchPane #bench-settings Label { width: auto; }
    BenchPane #bench-settings Input { width: 14; }
    BenchPane #bench-settings Select { width: 12; }
    BenchPane #bench-status { height: auto; padding: 0 1; background: $panel; }
    BenchPane #bench-bottom { height: 1fr; }
    BenchPane #bench-results { height: 12; }
    """

    BINDINGS = [
        Binding("ctrl+r", "run", "Run"),
        Binding("ctrl+o", "load", "Load"),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+t", "to_trace", "To trace tab"),
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self.tasks = []
        self.path = None
        self.last_trace = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="bench-top"):
            with Vertical(id="bench-tasks"):
                yield DataTable(id="b-tasks", cursor_type="row", zebra_stripes=True)
            with Vertical(id="bench-form"):
                with Horizontal():
                    yield Label("Task")
                    yield Input(placeholder="name", id="b-name")
                with Horizontal():
                    yield Label("WCET")
                    yield Input(placeholder="cycles", id="b-wcet")
                with Horizontal():
                    yield Label("Period")
                    yield Input(placeholder="empty: one-shot job", id="b-period")
                with Horizontal():
                    yield Label("Deadline")
                    yield Input(placeholder="empty: = period", id="b-deadline")
                with Horizontal(id="bench-buttons"):
                    yield Button("Add/Update", id="b-add", variant="primary")
                    yield Button("Delete", id="b-del")
                    yield Button("Clear", id="b-clear")
        with Horizontal(id="bench-settings"):
            yield Label(" Policy ")
            yield Select([(k, k) for k in benchmodel.ALGORITHMS], value="RM", allow_blank=False,
                         id="b-algo", compact=True)
            yield Label(" Quantum ")
            yield Input("20", id="b-quantum", compact=True)
            yield Label(" Horizon ")
            yield Input("", placeholder="2 × hyperperiod", id="b-horizon", compact=True)
            yield Label(" Clock Hz ")
            yield Input("", placeholder="optional", id="b-clock", compact=True)
            yield Button("Run", id="b-run", variant="success", compact=True)
        yield Static("Load a task set (ctrl+o) or add tasks; ctrl+r runs the simulation.", id="bench-status")
        with Vertical(id="bench-bottom"):
            yield GanttView(id="b-gantt")
            with TabbedContent(id="bench-results"):
                with TabPane("Tests", id="b-tab-tests"):
                    yield DataTable(id="b-tests", cursor_type="row")
                with TabPane("Response times", id="b-tab-rta"):
                    yield DataTable(id="b-rta", cursor_type="row")
                with TabPane("Misses", id="b-tab-miss"):
                    yield DataTable(id="b-miss", cursor_type="row")

    def on_mount(self):
        self.refresh_tasks()

    # ------------------------------------------------------------ table

    def refresh_tasks(self):
        rows = []
        for x in self.tasks:
            u = f"{x['wcet'] / x['period']:.4f}" if x.get("period") else "-"
            rows.append([x["name"], f"{x['wcet']:,}", f"{x['period']:,}" if x.get("period") else "one-shot",
                         f"{x['deadline']:,}" if x.get("deadline") else "= T" if x.get("period") else "-", u])
        fill(self.query_one("#b-tasks", DataTable), ["Task", "WCET", "Period", "Deadline", "U"], rows,
             keys=[x["name"] for x in self.tasks])
        hp = hyperperiod(self.tasks)
        u = schedtests.utilization(self.tasks)
        self.query_one("#bench-status", Static).update(
            f"{len(self.tasks)} tasks  U = {u:.4f}  hyperperiod = {hp:,}" if hp else
            f"{len(self.tasks)} tasks (no periodic task)")

    def on_data_table_row_selected(self, event):
        if event.data_table.id != "b-tasks":
            return
        name = event.row_key.value
        x = next((t for t in self.tasks if t["name"] == name), None)
        if x is None:
            return
        self.query_one("#b-name", Input).value = x["name"]
        self.query_one("#b-wcet", Input).value = str(x["wcet"])
        self.query_one("#b-period", Input).value = str(x["period"] or "")
        self.query_one("#b-deadline", Input).value = str(x["deadline"] or "")

    def on_button_pressed(self, event):
        bid = event.button.id
        if bid == "b-add":
            self.add_from_form()
        elif bid == "b-del":
            name = self.query_one("#b-name", Input).value.strip()
            self.tasks = [t for t in self.tasks if t["name"] != name]
            self.refresh_tasks()
        elif bid == "b-clear":
            self.tasks = []
            self.refresh_tasks()
        elif bid == "b-run":
            self.action_run()

    def add_from_form(self):
        try:
            name = self.query_one("#b-name", Input).value.strip()
            wcet = parse_number(self.query_one("#b-wcet", Input).value)
            period = parse_number(self.query_one("#b-period", Input).value, None)
            deadline = parse_number(self.query_one("#b-deadline", Input).value, None)
        except ValueError:
            self.app.notify("WCET, period and deadline are integers (cycles)", severity="error")
            return
        if wcet is None:
            self.app.notify("WCET is required", severity="error")
            return
        task = {"name": name, "wcet": int(wcet), "period": int(period) if period else None,
                "deadline": int(deadline) if deadline else None}
        others = [t for t in self.tasks if t["name"] != name]
        errs = benchmodel.validate(others + [task])
        if errs:
            self.app.notify("; ".join(errs), severity="error", timeout=8)
            return
        idx = next((i for i, t in enumerate(self.tasks) if t["name"] == name), None)
        if idx is None:
            self.tasks.append(task)
        else:
            self.tasks[idx] = task
        self.refresh_tasks()

    # ---------------------------------------------------------- actions

    def set_tasks(self, tasks, path=None):
        self.tasks = tasks
        self.path = path
        self.refresh_tasks()

    def action_load(self):
        def done(res):
            if not res or not res["path"]:
                return
            try:
                self.set_tasks(benchmodel.load_tasks(res["path"]), res["path"])
            except Exception as exc:   # noqa: BLE001
                self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)
        self.app.push_screen(FormDialog("Load task set (ORCA graph format)", [
            Field("path", "File", self.path or "", "path")],
            hint="Lines `label wcet [period [deadline]]` after `# nodes`; edges are ignored by the bench."), done)

    def action_save(self):
        def done(res):
            if not res or not res["path"]:
                return
            benchmodel.save_tasks(res["path"], self.tasks)
            self.path = res["path"]
            self.app.notify("saved " + res["path"])
        self.app.push_screen(FormDialog("Save task set", [Field("path", "File", self.path or "tasks.txt", "path")]),
                             done)

    def action_run(self):
        if not self.tasks:
            self.app.notify("no tasks", severity="warning")
            return
        errs = benchmodel.validate(self.tasks)
        if errs:
            self.app.notify("; ".join(errs), severity="error", timeout=8)
            return
        algo = self.query_one("#b-algo", Select).value
        try:
            quantum = int(parse_number(self.query_one("#b-quantum", Input).value, 20))
            hp = hyperperiod(self.tasks)
            default_h = 2 * hp if hp else sum(t["wcet"] for t in self.tasks) + 1
            horizon = int(parse_number(self.query_one("#b-horizon", Input).value, default_h))
            clock = parse_number(self.query_one("#b-clock", Input).value, None)
        except ValueError:
            self.app.notify("quantum, horizon and clock are numbers", severity="error")
            return
        if quantum <= 0:
            self.app.notify("quantum > 0 required", severity="error")
            return
        trace, misses, end, _ = benchmodel.simulate(self.tasks, algo, horizon, quantum, clock)
        self.last_trace = trace
        g = self.query_one("#b-gantt", GanttView)
        g.set_trace(trace)
        self.query_one("#bench-status", Static).update(
            f"{algo}, quantum {quantum}, horizon {horizon:,}: simulation ended at {end:,}; "
            f"{len(misses)} deadline misses")
        self.fill_results(algo, quantum, trace, misses, horizon)

    def fill_results(self, algo, quantum, trace, misses, horizon):
        rows = [[name, text, "✔" if ok else ("✖" if ok is False else "?")]
                for name, text, ok in schedtests.analyze(self.tasks, algo, quantum)]
        rows.append(["Simulation", f"{len(misses)} misses in {horizon:,} cycles", "✔" if not misses else "✖"])
        fill(self.query_one("#b-tests", DataTable), ["Test", "Result", ""], rows)

        obs = schedtests.observed_responses(trace.lane_slices("CPU"), self.tasks, horizon)
        fp = algo in ("RM", "DM")
        rta0 = {r["name"]: r for r in schedtests.response_times(self.tasks, algo)} if fp else {}
        rtaq = {r["name"]: r for r in schedtests.response_times(self.tasks, algo, quantum)} if fp else {}
        rows = []
        for t in self.tasks:
            o = obs.get(t["name"], (None, 0))
            r0 = rta0.get(t["name"], {}).get("R")
            rq = rtaq.get(t["name"], {}).get("R")
            d = (t.get("deadline") or t.get("period")) if t.get("period") else None
            rows.append([t["name"], f"{t['wcet']:,}", f"{t['period']:,}" if t.get("period") else "-",
                         "-" if d is None else f"{d:,}", "-" if r0 is None else f"{r0:,}",
                         "-" if rq is None else f"{rq:,}", "-" if o[0] is None else f"{o[0]:,}", o[1]])
        fill(self.query_one("#b-rta", DataTable),
             ["Task", "C", "T", "D", "R (RTA)", f"R (RTA, J = {quantum})", "R observed", "Jobs done"], rows)
        fill(self.query_one("#b-miss", DataTable), ["Task", "Deadline", "Completion"],
             [[name, f"{d:,}", "not finished" if c is None else f"{c:,}"] for name, d, c in misses])

    def action_to_trace(self):
        if self.last_trace is None:
            self.app.notify("run a simulation first", severity="warning")
            return
        self.app.show_in_trace(self.last_trace)
