"""Several applications on one NoC: the analysis flow of rttools.multiapp
on a composition (experiments/multiapp).

    python -m rttools.paper.multiapp run --config <config.json> --out <dir>
    python -m rttools.paper.multiapp maps --config <config.json> [--check]
    python -m rttools.paper.exp23 check <dir>/metrics.json <reference.json>

config.json (paths relative to the file):

| Key | Content |
|---|---|
| composition | composition file of rttools.multiapp (the composition of the RTL run) |
| alternatives | {name: composition file}: other placements of the same applications |
| maps | {application: .map file}: stored mapping of each application of `composition` (input of rttools.ucxgen compose); `maps --check` compares it with the placement |
| single | [{"app", "arch", "map"}]: each application alone through rttools.multiapp against search.minimum_frequency (the flow of one application) |
| random | {"placements", "seed"}: random placements of the clusters of `composition` on the mesh (one cluster per PE) |
| f0_hz | first frequency of the searches |

| Output | Content |
|---|---|
| metrics.json | Per application: PEs, mapping, f_CPU, f_NoC alone, R_bound at the frequency of the platform; the union: packets over H, f_NoC, f, network check at f_CPU, skipped packets; shared links; collisions of the schedules of each application alone at f; overlaps of the union schedule across hyperperiods; alternatives; random placements; single-application equivalence; clock of the RTL run |
| apps.csv | One row per application |
| links.csv | Links used by more than one application, with the packets of each application |
| values.tex | \\ExpMultiapp... macros |
| maps/<app>.map | Mapping of each application on the mesh |
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys

from rttools.modules.frequency import search
from rttools.modules.io import appparser, mapparser, nocparser
from rttools.modules.mapping import mapfile
from rttools.modules.routing import router
from rttools.multiapp import compose
from rttools.paper import exp23
from rttools.paper.frequency import search_config
from rttools.paper.rtlapp import task_deadlines
from rttools.tui.model import network


def read_config(path):
    with open(path) as f:
        cfg = json.load(f)
    base = os.path.dirname(os.path.abspath(path))

    def res(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))
    cfg["composition"] = res(cfg["composition"])
    cfg["alternatives"] = {k: res(v) for k, v in (cfg.get("alternatives") or {}).items()}
    cfg["maps"] = {k: res(v) for k, v in (cfg.get("maps") or {}).items()}
    cfg["single"] = [dict(s, csv=res(s["csv"]), arch=res(s["arch"]),
                          map=s["map"] if s["map"] == compose.MAP_SPIRAL else res(s["map"]))
                     for s in cfg.get("single") or []]
    return cfg


def load(path):
    with network.quiet():
        return compose.load(compose.read_spec(path))


def deadline_s(a):
    d = task_deadlines(a["csv"])
    return max(d.values()) if d else None


def binding(f, f_cpu, f_star):
    if f is None:
        return None
    return "cpu" if f_cpu is not None and f == f_cpu and (f_star is None or f_cpu > f_star) else "network"


def analyze_composition(comp, f0):
    """Analysis flow on one composition: frequency of the platform, union
    schedule at f, R_bound per application, isolated schedules, shared
    links and collisions."""
    apps, noc = comp["apps"], comp["noc"]
    with network.quiet():
        freq = compose.minimum_frequency(apps, noc, search_config(f0))
    f = freq["frequency_hz"]
    out = {"mesh": f"{comp['width']}x{comp['height']}", "arch": os.path.basename(comp["arch"]),
           "f_cpu_hz": freq["f_cpu_hz"], "f_star_hz": freq["f_star_hz"],
           "f_star_lower_hz": freq["network"]["lower"] if freq["network"] else None,
           "attempts": len(freq["network"]["attempts"]) if freq["network"] else None,
           "final_check": freq["final_check"], "frequency_hz": f,
           "binding": binding(f, freq["f_cpu_hz"], freq["f_star_hz"]), "apps": {}}
    if f is None:
        return out, freq
    cfg = search_config(f)
    with network.quiet():
        u = compose.schedule_union(apps, noc, f, cfg)
        iso = compose.isolated(apps, noc, f, cfg)
        packets, H, _, info = compose.union_packets(apps, noc, f)
    shared = compose.shared_links(packets)
    use = {}
    for p in packets:
        for e in p["path"]:
            use.setdefault(e["data"]["label"], {}).setdefault(p["app"], []).append(p["name"])
    coll = compose.collisions(iso, H)
    out["union"] = {"hyperperiod": H, "packets": len(u["problem"]["packets"]), "skipped": len(u["skipped"]),
                    "feasible": search.feasible(u), "periodic_overlaps": compose.periodic_overlaps(u)}
    out["shared_links"] = {"count": len(shared), "links": shared,
                           "packets": {l: {a: len(v) for a, v in use[l].items()} for l in shared}}
    out["isolated"] = {"collision_pairs": coll["pairs"], "collision_links": coll["links"],
                       "colliding_packets": coll["packets"], "packets": coll["packets_total"],
                       "feasible": {n: search.feasible(a) for n, a in iso.items()},
                       "periodic_overlaps": {n: compose.periodic_overlaps(a) for n, a in iso.items()}}
    for a in apps:
        cpu = freq["cpu"][a["name"]]
        with network.quiet():
            alone = search.search_minimum_frequency(a["graph"], noc, a["entries"], a["appname"],
                                                    search_config(f0))
        rb = compose.response_bound(a, noc, f)
        d = deadline_s(a)
        T = compose.app_period_s(a)
        out["apps"][a["name"]] = {
            "csv": os.path.basename(a["csv"]), "placement": a["placement"]["method"],
            "criterion": a["placement"].get("criterion"), "pes": a["pes"],
            "nodes": sorted(int(e["node"]) for e in a["entries"] if e["tasks"]),
            "mapping": {str(e["node"]): list(e["tasks"]) for e in a["entries"]},
            "sequences": rb["sequences"],
            "period_s": T, "cpu_demand_cycles": {str(k): v for k, v in cpu["demand"].items()},
            "f_cpu_hz": cpu["f_cpu_hz"], "utilization_at_f": cpu["f_cpu_hz"] / f,
            "f_star_alone_hz": alone["frequency"] if alone else None,
            "packets_per_hyperperiod": info[a["name"]]["packets"],
            "packets_in_H": info[a["name"]]["packets_in_H"],
            "response_bound": {"v_last": rb["v_last"], "phase": rb["phase"], "finish_cycles": rb["finish_cycles"],
                               "period_cycles": rb["period_cycles"], "cycles": rb["cycles"],
                               "ms": round(rb["s"] * 1e3, 9),
                               "deadline_ms": None if d is None else round(d * 1e3, 9),
                               "deadline_percent": None if d is None else round(100 * rb["s"] / d, 6),
                               "meets_deadline": None if d is None else rb["s"] <= d},
        }
    return out, freq


def random_placements(comp, f, n, seed):
    """`n` random placements of the clusters of the composition (one
    cluster per PE, every permutation of the clusters on the nodes equally
    likely; Python random with `seed`): collisions of the schedules of each
    application alone at f, and the union schedule at f."""
    apps, noc = comp["apps"], comp["noc"]
    clusters = []
    for i, a in enumerate(apps):
        if a["placement"]["method"] != compose.MAP_SPIRAL:
            raise ValueError("random placements need the Spiral placement (clusters of ORT/GCM)")
        clusters += [(i, c) for c in a["placement"]["cluster_nodes"]]
    nodes = list(range(comp["width"] * comp["height"]))
    rng = random.Random(seed)
    cfg = search_config(f)
    saved = [a["entries"] for a in apps]
    rows = []
    try:
        for _ in range(n):
            perm = rng.sample(nodes, len(clusters))
            cn = [dict() for _ in apps]
            for (i, c), node in zip(clusters, perm):
                cn[i][c] = node
            for i, a in enumerate(apps):
                a["entries"] = mapfile.from_dict({t: node for c, node in cn[i].items() for t in c.split(":")})
            with network.quiet():
                u = compose.schedule_union(apps, noc, f, cfg)
                iso = compose.isolated(apps, noc, f, cfg)
                packets, H, _, _ = compose.union_packets(apps, noc, f)
            c = compose.collisions(iso, H)
            rows.append({"shared_links": len(compose.shared_links(packets)), "pairs": c["pairs"],
                         "colliding_packets": sum(c["packets"].values()),
                         "isolated_feasible": all(search.feasible(a) for a in iso.values()),
                         "union_feasible": search.feasible(u)})
    finally:
        for a, e in zip(apps, saved):
            a["entries"] = e
    coll = [r for r in rows if r["pairs"] > 0]
    return {"placements": n, "seed": seed, "frequency_hz": f,
            "with_shared_links": sum(1 for r in rows if r["shared_links"] > 0),
            "with_collisions": len(coll),
            "with_collisions_percent": round(100 * len(coll) / n, 6) if n else None,
            "colliding_packets_max": max((r["colliding_packets"] for r in rows), default=None),
            "collision_pairs_max": max((r["pairs"] for r in rows), default=None),
            "shared_links_max": max((r["shared_links"] for r in rows), default=None),
            "isolated_infeasible": sum(1 for r in rows if not r["isolated_feasible"]),
            "union_feasible": sum(1 for r in rows if r["union_feasible"])}


def single_equivalence(s, f0):
    """One application through rttools.multiapp and through
    search.minimum_frequency (the flow of rttools/__main__.py)."""
    with network.quiet():
        noc = nocparser.loadFromFile(s["arch"])
        g, appname = appparser.loadFromFile(s["csv"])
        a = {"name": s["app"], "csv": s["csv"], "map": s["map"], "graph": g, "appname": appname,
             "pes": s.get("pes")}
        w, h = compose.mesh_size(noc)
        compose.place([a], w, h, list(noc.nodes))
        if s["map"] == compose.MAP_SPIRAL:
            from rttools import __main__ as cli
            from rttools.paper.frequency import mapping_entries
            ref_entries, _ = mapping_entries(cli.MAP_SPIRAL, g, noc)
        else:
            ref_entries = mapparser.loadFromFile(s["map"])
        multi = compose.minimum_frequency([a], noc, search_config(f0))
        one = search.minimum_frequency(g, noc, ref_entries, appname, search_config(f0))
    keys = ("f_star_hz", "f_cpu_hz", "frequency_hz", "final_check")
    same_attempts = (multi["network"]["attempts"] == one["network"]["attempts"]
                     if multi["network"] and one["network"] else multi["network"] is one["network"])
    return {"app": s["app"], "arch": os.path.basename(s["arch"]),
            "map": s["map"] if s["map"] == compose.MAP_SPIRAL else os.path.basename(s["map"]),
            "mapping_equal": a["entries"] == ref_entries,
            "f_star_hz": multi["f_star_hz"], "f_cpu_hz": multi["f_cpu_hz"], "frequency_hz": multi["frequency_hz"],
            "equal": all(multi[k] == one[k] for k in keys) and same_attempts,
            "attempts_equal": same_attempts}


def run(cfg, out_dir):
    f0 = cfg["f0_hz"]
    w = router.header_wait()
    comp = load(cfg["composition"])
    main, _ = analyze_composition(comp, f0)
    m = {"composition": os.path.basename(cfg["composition"]), "f0_hz": f0, "header_wait_cycles": w,
         "occupancy": "L0 + %d (m + 1)" % w if w else "L0", "main": main, "alternatives": {}}
    for name, path in cfg["alternatives"].items():
        alt, _ = analyze_composition(load(path), f0)
        m["alternatives"][name] = {k: alt.get(k) for k in ("mesh", "f_cpu_hz", "f_star_hz", "frequency_hz",
                                                           "binding", "union", "shared_links", "isolated")}
        m["alternatives"][name]["nodes"] = {n: a["nodes"] for n, a in alt["apps"].items()}
        m["alternatives"][name]["f_star_alone_hz"] = {n: a["f_star_alone_hz"] for n, a in alt["apps"].items()}
    f = main["frequency_hz"]
    if cfg.get("random") and f is not None:
        m["random"] = random_placements(comp, f, cfg["random"]["placements"], cfg["random"]["seed"])
    m["single"] = [single_equivalence(s, f0) for s in cfg["single"]]
    if f is not None:
        T = {compose.app_period_s(a) for a in comp["apps"]}
        if len(T) == 1:
            T = T.pop()
            clk = exp23.flow_clock(f, T)
            phase_max = max(a["response_bound"]["phase"] for a in main["apps"].values())
            rb_max = max(a["response_bound"]["ms"] for a in main["apps"].values()) / 1e3
            # release delay 3 ms + (n(v_last) warm-up + 8 measured iterations - 1) T + R_bound + one tick
            sim_s = 3e-3 + (phase_max + 8 - 1) * T + rb_max + T
            m["rtl"] = {"clock": clk, "period_s": T, "sim_ns_min": int(-(-sim_s * 1e9 // 1)),
                        "rule": "3 ms + (max n(v_last) + 8 - 1) T + max R_bound + T"}
    m["maps"] = {a["name"]: mapfile.to_text(a["entries"]) for a in comp["apps"]}
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f_:
        json.dump(m, f_, indent=1)
    os.makedirs(os.path.join(out_dir, "maps"), exist_ok=True)
    for a in comp["apps"]:
        mapfile.write(os.path.join(out_dir, "maps", a["name"] + ".map"), a["entries"])
    write_csvs(out_dir, m)
    write_values(os.path.join(out_dir, "values.tex"), m)
    return m


def write_csvs(out_dir, m):
    main = m["main"]
    with open(os.path.join(out_dir, "apps.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["app", "pes", "nodes", "criterion", "f_cpu_hz", "f_star_alone_hz", "packets_in_H",
                    "colliding_packets_alone", "v_last", "phase", "response_bound_ms", "deadline_ms"])
        for n, a in main["apps"].items():
            rb = a["response_bound"]
            w.writerow([n, a["pes"], " ".join(map(str, a["nodes"])), a["criterion"] or "", a["f_cpu_hz"],
                        a["f_star_alone_hz"], a["packets_in_H"], main["isolated"]["colliding_packets"].get(n),
                        rb["v_last"], rb["phase"], rb["ms"], rb["deadline_ms"]])
    with open(os.path.join(out_dir, "links.csv"), "w", newline="") as f:
        w = csv.writer(f)
        names = list(main["apps"])
        w.writerow(["link"] + [f"packets_{n}" for n in names])
        for l, per in main["shared_links"]["packets"].items():
            w.writerow([l] + [per.get(n, 0) for n in names])


def write_values(path, m):
    lines = ["% generated by python -m rttools.paper.multiapp; do not edit"]

    def put(text, *name):
        lines.append(f"\\newcommand{{\\{exp23.macro_name('multiapp', *name)}}}{{{text}}}")

    def mhz(v):
        return "-" if v is None else f"{v / 1e6:.1f}"

    main = m["main"]
    put(main["mesh"].replace("x", "$\\times$"), "mesh")
    put(str(sum(a["pes"] for a in main["apps"].values())), "pes")
    put(mhz(main["f_cpu_hz"]), "cpu", "mhz")
    put(mhz(main["f_star_hz"]), "network", "mhz")
    put(mhz(main["frequency_hz"]), "minimum", "mhz")
    put(main["binding"] or "-", "binding")
    u = main.get("union") or {}
    put(str(u.get("packets", "-")), "packets")
    put(str(u.get("skipped", "-")), "skipped")
    put(f"{u.get('hyperperiod', 0):,}", "hyperperiod", "cycles")
    put(str(main["shared_links"]["count"]), "shared", "links")
    put(str(main["isolated"]["collision_pairs"]), "collision", "pairs")
    put(str(sum(main["isolated"]["colliding_packets"].values())), "colliding", "packets")
    for n, a in main["apps"].items():
        rb = a["response_bound"]
        put(str(a["pes"]), n, "pes")
        put(mhz(a["f_cpu_hz"]), n, "cpu", "mhz")
        put(mhz(a["f_star_alone_hz"]), n, "network", "alone", "mhz")
        put(f"{100 * a['utilization_at_f']:.1f}", n, "utilization", "percent")
        put(str(a["packets_in_H"]), n, "packets")
        put(str(main["isolated"]["colliding_packets"].get(n, 0)), n, "colliding", "packets")
        put(f"{rb['ms']:.3f}", n, "response", "bound", "ms")
        put("-" if rb["deadline_ms"] is None else f"{rb['deadline_ms']:g}", n, "deadline", "ms")
        put("-" if rb["deadline_percent"] is None else f"{rb['deadline_percent']:.1f}", n, "response", "bound",
            "deadline", "percent")
    for name, alt in m["alternatives"].items():
        put(str(alt["shared_links"]["count"]), name, "shared", "links")
        put(mhz(alt["f_star_hz"]), name, "network", "mhz")
    r = m.get("random")
    if r:
        put(f"{r['placements']:,}", "random", "placements")
        put(f"{r['with_collisions']:,}", "random", "colliding")
        put(f"{r['with_collisions_percent']:.1f}", "random", "colliding", "percent")
        put(str(r["colliding_packets_max"]), "random", "colliding", "packets", "max")
        put(f"{r['union_feasible']:,}", "random", "union", "feasible")
    rtl = m.get("rtl")
    if rtl:
        put(exp23.mhz_text(rtl["clock"]["f_clk_hz"]), "rtl", "clock", "mhz")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def check_maps(cfg):
    """Stored .map files (config `maps`) against the placement of the
    composition; returns the list of differences."""
    comp = load(cfg["composition"])
    diffs = []
    for a in comp["apps"]:
        path = cfg["maps"].get(a["name"])
        text = mapfile.to_text(a["entries"])
        if path is None:
            diffs.append(f"{a['name']}: no stored map in the config")
        elif not os.path.exists(path) or open(path).read() != text:
            diffs.append(f"{a['name']}: {path} differs from the placement")
    return diffs


def write_maps(cfg):
    comp = load(cfg["composition"])
    for a in comp["apps"]:
        mapfile.write(cfg["maps"][a["name"]], a["entries"])
        print("wrote " + cfg["maps"][a["name"]])


def mhz_txt(v):
    return "none" if v is None else f"{v / 1e6:.3f} MHz"


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.multiapp", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--out", required=True)
    mp = sub.add_parser("maps")
    mp.add_argument("--config", required=True)
    mp.add_argument("--check", action="store_true")
    a = p.parse_args(argv)
    cfg = read_config(a.config)
    if a.cmd == "maps":
        if a.check:
            d = check_maps(cfg)
            for x in d:
                print(x)
            if not d:
                print("maps match the placement of " + os.path.basename(cfg["composition"]))
            return 1 if d else 0
        write_maps(cfg)
        return 0
    m = run(cfg, a.out)
    mn = m["main"]
    print(f"  {m['composition']}: mesh {mn['mesh']}, link occupancy o_i = {m['occupancy']}")
    for n, x in mn["apps"].items():
        rb = x["response_bound"]
        print(f"  {n}: {x['pes']} PEs {x['nodes']}, f_CPU {mhz_txt(x['f_cpu_hz'])}, f_NoC alone "
              f"{mhz_txt(x['f_star_alone_hz'])}, R_bound {rb['ms']:.3f} ms ({rb['v_last']}, phase {rb['phase']}; "
              f"deadline {rb['deadline_ms']} ms)")
    u = mn.get("union") or {}
    print(f"  union: {u.get('packets')} packets over H = {u.get('hyperperiod')} cycles, f_NoC "
          f"{mhz_txt(mn['f_star_hz'])}, f {mhz_txt(mn['frequency_hz'])} ({mn['binding']}), skipped {u.get('skipped')}")
    print(f"  shared links {mn['shared_links']['count']} {mn['shared_links']['links']}; schedules alone at f: "
          f"{mn['isolated']['collision_pairs']} colliding pairs, packets {mn['isolated']['colliding_packets']}")
    for n, alt in m["alternatives"].items():
        print(f"  {n}: shared links {alt['shared_links']['count']}, f_NoC {mhz_txt(alt['f_star_hz'])}, "
              f"colliding pairs alone {alt['isolated']['collision_pairs']}")
    if m.get("random"):
        r = m["random"]
        print(f"  random placements {r['placements']} (seed {r['seed']}): {r['with_collisions']} with collisions "
              f"alone ({r['with_collisions_percent']:.1f}%), max {r['colliding_packets_max']} packets; union "
              f"feasible in {r['union_feasible']}")
    for s in m["single"]:
        print(f"  {s['app']} alone on {s['arch']} ({s['map']}): equal to the flow of one application {s['equal']}")
    if m.get("rtl"):
        print(f"  RTL clock {m['rtl']['clock']['f_clk_hz']} Hz, simulation >= {m['rtl']['sim_ns_min']} ns")
    print("wrote " + a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
