"""Program image of one PE: instruction words, symbols, read-only data and
the loop bounds that the source code records in the section .wcet_bounds.

Two inputs give the same Image:

| Input | Source of each item |
|---|---|
| ELF (image.elf of the ucx-os build) | pyelftools: words of .text, symbols (functions with st_size, or up to the next symbol), read-only bytes of .text and of [_rodata, _erodata) (hf-risc.ld places .rodata in the output section .data), _gp, entries of .wcet_bounds |
| objdump listing (image.lst, `objdump --disassemble`) | the address and word of each instruction line and the `<symbol>:` headers; a function ends at the next header. A listing has no data sections: loads from .rodata stay unknown, jump tables need an annotation, and .wcet_bounds is empty |

The stored runs of the paper keep listings only (experiments/exp23/logs/
G.image.lst, H.image.lst); the images built by experiments/wcet are ELF
files.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

from rttools.wcet.decode import Instr, decode

BOUNDS_SECTION = ".wcet_bounds"


class ImageError(ValueError):
    pass


@dataclass
class Function:
    name: str
    start: int
    end: int          # exclusive

    def contains(self, addr):
        return self.start <= addr < self.end


@dataclass
class Image:
    path: str
    kind: str                                   # "elf" or "listing"
    words: dict = field(default_factory=dict)   # address -> instruction word (text)
    rodata: dict = field(default_factory=dict)  # address -> byte (read-only data and text)
    symbols: dict = field(default_factory=dict)  # name -> address (every symbol)
    functions: list = field(default_factory=list)  # Function, sorted by start
    bounds: list = field(default_factory=list)  # (address, bound) of .wcet_bounds
    aliases: dict = field(default_factory=dict)  # every function name -> name of its Function
    gp: int | None = None
    _decoded: dict = field(default_factory=dict)

    def canonical(self, name):
        """Name of the Function of `name` (aliases such as _yield and
        yield share one function)."""
        return self.aliases.get(name, name)

    def function(self, name):
        name = self.canonical(name)
        for f in self.functions:
            if f.name == name:
                return f
        raise ImageError(f"{self.path}: no function {name!r}")

    def has_function(self, name):
        name = self.canonical(name)
        return any(f.name == name for f in self.functions)

    def function_at(self, addr):
        """Function whose range holds `addr` (None outside every function)."""
        lo, hi = 0, len(self.functions)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.functions[mid].start <= addr:
                lo = mid + 1
            else:
                hi = mid
        if lo and self.functions[lo - 1].contains(addr):
            return self.functions[lo - 1]
        return None

    def function_starting_at(self, addr):
        f = self.function_at(addr)
        return f if f is not None and f.start == addr else None

    def instr(self, addr):
        if addr not in self._decoded:
            if addr not in self.words:
                raise ImageError(f"{self.path}: no instruction at {addr:08x}")
            self._decoded[addr] = decode(self.words[addr], addr)
        return self._decoded[addr]

    def read(self, addr, width, signed=False):
        """Value of `width` bytes at `addr` when every byte is read-only
        data of the image; None otherwise."""
        bs = []
        for a in range(addr, addr + width):
            if a not in self.rodata:
                return None
            bs.append(self.rodata[a])
        v = int.from_bytes(bytes(bs), "little")
        if signed and v >> (8 * width - 1):
            v -= 1 << (8 * width)
        return v & 0xFFFFFFFF

    def address(self, spec, function=None):
        """Address of `spec`: an int, "0x..." (absolute), "+0x.." (offset
        in `function`) or a symbol name."""
        if isinstance(spec, int):
            return spec
        s = str(spec).strip()
        if s.startswith("+"):
            if function is None:
                raise ImageError(f"offset {s} needs a function")
            return self.function(function).start + int(s[1:], 0)
        if re.fullmatch(r"0x[0-9a-fA-F]+", s):
            return int(s, 16)
        if s in self.symbols:
            return self.symbols[s]
        raise ImageError(f"{self.path}: unknown address {spec!r}")


def _finish(img, starts):
    """Functions from the symbol starts (name, start, size or None) inside
    the text range: size from the symbol, else up to the next start."""
    text_end = max(img.words) + 4 if img.words else 0
    starts = sorted({(a, n, s) for n, a, s in starts if a in img.words}, key=lambda t: (t[0], t[1]))
    # one function per start; its name: the first name without a leading
    # underscore (yield, not the alias _yield), else the first name
    names = {}
    sizes = {}
    for a, n, s in starts:
        names.setdefault(a, []).append(n)
        if s:
            sizes[a] = max(sizes.get(a, 0), s)
    seen = {}
    for a, ns in names.items():
        pref = sorted(ns, key=lambda n: (n.startswith("_"), n))[0]
        seen[a] = (pref, sizes.get(a))
        for n in ns:
            img.aliases[n] = pref
    addrs = sorted(seen)
    for i, a in enumerate(addrs):
        n, s = seen[a]
        nxt = addrs[i + 1] if i + 1 < len(addrs) else text_end
        end = a + s if s else nxt
        img.functions.append(Function(n, a, min(end, nxt) if s else end))
    return img


def load_listing(path):
    """Image from an objdump listing (objdump --disassemble [-Mno-aliases])."""
    img = Image(path, "listing")
    head = re.compile(r"^([0-9a-f]{8}) <([^>]+)>:\s*$")
    line_re = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s")
    starts = []
    with open(path) as f:
        for line in f:
            m = head.match(line)
            if m:
                a = int(m[1], 16)
                img.symbols[m[2]] = a
                starts.append((m[2], a, None))
                continue
            m = line_re.match(line)
            if m:
                a = int(m[1], 16)
                w = int(m[2], 16)
                img.words[a] = w
                for k in range(4):
                    img.rodata[a + k] = (w >> (8 * k)) & 0xFF
    if not img.words:
        raise ImageError(f"{path}: no instruction lines")
    return _finish(img, starts)


def load_elf(path):
    """Image from an ELF file (pyelftools)."""
    try:
        from elftools.elf.elffile import ELFFile
        from elftools.elf.sections import SymbolTableSection
    except ImportError as e:  # pragma: no cover
        raise ImageError("reading an ELF file needs pyelftools (requirements.txt)") from e
    img = Image(path, "elf")
    starts = []
    with open(path, "rb") as fh:
        elf = ELFFile(fh)
        if elf["e_machine"] != "EM_RISCV" or elf.elfclass != 32:
            raise ImageError(f"{path}: not a 32-bit RISC-V ELF file")
        text = elf.get_section_by_name(".text")
        if text is None:
            raise ImageError(f"{path}: no .text section")
        tbase, tdata = text["sh_addr"], text.data()
        for i in range(0, len(tdata) - 3, 4):
            w = struct.unpack_from("<I", tdata, i)[0]
            img.words[tbase + i] = w
        for i, b in enumerate(tdata):
            img.rodata[tbase + i] = b
        symtab = elf.get_section_by_name(".symtab")
        if not isinstance(symtab, SymbolTableSection):
            raise ImageError(f"{path}: no symbol table")
        for s in symtab.iter_symbols():
            if not s.name or s.name.startswith(".L") or s.name.startswith("$"):
                continue
            img.symbols.setdefault(s.name, s["st_value"])
            typ = s["st_info"]["type"]
            if typ in ("STT_FUNC", "STT_NOTYPE") and tbase <= s["st_value"] < tbase + len(tdata):
                starts.append((s.name, s["st_value"], s["st_size"] if typ == "STT_FUNC" else None))
        lo, hi = img.symbols.get("_rodata"), img.symbols.get("_erodata")
        if lo is not None and hi is not None and hi > lo:
            for sec in elf.iter_sections():
                a = sec["sh_addr"]
                if sec["sh_type"] != "SHT_PROGBITS" or not a or sec is text:
                    continue
                data = sec.data()
                for i, b in enumerate(data):
                    if lo <= a + i < hi:
                        img.rodata[a + i] = b
        img.gp = img.symbols.get("_gp", img.symbols.get("__global_pointer$"))
        sec = elf.get_section_by_name(BOUNDS_SECTION)
        if sec is not None:
            data = sec.data()
            if len(data) % 8:
                raise ImageError(f"{path}: {BOUNDS_SECTION} size {len(data)} is not a multiple of 8")
            for i in range(0, len(data), 8):
                img.bounds.append(struct.unpack_from("<II", data, i))
    return _finish(img, starts)


def load(path):
    """ELF or listing, by the first bytes of the file."""
    with open(path, "rb") as f:
        magic = f.read(4)
    return load_elf(path) if magic == b"\x7fELF" else load_listing(path)


def instructions(img, func):
    """Decoded instructions of a function (Function or name)."""
    f = img.function(func) if isinstance(func, str) else func
    out = []
    a = f.start
    while a < f.end:
        out.append(img.instr(a))
        a += 4
    return out


__all__ = ["Image", "Function", "ImageError", "load", "load_elf", "load_listing", "instructions", "Instr"]
