"""Gantt widget: one row per lane, one column per time bin."""
from __future__ import annotations

from rich.segment import Segment
from rich.style import Style
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.reactive import reactive
from textual.strip import Strip
from textual.widget import Widget

from rttools.tui.model.export import label_color, ticks
from rttools.tui.model.timeunit import format_value

MARK_GLYPH = {"send": "▼", "recv": "▲", "release": "↑", "deadline": "↓", "miss": "✖", "event": "•"}
MARK_COLOR = {"send": "#5fafff", "recv": "#5fd75f", "release": "#bcbcbc", "deadline": "#ff8787",
              "miss": "#ff3030", "event": "#d7d75f"}
IDLE_BG = "#303030"
EMPTY_BG = "#121212"
AXIS = Style(color="#9e9e9e", bgcolor=EMPTY_BG)


def text_color(hex_bg):
    r, g, b = (int(hex_bg[i:i + 2], 16) for i in (1, 3, 5))
    return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) > 140 else "#ffffff"


class GanttView(Widget, can_focus=True):
    """Keys: left/right move the cursor one column (shift: 10 columns),
    n/p next/previous event of the selected lane, N/P of any lane,
    up/down select a lane, +/- zoom around the cursor, f fit, z zoom to
    the interval between the mark and the cursor, m set the mark at the
    cursor, x clear the mark, < and > pan half a screen. Mouse: click moves
    the cursor and selects the lane; the wheel zooms."""

    DEFAULT_CSS = """
    GanttView { height: auto; max-height: 70%; min-height: 4; background: #121212; }
    GanttView:focus { border-left: thick $accent; }
    """

    BINDINGS = [
        Binding("left", "move(-1)", "◀", show=False),
        Binding("right", "move(1)", "▶", show=False),
        Binding("shift+left", "move(-10)", show=False),
        Binding("shift+right", "move(10)", show=False),
        Binding("up", "lane(-1)", show=False),
        Binding("down", "lane(1)", show=False),
        Binding("plus,equals_sign", "zoom(0.5)", "Zoom in"),
        Binding("minus", "zoom(2)", "Zoom out"),
        Binding("f", "fit", "Fit"),
        Binding("z", "zoom_mark", "Zoom mark-cursor"),
        Binding("m", "mark", "Mark"),
        Binding("x", "clear_mark", show=False),
        Binding("n", "event(1, False)", "Next event"),
        Binding("p", "event(-1, False)", show=False),
        Binding("N", "event(1, True)", show=False),
        Binding("P", "event(-1, True)", show=False),
        Binding("less_than_sign", "pan(-0.5)", show=False),
        Binding("greater_than_sign", "pan(0.5)", show=False),
        Binding("home", "edge(0)", show=False),
        Binding("end", "edge(1)", show=False),
    ]

    class CursorMoved(Message):
        def __init__(self, view, time, lane):
            super().__init__()
            self.view = view
            self.time = time
            self.lane = lane

    mode = reactive("raw")

    def __init__(self, trace=None, **kw):
        super().__init__(**kw)
        self.trace = None
        self.view_t0 = 0.0
        self.view_span = 1.0
        self.cursor = 0
        self.mark = None
        self.lane_index = 0
        self.lane_offset = 0
        self._cache_key = None
        self._rows = []
        if trace is not None:
            self.set_trace(trace)

    # ------------------------------------------------------------ state

    def set_trace(self, trace, keep_view=False):
        self.trace = trace
        if not keep_view:
            self.view_t0 = float(trace.t0)
            self.view_span = float(max(1, trace.t1 - trace.t0))
            self.cursor = trace.t0
            self.mark = None
            self.lane_index = 0
            self.lane_offset = 0
        modes = trace.unit.available_modes()
        if self.mode not in modes:
            self.mode = "raw"
        self._invalidate()
        self._notify()

    def _invalidate(self):
        self._cache_key = None
        self.refresh()

    def watch_mode(self, _):
        self._invalidate()
        self._notify()

    @property
    def label_width(self):
        if not self.trace or not self.trace.lanes:
            return 6
        return min(16, max(len(l) for l in self.trace.lanes) + 1)

    @property
    def plot_width(self):
        return max(1, self.size.width - self.label_width)

    @property
    def dt(self):
        return self.view_span / self.plot_width

    def col_of(self, t):
        return int((t - self.view_t0) / self.dt)

    def time_of(self, col):
        return int(self.view_t0 + col * self.dt)

    @property
    def selected_lane(self):
        if not self.trace or not self.trace.lanes:
            return None
        return self.trace.lanes[min(self.lane_index, len(self.trace.lanes) - 1)]

    def visible_window(self):
        return int(self.view_t0), int(self.view_t0 + self.view_span)

    def lanes_visible(self):
        return max(1, self.size.height - 2)

    def _notify(self):
        if self.trace is not None:
            self.post_message(self.CursorMoved(self, self.cursor, self.selected_lane))

    def _ensure_cursor_visible(self):
        if self.cursor < self.view_t0:
            self.view_t0 = float(self.cursor) - self.view_span * 0.1
        elif self.cursor >= self.view_t0 + self.view_span:
            self.view_t0 = float(self.cursor) - self.view_span * 0.9

    def _ensure_lane_visible(self):
        n = self.lanes_visible()
        if self.lane_index < self.lane_offset:
            self.lane_offset = self.lane_index
        elif self.lane_index >= self.lane_offset + n:
            self.lane_offset = self.lane_index - n + 1

    def set_cursor(self, t, lane_index=None):
        if self.trace is None:
            return
        self.cursor = int(t)
        if lane_index is not None:
            self.lane_index = max(0, min(lane_index, len(self.trace.lanes) - 1))
            self._ensure_lane_visible()
        self._ensure_cursor_visible()
        self._invalidate()
        self._notify()

    def set_view(self, t0, t1):
        if t1 <= t0:
            t1 = t0 + 1
        self.view_t0 = float(t0)
        self.view_span = float(t1 - t0)
        if self.trace is not None:
            lo, hi = self.span_limits()
            self.view_span = min(hi, max(lo, self.view_span))
        self._invalidate()

    # ---------------------------------------------------------- actions

    def action_move(self, cols):
        if self.trace is None:
            return
        step = max(1, int(round(self.dt * abs(cols))))
        self.set_cursor(self.cursor + (step if cols > 0 else -step))

    def action_lane(self, d):
        if self.trace is None:
            return
        self.lane_index = max(0, min(self.lane_index + d, len(self.trace.lanes) - 1))
        self._ensure_lane_visible()
        self._invalidate()
        self._notify()

    def span_limits(self):
        """Smallest span: 4 columns per raw unit; largest: 100 times the
        trace (at least 100 units)."""
        lo = float(self.plot_width) / 4
        hi = max(100.0 * (self.trace.t1 - self.trace.t0), 100.0, lo)
        return lo, hi

    def action_zoom(self, factor, center=None):
        if self.trace is None:
            return
        center = self.cursor if center is None else center
        lo, hi = self.span_limits()
        new_span = min(hi, max(lo, self.view_span * float(factor)))
        if float(factor) < 1 and new_span > self.view_span:
            new_span = self.view_span
        frac = (center - self.view_t0) / self.view_span if self.view_span else 0.5
        frac = min(max(frac, 0.0), 1.0)
        self.view_t0 = center - frac * new_span
        self.view_span = new_span
        self._invalidate()

    def action_fit(self):
        if self.trace is None:
            return
        self.set_view(self.trace.t0, max(self.trace.t1, self.trace.t0 + 1))

    def action_zoom_mark(self):
        if self.mark is None or self.trace is None:
            self.app.bell()
            return
        a, b = sorted((self.mark, self.cursor))
        pad = max(1, (b - a) // 20)
        self.set_view(a - pad, b + pad)

    def action_mark(self):
        self.mark = self.cursor
        self._invalidate()
        self._notify()

    def action_clear_mark(self):
        self.mark = None
        self._invalidate()
        self._notify()

    def action_event(self, direction, any_lane):
        if self.trace is None:
            return
        t = None
        if any_lane:
            t = self.trace.next_event(self.cursor) if direction > 0 else self.trace.prev_event(self.cursor)
        else:
            lane = self.selected_lane
            times = sorted({s.start for s in self.trace.lane_slices(lane)}
                           | {s.end for s in self.trace.lane_slices(lane)}
                           | {m.time for m in self.trace.lane_marks(lane)})
            if direction > 0:
                t = next((x for x in times if x > self.cursor), None)
            else:
                t = next((x for x in reversed(times) if x < self.cursor), None)
        if t is None:
            self.app.bell()
            return
        self.set_cursor(t)

    def action_pan(self, frac):
        self.view_t0 += self.view_span * float(frac)
        self._invalidate()

    def action_edge(self, which):
        if self.trace is None:
            return
        self.set_cursor(self.trace.t0 if int(which) == 0 else self.trace.t1)

    # ------------------------------------------------------------ mouse

    def _content_xy(self, event):
        """Mouse position inside the content region (the focus border adds
        a gutter on the left)."""
        off = event.get_content_offset(self)
        if off is None:
            return None, None
        return off.x, off.y

    def on_click(self, event):
        if self.trace is None:
            return
        x, y = self._content_xy(event)
        if x is None:
            return
        col = x - self.label_width
        row = y - 2
        lane = self.lane_offset + row if row >= 0 else None
        if lane is not None and lane >= len(self.trace.lanes):
            lane = None
        if col >= 0:
            self.set_cursor(self.time_of(col) + int(self.dt / 2), lane)
        elif lane is not None:
            self.lane_index = lane
            self._invalidate()
            self._notify()
        self.focus()

    def on_mouse_scroll_up(self, event):
        x, _ = self._content_xy(event)
        col = (x if x is not None else 0) - self.label_width
        center = self.time_of(col) if col >= 0 else None
        self.action_zoom(0.8, center)
        event.stop()

    def on_mouse_scroll_down(self, event):
        x, _ = self._content_xy(event)
        col = (x if x is not None else 0) - self.label_width
        center = self.time_of(col) if col >= 0 else None
        self.action_zoom(1.25, center)
        event.stop()

    def on_resize(self, _):
        self._ensure_lane_visible()
        self._invalidate()

    # ----------------------------------------------------------- render

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        n = len(self.trace.lanes) if self.trace else 1
        return n + 2

    def _layout(self):
        key = (self.size, self.view_t0, self.view_span, self.cursor, self.mark,
               self.lane_index, self.lane_offset, self.mode, id(self.trace))
        if key == self._cache_key:
            return
        self._cache_key = key
        W = self.size.width
        H = self.size.height
        rows = []
        if self.trace is None or W <= 0:
            self._rows = [[Segment(" " * max(W, 0), AXIS)] for _ in range(H)]
            return
        lw = self.label_width
        pw = self.plot_width
        dt = self.dt
        t0 = self.view_t0
        t1 = t0 + self.view_span
        cur_col = self.col_of(self.cursor) if t0 <= self.cursor < t1 else None
        mark_col = self.col_of(self.mark) if self.mark is not None and t0 <= self.mark < t1 else None

        # axis: tick labels and tick marks
        axis = [" "] * pw
        tick_row = ["─"] * pw
        for raw, text in ticks(self.trace, t0, t1, self.mode, target=max(2, pw // 14)):
            c = self.col_of(raw)
            if 0 <= c < pw:
                tick_row[c] = "┬"
                start = max(0, min(c - len(text) // 2, pw - len(text)))
                if all(ch == " " for ch in axis[max(0, start - 1):start + len(text) + 1]):
                    axis[start:start + len(text)] = list(text)
        rows.append([Segment(" " * lw, AXIS), Segment("".join(axis), AXIS)])
        tick_segs = [Segment(" " * lw, AXIS)]
        for c, ch in enumerate(tick_row):
            st = AXIS
            if c == cur_col:
                st = Style(color="#000000", bgcolor="#ffd700")
            elif c == mark_col:
                st = Style(color="#000000", bgcolor="#87afff")
            tick_segs.append(Segment(ch, st))
        rows.append(tick_segs)

        lanes = self.trace.lanes
        for r in range(H - 2):
            li = self.lane_offset + r
            if li >= len(lanes):
                rows.append([Segment(" " * W, Style(bgcolor=EMPTY_BG))])
                continue
            lane = lanes[li]
            sel = li == self.lane_index
            name = lane[:lw - 1].ljust(lw - 1) + " "
            lstyle = Style(color="#000000", bgcolor="#d7d7d7", bold=True) if sel else Style(color="#d0d0d0", bgcolor=EMPTY_BG)
            segs = [Segment(name, lstyle)]
            cov = [None] * pw   # (label, fraction, idle)
            acc = [dict() for _ in range(pw)]
            for s in self.trace.slices_between(lane, int(t0) - 1, int(t1) + 1):
                a = max(s.start, t0)
                b = min(s.end, t1)
                if b < a:
                    continue
                c0 = int((a - t0) / dt)
                c1 = int((b - t0) / dt)
                if s.start == s.end:
                    c1 = c0
                for c in range(max(0, c0), min(pw - 1, c1) + 1):
                    cs = t0 + c * dt
                    ov = max(0.0, min(b, cs + dt) - max(a, cs))
                    if s.start == s.end:
                        ov = 1e-9
                    elif ov <= 0:
                        continue
                    key = (s.label, self.trace.is_idle(s))
                    acc[c][key] = acc[c].get(key, 0.0) + ov
            for c in range(pw):
                if acc[c]:
                    (lab, idle), v = max(acc[c].items(), key=lambda kv: kv[1])
                    cov[c] = (lab, v / dt if dt > 0 else 1.0, idle)
            chars = [" "] * pw
            styles = [Style(bgcolor=EMPTY_BG)] * pw
            for c in range(pw):
                if cov[c] is None:
                    continue
                lab, frac, idle = cov[c]
                if idle:
                    chars[c] = " "
                    styles[c] = Style(bgcolor=IDLE_BG)
                    continue
                color = label_color(lab)
                if frac >= 0.5:
                    styles[c] = Style(bgcolor=color, color=text_color(color))
                else:
                    chars[c] = "▌"
                    styles[c] = Style(color=color, bgcolor=EMPTY_BG)
            # labels inside runs of the same non-idle label
            c = 0
            while c < pw:
                if cov[c] is None or cov[c][2] or cov[c][1] < 0.5:
                    c += 1
                    continue
                lab = cov[c][0]
                e = c
                while e + 1 < pw and cov[e + 1] is not None and cov[e + 1][0] == lab and cov[e + 1][1] >= 0.5:
                    e += 1
                n = e - c + 1
                if n >= len(lab) + 2:
                    off = c + (n - len(lab)) // 2
                    for i, ch in enumerate(lab):
                        chars[off + i] = ch
                c = e + 1
            for m in self.trace.marks_between(lane, int(t0), int(t1) + 1):
                c = int((m.time - t0) / dt)
                if 0 <= c < pw:
                    chars[c] = MARK_GLYPH.get(m.kind, "•")
                    bg = styles[c].bgcolor
                    styles[c] = Style(color=MARK_COLOR.get(m.kind, "#ffffff"),
                                      bgcolor=bg if bg is not None else EMPTY_BG, bold=True)
            for c, bg in ((mark_col, "#5f87d7"), (cur_col, "#d7af00")):
                if c is None:
                    continue
                if chars[c] == " ":
                    chars[c] = "│"
                styles[c] = Style(color="#000000", bgcolor=bg, bold=True)
            # merge consecutive cells with the same style
            run_start = 0
            for c in range(1, pw + 1):
                if c == pw or styles[c] != styles[run_start]:
                    segs.append(Segment("".join(chars[run_start:c]), styles[run_start]))
                    run_start = c
            rows.append(segs)
        self._rows = rows

    def render_line(self, y):
        self._layout()
        if y < len(self._rows):
            return Strip(self._rows[y])
        return Strip([Segment(" " * self.size.width, Style(bgcolor=EMPTY_BG))])

    # ----------------------------------------------------------- helpers

    def describe_cursor(self):
        """Lines for the cursor panel."""
        tr = self.trace
        if tr is None:
            return []
        u = tr.unit
        lines = []
        modes = u.available_modes()
        lines.append("cursor  " + "   ".join(format_value(u.convert(self.cursor, m), m) for m in modes))
        if self.mark is not None:
            d = self.cursor - self.mark
            lines.append("mark    " + "   ".join(format_value(u.convert(self.mark, m), m) for m in modes))
            lines.append("Δ       " + "   ".join(format_value(u.convert(d, m), m) for m in modes))
        a, b = self.visible_window()
        lines.append("view    " + format_value(u.convert(a, self.mode), self.mode) + " → "
                     + format_value(u.convert(b, self.mode), self.mode)
                     + "   column = " + format_value(u.convert(self.dt, self.mode), self.mode))
        return lines
