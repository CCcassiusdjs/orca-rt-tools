"""Command line of rttools.ucxgen (see the package docstring).

    python -m rttools.ucxgen generate <csv> <map> --name N [--mesh WxH] --out DIR
           [--cycles-per-count C] [--reserve R] [--payload-divisor D] [--tag-mod M] [--delay-ns NS]
           [--bodies BODIES.json] [--release tick|data]
    python -m rttools.ucxgen check <csv> <map> --name N ... --out DIR
           (exit 1 when DIR/N.{c,json,sim} differ from a new generation)
    python -m rttools.ucxgen compose --app A:<csv>:<map> --app B:<csv>:<map> ... --name N [--mesh WxH]
           --out DIR [--cycles-per-count C] [--payload-divisor D] [--tag-mod M] [--delay-ns NS]
           [--release tick|data]
           (one image for several applications on disjoint PEs, rttools.multiapp; model.compose)
    python -m rttools.ucxgen compose-check --app ... --name N ... --out DIR
           (exit 1 when DIR/N.{c,json,sim} differ from a new composition)
    python -m rttools.ucxgen memory DIR/N.json [--image-map image.map | --heap BYTES]
           [--in-flight K] [--divisors 1,2,4] [--json OUT]
           (exit 1 when the worst PE does not fit with the payload divisor 1 of the manifest)

    python -m rttools.ucxgen tt <csv> <map> --arch ARCH.gml --name N --clock HZ [--clock HZ ...] --out DIR
           [--style named|array|jobs]
           (table DIR/N_tt.h of the time-triggered injection, lib/noc_tt.c: the instant of each packet
           between PEs in the link schedule at each clock; rttools.ucxgen.tt. Style: array, or jobs for a
           time-triggered application, with the flows of DIR/N.json; named (TT_AT_<source>_<target>) with
           the flows of the CSV, for application E, app/weird_a.c)
    python -m rttools.ucxgen tt-check ... (exit 1 when DIR/N_tt.h differs from a new generation)
    python -m rttools.ucxgen tt-compose --composition C.json --name N --clock HZ ... --out DIR
           (the same for a composition: link schedule of the union of the packets, flows of DIR/N.json)
    python -m rttools.ucxgen tt-compose-check ...

--release: tick (default) writes the release by tick (lib/tick_release.c,
-DUCX_TICK_RELEASE) with the data-driven code under #ifndef; data writes the
files of the generator before the release by tick (runs CV, CV2 and MA).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from rttools.ucxgen import emit, memory, model


def outputs(m):
    return {f"{m['name']}.c": emit.c_source(m), f"{m['name']}.json": emit.manifest(m),
            f"{m['name']}.sim": emit.sim_setup(m)}


def add_gen_args(p):
    p.add_argument("csv")
    p.add_argument("map")
    p.add_argument("--name", required=True)
    p.add_argument("--mesh", default="4x4")
    p.add_argument("--out", required=True)
    p.add_argument("--cycles-per-count", type=float, default=model.CYCLES_PER_COUNT)
    p.add_argument("--reserve", type=int, default=None,
                   help="cycles of c(v) outside ucx_sleep (default: scheduler_cycles of the CSV)")
    p.add_argument("--payload-divisor", type=int, default=1)
    p.add_argument("--tag-mod", type=int, default=model.TAG_MOD)
    p.add_argument("--delay-ns", type=int, default=model.DEFAULT_DELAY_NS)
    p.add_argument("--bodies", default=None,
                   help="JSON file with the body of each task (sleep, sort, search, count); default: sleep")
    add_release_arg(p)


def add_release_arg(p):
    p.add_argument("--release", choices=model.RELEASE_RULES, default=model.TICK,
                   help="release rule of the tasks: tick (default; wait for the tick of the phase k + n(v)) "
                        "or data (the code of the runs CV, CV2 and MA)")


def build(a):
    cpc = int(a.cycles_per_count) if float(a.cycles_per_count).is_integer() else a.cycles_per_count
    return model.build(a.csv, a.map, a.name, mesh=a.mesh, cycles_per_count=cpc, reserve=a.reserve,
                       payload_divisor=a.payload_divisor, tag_mod=a.tag_mod, delay_ns=a.delay_ns,
                       bodies=a.bodies, release_rule=a.release)


def cmd_generate(a):
    m = build(a)
    os.makedirs(a.out, exist_ok=True)
    for name, text in outputs(m).items():
        with open(os.path.join(a.out, name), "w") as f:
            f.write(text)
    for w in m["warnings"]:
        print("warning: " + w, file=sys.stderr)
    r = m["release"]
    print(f"{m['name']}: {len(m['tasks'])} tasks, {len(m['flows'])} flows "
          f"({sum(not f['local'] for f in m['flows'])} between PEs), mesh {a.mesh}, "
          f"release mask {r.get('tick_mask', r['mask'])} "
          f"(PEs {', '.join(map(str, r.get('tick_pes', r['pes'])))}, release {r.get('rule', model.DATA)}) -> {a.out}")
    return 0


def cmd_check(a):
    m = build(a)
    diff = []
    for name, text in outputs(m).items():
        path = os.path.join(a.out, name)
        if not os.path.exists(path) or open(path).read() != text:
            diff.append(path)
    for p in diff:
        print("differs from the generator: " + p)
    if not diff:
        print(f"{m['name']}: generated files match ({a.out})")
    return 1 if diff else 0


def add_compose_args(p):
    p.add_argument("--app", action="append", required=True, metavar="NAME:CSV:MAP",
                   help="application of the composition (repeat; the order numbers ports, flows and letters)")
    p.add_argument("--name", required=True)
    p.add_argument("--mesh", default="4x4")
    p.add_argument("--out", required=True)
    p.add_argument("--cycles-per-count", type=float, default=model.CYCLES_PER_COUNT)
    p.add_argument("--payload-divisor", type=int, default=1)
    p.add_argument("--tag-mod", type=int, default=model.TAG_MOD)
    p.add_argument("--delay-ns", type=int, default=model.DEFAULT_DELAY_NS)
    add_release_arg(p)


def build_composition(a):
    parts = []
    for spec in a.app:
        name, sep, rest = spec.partition(":")
        csv_path, sep2, map_path = rest.rpartition(":")
        if not (sep and sep2 and name and csv_path and map_path):
            raise model.GenError(f"--app NAME:CSV:MAP expected, got {spec!r}")
        parts.append((name, csv_path, map_path))
    cpc = int(a.cycles_per_count) if float(a.cycles_per_count).is_integer() else a.cycles_per_count
    return model.compose(parts, a.name, mesh=a.mesh, cycles_per_count=cpc, payload_divisor=a.payload_divisor,
                         tag_mod=a.tag_mod, delay_ns=a.delay_ns, release_rule=a.release)


def cmd_compose(a):
    m = build_composition(a)
    os.makedirs(a.out, exist_ok=True)
    for name, text in outputs(m).items():
        with open(os.path.join(a.out, name), "w") as f:
            f.write(text)
    for w in m["warnings"]:
        print("warning: " + w, file=sys.stderr)
    r = m["release"]
    for x in m["apps"]:
        print(f"{x['name']}: {len(x['tasks'])} tasks, flows {x['flows'][0]} to {x['flows'][-1]}, "
              f"PEs {', '.join(map(str, x['pes']))}, sources on PEs {', '.join(map(str, x['release_pes']))}")
    print(f"{m['name']}: {len(m['tasks'])} tasks, {len(m['flows'])} flows "
          f"({sum(not f['local'] for f in m['flows'])} between PEs), mesh {a.mesh}, "
          f"release mask {r.get('tick_mask', r['mask'])} "
          f"(PEs {', '.join(map(str, r.get('tick_pes', r['pes'])))}, release {r.get('rule', model.DATA)}) -> {a.out}")
    return 0


def cmd_compose_check(a):
    m = build_composition(a)
    diff = [os.path.join(a.out, n) for n, text in outputs(m).items()
            if not os.path.exists(os.path.join(a.out, n)) or open(os.path.join(a.out, n)).read() != text]
    for p in diff:
        print("differs from the generator: " + p)
    if not diff:
        print(f"{m['name']}: generated files match ({a.out})")
    return 1 if diff else 0


def cmd_memory(a):
    m = json.load(open(a.manifest))
    heap = a.heap if a.heap is not None else (memory.heap_size(a.image_map) if a.image_map else None)
    divisors = [int(x) for x in a.divisors.split(",")]
    base = m.get("payload_divisor", 1)
    if base not in divisors:
        divisors.insert(0, base)
    rows = memory.report(m, heap, a.in_flight, divisors)
    print(f"{m['name']}: heap {heap if heap is not None else 'unknown'} bytes "
          f"(usable {memory.usable(heap) if heap is not None else 'unknown'}), "
          f"{a.in_flight} received packets in flight per input edge between PEs")
    print("divisor  largest_payload  worst_pe  demand  margin  fits")
    for r in rows:
        print(f"{r['divisor']:>7}  {r['largest_payload']:>15}  {r['worst_pe']:>8}  {r['bytes']:>6}  "
              f"{'-' if r['margin'] is None else r['margin']:>6}  {'-' if r['fits'] is None else r['fits']}")
    per_pe = memory.pe_demand(m, a.in_flight)
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"heap": heap, "usable": memory.usable(heap), "in_flight": a.in_flight,
                       "per_pe": per_pe, "divisors": rows}, f, indent=1)
    own = next(r for r in rows if r["divisor"] == base)
    return 1 if own["fits"] is False else 0


def add_tt_args(p, composition=False):
    if composition:
        p.add_argument("--composition", required=True, help="composition file of rttools.multiapp")
    else:
        p.add_argument("csv")
        p.add_argument("map")
        p.add_argument("--arch", required=True, help="architecture (.gml) of the link schedule")
        p.add_argument("--style", choices=("named", "array", "jobs"), default=None,
                       help="named: TT_AT_<source>_<target> from the flows of the CSV (application E); "
                            "default: array (one release period) or jobs (time-triggered application) with the "
                            "flows of DIR/N.json")
    p.add_argument("--name", required=True)
    p.add_argument("--clock", type=int, action="append", required=True, help="clock F_CLK of a build (Hz); repeat")
    p.add_argument("--out", required=True)
    p.add_argument("--ni", default="tt",
                   help="network-interface model of the link schedule (rttools/modules/routing/router.py, "
                        "parse_ni; default tt: the resource and w_NI = NI_WAIT_CYCLES)")


def tt_text(a, composition=False):
    """Text of DIR/N_tt.h with the network-interface model --ni (default tt)."""
    from rttools.modules.routing import router
    prev = router.set_ni(a.ni)
    try:
        return _tt_text(a, composition)
    finally:
        router.set_ni(None if prev is None else prev)


def _tt_text(a, composition=False):
    from rttools.modules.io import appparser, mapparser, nocparser
    from rttools.tui.model import network as tnet
    from rttools.ucxgen import tt
    rel = os.path.basename
    if composition:
        from rttools.multiapp import compose
        spec = compose.read_spec(a.composition)
        with tnet.quiet():
            comp = compose.load(spec)
        tables = [tt.union(comp, f) for f in sorted(set(a.clock))]
        m = json.load(open(os.path.join(a.out, a.name + ".json")))
        flows = m["flows"]
        paths = [a.composition, spec["arch"]] + [x["csv"] for x in spec["apps"]] + [
            x["map"] for x in spec["apps"] if x["map"] != compose.MAP_SPIRAL]
        cmd = (f"tt-compose --composition {rel(a.composition)} --name {a.name} "
               + " ".join(f"--clock {f}" for f in sorted(set(a.clock))) + (f" --ni {a.ni}" if a.ni != "tt" else ""))
        style = "array"
    else:
        with tnet.quiet():
            g, appname = appparser.loadFromFile(a.csv)
            noc = nocparser.loadFromFile(a.arch)
            entries = mapparser.loadFromFile(a.map)
        tables = [tt.single(g, noc, entries, appname, f) for f in sorted(set(a.clock))]
        style = a.style
        if style == "named":
            _, csv_flows, _ = model.read_csv(a.csv)
            flows = [{"id": int(f["id"]), "csv_id": int(f["id"]), "source": f["source"], "target": f["target"]}
                     for f in csv_flows]
        else:
            m = json.load(open(os.path.join(a.out, a.name + ".json")))
            flows = m["flows"]
            if style is None:
                style = "jobs" if m.get("model") == "time_triggered" else "array"
        paths = [a.csv, a.map, a.arch]
        cmd = (f"tt {rel(a.csv)} {rel(a.map)} --arch {rel(a.arch)} --name {a.name} "
               + " ".join(f"--clock {f}" for f in sorted(set(a.clock))) + (f" --style {a.style}" if a.style else "")
               + (f" --ni {a.ni}" if a.ni != "tt" else ""))
    return tt.header(a.name, cmd, tt.inputs_comment(paths), tables, flows, style)


def cmd_tt(a, composition=False):
    text = tt_text(a, composition)
    path = os.path.join(a.out, a.name + "_tt.h")
    with open(path, "w") as f:
        f.write(text)
    print(f"{a.name}: injection table for {', '.join(map(str, sorted(set(a.clock))))} Hz -> {path}")
    return 0


def cmd_tt_check(a, composition=False):
    text = tt_text(a, composition)
    path = os.path.join(a.out, a.name + "_tt.h")
    if not os.path.exists(path) or open(path).read() != text:
        print("differs from the generator: " + path)
        return 1
    print(f"{a.name}: injection table matches ({path})")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m rttools.ucxgen", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    add_gen_args(sub.add_parser("generate"))
    add_gen_args(sub.add_parser("check"))
    add_compose_args(sub.add_parser("compose"))
    add_compose_args(sub.add_parser("compose-check"))
    p = sub.add_parser("memory")
    p.add_argument("manifest")
    p.add_argument("--image-map")
    p.add_argument("--heap", type=int)
    p.add_argument("--in-flight", type=int, default=2)
    p.add_argument("--divisors", default="1,2,4,8,16")
    p.add_argument("--json")
    add_tt_args(sub.add_parser("tt"))
    add_tt_args(sub.add_parser("tt-check"))
    add_tt_args(sub.add_parser("tt-compose"), composition=True)
    add_tt_args(sub.add_parser("tt-compose-check"), composition=True)
    a = ap.parse_args(argv)
    try:
        return {"generate": cmd_generate, "check": cmd_check, "memory": cmd_memory, "compose": cmd_compose,
                "compose-check": cmd_compose_check, "tt": cmd_tt, "tt-check": cmd_tt_check,
                "tt-compose": lambda x: cmd_tt(x, True),
                "tt-compose-check": lambda x: cmd_tt_check(x, True)}[a.cmd](a)
    except ValueError as e:      # model.GenError, mapfile.MappingError, tt.TTError
        print("error: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
