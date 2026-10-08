#!/usr/bin/env python3
"""Anonymized copy of the repository for double-anonymous review.

    anonymize.py apply  <dir> --repo <git dir> [--overlay <dir>]
    anonymize.py verify <dir> --repo <git dir>

`apply` edits <dir>, a `git archive` of the repository (export.sh makes it),
in this order:

| Step | Rule |
|---|---|
| 1 | Delete DELETE (paths and globs) |
| 2 | Copy the overlay directory over the tree (files that replace a file of the repository) |
| 3 | Remove the lines between `anon:drop-begin` and `anon:drop-end` and every line with `anon:drop-line` |
| 4 | Remove the lines of DROP_LINES; apply JSON_EDITS and CODE_EDITS (a required edit that matches nothing stops the export) |
| 5 | Remove the test functions of TEST_FILES that use a removed file or output (TEST_TOKENS) |
| 6 | Replace the identifying strings of IDENTITY in every text file |
| 7 | Replace the abbreviated and full hashes of the commits of <repo> in documentation, data and code files |
| 8 | Restore the export-subst template of experiments/exp23/VERSION (git archive wrote the commit there) |

`verify` searches every file (text and binary) of <dir> for PATTERNS and for
hashes of commits of <repo>, prints each hit, marks the hits of ALLOWED
(headers of third-party files) and exits with 1 when another hit remains.
It also lists the paths of removed thesis-comparison material that still
exist and the remaining occurrences of the word "thesis".

Only the standard library; run with python3 -I.
"""
from __future__ import annotations

import argparse
import ast
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys

# ------------------------------------------------------------ rules

DELETE = [
    "tools/anonymize",                       # this tool and its rules
    "orca-rt-tools/tests/test_artifact_anonymize.py",   # test of this tool
    "experiments/ch6",                       # Ch. 6 tables of the thesis; not in the paper
    "orca-rt-tools/rttools/paper/ch6.py",
    "orca-rt-tools/tests/test_paper_ch6.py",
    "experiments/exp23/logs/A.events.txt",   # runs A to D: thesis code and comparison runs
    "experiments/exp23/logs/B.events.txt",
    "experiments/exp23/logs/C.events.txt",
    "experiments/exp23/logs/D.events.txt",
    "experiments/exp23/reference_D.json",
    "**/.~lock.*#",                          # LibreOffice lock files (user and host names)
    "**/*.o",                                # object files of porca (paths and names in debug data)
    "orca-rt-tools/rttools/porca/old-ccp-migration/apps/kprofiler/target",   # Maven build output
    "**/wlft*",                              # ModelSim waveform temporary file (paths, host)
]

# (glob, regex): lines removed from the files that match the glob
DROP_LINES = [
    ("experiments/exp23/README.md", r"`thesis\.(tex|csv)`"),
    ("orca-rt-tools/rttools/paper/exp23.py", r"^\| thesis\.tex, thesis\.csv \|"),
    ("experiments/ch7/Makefile", r"^#\s+make n16\b"),
]

# (file, regex, replacement, flags, required)
CODE_EDITS = [
    # exp23: no comparison with the values printed in the thesis
    ("orca-rt-tools/rttools/paper/exp23.py",
     r'^    th = cfg\.get\("thesis", \{\}\)\n.*?^    m\["thesis_comparison"\] = thesis_rows\n',
     "", re.M | re.S, True),
    ("orca-rt-tools/rttools/paper/exp23.py",
     r'^    write_table\(os\.path\.join\(out_dir, "thesis"\),\n.*?"tab:exp23-thesis"\)\n',
     "", re.M | re.S, True),
    # ch7: the printed table becomes the reference values of the configuration
    ("orca-rt-tools/rttools/paper/ch7.py", r"thesis", "reference", 0, True),
    ("experiments/ch7/Makefile", r"^n16:\n(?:\t.*\n)+\n?", "", re.M, False),
    ("experiments/ch7/Makefile", r"^(\.PHONY:.*?) n16\b", r"\1", re.M, False),
    # exp23 README: sentence on the unit of the original commit
    ("experiments/exp23/README.md",
     r" Commit \w+ prints the PE time in units of 100 ps; the fixed RTL in ns\.", "", 0, False),
    # TUI hint on the unit of the original logs
    ("orca-rt-tools/rttools/tui/ui/trace_pane.py",
     r'hint="The thesis \(Ch\. 8\) read logs of \w+ as 1 ns; the PE prints \$time in units of 100 ps\."',
     'hint="Without `timescale, the PE prints $time in units of 100 ps."', 0, False),
    # the stored runs A to D are not in the copy
    ("orca-rt-tools/tests/test_paper_exp23.py", r'for r in "ABCDE":', 'for r in "E":', 0, False),
    ("orca-rt-tools/tests/test_paper_exp23.py", r'@pytest\.mark\.parametrize\("run", "ABCDE"\)',
     '@pytest.mark.parametrize("run", "E")', 0, False),
]

