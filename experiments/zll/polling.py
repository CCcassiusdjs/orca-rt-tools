"""Event-triggered bound of rttools/modules/routing/wctt.py against GHDL
(tb_poll.vhd): packets of four sources compete for the LOCAL output of
router 4 of a 3x3 mesh.

    python3 polling.py <out_dir> [--ghdl ghdl] [--random 600] [--seed 1]
        [--jobs N] [--reference reference_polling.json]

Cases: --random cases with a random number of packets per source (0 to 6,
at least two packets in all), random request offsets (0 to 20 cycles) and a
random p in {1, 4, 16, 64} (random.Random(--seed)). For each packet, the
bound of wctt.wctt (packets of the case, network-interface terms off: ideal
source and sink; w_h = 20) with the polling rule of the Hermes control unit
(sum over the packets of each other input port) and with the rule of one
round-robin arbiter per output (at most one packet per other input port).

Outputs in <out_dir>: polling.csv (one line per packet) and metrics.json.
The script exits with 1 if a simulation times out or loses a packet, if a
flit arrives with an error, if a latency exceeds the bound of the polling
rule, or if metrics.json differs from --reference.
"""
import argparse
import concurrent.futures
import csv
import json
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "orca-rt-tools")))
from rttools.modules.routing import wctt  # noqa: E402

HERMES = os.path.normpath(os.path.join(HERE, "..", "..", "pkt-sim", "hw", "router", "hermes"))
SOURCES = ["Hermes_package", "Hermes_buffer", "Hermes_switchcontrol", "Hermes_crossbar", "RouterCC", "TopNOC"]
PS = (1, 4, 16, 64)
NODES = (3, 5, 1, 7)
XR = 3
DST = 4
LINE = re.compile(r"POLL k=(\d+) n=(\d+) p=(\d+) req=(-?\d+) latency=(-?\d+) bad=(\d+)")


def cases(n_random, seed):
    rng = random.Random(seed)
    out = []
    while len(out) < n_random:
        p = rng.choice(PS)
        ns = tuple(rng.randint(0, 6) for _ in NODES)
        if sum(ns) < 2:
            continue
        offs = tuple(rng.randint(0, 20) for _ in NODES)
        out.append((p, ns, offs))
    return out


def xy_links(src, dst):
    """Link labels of the XY route (flowUnwrapper convention: L-<src>, a-b, <dst>-L)."""
    x, y = src % XR, src // XR
    dx, dy = dst % XR, dst // XR
    out = ["L-%d" % src]
    node = src
    while x != dx:
        x += 1 if dx > x else -1
        nxt = y * XR + x
        out.append("%d-%d" % (node, nxt))
        node = nxt
    while y != dy:
        y += 1 if dy > y else -1
        nxt = y * XR + x
        out.append("%d-%d" % (node, nxt))
        node = nxt
    out.append("%d-L" % dst)
    return out


def bounds(p, ns, arbitration):
    packets = []
    for k, (node, n) in enumerate(zip(NODES, ns)):
        for i in range(n):
            packets.append({"name": "%d:%d" % (k, i), "path": [{"data": {"label": l}} for l in xy_links(node, DST)],
                            "flits": p, "min_start": 0, "abs_deadline": 0})
    return wctt.wctt(packets, wait="bound", ni="off", arbitration=arbitration)


def build(ghdl, work):
    flags = ["--workdir=" + work, "-fsynopsys", "-fexplicit"]
    os.makedirs(work, exist_ok=True)
    for f in SOURCES:
        subprocess.run([ghdl, "-a"] + flags + [os.path.join(HERMES, f + ".vhd")], check=True,
                       capture_output=True, text=True)
    subprocess.run([ghdl, "-a"] + flags + [os.path.join(HERE, "tb_poll.vhd")], check=True)
    subprocess.run([ghdl, "-e"] + flags + ["tb_poll"], check=True, cwd=work)
    return flags


def simulate(ghdl, flags, work, case):
    p, ns, offs = case
    g = ["-gP=%d" % p] + ["-gN%d=%d" % (k, n) for k, n in enumerate(ns)] + \
        ["-gO%d=%d" % (k, o) for k, o in enumerate(offs)]
    r = subprocess.run([ghdl, "-r"] + flags + ["tb_poll"] + g + ["--ieee-asserts=disable", "--stop-time=200us"],
                       capture_output=True, text=True, cwd=work)
    text = r.stdout + r.stderr
    return [[int(x) for x in m.groups()] for m in LINE.finditer(text)], "POLL timeout" in text


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("out")
    a.add_argument("--ghdl", default="ghdl")
    a.add_argument("--random", type=int, default=600)
    a.add_argument("--seed", type=int, default=1)
    a.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    a.add_argument("--reference", default=None)
    args = a.parse_args(argv)
    out = os.path.abspath(args.out)
    work = os.path.join(out, "work")
    flags = build(args.ghdl, work)
    todo = cases(args.random, args.seed)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(lambda c: simulate(args.ghdl, flags, work, c), todo))

    problems = []
    npk = nbad = ntimeout = above_rr = above_poll = overtaken = 0
    ratio = 0.0
    largest = None
    with open(os.path.join(out, "polling.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["p", "ns", "offs", "source", "packet", "latency", "bound_polling", "bound_round_robin"])
        for (p, ns, offs), (res, timeout) in zip(todo, results):
            if timeout or len(res) != sum(ns):
                ntimeout += 1
                problems.append(f"p={p} ns={ns} offs={offs}: {len(res)} of {sum(ns)} packets")
                continue
            bp, br = bounds(p, ns, "polling"), bounds(p, ns, "round_robin")
            order = [k for k, *_ in res]
            for pos, (k, n, pp, req, lat, bad) in enumerate(res):
                name = "%d:%d" % (k, n)
                w.writerow([p, "/".join(map(str, ns)), "/".join(map(str, offs)), k, n, lat, bp[name], br[name]])
                npk += 1
                nbad += bad
                above_poll += lat > bp[name]
                above_rr += lat > br[name]
                if lat > bp[name]:
                    problems.append(f"p={p} ns={ns} offs={offs} packet {name}: latency {lat} > bound {bp[name]}")
                if ratio < lat / bp[name]:
                    ratio, largest = lat / bp[name], {"p": p, "ns": list(ns), "offs": list(offs), "packet": name,
                                                      "latency": lat, "bound": bp[name]}
                # packets of one other source delivered between the request of this packet and its delivery
                same = {}
                for kk, nn, _, rq, lt, _ in res[:pos]:
                    if kk != k and rq + lt > req:
                        same[kk] = same.get(kk, 0) + 1
                overtaken = max(overtaken, max(same.values(), default=0))
    if nbad:
        problems.append(f"{nbad} flits with error")
    metrics = {"runs": len(todo), "packets": npk, "flits_with_error": nbad, "lost_or_timeout": ntimeout,
               "above_bound_polling": above_poll, "above_bound_round_robin": above_rr,
               "largest_latency_over_bound": round(ratio, 4), "largest_case": largest,
               "largest_packets_of_one_port_before_a_packet": overtaken}
    with open(os.path.join(out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1)
    print(json.dumps(metrics, indent=1))
    if args.reference:
        with open(args.reference) as f:
            ref = json.load(f)
        if ref != metrics:
            problems.append("metrics.json differs from " + args.reference)
    for line in problems[:20]:
        print("PROBLEM", line)
    print("polling:", "MISMATCH" if problems else "match")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
