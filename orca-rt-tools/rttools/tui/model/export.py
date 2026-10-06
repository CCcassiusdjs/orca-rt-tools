"""Export of traces: CSV, SVG (no dependency) and PNG (matplotlib)."""
from __future__ import annotations

import colorsys
import hashlib
import math
from xml.sax.saxutils import escape

from rttools.tui.model.timeunit import format_value

MARK_KINDS = ("send", "recv", "release", "deadline", "miss", "event")


def query_end(trace, t1):
    """Query end for [t0, t1): includes the zero-length slices at the
    end of the trace when the window reaches it."""
    return t1 + 1 if t1 >= trace.t1 else t1


def write_csv(trace, path, t0=None, t1=None):
    t0 = trace.t0 if t0 is None else t0
    t1 = query_end(trace, trace.t1 if t1 is None else t1)
    u = trace.unit
    with open(path, "w") as f:
        f.write(f"# unit_seconds={u.seconds} unit_name={u.name.replace(' ', '_')} "
                f"clock_hz={u.clock_hz}\n")
        f.write("lane,start,end,label,kind\n")
        for lane in trace.lanes:
            for s in trace.slices_between(lane, t0, t1):
                f.write(f"{lane},{s.start},{s.end},{s.label},{s.kind}\n")
            for m in trace.marks_between(lane, t0, t1):
                f.write(f"{lane},{m.time},{m.time},{m.label},{m.kind}\n")


def label_color(label, idle=False):
    """Stable color per label (same hue in the TUI, SVG and PNG)."""
    if idle:
        return "#d0d0d0"
    h = int(hashlib.md5(label.encode()).hexdigest()[:6], 16) / 0xFFFFFF
    r, g, b = colorsys.hls_to_rgb(h, 0.55, 0.55)
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def nice_step(span, target):
    """Tick step (1, 2 or 5 x 10^k) for about `target` ticks over `span`."""
    if span <= 0:
        return 1
    raw = span / max(1, target)
    k = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 5, 10):
        if raw <= m * k:
            return m * k
    return 10 * k


def ticks(trace, t0, t1, mode, target=8):
    """Tick positions (raw) at round values of the display mode."""
    u = trace.unit
    a, b = u.convert(t0, mode), u.convert(t1, mode)
    if a is None or b is None:
        mode, a, b = "raw", t0, t1
    step = nice_step(b - a, target)
    v = math.ceil(a / step) * step
    out = []
    while v <= b + 1e-9:
        raw = u.from_display(v, mode) if mode != "raw" else v
        out.append((raw, format_value(v, mode)))
        v += step
    return out


def write_svg(trace, path, t0=None, t1=None, mode="raw", width=1400, lane_h=22,
              show_labels=True, title=None):
    t0 = trace.t0 if t0 is None else t0
    t1 = trace.t1 if t1 is None else t1
    if t1 <= t0:
        t1 = t0 + 1
    left, right, top = 90, 20, 40
    plot_w = width - left - right
    height = top + lane_h * len(trace.lanes) + 50
    sx = plot_w / (t1 - t0)

    def x(t):
        return left + (t - t0) * sx

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'font-family="Helvetica, Arial, sans-serif" font-size="11">',
           f'<rect width="{width}" height="{height}" fill="white"/>']
    title = title or trace.name
    out.append(f'<text x="{left}" y="18" font-size="13" font-weight="bold">{escape(title)}</text>')
    out.append(f'<text x="{width - right}" y="18" text-anchor="end">{escape(trace.unit.describe())}</text>')
    for raw, text in ticks(trace, t0, t1, mode):
        xx = x(raw)
        out.append(f'<line x1="{xx:.2f}" y1="{top - 4}" x2="{xx:.2f}" '
                   f'y2="{top + lane_h * len(trace.lanes)}" stroke="#e4e4e4"/>')
        out.append(f'<text x="{xx:.2f}" y="{top + lane_h * len(trace.lanes) + 16}" '
                   f'text-anchor="middle">{escape(text)}</text>')
    for i, lane in enumerate(trace.lanes):
        y = top + i * lane_h
        out.append(f'<text x="{left - 6}" y="{y + lane_h * 0.68:.1f}" text-anchor="end">{escape(lane)}</text>')
        out.append(f'<line x1="{left}" y1="{y + lane_h}" x2="{width - right}" y2="{y + lane_h}" stroke="#f0f0f0"/>')
        for s in trace.slices_between(lane, t0, query_end(trace, t1)):
            a, b = max(s.start, t0), min(s.end, t1)
            w = max((b - a) * sx, 0.6)
            color = label_color(s.label, trace.is_idle(s))
            out.append(f'<rect x="{x(a):.2f}" y="{y + 3}" width="{w:.2f}" height="{lane_h - 6}" '
                       f'fill="{color}"><title>{escape(s.label)} [{s.start}, {s.end})</title></rect>')
            if show_labels and not trace.is_idle(s) and w > 7 * len(s.label) + 4:
                out.append(f'<text x="{x(a) + w / 2:.2f}" y="{y + lane_h * 0.68:.1f}" '
                           f'text-anchor="middle" fill="white">{escape(s.label)}</text>')
        for m in trace.marks_between(lane, t0, t1 + 1):
            xx = x(m.time)
            color = {"send": "#1f5fbf", "recv": "#1f8f3f", "miss": "#d01010",
                     "deadline": "#d01010", "release": "#555555"}.get(m.kind, "#444444")
            if m.kind in ("send", "release"):
                pts = f"{xx - 3:.2f},{y + 2} {xx + 3:.2f},{y + 2} {xx:.2f},{y + 8}"
            else:
                pts = f"{xx - 3:.2f},{y + lane_h - 2} {xx + 3:.2f},{y + lane_h - 2} {xx:.2f},{y + lane_h - 8}"
            out.append(f'<polygon points="{pts}" fill="{color}"><title>{escape(m.kind)} '
                       f'{escape(m.label)} @ {m.time}</title></polygon>')
    out.append("</svg>")
    with open(path, "w") as f:
        f.write("\n".join(out))


def write_png(trace, path, t0=None, t1=None, mode="raw", dpi=200):
    """PNG through matplotlib (optional dependency)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t0 = trace.t0 if t0 is None else t0
    t1 = trace.t1 if t1 is None else t1
    n = len(trace.lanes)
    fig, ax = plt.subplots(figsize=(12, 0.45 * n + 1.2))
    for i, lane in enumerate(trace.lanes):
        y = n - 1 - i
        for s in trace.slices_between(lane, t0, query_end(trace, t1)):
            a, b = max(s.start, t0), min(s.end, t1)
            ax.broken_barh([(a, max(b - a, 0))], (y - 0.35, 0.7),
                           facecolors=label_color(s.label, trace.is_idle(s)))
    ax.set_yticks(range(n))
    ax.set_yticklabels(list(reversed(trace.lanes)))
    ax.set_xlim(t0, t1)
    tk = ticks(trace, t0, t1, mode)
    ax.set_xticks([r for r, _ in tk])
    ax.set_xticklabels([t for _, t in tk])
    ax.grid(True, axis="x", color="#e4e4e4")
    ax.set_title(trace.name + "  (" + trace.unit.describe() + ")", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
