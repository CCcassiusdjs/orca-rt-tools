"""Model of a generated UCX-OS application: tasks, flows and PEs from the
CSV of the application and the .map file of the analysis flow.

`build` returns a dict (the manifest <name>.json) with every value that
the C code uses; rttools.ucxgen.emit writes the code from it.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re

from rttools.modules.instances import release
from rttools.modules.io import appparser
from rttools.modules.mapping import mapfile

# ucx_sleep (kernel/ucx.c, compiled with -O0): cycles per count. Run F
# (experiments/exp23/logs/F.events.txt, 500 MHz): from the dispatch to the
# send of B, D, F and C (counts 4560, 1200, 6780, 7890 of weird_a.c),
# a linear fit gives 10.09 cycles per count and 160 cycles of receive path.
CYCLES_PER_COUNT = 10
TAG_MOD = 1024
MAX_TAG = 0xFFFF
# payload_size of noc_packet_t is uint16_t (include/lib/noc.h) and the
# driver rounds the payload up to a multiple of 4 (lib/noc.c)
MAX_PAYLOAD = 0xFFFF - 3
# MAX_TASKS of include/lib/noc.h counts the IDLE task
MAX_TASKS_PER_PE = 15
MAX_NAME = 4               # char name[5] of struct tcb_s (include/kernel/kernel.h)
DEFAULT_DELAY_NS = 3_000_000


class GenError(ValueError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def read_csv(path):
    """Tasks, flows and #parameters of an application CSV (the readers of
    rttools/modules/io/appparser.py). Tasks: [{"id", "label", "wcet",
    "period"}]; flows: [{"id", "period", "datasize", "deadline", "source",
    "target"}], in file order."""
    tasks, flows = [], []
    mode = 0
    row_parser = appparser.parseTaskRowWcet
    legacy = False
    with open(path) as f:
        for row in csv.reader(f):
            if not row or not any(c.strip() for c in row):
                continue
            head = row[0].strip()
            if mode == 0:
                if head == "#tasks":
                    mode = 1
            elif mode == 1:
                row_parser = appparser.selectTaskRowParser(row)
                legacy = row_parser is appparser.parseTaskRowLegacy
                mode = 2
            elif mode == 2:
                if head == "#flows":
                    mode = 3
                else:
                    t = row_parser(row)
                    t["period"] = row[1].strip() if legacy else "0"
                    tasks.append(t)
            elif mode == 3:
                mode = 4
            elif mode == 4:
                if head == "#parameters":
                    break
                flows.append(appparser.parseFlowRow(row))
    if not tasks:
        raise GenError(f"{path}: no #tasks section")
    return tasks, flows, appparser.readParameters(path)


def number(text, what):
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        raise GenError(f"{what}: number expected, got {text!r}") from None


def release_period_ns(tasks, flows):
    """Release period T of the application in ns: the single nonzero period
    of the task and flow rows (the phase model has one period)."""
    periods = {number(x["period"], "period") for x in tasks + flows} - {0.0}
    if len(periods) != 1:
        raise GenError("the application needs one release period, got "
                       + (", ".join(f"{p:g}" for p in sorted(periods)) or "none"))
    return round(periods.pop() * 1e9)


def c_ident(label, used):
    s = re.sub(r"\W", "_", label)
    if not s or s[0].isdigit():
        s = "t_" + s
    base, k = s, 2
    while s in used:
        s = f"{base}_{k}"
        k += 1
    used.add(s)
    return s


def parse_mesh(text):
    m = re.fullmatch(r"(\d+)x(\d+)", str(text))
    if not m or int(m[1]) < 1 or int(m[2]) < 1:
        raise GenError(f"mesh WxH expected, got {text!r}")
    return int(m[1]), int(m[2])


def build(csv_path, map_path, name, mesh="4x4", cycles_per_count=CYCLES_PER_COUNT, reserve=None,
          payload_divisor=1, tag_mod=TAG_MOD, delay_ns=DEFAULT_DELAY_NS):
    if not re.fullmatch(r"[A-Za-z_]\w*", name):
        raise GenError(f"name must be a C identifier, got {name!r}")
    width, height = parse_mesh(mesh)
    if cycles_per_count <= 0:
        raise GenError("cycles_per_count must be positive")
    if payload_divisor < 1:
        raise GenError("payload_divisor must be >= 1")
    if tag_mod < 1:
        raise GenError("tag_mod must be >= 1")

    tasks, flows, params = read_csv(csv_path)
    labels = [t["label"] for t in tasks]
    if len(set(labels)) != len(labels):
        raise GenError("repeated task label in " + csv_path)
    known = set(labels)
    for f in flows:
        for end in ("source", "target"):
            if f[end] not in known:
                raise GenError(f"flow {f['id']}: unknown task {f[end]!r}")
    if reserve is None:
        reserve = int(params.get("scheduler_cycles", 0))
    period_ns = release_period_ns(tasks, flows)

    entries = mapfile.read(map_path)
    mapfile.check(entries, labels, nodes=range(width * height))
    node_of = {t: int(e["node"]) for e in entries for t in e["tasks"] if t in known}

    # dispatch order of each PE, as the analysis computes it
    edges = [(f["source"], f["target"]) for f in flows]
    order = {}
    for e in entries:
        ts = [t for t in e["tasks"] if t in known]
        if not ts:
            continue
        seq = release.matching_sequence(e["node"], ts, params.get("sequences"))
        if seq is None:
            seq = release.stable_topological(ts, [(u, v) for u, v in edges if u in ts and v in ts])
        order[int(e["node"])] = seq
        if len(seq) > MAX_TASKS_PER_PE:
            raise GenError(f"PE {e['node']}: {len(seq)} tasks (at most {MAX_TASKS_PER_PE}, MAX_TASKS of noc.h)")

    def label(node):
        return f"{node % width}-{node // width}"

    out_flows = []
    if len(flows) * tag_mod + tag_mod - 1 > MAX_TAG:
        raise GenError(f"{len(flows)} flows with tag_mod {tag_mod} exceed the 16-bit tag")
    for i, f in enumerate(flows, 1):
        raw = int(number(f["datasize"], f"flow {f['id']} data"))
        b = raw // payload_divisor
        if b > MAX_PAYLOAD:
            raise GenError(f"flow {f['id']} ({f['source']}->{f['target']}): payload {b} bytes "
                           f"> {MAX_PAYLOAD} (uint16_t payload_size); raise the payload divisor")
        s, d = node_of[f["source"]], node_of[f["target"]]
        out_flows.append({"id": i, "csv_id": f["id"], "source": f["source"], "target": f["target"],
                          "src_pe": s, "dst_pe": d, "src_label": label(s), "dst_label": label(d),
                          "local": s == d, "csv_bytes": raw, "bytes": b,
                          "tag_base": i * tag_mod})

    used = set()
    out_tasks = []
    for port, t in enumerate(tasks, 1):       # port 0 is not usable (weird_a.c)
        v = t["label"]
        wcet = int(number(t["wcet"], f"task {v} capacity"))
        workload = max(0, round((wcet - reserve) / cycles_per_count))
        node = node_of[v]
        ins = [f["id"] for f in out_flows if f["target"] == v]
        outs = [f["id"] for f in out_flows if f["source"] == v]
        out_tasks.append({"name": v, "ident": c_ident(v, used), "port": port, "pe": node,
                          "pe_label": label(node), "order": order[node].index(v),
                          "kernel_id": order[node].index(v) + 1, "wcet": wcet, "workload": workload,
                          "inputs": ins, "outputs": outs, "source": not ins})
    sources = sorted({t["pe"] for t in out_tasks if t["source"]})
    if not sources:
        raise GenError("no source task (every task has an input edge)")
    names = {}
    for t in out_tasks:
        names.setdefault((t["pe"], t["name"][:MAX_NAME]), []).append(t["name"])
    clash = [ns for ns in names.values() if len(ns) > 1]

    return {
        "name": name,
        "generator": "rttools.ucxgen",
        "inputs": {"csv": {"file": os.path.basename(csv_path), "sha256": sha256(csv_path)},
                   "map": {"file": os.path.basename(map_path), "sha256": sha256(map_path)}},
        "mesh": [width, height],
        "cycles_per_count": cycles_per_count,
        "reserve_cycles": reserve,
        "payload_divisor": payload_divisor,
        "tag_mod": tag_mod,
        "release": {"period_ns": period_ns, "delay_ns": delay_ns, "pes": sources,
                    "pe_labels": [label(n) for n in sources],
                    "mask": sum(1 << n for n in sources)},
        "pe_tasks": {label(n): ["IDLE"] + order[n] for n in sorted(order)},
        "tasks": out_tasks,
        "flows": out_flows,
        "warnings": [f"tasks {', '.join(ns)} share the kernel name {ns[0][:MAX_NAME]!r} on one PE"
                     for ns in clash],
    }