# (file, edit): edit(data) changes the parsed JSON in place
JSON_EDITS = [
    ("experiments/exp23/config.json", lambda d: (
        d.pop("thesis", None),
        d.__setitem__("_doc", "Application E on the 2x2 manycore (pkt-sim/software/ucx-os/app/weird_a.c). "
                              "Times in seconds or cycles of the 500 MHz clock."))),
    ("experiments/exp23/reference_head.json", lambda d: d.__setitem__(
        "_doc", "Expected results of make paper: run E (logs/E.events.txt), Questa 2025.3, riscv64-elf-gcc 12.2.0.")),
    ("experiments/ch7/config.json", lambda d: (
        d.__setitem__("reference_rows", d.pop("thesis_rows")) if "thesis_rows" in d else None,
        d.__setitem__("_doc", "Random graphs 10_<|V|>.txt (values in [2000; 20000]) collapsed to N = 4 clusters; "
                              "reference_rows holds the reference values of each graph."))),
    ("experiments/ch7/reference.json", lambda d: d.__setitem__(
        "_doc", "make (|V| = 20 to 100, N = 4): every cell agrees with reference_rows of config.json.")),
    ("experiments/ch7/reference_full.json", lambda d: d.__setitem__(
        "_doc", "make full (|V| = 20 to 900, N = 4): every cell agrees with reference_rows of config.json.")),
]

# test functions of TEST_FILES (orca-rt-tools/tests) that contain one of TEST_TOKENS are removed
TEST_FILES = ["test_paper_exp23.py", "test_paper_ch7.py", "test_tui_model.py", "test_ags.py"]
TEST_TOKENS = ["reference_D.json", "thesis", 'runs["A"]', 'runs["B"]', 'runs["C"]', 'runs["D"]',
               "paper import ch6", "paper.ch6", "logs/D.events",
               'exp23_log("A")', 'exp23_log("B")', 'exp23_log("C")', 'exp23_log("D")']

# (regex, replacement), applied in order to every text file
IDENTITY = [
    (r"ti\.andersondomingues@gmail\.com", "anonymous@example.org"),
    (r"c\.jones@edu\.pucrs\.br", "anonymous@example.org"),
    (r"cassiojonesdhein@gmail\.com", "anonymous@example.org"),
    (r"https?://(?:https?://)?github\.com/andersondomingues/+", "https://github.com/anonymous/"),
    (r"andersondomingues", "anonymous"),
    (r"anderson\.domingues", "anonymous"),
    (r"Anderson\s+(?:R(?:oberto|\.)\s+)?(?:P(?:inheiro|\.)\s+)?Domingues", "Anonymous Author"),
    (r"Domingues", "Anonymous"),
    (r"C[áa]ssio(?:\s+Jones)?(?:\s+Dhein)?(?:\s+da)?(?:\s+J\.\s*D\.)?\s+Silva", "Anonymous Author"),
    (r"/home/csilva\b", "/home/user"),
    (r"\bcsilva\b", "user"),
    (r"\bc\.jones\b", "user"),
    (r"/soft64/source_gaph", "/path/to/site-setup.sh"),
    (r"gaphs\d*\.portoalegre\.pucrsnet\.br", "host.example.org"),
    (r"(?i)\bpaxos(?:\.inf\.pucrs\.br)?\b", "simulation-server"),
    (r"(?:the )?GAPH server", "the simulation server"),
    (r"GAPH/PUCRS", "Anonymous Lab"),
    (r"\bGAPH\b", "Anonymous Lab"),
    (r"\bPUCRS\b", "Anonymous University"),
]

# case-insensitive search of verify
PATTERNS = ["domingues", "anderson", "silva", "pucrs", "gaph", "csilva", "c.jones", "soft64", "paxos",
            "cassio", "cássio", "dhein", "jones", "nsesd", "portoalegre", "porto alegre"]
WORD_PATTERNS = [r"\blsa\b"]

