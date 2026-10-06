"""Network case (application, mapping, NoC) for the TUI: flows, mesh,
link schedule as a trace, validation of the AGS schedule, and a worker
process for the frequency search."""
from __future__ import annotations

import contextlib
import io
import re
import threading
import time
import traceback

from rttools.modules.io import appparser, mapparser, nocparser
from rttools.modules.backend.ags import heuristics, search3
from rttools.modules.frequency import search
from rttools.modules.instances import instantiator
from rttools.modules.unwrapper import flowUnwrapper
from rttools.modules.routing import router
from rttools.tui.model.timeunit import cycle_unit
from rttools.tui.model.trace import Mark, Slice, Trace

HEURISTICS = {
    "mbcf": heuristics.mbcf,
    "lstf": heuristics.lstf,
    "mcpf": heuristics.mcpf,
}

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(text):
    return ANSI.sub("", text)


@contextlib.contextmanager
def quiet():
    """Captures what the rttools modules print."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def load_case(app_file, map_file, noc_file):
    # the parsers call exit() on a missing file; check first
    import os
    for f in (app_file, map_file, noc_file):
        if not os.path.isfile(f):
            raise FileNotFoundError(f)
    with quiet():
        app, appname = appparser.loadFromFile(app_file)
        noc = nocparser.loadFromFile(noc_file)
        mapping = mapparser.loadFromFile(map_file)
    return {"app": app, "appname": appname, "noc": noc, "mapping": mapping,
            "files": (app_file, map_file, noc_file)}


def mesh(case):
    """Node coordinates and mapped tasks."""
    nodes = {}
    for n, d in case["noc"].nodes(data=True):
        nodes[n] = (int(d["X"]), int(d["Y"]))
    tasks = {n: [] for n in nodes}
    for m in case["mapping"]:
        if m["node"] in tasks:
            tasks[m["node"]] += [t for t in m["tasks"] if t]
        else:
            tasks[m["node"]] = [t for t in m["tasks"] if t]
    width = max((x for x, _ in nodes.values()), default=0) + 1
    height = max((y for _, y in nodes.values()), default=0) + 1
    return {"nodes": nodes, "tasks": tasks, "width": width, "height": height}


def task_node(case, task):
    for m in case["mapping"]:
        if task in m["tasks"]:
            return m["node"]
    return None


def flows_at(case, frequency):
    """Flows of the application at `frequency` (period and deadline in
    cycles), with nodes, hops, flits and network time of one packet.
    Returns (rows, hyperperiod, packets)."""
    with quiet():
        inst = instantiator.createInstance(case["app"], case["noc"], frequency)
        packets, hp, nlinks = flowUnwrapper.unwrap(inst, case["noc"], case["mapping"])
    rows = []
    for s, t, d in inst["flows"]:
        src, dst = task_node(case, s), task_node(case, t)
        hops = None
        net = None
        if src is not None and dst is not None:
            hops = router.manhattan(src, dst, case["noc"])
            flits = router.getNumFlits(int(d["datasize"]))
            net = flits + (hops + 1) * router.getRoutingTime() + 1
        else:
            flits = router.getNumFlits(int(d["datasize"]))
        n_packets = sum(1 for p in (packets or []) if p["flow"] == d["label"])
        rows.append({
            "flow": d["label"], "source": s, "target": t, "src_node": src, "dst_node": dst,
            "period": d["period"], "deadline": d["deadline"], "datasize": int(d["datasize"]),
            "flits": flits, "hops": hops, "net_time": net, "packets": n_packets,
            "local": src == dst,
        })
    rows.sort(key=lambda r: (len(r["flow"]), r["flow"]))
    return rows, hp, packets


def schedule_trace(result):
    """Link schedule as a trace: one lane per used link, one slice per
    packet on the link, release and deadline marks on the first link of
    each packet."""
    p = result["problem"]
    sched = result["schedule"]
    links = [d["label"] for (_, _, d) in p["links"]]
    slices = []
    marks = []
    for l, lab in enumerate(links):
        for k, pkt in enumerate(p["packets"]):
            st = sched[l][k] if sched is not None else None
            if st is None:
                continue
            occ = p["occupancy"][l][k]
            slices.append(Slice(lab, st, st + occ, pkt["flow"], "packet", pkt["name"]))
    for k, pkt in enumerate(p["packets"]):
        first = next((l for l in range(len(links)) if p["occupancy"][l][k] is not None), None)
        if first is None:
            continue
        marks.append(Mark(links[first], pkt["min_start"], "release", pkt["name"]))
        marks.append(Mark(links[first], pkt["abs_deadline"], "deadline", pkt["name"]))
    unit = cycle_unit(result["frequency"])
    return Trace(f"links @ {result['frequency']:g} Hz", unit, links, slices, marks,
                 {"format": "network", "hyperperiod": p["hyperperiod"]})


def link_usage(result):
    p = result["problem"]
    hp = p["hyperperiod"]
    rows = []
    for l, (s, t, d) in enumerate(p["links"]):
        occ = [o for o in p["occupancy"][l] if o is not None]
        busy = sum(occ)
        rows.append({"link": d["label"], "packets": len(occ), "busy": busy,
                     "utilization": busy / hp if hp else 0.0})
    rows.sort(key=lambda r: -r["utilization"])
    return rows


def packet_rows(result):
    p = result["problem"]
    sched = result["schedule"]
    rows = []
    for k, pkt in enumerate(p["packets"]):
        links = [l for l in range(len(p["links"])) if p["occupancy"][l][k] is not None]
        start = None
        if sched is not None and links:
            start = sched[links[0]][k]
        occ = p["occupancy"][links[0]][k] if links else None
        end = start + occ if start is not None else None
        rows.append({
            "packet": pkt["name"], "flow": pkt["flow"], "source": pkt["source"],
            "target": pkt["target"], "release": pkt["min_start"], "deadline": pkt["abs_deadline"],
            "start": start, "end": end, "occupancy": occ,
            "slack": pkt["abs_deadline"] - end if end is not None else None,
            "path": " ".join(p["links"][l][2]["label"] for l in links),
            "skipped": k in result["skipped"],
        })
    return rows


def validate(result):
    """Independent check of the AGS schedule. Returns a list of issue
    strings: overlap of two packets on one link, start before release,
    end after deadline, missing start, skipped packet."""
    p = result["problem"]
    sched = result["schedule"]
    issues = []
    if sched is None:
        return ["no schedule"]
    for k in result["skipped"]:
        issues.append(f"packet {p['packets'][k]['name']} skipped by the search")
    for l, (_, _, d) in enumerate(p["links"]):
        iv = []
        for k, pkt in enumerate(p["packets"]):
            occ = p["occupancy"][l][k]
            if occ is None:
                continue
            st = sched[l][k]
            if st is None:
                issues.append(f"{pkt['name']} on {d['label']}: no start")
                continue
            if st < pkt["min_start"]:
                issues.append(f"{pkt['name']} on {d['label']}: start {st} before release {pkt['min_start']}")
            if st + occ > pkt["abs_deadline"]:
                issues.append(f"{pkt['name']} on {d['label']}: end {st + occ} after deadline {pkt['abs_deadline']}")
            iv.append((st, st + occ, pkt["name"]))
        iv.sort()
        active = []
        for b0, b1, bn in iv:
            active = [a for a in active if a[1] > b0]
            for a0, a1, an in active:
                issues.append(f"{an} and {bn} overlap on {d['label']} ([{a0}, {a1}) and [{b0}, {b1}))")
            active.append((b0, b1, bn))
    return issues


# ---------------------------------------------------------------- worker
#
# The search runs in a child process (`python -m rttools.tui.worker`) so
# the TUI stays responsive and a search can be cancelled. The child writes
# one JSON object per line to its stdout: {"kind": ..., "data": ...}.
# The result travels as a base64 pickle (local, trusted process).

class _LineWriter(io.TextIOBase):
    """stdout replacement in the child: each printed line becomes a
    ("log", line) message."""

    def __init__(self, emit):
        self.emit = emit
        self.buf = ""

    def write(self, s):
        self.buf += s
        while True:
            cut = [i for i in (self.buf.find("\n"), self.buf.find("\r")) if i >= 0]
            if not cut:
                break
            i = min(cut)
            line = strip_ansi(self.buf[:i]).strip()
            self.buf = self.buf[i + 1:]
            if line:
                self.emit("log", line)
        return len(s)

    def flush(self):
        pass


def _summary(attempt):
    out = {k: attempt[k] for k in ("frequency", "hyperperiod", "problem", "schedule", "skipped")}
    if "attempts" in attempt:
        out["attempts"] = attempt["attempts"]
    return out


def run_worker(params, emit):
    """Runs the search; emit(kind, data) receives ("log", text),
    ("progress", dict), ("attempt", dict), ("result", dict or None) and
    ("error", text). params: app, map, noc, frequency, pruning_factor,
    fail_threshold, heuristic (name), scaling_tolerance, optimize."""
    import sys
    old = sys.stdout
    sys.stdout = _LineWriter(emit)
    stop = threading.Event()

    def progress():
        while not stop.wait(0.5):
            emit("progress", {"entered": search3.hsearch.entered,
                              "ignored": search3.hsearch.ignored,
                              "skipped": len(search3.hsearch.skipped)})

    th = threading.Thread(target=progress, daemon=True)
    th.start()
    try:
        case = load_case(params["app"], params["map"], params["noc"])
        cfg = {
            "frequency": params["frequency"],
            "pruning_factor": params["pruning_factor"],
            "fail_threshold": params["fail_threshold"],
            "heuristic": HEURISTICS[params["heuristic"]],
            "scaling_tolerance": params["scaling_tolerance"],
        }

        def on_attempt(a, ok):
            emit("attempt", {"frequency": a["frequency"], "ok": ok,
                             "skipped": len(a["skipped"]), "hyperperiod": a["hyperperiod"],
                             "packets": len(a["problem"]["packets"]), "time": time.time()})

        if params["optimize"]:
            res = search.search_minimum_frequency(case["app"], case["noc"], case["mapping"],
                                                  case["appname"], cfg, on_attempt)
        else:
            res = search.schedule_at(case["app"], case["noc"], case["mapping"],
                                     case["appname"], cfg["frequency"], cfg)
            if res is not None:
                on_attempt(res, search.feasible(res))
        stop.set()
        emit("result", None if res is None else _summary(res))
    except BaseException:
        stop.set()
        emit("error", traceback.format_exc())
    finally:
        sys.stdout = old


def encode_result(res):
    import base64
    import pickle
    return base64.b64encode(pickle.dumps(res)).decode()


def decode_result(text):
    import base64
    import pickle
    return pickle.loads(base64.b64decode(text))


def start_worker(params):
    """Starts `python -m rttools.tui.worker` with the parameters as JSON.
    Returns the Popen object; its stdout carries the messages."""
    import json
    import os
    import subprocess
    import sys
    pkg_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
    env = dict(os.environ)
    env["PYTHONPATH"] = pkg_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, "-m", "rttools.tui.worker", json.dumps(params)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, env=env, close_fds=True)


def read_messages(stream):
    """Yields (kind, data) from the stdout of the worker; lines that are
    not JSON become ("log", line)."""
    import json
    for line in stream:
        line = line.rstrip("\n")
        if not line:
            continue
        try:
            msg = json.loads(line)
            kind, data = msg["kind"], msg["data"]
        except (ValueError, KeyError, TypeError):
            yield "log", line
            continue
        if kind == "result" and data is not None:
            data = decode_result(data)
        yield kind, data


def repo_root():
    """Root of the repository (apps/ and arch/), two levels above the
    package directory."""
    import os
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", "..", ".."))


def examples(root=None):
    """Cases of apps/: (name, app csv, map, gml). The NoC file comes from
    the `<a>x<b>` in the map file name (hermes-<a>x<b>.gml or
    hermes-<b>x<a>.gml)."""
    import glob
    import os
    root = root or repo_root()
    out = []
    for m in sorted(glob.glob(os.path.join(root, "apps", "*", "*.map"))):
        d = os.path.dirname(m)
        csvs = sorted(glob.glob(os.path.join(d, "*.csv")))
        g = re.search(r"(\d+)x(\d+)", os.path.basename(m))
        if len(csvs) != 1 or g is None:
            continue
        a, b = g.groups()
        noc = None
        for cand in (f"hermes-{a}x{b}.gml", f"hermes-{b}x{a}.gml"):
            p = os.path.join(root, "arch", cand)
            if os.path.isfile(p):
                noc = p
                break
        if noc:
            out.append((os.path.basename(d), csvs[0], m, noc))
    return out
