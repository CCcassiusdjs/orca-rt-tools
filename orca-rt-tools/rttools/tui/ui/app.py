"""ORCA RT-Tools terminal user interface."""
from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, Markdown, TabbedContent, TabPane

from rttools.tui.ui.bench_pane import BenchPane
from rttools.tui.ui.gantt import GanttView
from rttools.tui.ui.graph_pane import GraphPane
from rttools.tui.ui.network_pane import NetworkPane
from rttools.tui.ui.trace_pane import TracePane

HELP = """
# ORCA RT-Tools TUI

| Tab | Content |
|---|---|
| Trace | Gantt of RTL logs (ModelSim/Questa), bench output, KProfiler `.sch` and CSV; metrics, bursts, packet latency, comparison of two runs, export |
| Bench | Task set editor, ORT/BENCH simulation (RM, DM, EDF, RR), schedulability tests and response times |
| Network | Application, mapping and NoC; flows; ORT/FNS schedule and minimum frequency search with progress; link schedule, link usage, validation |
| Graphs | Task graph (ORCA format): GDE metrics, GCPA costs and critical path, layers, GCM clustering |

## Gantt keys (all tabs)

| Key | Action |
|---|---|
| ← → (shift: ×10) | Move the cursor one column |
| ↑ ↓ | Select a lane |
| n / p | Next / previous event of the selected lane (N / P: any lane) |
| + / - , mouse wheel | Zoom around the cursor (mouse) |
| f | Fit the whole trace |
| m, x | Set / clear the mark; the cursor panel shows the interval mark → cursor in every unit |
| z | Zoom to the interval between the mark and the cursor |
| < > | Pan half a screen |
| Home / End | Cursor to the start / end |
| click | Cursor and lane under the mouse |

## Trace tab

| Key | Action |
|---|---|
| o | Open a trace (format detected; RTL options: raw unit, task map, X-Y swap) |
| u | Cycle the display unit (raw, cycles, ns, µs, ms) |
| U | Set the raw unit and clock (presets: 100 ps for 4c299fc, 1 ns) |
| g | Go to a time in the display unit |
| c | Compare with a second trace (scale for B: 10 compares a 1 ns log with a 100 ps log) |
| e | Export SVG, PNG or CSV (visible window or whole trace) |
| w | Tables over the visible window or the whole trace |
| r | Reload the file |

The Lanes table gives busy time, utilization and time per label; Bursts lists the runs of the selected lane between two passes through IDLE (the cluster executions of Ch. 8); Packets pairs `->` and `<-` TAG lines of the RTL log by tag (FIFO) and gives the latency.

## Units of RTL logs

`manycore_pe.sv` of commit 4c299fc has no `` `timescale ``; ModelSim/Questa then prints `$time` of the PE in units of 100 ps (one cycle of the 500 MHz clock = 20 units). The fixed RTL declares `` `timescale 1ns/100ps ``. The parser reads the unit from a `$printtimescale` line when the log has one; otherwise it assumes 1 ns and marks the unit as assumed.

## Bench tab

ctrl+o load, ctrl+s save, ctrl+r run, ctrl+t open the result in the Trace tab. Tests: utilization, Liu-Layland and hyperbolic bounds (RM, D = T), response time analysis (RM, DM; also with release jitter J = quantum, since the engine preempts only at scheduler interrupts), processor demand (EDF). The Response times table compares the analysis with the response observed in the simulation.

## Network tab

ctrl+o open a case or pick an example; Enter on the frequency recomputes the flows; ctrl+r runs the search (in a separate process), ctrl+k cancels it, ctrl+t opens the link schedule in the Trace tab. The Validation tab checks the AGS schedule independently (overlaps per link, release, deadline). The search reports the last feasible attempt; the status line warns when an earlier attempt was feasible at a lower frequency.

## Graphs tab

ctrl+o load, ctrl+l cluster, ctrl+s save the clustered graph (same format as `python -m rttools.gcm`). MAX_PROC with 4 clusters on `apps/sample-graph-b` gives ABDF, C, EHI and GJ (Ch. 8).

## Command line

| Command | Effect |
|---|---|
| `python -m rttools.tui [file]` | Opens the TUI (a file opens in the Trace tab, or in Bench/Graphs with `--tab`) |
| `python -m rttools.tui stats <trace> [--unit 100ps] [--from T --to T]` | Lane metrics and bursts as text |
| `python -m rttools.tui export <trace> <out.svg/.png/.csv> [--unit 100ps] [--display ms]` | Export without the TUI |
| `python -m rttools.tui compare <A> <B> [--scale-b 10]` | Comparison as text; exit code 0 when identical |
| `textual serve "python -m rttools.tui"` | Same TUI in a web browser (needs `pip install textual-dev`) |
"""


class RTToolsApp(App):
    TITLE = "ORCA RT-Tools"
    SUB_TITLE = "trace · bench · network · graphs"
    CSS = """
    TabbedContent#main { height: 1fr; }
    #main > ContentSwitcher { height: 1fr; }
    #main TabPane { height: 1fr; padding: 0; }
    Markdown { padding: 0 2; }
    """
    BINDINGS = [
        Binding("f1", "show_tab('tab-help')", "Help"),
        Binding("f2", "show_tab('tab-trace')", "Trace"),
        Binding("f3", "show_tab('tab-bench')", "Bench"),
        Binding("f4", "show_tab('tab-network')", "Network"),
        Binding("f5", "show_tab('tab-graphs')", "Graphs"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self, open_file=None, tab=None, open_opts=None):
        super().__init__()
        self.open_file = open_file
        self.start_tab = tab
        self.open_opts = open_opts or {}

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="main", initial="tab-trace"):
            with TabPane("Trace", id="tab-trace"):
                yield TracePane(id="trace")
            with TabPane("Bench", id="tab-bench"):
                yield BenchPane(id="bench")
            with TabPane("Network", id="tab-network"):
                yield NetworkPane(id="network")
            with TabPane("Graphs", id="tab-graphs"):
                yield GraphPane(id="graphs")
            with TabPane("Help", id="tab-help"):
                yield Markdown(HELP)
        yield Footer()

    def on_mount(self):
        if self.open_file:
            tab = self.start_tab or "trace"
            try:
                if tab == "bench":
                    from rttools.tui.model import benchmodel
                    self.query_one(BenchPane).set_tasks(benchmodel.load_tasks(self.open_file), self.open_file)
                elif tab == "graphs":
                    self.query_one(GraphPane).load(self.open_file)
                else:
                    self.query_one(TracePane).load_file(self.open_file, **self.open_opts)
            except Exception as exc:   # noqa: BLE001
                self.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=10)
            self.action_show_tab("tab-" + tab)
        elif self.start_tab:
            self.action_show_tab("tab-" + self.start_tab)

    def action_show_tab(self, tab):
        self.query_one("#main", TabbedContent).active = tab
        pane = self.query_one("#main", TabbedContent).get_pane(tab)
        g = next(iter(pane.query(GanttView)), None) if pane is not None else None
        if g is not None and g.trace is not None:
            g.focus()

    def show_in_trace(self, trace):
        tp = self.query_one(TracePane)
        tp.source = None
        tp.show_trace(trace)
        self.action_show_tab("tab-trace")