# (glob, line regex): hits that stay (third-party copyright and author headers)
ALLOWED = [
    ("pkt-sim/**", r"Sergio Johann Filho\s*[<\[]sergio\.(?:filho|johann)@(?:acad\.)?pucrs\.br[>\]]"),
    ("pkt-sim/software/hfrisc-software/app/coremark/readme.txt", r"Alan Anderson, ADI"),
    ("orca-rt-tools/rttools/porca/**", r"Sergio F\. Johann \(sergio\.johann@acad\.pucrs\.br\)"),
]

# documentation, data and code files where commit hashes are masked
HASH_EXT = {".md", ".json", ".py", ".sh", ".yml", ".yaml", ".txt", ".tex", ".cfg", ".ini", ".csv", ".svh",
            ".sv", ".vhd", ".c", ".h", ".do"}
HASH_NAMES = {"Makefile", "VERSION", "README"}

REMOVED_OUTPUTS = ["experiments/exp23/logs/[ABCD].events.txt", "experiments/exp23/reference_D.json",
                   "experiments/ch6", "**/thesis.tex", "**/thesis.csv"]


# ------------------------------------------------------------ helpers

def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for f in files:
            p = os.path.join(d, f)
            if os.path.isfile(p) and not os.path.islink(p):
                yield os.path.relpath(p, root)


def match(rel, pattern):
    if "**" in pattern:
        return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(rel, pattern.replace("**/", ""))
    return fnmatch.fnmatch(rel, pattern)


def read_text(path):
    """(text, encoding) or (None, None) for a binary file."""
    with open(path, "rb") as f:
        data = f.read()
    if b"\0" in data:
        return None, None
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def write_text(path, text, enc):
    with open(path, "wb") as f:
        f.write(text.encode(enc))


def commits(repo):
    out = subprocess.run(["git", "-C", repo, "rev-list", "--all"], capture_output=True, text=True, check=True)
    return set(out.stdout.split())


HEX = re.compile(r"\b[0-9a-f]{7,40}\b")


def commit_tokens(text, full):
    """Hex tokens of text that abbreviate a commit of the repository."""
    found = set()
    for t in set(HEX.findall(text)):
        if not (re.search(r"[a-f]", t) and re.search(r"[0-9]", t)):
            continue
        if any(c.startswith(t) for c in full):
            found.add(t)
    return found


# ------------------------------------------------------------ apply

def apply(root, repo, overlay, log):
    for pat in DELETE:
        hits = [rel for rel in list(walk(root)) if match(rel, pat) or rel.startswith(pat.rstrip("/") + "/")]
        target = os.path.join(root, pat)
        if os.path.isdir(target):
            shutil.rmtree(target)
            log(f"delete {pat}/")
        else:
            for rel in hits:
                os.remove(os.path.join(root, rel))
                log(f"delete {rel}")

    if overlay and os.path.isdir(overlay):
        for rel in walk(overlay):
            dst = os.path.join(root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(overlay, rel), dst)
            log(f"overlay {rel}")

    for rel in walk(root):
        p = os.path.join(root, rel)
        text, enc = read_text(p)
        if text is None or "anon:drop" not in text:
            continue
        out, skip, n = [], False, 0
        for line in text.splitlines(keepends=True):
            if "anon:drop-begin" in line:
                skip, n = True, n + 1
                continue
            if "anon:drop-end" in line:
                skip = False
                continue
            if skip or "anon:drop-line" in line:
                n += 0 if skip else 1
                continue
            out.append(line)
        if skip:
            raise SystemExit(f"{rel}: anon:drop-begin without anon:drop-end")
        write_text(p, "".join(out), enc)
        log(f"markers {rel}: {n} blocks or lines")

    for glob, rx in DROP_LINES:
        for rel in walk(root):
            if not match(rel, glob):
                continue
            p = os.path.join(root, rel)
            text, enc = read_text(p)
            lines = text.splitlines(keepends=True)
            kept = [l for l in lines if not re.search(rx, l)]
            if len(kept) != len(lines):
                write_text(p, "".join(kept), enc)
                log(f"drop-lines {rel}: {len(lines) - len(kept)} ({rx})")

    for rel, edit in JSON_EDITS:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            log(f"json {rel}: absent")
            continue
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        edit(d)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
            f.write("\n")
        log(f"json {rel}")

    for rel, rx, rep, flags, required in CODE_EDITS:
        p = os.path.join(root, rel)
        if not os.path.exists(p):
            if required:
                raise SystemExit(f"required edit: {rel} is missing")
            continue
        text, enc = read_text(p)
        new, n = re.subn(rx, rep, text, flags=flags)
        if n == 0 and required:
            raise SystemExit(f"required edit did not match: {rel}: {rx}")
        if n:
            write_text(p, new, enc)
            log(f"edit {rel}: {n} ({rx[:60]})")

    tests = os.path.join(root, "orca-rt-tools", "tests")
    for rel in sorted(walk(tests)) if os.path.isdir(tests) else []:
        if rel not in TEST_FILES:
            continue
        p = os.path.join(tests, rel)
        text, enc = read_text(p)
        tree = ast.parse(text)
        lines = text.splitlines(keepends=True)
        drop = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
                src = "".join(lines[start:node.end_lineno])
                if any(t in src for t in TEST_TOKENS):
                    drop.append((start, node.end_lineno, node.name))
        for start, end, name in reversed(drop):
            del lines[start:end]
            log(f"test removed {rel}::{name}")
        if drop:
            write_text(p, "".join(lines), enc)

    full = commits(repo)
    for rel in walk(root):
        p = os.path.join(root, rel)
        text, enc = read_text(p)
        if text is None:
            continue
        new = text
        for rx, rep in IDENTITY:
            new = re.sub(rx, rep, new)
        name = os.path.basename(rel)
        if os.path.splitext(name)[1] in HASH_EXT or name in HASH_NAMES:
            toks = commit_tokens(new, full)
            for t in sorted(toks, key=len, reverse=True):
                new = re.sub(rf"\b{t}\b", "x" * min(len(t), 7), new)
            if toks:
                log(f"hashes {rel}: {', '.join(sorted(toks))}")
        if new != text:
            write_text(p, new, enc)
            if new.count("Anonymous") + new.count("anonymous") > text.count("Anonymous") + text.count("anonymous"):
                log(f"identity {rel}")

    # git archive wrote the commit into VERSION; the template comes back
    # (a copy without git reports nogit, a new git archive of the copy its own commit)
    v = os.path.join(root, "experiments", "exp23", "VERSION")
    if os.path.exists(v):
        write_text(v, "commit=$Format:%H$\ndescribe=$Format:%(describe:tags=true)$\n", "utf-8")
        log("VERSION template restored")


