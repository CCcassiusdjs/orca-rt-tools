"""Entry point: `python -m rttools.tui [options] [file]` opens the TUI;
`stats`, `export` and `compare` run without the TUI (batch use, for
example on the simulation server)."""
from __future__ import annotations

import argparse
import sys


def _unit(args):
    from rttools.tui.model.timeunit import RTL_PRESETS
    return RTL_PRESETS.get(args.unit) if getattr(args, "unit", None) else None


def _load(path, args, swap=False):
    from rttools.tui.model import parsers
    names = parsers.load_names(args.map) if getattr(args, "map", None) else None
    return parsers.load_trace(path, args.format, names, swap or args.swap_xy, _unit(args))


def _common(p):
    p.add_argument("--format", choices=["rtl", "bench", "kprofiler", "csv"], default=None,
                   help="trace format (default: detect)")
    p.add_argument("--unit", choices=["100ps", "1ns"], default=None,
                   help="raw unit of RTL logs (default: $printtimescale line, else 1 ns)")
    p.add_argument("--map", default=None, help="RTL task map (JSON, as log2gannt --map)")
    p.add_argument("--swap-xy", action="store_true", help="swap X and Y of the RTL node labels")


def cmd_stats(argv):
    from rttools.tui.model import metrics
    from rttools.tui.model.timeunit import format_value
    p = argparse.ArgumentParser(prog="rttools.tui stats")
    p.add_argument("trace")
    _common(p)
    p.add_argument("--display", default="raw", choices=["raw", "cycles", "ns", "us", "ms"])
    p.add_argument("--from", dest="t0", type=int, default=None, help="raw time")
    p.add_argument("--to", dest="t1", type=int, default=None, help="raw time")
    a = p.parse_args(argv)
    tr = _load(a.trace, a)
    u = tr.unit
    if a.display not in u.available_modes():
        print(f"display {a.display} needs a known unit/clock; using raw", file=sys.stderr)
        a.display = "raw"

    def f(v):
        return format_value(u.convert(v, a.display), a.display)
    t0 = tr.t0 if a.t0 is None else a.t0
    t1 = tr.t1 if a.t1 is None else a.t1
    print(f"{tr.name}: {len(tr.lanes)} lanes, {len(tr.slices)} slices, {u.describe()}")
    print(f"window {f(t0)} .. {f(t1)}")
    print("| Lane | Busy | Utilization | Slices | Time per label |")
    print("|---|---:|---:|---:|---|")
    for st in metrics.all_stats(tr, t0, t1):
        per = ", ".join(f"{k} {f(v)}" for k, v in sorted(st.per_label.items(), key=lambda kv: -kv[1]))
        print(f"| {st.lane} | {f(st.busy)} | {100 * st.utilization:.2f}% | {st.slices} | {per} |")
    print()
    print("| Lane | Burst start | Burst end | Duration | Sequence |")
    print("|---|---:|---:|---:|---|")
    for lane in tr.lanes:
        for b in metrics.bursts(tr, lane, t0, t1):
            print(f"| {lane} | {f(b['start'])} | {f(b['end'])} | {f(b['duration'])} | "
                  f"{b['sequence']}{' (partial)' if b['partial'] else ''} |")
    pk = tr.meta.get("packets")
    if pk:
        stats, unmatched = metrics.packet_stats(pk)
        print()
        print("| Tag | From | To | Count | Min | Mean | Max |")
        print("|---|---|---|---:|---:|---:|---:|")
        for r in stats:
            print(f"| {r['tag']} | {r['src']} | {r['dst']} | {r['count']} | {f(r['min'])} | "
                  f"{f(round(r['mean']))} | {f(r['max'])} |")
        if unmatched:
            print(f"unpaired send/receive lines: {unmatched}")
    return 0


def cmd_export(argv):
    from rttools.tui.model import export
    p = argparse.ArgumentParser(prog="rttools.tui export")
    p.add_argument("trace")
    p.add_argument("out", help="output file (.svg, .png or .csv)")
    _common(p)
    p.add_argument("--display", default="raw", choices=["raw", "cycles", "ns", "us", "ms"])
    p.add_argument("--from", dest="t0", type=int, default=None)
    p.add_argument("--to", dest="t1", type=int, default=None)
    a = p.parse_args(argv)
    tr = _load(a.trace, a)
    if a.display not in tr.unit.available_modes():
        a.display = "raw"
    if a.out.endswith(".svg"):
        export.write_svg(tr, a.out, a.t0, a.t1, a.display)
    elif a.out.endswith(".png"):
        export.write_png(tr, a.out, a.t0, a.t1, a.display)
    elif a.out.endswith(".csv"):
        export.write_csv(tr, a.out, a.t0, a.t1)
    else:
        p.error("output extension: .svg, .png or .csv")
    print("wrote " + a.out)
    return 0


def cmd_compare(argv):
    from rttools.tui.model import compare
    p = argparse.ArgumentParser(prog="rttools.tui compare")
    p.add_argument("a")
    p.add_argument("b")
    _common(p)
    p.add_argument("--scale-b", type=float, default=1.0, help="multiply the times of B")
    p.add_argument("--swap-xy-b", action="store_true", help="swap X and Y in B only")
    a = p.parse_args(argv)
    ta = _load(a.a, a)
    tb = _load(a.b, a, swap=a.swap_xy_b)
    res = compare.compare(ta, tb, a.scale_b)

    def num(v):
        if v is None:
            return "-"
        return str(int(v)) if float(v).is_integer() else f"{v:g}"
    print("| Lane | Slices A | Slices B | Same label | Same time | First label diff | Δ min | Δ max |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for lane, r in res.items():
        print(f"| {lane} | {r['count_a']} | {r['count_b']} | {r['matched']} | {r['equal_times']} | "
              f"{'-' if r['first_label_mismatch'] is None else r['first_label_mismatch']} | "
              f"{num(r['min_delta'])} | {num(r['max_delta'])} |")
    same = compare.identical(res)
    print("identical" if same else "different")
    return 0 if same else 1


def cmd_tui(argv):
    p = argparse.ArgumentParser(prog="rttools.tui", description="ORCA RT-Tools terminal user interface. "
                                "Subcommands without the TUI: stats, export, compare.")
    p.add_argument("file", nargs="?", help="file to open")
    p.add_argument("--tab", choices=["trace", "bench", "network", "graphs", "help"], default=None)
    _common(p)
    a = p.parse_args(argv)
    from rttools.tui.ui.app import RTToolsApp
    opts = {}
    if a.file and (a.tab in (None, "trace")):
        from rttools.tui.model import parsers
        opts = {"fmt": a.format, "names": parsers.load_names(a.map) if a.map else None,
                "swap_xy": a.swap_xy, "unit": _unit(a)}
    RTToolsApp(a.file, a.tab, opts).run()
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("stats", "export", "compare"):
        return {"stats": cmd_stats, "export": cmd_export, "compare": cmd_compare}[argv[0]](argv[1:])
    return cmd_tui(argv)


if __name__ == "__main__":
    sys.exit(main())
