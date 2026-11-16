"""Mapping files (.map): one line per node, "NODE:TASK,TASK,...".

NODE is the node index y * width + x of arch/hermes-*.gml. Blank lines
and text after '#' are ignored. `read` returns the entries in the format
of rttools.modules.io.mapparser ({"node": str, "tasks": [str]}), which
rttools.modules.mapping.mapper.getMap reads; `check` tells whether every
task of an application appears exactly once; `write` saves a task -> node
mapping.
"""
from __future__ import annotations


class MappingError(ValueError):
    pass


def parse(text, source="<map>"):
    entries = []
    for n_line, line in enumerate(text.splitlines(), 1):
        line = line.split("#")[0].strip()
        if not line:
            continue
        node, sep, tasks = line.partition(":")
        node = node.strip()
        if not sep or not node.isdigit():
            raise MappingError(f"{source}:{n_line}: NODE:TASK,TASK expected, got {line!r}")
        ts = [t.strip() for t in tasks.split(",") if t.strip()]
        entries.append({"node": node, "tasks": ts})
    return entries


def read(path):
    with open(path) as f:
        return parse(f.read(), path)


def problems(entries, tasks=None, nodes=None, unknown=False):
    """List of messages: a task on more than one line or twice on a line,
    a node on more than one line, a task of `tasks` that no line maps, a
    node not in `nodes` and, with unknown=True, a task of the file not in
    `tasks` (apps/synthetic-flow-d maps tasks that its .csv does not
    have; the command line only warns about them)."""
    out = []
    seen = {}
    lines = {}
    for e in entries:
        if e["node"] in lines:
            out.append(f"node {e['node']} on more than one line")
        lines[e["node"]] = True
        if nodes is not None and e["node"] not in {str(n) for n in nodes}:
            out.append(f"node {e['node']} is not in the architecture")
        for t in e["tasks"]:
            seen.setdefault(t, []).append(e["node"])
    for t, ns in seen.items():
        if len(ns) > 1:
            out.append(f"task {t} mapped {len(ns)} times (nodes {', '.join(ns)})")
    if tasks is not None:
        known = [str(t) for t in tasks]
        for t in known:
            if t not in seen:
                out.append(f"task {t} not mapped")
        for t in seen:
            if unknown and t not in known:
                out.append(f"task {t} is not in the application")
    return out


def unknown_tasks(entries, tasks):
    known = {str(t) for t in tasks}
    return [t for e in entries for t in e["tasks"] if t not in known]


def check(entries, tasks=None, nodes=None, unknown=False):
    """Raises MappingError with every problem of `problems`."""
    p = problems(entries, tasks, nodes, unknown)
    if p:
        raise MappingError("; ".join(p))
    return entries


def from_dict(mapping):
    """Entries (sorted by node, tasks in insertion order) of a
    task -> node dict."""
    per = {}
    for t, n in mapping.items():
        per.setdefault(int(n), []).append(str(t))
    return [{"node": str(n), "tasks": per[n]} for n in sorted(per)]


def to_text(entries):
    return "".join(f"{e['node']}:{','.join(e['tasks'])}\n" for e in entries)


def write(path, mapping):
    """Writes a task -> node dict (or a list of entries) as a .map file."""
    entries = from_dict(mapping) if isinstance(mapping, dict) else mapping
    with open(path, "w") as f:
        f.write(to_text(entries))
    return path