# ------------------------------------------------------------ verify

def verify(root, repo):
    full = commits(repo)
    bad, allowed = [], []
    pats = [re.compile(re.escape(p), re.I) for p in PATTERNS] + [re.compile(p, re.I) for p in WORD_PATTERNS]
    for rel in sorted(walk(root)):
        for rx in pats:
            if rx.search(rel):
                bad.append(f"{rel}: file name ({rx.pattern})")
        p = os.path.join(root, rel)
        text, _ = read_text(p)
        if text is None:
            with open(p, "rb") as f:
                data = f.read().decode("latin-1")
            for rx in pats:
                if rx.search(data):
                    bad.append(f"{rel}: binary file contains {rx.pattern}")
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            hit = [rx.pattern for rx in pats if rx.search(line)]
            toks = commit_tokens(line, full)
            if toks:
                hit.append("commit " + ",".join(sorted(toks)))
            if not hit:
                continue
            entry = f"{rel}:{i}: [{', '.join(hit)}] {line.strip()[:160]}"
            ok = not toks and any(match(rel, g) and re.search(lx, line) for g, lx in ALLOWED)
            (allowed if ok else bad).append(entry)
    removed = sorted({rel for rel in walk(root) for g in REMOVED_OUTPUTS if match(rel, g)}
                     | {g for g in REMOVED_OUTPUTS if "*" not in g and os.path.exists(os.path.join(root, g))})
    thesis = {}
    for rel in walk(root):
        text, _ = read_text(os.path.join(root, rel))
        if text:
            n = len(re.findall(r"\bthesis\b", text, re.I))
            if n:
                thesis[rel] = n
    print(f"identifying strings: {len(bad)} unexpected, {len(allowed)} allowed (third-party headers)")
    for e in bad:
        print("  UNEXPECTED " + e)
    for e in allowed:
        print("  allowed    " + e)
    print(f"removed thesis-comparison material still present: {len(removed)}")
    for r in removed:
        print("  " + r)
    print(f"word 'thesis' (information): {sum(thesis.values())} occurrences in {len(thesis)} files")
    for rel, n in sorted(thesis.items(), key=lambda x: -x[1]):
        print(f"  {n:4d} {rel}")
    return 1 if bad or removed else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["apply", "verify"])
    ap.add_argument("dir")
    ap.add_argument("--repo", required=True, help="git repository of the source (commit hashes)")
    ap.add_argument("--overlay", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "apply":
        apply(a.dir, a.repo, a.overlay, lambda m: print(m, flush=True))
        return 0
    return verify(a.dir, a.repo)


if __name__ == "__main__":
    sys.exit(main())
