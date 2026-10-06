"""Trace viewer pane."""
from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static, TabbedContent, TabPane

from rttools.tui.model import compare as cmp
from rttools.tui.model import export, metrics, parsers
from rttools.tui.model.timeunit import (
    DISPLAY_MODES, RTL_CLOCK_HZ, RTL_PRESETS, SI, TimeUnit, format_frequency, format_value,
)
from rttools.tui.model.trace import Trace
from rttools.tui.ui.dialogs import Field, FormDialog, guarded, parse_number
from rttools.tui.ui.gantt import GanttView
from rttools.tui.ui.tables import esc, fill


def merged_for_compare(a, b, scale_b=1.0):
    """Trace with the lanes of a and b interleaved (A:lane, B:lane); the
    times of b are multiplied by scale_b."""
    from rttools.tui.model.trace import Mark, Slice
    lanes = []
    for l in a.lanes:
        lanes.append("A:" + l)
        if l in b.lanes:
            lanes.append("B:" + l)
    lanes += ["B:" + l for l in b.lanes if l not in a.lanes]
    sl = [Slice("A:" + s.lane, s.start, s.end, s.label, s.kind, s.detail) for s in a.slices]
    sl += [Slice("B:" + s.lane, int(s.start * scale_b), int(s.end * scale_b), s.label, s.kind, s.detail)
           for s in b.slices]
    mk = [Mark("A:" + m.lane, m.time, m.kind, m.label) for m in a.marks]
    mk += [Mark("B:" + m.lane, int(m.time * scale_b), m.kind, m.label) for m in b.marks]
    return Trace(f"{a.name} vs {b.name}", a.unit, lanes, sl, mk, {"format": "compare"})


