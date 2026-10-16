"""The 17 ORT/RGG graphs of the table of the random graphs stored in the repository.

    python -m rttools.paper.graphs extract --src <graphs dir> --out <dir>
    python -m rttools.paper.graphs verify <dir> --sums <SHA256SUMS>
    python -m rttools.paper.graphs pack <dir with 10_<|V|>.txt> --out <archive.tar.xz> [--sizes 200,300]

The graphs come from tp-tools/apps/var-nnodes/10_<|V|>.txt of commit
xxxxxxx. The generator of that commit (tp-tools/rgg) draws the values with
numpy.random.normal and the endpoints with random.randint without a seed,
so it cannot regenerate the files; the repository keeps them instead:
the nine graphs with |V| <= 100 as text files and the eight graphs with
|V| = 200 to 900 in one xz-compressed tar archive. SHA256SUMS holds the
hash of each of the 17 files.

`extract` copies the text files of <src>, unpacks every *.tar.xz archive
of <src> into <out> and checks the hashes of SHA256SUMS (when <src> has
one). It uses only the Python standard library (tarfile, lzma, hashlib).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import shutil
import sys
import tarfile

SUMS = "SHA256SUMS"
MTIME = 1704153600  # 2024-01-02 00:00 UTC, date of commit xxxxxxx


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_sums(path):
    out = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                digest, name = line.split(None, 1)
                out[name.lstrip("*")] = digest
    return out


def verify(directory, sums_path):
    """Returns the list of problems (missing file or different hash)."""
    problems = []
    for name, digest in sorted(read_sums(sums_path).items()):
        p = os.path.join(directory, name)
        if not os.path.exists(p):
            problems.append(f"{name}: missing")
        elif sha256(p) != digest:
            problems.append(f"{name}: sha256 differs")
    return problems


def extract(src, out):
    """Copies <src>/10_*.txt and unpacks <src>/*.tar.xz into <out>.
    Returns the sorted list of file names in <out>."""
    os.makedirs(out, exist_ok=True)
    for name in sorted(os.listdir(src)):
        p = os.path.join(src, name)
        if name.endswith(".txt") and name.startswith("10_"):
            shutil.copyfile(p, os.path.join(out, name))
        elif name.endswith(".tar.xz"):
            with tarfile.open(p, "r:xz") as tar:
                for member in tar.getmembers():
                    base = os.path.basename(member.name)
                    if not member.isfile() or base != member.name or not base.startswith("10_"):
                        raise ValueError(f"{name}: unexpected member {member.name!r}")
                    with tar.extractfile(member) as fin, open(os.path.join(out, base), "wb") as fout:
                        shutil.copyfileobj(fin, fout)
    return sorted(n for n in os.listdir(out) if n.startswith("10_"))


def pack(directory, archive, sizes):
    """Writes the graphs 10_<size>.txt of <directory> into an xz tar
    archive with fixed owner and time (the same input gives the same
    archive)."""
    with tarfile.open(archive, "w:xz", preset=9) as tar:
        for size in sizes:
            name = f"10_{size}.txt"
            with open(os.path.join(directory, name), "rb") as f:
                data = f.read()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = MTIME
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))


def main(argv=None):
    p = argparse.ArgumentParser(prog="rttools.paper.graphs", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--src", required=True)
    e.add_argument("--out", required=True)
    v = sub.add_parser("verify")
    v.add_argument("dir")
    v.add_argument("--sums", required=True)
    k = sub.add_parser("pack")
    k.add_argument("dir")
    k.add_argument("--out", required=True)
    k.add_argument("--sizes", required=True)
    a = p.parse_args(argv)
    if a.cmd == "pack":
        pack(a.dir, a.out, [int(x) for x in a.sizes.split(",")])
        print(f"wrote {a.out} ({os.path.getsize(a.out)} bytes)")
        return 0
    if a.cmd == "extract":
        names = extract(a.src, a.out)
        print(f"{len(names)} graphs in {a.out}")
        sums = os.path.join(a.src, SUMS)
        if not os.path.exists(sums):
            return 0
        directory = a.out
    else:
        sums, directory = a.sums, a.dir
    problems = verify(directory, sums)
    for x in problems:
        print(x)
    print("sha256 ok" if not problems else f"{len(problems)} problems")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
