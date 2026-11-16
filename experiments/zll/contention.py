"""Header wait at one Hermes router with GHDL (tb_cont.vhd).

    python3 contention.py <out_dir> [--ghdl ghdl] [--random 2500] [--seed 1]
        [--jobs N] [--reference reference_contention.json]

Cases: every nonempty subset of the five packets of tb_cont.vhd with the
offsets (0, 0, 0, 0, 6) for p in {1, 4, 16, 64}, and --random cases with a
random subset, random offsets (0 to 12 cycles for the four packets with
m = 2, 0 to 18 cycles for the LOCAL packet) and a random p from the same
set (random.Random(--seed)). Each packet that arrives gives
extra = latency - L0, the wait of its header at the SwitchControl of
router 4.

Outputs in <out_dir>:
  contention.csv          p,en,n_active,offs,k,m,latency,l0,extra,bad (one line per packet)
  contention_summary.txt  largest wait per number n of headers at router 4
  metrics.json            the same numbers for the check

The script exits with 1 if a simulation times out or loses a packet, if a
flit arrives with an error, if a wait exceeds S (n - 1) with S the service
time of one header, or if metrics.json differs from --reference.
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
HERMES = os.path.normpath(os.path.join(HERE, "..", "..", "pkt-sim", "hw", "router", "hermes"))
SOURCES = ["Hermes_package", "Hermes_buffer", "Hermes_switchcontrol", "Hermes_crossbar", "RouterCC", "TopNOC"]
PS = (1, 4, 16, 64)
NPACKETS = 5
LINE = re.compile(r"CONT k=(\d+) m=(\d+) p=(\d+) off=(-?\d+) start=(\d+) latency=(-?\d+) "
                  r"l0=(\d+) extra=(-?\d+) bad=(\d+)")


def cases(n_random, seed):
    """Fixed cases, then the random cases (same order as the r9 sweep)."""
    out = [(p, en, (0, 0, 0, 0, 6)) for p in PS for en in range(1, 2 ** NPACKETS)]
    rng = random.Random(seed)
    for _ in range(n_random):
        p = rng.choice(PS)
        en = rng.randint(1, 2 ** NPACKETS - 1)
        offs = tuple(rng.randint(0, 12) for _ in range(4)) + (rng.randint(0, 18),)
        out.append((p, en, offs))
    return out


def build(ghdl, work):
    flags = ["--workdir=" + work, "-fsynopsys", "-fexplicit"]
    os.makedirs(work, exist_ok=True)
    for f in SOURCES:
        subprocess.run([ghdl, "-a"] + flags + [os.path.join(HERMES, f + ".vhd")], check=True,
                       capture_output=True, text=True)
    subprocess.run([ghdl, "-a"] + flags + [os.path.join(HERE, "tb_cont.vhd")], check=True)
    subprocess.run([ghdl, "-e"] + flags + ["tb_cont"], check=True, cwd=work)
    return flags


def simulate(ghdl, flags, work, case):
    p, en, offs = case
    g = ["-gP=%d" % p, "-gEN=%d" % en] + ["-gO%d=%d" % (k, o) for k, o in enumerate(offs)]
    r = subprocess.run([ghdl, "-r"] + flags + ["tb_cont"] + g + ["--ieee-asserts=disable", "--stop-time=100us"],
                       capture_output=True, text=True, cwd=work)
    text = r.stdout + r.stderr
    res = [[int(x) for x in m.groups()] for m in LINE.finditer(text)]
    return res, "CONT timeout" in text


def flatten(d, prefix=""):
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(flatten(v, f"{prefix}{k}."))
    else:
        out[prefix[:-1]] = d
    return out


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    a.add_argument("out")
    a.add_argument("--ghdl", default="ghdl")
    a.add_argument("--random", type=int, default=2500, help="number of random cases (default 2500)")
    a.add_argument("--seed", type=int, default=1)
    a.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    a.add_argument("--reference", default=None, help="reference_contention.json")
    args = a.parse_args(argv)

    out = os.path.abspath(args.out)
    work = os.path.join(out, "work")
    flags = build(args.ghdl, work)
    todo = cases(args.random, args.seed)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as ex:
        results = list(ex.map(lambda c: simulate(args.ghdl, flags, work, c), todo))

    problems = []
    worst, samples = {}, {}
    npk = nbad = ntimeout = 0
    with open(os.path.join(out, "contention.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["p", "en", "n_active", "offs", "k", "m", "latency", "l0", "extra", "bad"])
        for (p, en, offs), (res, timeout) in zip(todo, results):
            n = bin(en).count("1")
            if timeout or len(res) != n:
                ntimeout += 1
                problems.append(f"p={p} en={en} offs={offs}: {len(res)} of {n} packets"
                                + (" (timeout)" if timeout else ""))
                continue
            for k, m, pp, off, start, lat, l0, extra, bad in res:
                w.writerow([p, en, n, "/".join(map(str, offs)), k, m, lat, l0, extra, bad])
                npk += 1
                nbad += bad
                if extra < 0:
                    problems.append(f"p={p} en={en} offs={offs} k={k}: latency {lat} below L0 = {l0}")
                worst[n] = max(worst.get(n, extra), extra)
                samples[n] = samples.get(n, 0) + 1

    # service time S of one header: the largest wait grows by S per competing header
    steps = {worst[n] - worst[n - 1] for n in range(2, NPACKETS + 1) if n in worst and n - 1 in worst}
    service = steps.pop() if len(steps) == 1 else None
    if service is None:
        problems.append(f"largest wait per header count is not linear: {worst}")
    else:
        for n, v in worst.items():
            if v > service * (n - 1):
                problems.append(f"n={n}: wait {v} > {service} x {n - 1}")
    if nbad:
        problems.append(f"{nbad} flits with error")

    metrics = {
        "runs": len(todo), "packets": npk, "flits_with_error": nbad, "lost_or_timeout": ntimeout,
        "service_cycles_per_header": service,
        "competing_headers_max": NPACKETS - 1,
        "largest_wait_cycles": max(worst.values()) if worst else None,
        "largest_wait_by_headers": {str(n): worst[n] for n in sorted(worst)},
        "samples_by_headers": {str(n): samples[n] for n in sorted(samples)},
    }
    with open(os.path.join(out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=1)

    ghdl_version = subprocess.run([args.ghdl, "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    lines = [f"Hermes header wait at router 4 of a 3x3 mesh: {ghdl_version.split(' (')[0]}, "
             f"{len(todo)} runs (seed {args.seed}), p in {{{', '.join(map(str, PS))}}}",
             f"packets {npk}, flits with error {nbad}, runs that lost a packet or timed out {ntimeout}",
             "wait = latency - L0, L0 = 6(m+1) + p + 1; n = headers that cross router 4 in the run",
             "n\tsamples\tlargest wait (cycles)\tS (n - 1)"]
    for n in sorted(worst):
        lines.append(f"{n}\t{samples[n]}\t{worst[n]}\t" + ("-" if service is None else str(service * (n - 1))))
    lines.append(f"service time per header S = {service} cycles; largest wait {metrics['largest_wait_cycles']} "
                 f"cycles with {NPACKETS - 1} competing headers")

    if args.reference:
        with open(args.reference) as f:
            ref = flatten(json.load(f))
        got = flatten(metrics)
        diffs = [f"{k}: expected {v!r}, got {got.get(k, '<missing>')!r}"
                 for k, v in ref.items() if not k.startswith("_") and got.get(k, "<missing>") != v]
        problems += diffs
        lines.append(f"check against {os.path.basename(args.reference)}: "
                     + ("ok" if not diffs else f"{len(diffs)} differences"))
    lines += ["problem: " + p for p in problems]
    with open(os.path.join(out, "contention_summary.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