class TracePane(Widget):
    DEFAULT_CSS = """
    TracePane { height: 1fr; }
    TracePane #trace-head { height: auto; padding: 0 1; background: $panel; }
    TracePane #trace-cursor { height: auto; padding: 0 1; }
    TracePane TabbedContent { height: 1fr; min-height: 8; }
    TracePane DataTable { height: 1fr; }
    """

    BINDINGS = [
        Binding("o", "open", "Open"),
        Binding("r", "reload", "Reload", show=False),
        Binding("c", "compare", "Compare"),
        Binding("e", "export", "Export"),
        Binding("u", "cycle_mode", "Units"),
        Binding("U", "unit", "Raw unit"),
        Binding("g", "goto", "Go to"),
        Binding("w", "toggle_window", "Stats window"),
    ]

    def __init__(self, **kw):
        super().__init__(**kw)
        self.trace = None
        self.base = None          # trace before a comparison merge
        self.source = None        # dict with path and options
        self.stats_on_view = True
        self.compare_result = None

    def compose(self) -> ComposeResult:
        yield Static("No trace. Press o to open a file (RTL log, bench output, KProfiler .sch, CSV).",
                     id="trace-head")
        yield GanttView(id="gantt")
        yield Static("", id="trace-cursor", markup=False)
        with TabbedContent(id="trace-tabs"):
            with TabPane("Lanes", id="tab-lanes"):
                yield DataTable(id="t-lanes", cursor_type="row")
            with TabPane("Bursts", id="tab-bursts"):
                yield DataTable(id="t-bursts", cursor_type="row")
            with TabPane("Packets", id="tab-packets"):
                yield DataTable(id="t-packets", cursor_type="row")
            with TabPane("Compare", id="tab-compare"):
                yield DataTable(id="t-compare", cursor_type="row")

    @property
    def gantt(self):
        return self.query_one("#gantt", GanttView)

    # -------------------------------------------------------- loading

    def load_file(self, path, fmt=None, names=None, swap_xy=False, unit=None, clock_hz=None):
        tr = parsers.load_trace(path, fmt, names, swap_xy, unit, clock_hz)
        self.source = {"path": path, "fmt": fmt, "names": names, "swap_xy": swap_xy,
                       "unit": unit, "clock_hz": clock_hz}
        self.show_trace(tr)
        return tr

    def show_trace(self, tr, keep_view=False):
        self.trace = tr
        self.base = tr
        self.compare_result = None
        self.gantt.set_trace(tr, keep_view)
        self.update_head()
        self.update_tables()
        self.query_one("#t-compare", DataTable).clear(columns=True)

    def update_head(self):
        tr = self.gantt.trace
        if tr is None:
            return
        u = tr.unit
        warn = ""
        if u.assumed:
            warn = ("  [b red]unit assumed[/]: the log has no $printtimescale line; "
                    "press U to choose 100 ps (4c299fc) or 1 ns")
        fmt = tr.meta.get("format", "?")
        self.query_one("#trace-head", Static).update(
            f"[b]{esc(tr.name)}[/b]  format {fmt}  lanes {len(tr.lanes)}  slices {len(tr.slices)}  "
            f"marks {len(tr.marks)}  {u.describe()}  display [b]{self.gantt.mode}[/b]{warn}")

    def on_gantt_view_cursor_moved(self, event):
        if event.view is not self.gantt:
            return
        g = self.gantt
        tr = g.trace
        lines = g.describe_cursor()
        lane = event.lane
        if lane is not None:
            s = tr.slice_at(lane, event.time)
            if s is not None:
                lines.append(f"{lane}: {s.label} [{format_value(tr.unit.convert(s.start, g.mode), g.mode)}, "
                             f"{format_value(tr.unit.convert(s.end, g.mode), g.mode)})  duration "
                             f"{format_value(tr.unit.convert(s.duration, g.mode), g.mode)}"
                             + (f"  {s.detail}" if s.detail else ""))
            near = [m for m in tr.lane_marks(lane) if abs(m.time - event.time) <= max(1, g.dt)]
            for m in near[:3]:
                lines.append(f"{lane}: {m.kind} {m.label} at "
                             f"{format_value(tr.unit.convert(m.time, g.mode), g.mode)}")
        self.query_one("#trace-cursor", Static).update("\n".join(lines))
        if self.stats_on_view:
            self.update_tables()

    def _fmt(self, raw):
        g = self.gantt
        return format_value(g.trace.unit.convert(raw, g.mode), g.mode)

    def update_tables(self):
        g = self.gantt
        tr = g.trace
        if tr is None:
            return
        t0, t1 = g.visible_window() if self.stats_on_view else (tr.t0, tr.t1)
        t0, t1 = max(t0, tr.t0), min(t1, tr.t1)
        if t1 <= t0:
            t0, t1 = tr.t0, tr.t1
        rows = []
        for st in metrics.all_stats(tr, t0, t1):
            per = ", ".join(f"{k} {100 * v / st.window:.1f}%" for k, v in
                            sorted(st.per_label.items(), key=lambda kv: -kv[1])[:8] if st.window)
            rows.append([st.lane, self._fmt(st.busy), self._fmt(st.idle), f"{100 * st.utilization:.2f}%",
                         st.slices, st.switches, per])
        fill(self.query_one("#t-lanes", DataTable),
             ["Lane", "Busy", "Idle", "Utilization", "Slices", "Switches", "Time per label"], rows)
        rows = []
        lane = g.selected_lane
        if lane is not None:
            for b in metrics.bursts(tr, lane, t0, t1)[:500]:
                rows.append([lane, self._fmt(b["start"]), self._fmt(b["end"]), self._fmt(b["duration"]),
                             b["sequence"], "partial" if b["partial"] else ""])
        fill(self.query_one("#t-bursts", DataTable), ["Lane", "Start", "End", "Duration", "Sequence", ""], rows)
        packets = tr.meta.get("packets") or (self.base.meta.get("packets") if self.base else None)
        pt = self.query_one("#t-packets", DataTable)
        if packets:
            stats, unmatched = metrics.packet_stats(packets)
            rows = [[r["tag"], r["src"] or "?", r["dst"] or "?", r["count"], self._fmt(r["min"]),
                     self._fmt(round(r["mean"])), self._fmt(r["max"])] for r in stats]
            if unmatched:
                rows.append(["unpaired", "", "", unmatched, "", "", ""])
            fill(pt, ["Tag", "From", "To", "Count", "Min latency", "Mean", "Max"], rows)
        else:
            fill(pt, ["Packets"], [["no send/receive marks in this trace"]])

    # -------------------------------------------------------- actions

    def action_open(self):
        def done(res):
            if not res or not res.get("path"):
                return
            names = parsers.load_names(res["map"]) if res.get("map") else None
            unit = None
            if res.get("unit") in RTL_PRESETS:
                unit = RTL_PRESETS[res["unit"]]
            fmt = None if res.get("fmt") == "auto" else res.get("fmt")
            clock = parse_number(res.get("clock"), None)
            try:
                self.load_file(res["path"], fmt, names, res.get("swap"), unit, clock)
                self.gantt.focus()
            except Exception as exc:   # noqa: BLE001 - shown to the user
                self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)

        self.app.push_screen(FormDialog("Open trace", [
            Field("path", "File", self.source["path"] if self.source else "", "path"),
            Field("fmt", "Format", "auto", "select",
                  [("detect", "auto"), ("RTL log", "rtl"), ("bench output", "bench"),
                   ("KProfiler .sch", "kprofiler"), ("CSV", "csv")]),
            Field("unit", "RTL raw unit", "auto", "select",
                  [("detect from $printtimescale, else 1 ns", "auto"),
                   ("100 ps (manycore_pe without `timescale, 4c299fc)", "100ps"),
                   ("1 ns (manycore_pe with `timescale 1ns/100ps)", "1ns")]),
            Field("map", "RTL task map (JSON)", "", "path", placeholder="empty: map of rttools/log2gannt"),
            Field("swap", "RTL swap X and Y", False, "switch"),
            Field("clock", "Bench clock (Hz)", "", "text", placeholder="for ns/ms display, e.g. 500M"),
        ], hint="RTL map: JSON object PE -> list of task names by index, as in log2gannt --map."), guarded(self.app, done))

    def action_reload(self):
        if self.source:
            s = self.source
            try:
                self.load_file(s["path"], s["fmt"], s["names"], s["swap_xy"], s["unit"], s["clock_hz"])
            except Exception as exc:   # noqa: BLE001
                self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)

    def action_cycle_mode(self):
        g = self.gantt
        if g.trace is None:
            return
        modes = g.trace.unit.available_modes()
        g.mode = modes[(modes.index(g.mode) + 1) % len(modes)] if g.mode in modes else modes[0]
        self.update_head()
        self.update_tables()

    def action_unit(self):
        g = self.gantt
        if g.trace is None:
            return

        def done(res):
            if not res:
                return
            if res["preset"] in RTL_PRESETS:
                unit = RTL_PRESETS[res["preset"]]
            else:
                txt = res["custom"].replace(" ", "")
                num = "".join(ch for ch in txt if ch.isdigit() or ch == ".")
                suf = txt[len(num):] or "ns"
                try:
                    value = float(num)
                except ValueError:
                    value = 0.0
                if suf not in SI or value <= 0:
                    self.app.notify("raw unit: positive number + fs|ps|ns|us|ms|s, e.g. 100ps", severity="error")
                    return
                unit = TimeUnit(value * SI[suf], f"{num} {suf}")
            clk = parse_number(res["clock"], None)
            if clk is not None and clk <= 0:
                self.app.notify("clock: positive number of Hz", severity="error")
                return
            unit = unit.with_clock(clk if clk else unit.clock_hz)
            for tr in {id(self.base): self.base, id(g.trace): g.trace}.values():
                tr.unit = unit
            if self.source:
                self.source["unit"] = unit
            g.set_trace(g.trace, keep_view=True)
            self.update_head()
            self.update_tables()

        u = g.trace.unit
        self.app.push_screen(FormDialog("Raw time unit", [
            Field("preset", "Preset", "custom", "select",
                  [("custom (fields below)", "custom"),
                   ("RTL 100 ps, clock 500 MHz (4c299fc)", "100ps"),
                   ("RTL 1 ns, clock 500 MHz", "1ns")]),
            Field("custom", "Custom raw unit", u.name.replace(" ", ""), "text", placeholder="100ps, 1ns, 1us"),
            Field("clock", "Clock (Hz)", f"{u.clock_hz:g}" if u.clock_hz else "", "text",
                  placeholder="500M"),
        ], hint="The thesis (Ch. 8) read logs of 4c299fc as 1 ns; the PE prints $time in units of 100 ps."),
            guarded(self.app, done))

    def action_goto(self):
        g = self.gantt
        if g.trace is None:
            return

        def done(res):
            if not res or not res["value"]:
                return
            try:
                v = parse_number(res["value"])
            except ValueError:
                self.app.notify("not a number", severity="error")
                return
            raw = g.trace.unit.from_display(v, g.mode)
            if raw is None:
                return
            g.set_cursor(int(round(raw)))
            g.focus()

        self.app.push_screen(FormDialog(f"Go to time ({g.mode})", [
            Field("value", "Time", "", "text", placeholder="value in the current display unit")]), guarded(self.app, done))

    def action_toggle_window(self):
        self.stats_on_view = not self.stats_on_view
        self.app.notify("tables: " + ("visible window" if self.stats_on_view else "whole trace"))
        self.update_tables()

    def action_export(self):
        g = self.gantt
        if g.trace is None:
            return
        base = os.path.splitext(self.source["path"])[0] if self.source else "trace"

        def done(res):
            if not res or not res["path"]:
                return
            t0, t1 = g.visible_window() if res["range"] == "view" else (g.trace.t0, g.trace.t1)
            try:
                if res["fmt"] == "svg":
                    export.write_svg(g.trace, res["path"], t0, t1, g.mode)
                elif res["fmt"] == "png":
                    export.write_png(g.trace, res["path"], t0, t1, g.mode)
                else:
                    export.write_csv(g.trace, res["path"], t0, t1)
                self.app.notify("saved " + res["path"])
            except Exception as exc:   # noqa: BLE001
                self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)

        self.app.push_screen(FormDialog("Export", [
            Field("fmt", "Format", "svg", "select", [("SVG", "svg"), ("PNG (matplotlib)", "png"), ("CSV", "csv")]),
            Field("range", "Range", "view", "select", [("visible window", "view"), ("whole trace", "all")]),
            Field("path", "File", base + ".svg", "path"),
        ], hint="The axis of SVG and PNG uses the current display unit."), guarded(self.app, done))

    def action_compare(self):
        if self.base is None:
            self.app.notify("open a trace first", severity="warning")
            return

        def done(res):
            if not res or not res["path"]:
                return
            try:
                other = parsers.load_trace(res["path"], None, self.source.get("names") if self.source else None,
                                           res["swap"])
                scale = float(parse_number(res["scale"], 1))
            except Exception as exc:   # noqa: BLE001
                self.app.notify(f"{type(exc).__name__}: {exc}", severity="error", timeout=8)
                return
            self.show_comparison(other, scale)

        self.app.push_screen(FormDialog("Compare with another trace (B)", [
            Field("path", "Trace B", "", "path"),
            Field("scale", "Scale of B times", "1", "text",
                  placeholder="10 compares a 1 ns log (B) with a 100 ps log (A)"),
            Field("swap", "Swap X and Y in B", False, "switch"),
        ], hint="Lanes are matched by name; events by index of the slice in each lane."), guarded(self.app, done))

    def show_comparison(self, other, scale):
        base = self.base
        res = cmp.compare(base, other, scale_b=scale)
        self.compare_result = res
        merged = merged_for_compare(base, other, scale)
        self.trace = merged
        self.gantt.set_trace(merged)
        self.update_head()
        rows = []
        for lane, r in res.items():
            ftm = r["first_time_mismatch"]
            rows.append([lane, r["count_a"], r["count_b"], r["matched"], r["equal_times"],
                         "-" if r["first_label_mismatch"] is None else r["first_label_mismatch"],
                         "-" if ftm is None else f"#{ftm[0]}: {self._fmt(ftm[1])}, {self._fmt(int(ftm[2]))}",
                         "-" if r["min_delta"] is None else self._fmt(int(r["min_delta"])),
                         "-" if r["max_delta"] is None else self._fmt(int(r["max_delta"]))])
        fill(self.query_one("#t-compare", DataTable),
             ["Lane", "Slices A", "Slices B", "Same label", "Same time", "First label diff",
              "First time diff (A, B)", "Δ min", "Δ max"], rows)
        verdict = "identical" if cmp.identical(res) else "different"
        self.app.notify(f"comparison: {verdict}", timeout=6)
        self.query_one("#trace-tabs", TabbedContent).active = "tab-compare"
        self.update_tables()
