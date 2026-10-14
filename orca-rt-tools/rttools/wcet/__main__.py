"""Command line of rttools.wcet.

    python -m rttools.wcet analyze --spec SPEC.json [--image IMAGE] [--param k=v ...]
           [--out costs.json] [--csv costs.csv]
    python -m rttools.wcet function IMAGE FUNCTION [--arg a0=N ...] [--annotations FILE ...]
           [--param k=v ...]

`analyze` writes t(v) of every task of an application (rttools.wcet.ucx)
and prints one line per task. The spec (JSON; paths relative to the spec
file) names:

| Key | Content |
|---|---|
| image | ELF file or objdump listing of the PE program (one image for every PE: the UCX-OS build links the tasks of all PEs) |
| annotations | list of annotation files (rttools.wcet.annotations) |
| params | values of the annotation params (tcb, heap_blocks, ...) |
| app | application CSV (tasks and edges), or |
| manifest | manifest of rttools.ucxgen (<name>.json: tasks, flows, C identifiers) |
| functions | {task: function}; default "task_" + lower-case label (app) or "task_" + ident (manifest) |
| iteration_calls | {function: calls per iteration} (default {"set_iter_mark": 2}) |

`function` prints the WCET of one call of a function with the given
argument values.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from rttools.wcet import annotations as annmod
from rttools.wcet import image as imgmod
from rttools.wcet import ucx
from rttools.wcet.analysis import Analyzer, WcetError
from rttools.wcet.decode import REG


def _params(items):
    out = {}
    for it in items or ():
        k, _, v = it.partition("=")
        if not k or not v:
            raise SystemExit(f"--param needs name=value, got {it!r}")
        out[k] = int(v, 0)
    return out


def load_spec(path):
    with open(path) as f:
        spec = json.load(f)
    base = os.path.dirname(os.path.abspath(path))

    def rel(p):
        return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))
    out = dict(spec)
    for k in ("image", "app", "manifest"):
        if k in out:
            out[k] = rel(out[k])
    out["annotations"] = [rel(p) for p in spec.get("annotations", [])]
    return out


def tasks_of(spec):
    """(labels, edges, functions) of the spec."""
    if "manifest" in spec:
        m = json.load(open(spec["manifest"]))
        labels = [t["name"] for t in m["tasks"]]
        edges = [(f["source"], f["target"]) for f in m["flows"]]
        funcs = {t["name"]: "task_" + t["ident"] for t in m["tasks"]}
    elif "app" in spec:
        labels, edges = ucx.read_graph(spec["app"])
        funcs = {t: "task_" + t.lower() for t in labels}
    else:
        raise SystemExit("the spec needs `app` or `manifest`")
    funcs.update(spec.get("functions", {}))
    return labels, edges, funcs


def run_spec(spec, image=None, params=None):
    """Result of ucx.analyze for a spec (dict from load_spec) plus the
    identification of the inputs."""
    path = image or spec["image"]
    img = imgmod.load(path)
    ann = annmod.Annotations.load(spec["annotations"])
    p = dict(spec.get("params", {}))
    p.update(params or {})
    labels, edges, funcs = tasks_of(spec)
    res = ucx.analyze(img, ann, labels, edges, funcs, params=p,
                      iteration_calls=spec.get("iteration_calls"))
    res["image"] = {"file": os.path.basename(path), "kind": img.kind, "sha256": ucx.sha256(path)}
    res["scheduler_cycles"] = res["kernel"]["dispatch"]
    res["annotations"] = [os.path.basename(a) for a in spec["annotations"]]
    res["generator"] = "rttools.wcet"
    res["_doc"] = ("t(v) of each task from the static WCET of its code and of the kernel "
                   "(rttools/wcet/ucx.py), cycles of the HF-RISC core; terms: body, send, receive "
                   "(job), dispatch, send_isr, receive_isr, tick, release")
    return res


def cmd_analyze(a):
    spec = load_spec(a.spec)
    res = run_spec(spec, a.image, _params(a.param))
    k = res["kernel"]
    print(f"kernel: dispatch {k['dispatch']}, tick {k['tick']}, send_isr {k['send_isr']}, "
          f"receive_isr {k['receive_isr']}" + (f", release {k['release']}" if "release" in k else ""))
    for t, r in res["tasks"].items():
        terms = " ".join(f"{n} {v}" for n, v in r["terms"].items() if v)
        print(f"{t} t {r['t']} ({terms})")
    if a.out:
        with open(a.out, "w") as f:
            json.dump(res, f, indent=1, sort_keys=False)
            f.write("\n")
    if a.csv:
        ucx.write_csv(a.csv, res)
    return 0


def cmd_function(a):
    img = imgmod.load(a.image)
    ann = annmod.Annotations.load(a.annotations)
    an = Analyzer(img, ann, params=_params(a.param))
    args = {}
    for it in a.arg or ():
        k, _, v = it.partition("=")
        if k not in REG or not v:
            raise SystemExit(f"--arg needs a0=value, got {it!r}")
        args[REG[k]] = int(v, 0) & 0xFFFFFFFF
    r = an.function(a.function, args)
    print(f"{a.function}: {r.cycles} cycles")
    for f, h, b, s in r.loops:
        print(f"  loop {h:08x} of {f}: bound {b} ({s})")
    for c in sorted(r.calls, key=lambda c: c.addr):
        if c.count:
            print(f"  call {c.addr:08x} {c.callee}: {c.cycles} cycles x {c.count}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m rttools.wcet", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze")
    p.add_argument("--spec", required=True)
    p.add_argument("--image")
    p.add_argument("--param", action="append")
    p.add_argument("--out")
    p.add_argument("--csv")
    p = sub.add_parser("function")
    p.add_argument("image")
    p.add_argument("function")
    p.add_argument("--arg", action="append")
    p.add_argument("--annotations", action="append", default=[])
    p.add_argument("--param", action="append")
    a = ap.parse_args(argv)
    try:
        return {"analyze": cmd_analyze, "function": cmd_function}[a.cmd](a)
    except (WcetError, imgmod.ImageError, annmod.AnnotationError) as e:
        print("error: " + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
