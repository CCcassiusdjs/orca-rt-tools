"""Command line of rttools.ucxgen (see the package docstring).

    python -m rttools.ucxgen generate <csv> <map> --name N [--mesh WxH] --out DIR
           [--cycles-per-count C] [--reserve R] [--payload-divisor D] [--tag-mod M] [--delay-ns NS]
    python -m rttools.ucxgen check <csv> <map> --name N ... --out DIR
           (exit 1 when DIR/N.{c,json,sim} differ from a new generation)
    python -m rttools.ucxgen compose --app A:<csv>:<map> --app B:<csv>:<map> ... --name N [--mesh WxH]
           --out DIR [--cycles-per-count C] [--payload-divisor D] [--tag-mod M] [--delay-ns NS]
           (one image for several applications on disjoint PEs, rttools.multiapp; model.compose)
    python -m rttools.ucxgen compose-check --app ... --name N ... --out DIR
           (exit 1 when DIR/N.{c,json,sim} differ from a new composition)
    python -m rttools.ucxgen memory DIR/N.json [--image-map image.map | --heap BYTES]
           [--in-flight K] [--divisors 1,2,4] [--json OUT]
           (exit 1 when the worst PE does not fit with the payload divisor 1 of the manifest)
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


def build(a):
    cpc = int(a.cycles_per_count) if float(a.cycles_per_count).is_integer() else a.cycles_per_count
    return model.build(a.csv, a.map, a.name, mesh=a.mesh, cycles_per_count=cpc, reserve=a.reserve,
                       payload_divisor=a.payload_divisor, tag_mod=a.tag_mod, delay_ns=a.delay_ns)


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
          f"release mask {r['mask']} (PEs {', '.join(map(str, r['pes']))}) -> {a.out}")
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
                         tag_mod=a.tag_mod, delay_ns=a.delay_ns)


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
          f"release mask {r['mask']} (PEs {', '.join(map(str, r['pes']))}) -> {a.out}")
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
    a = ap.parse_args(argv)
    try:
        return {"generate": cmd_generate, "check": cmd_check, "memory": cmd_memory, "compose": cmd_compose,
                "compose-check": cmd_compose_check}[a.cmd](a)
    except ValueError as e:      # model.GenError, mapfile.MappingError
        print("error: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
