"""Flow facts that the analysis cannot derive from the code: loop bounds,
targets of indirect jumps and calls, calls on error paths.

File format (JSON; several files merge in order, a later entry of the same
function and selector wins):

    {
      "params": {"tcb": 5, "heap_blocks": 32},
      "exclude_calls": ["ucx_printf", "tprintf"],
      "functions": {
        "ucx_sleep": {"loops": [{"select": "all", "bound": "a0 + 1"}]},
        "ucx_malloc": {"loops": [{"select": "all", "bound": "2 * heap_blocks", "scope": "function"}]},
        "_isr": {"indirect_jumps": [{"at": "all", "return": true}]},
        "irq0_handler": {"indirect_jumps": [{"at": "all", "indices": [0, 4]}],
                         "indirect_calls": [{"at": "all", "targets": ["timer1ctc_handler"], "max_count": 1}]}
      }
    }

| Key | Meaning |
|---|---|
| params | names that bound expressions may use (the analysis query may override them) |
| exclude_calls | functions whose call sites the worst-case path does not take (error paths that print and halt); the analysis fixes the count of each such call block at 0 |
| loops | `select`: "all" (every loop of the function), "rest" (the loops without another bound: no other selector, no WCET_LOOP_BOUND, no counted loop), {"header": "+0x34" or "0x40000234" or a symbol}, {"contains_call": "f"} (the innermost loops with a call to f), {"index": k} (k-th loop by header address); `bound`: integer or expression (rttools.wcet.loopbound.evaluate, with the params); `scope`: "loop" (default: header executions per entry into the loop) or "function" (per call of the function) |
| indirect_jumps | `at`: "all" or the address of the jalr; `targets` (addresses in the function), `return: true` (the jump leaves the function) or `indices` (entries of the jump table of an ELF image); `max`: {target or index: n}, the jumps to that target per call of the function |
| indirect_calls | `at`: "all" or the address of the jalr; `targets`: function names; `max_count`: calls per call of the function |

The C macro WCET_LOOP_BOUND(n) of pkt-sim/software/ucx-os/include/lib/
wcet.h records (address, n) in the section .wcet_bounds of the object
file; the analysis applies n to the innermost loop that holds the address
(rttools.wcet.image, bounds).
"""
from __future__ import annotations

import json


class AnnotationError(ValueError):
    pass


class Annotations:
    def __init__(self, data=None):
        self.params = {}
        self.exclude = set()
        self.funcs = {}
        if data:
            self.merge(data)

    @classmethod
    def load(cls, paths):
        a = cls()
        for p in paths or ():
            with open(p) as f:
                a.merge(json.load(f), p)
        return a

    def merge(self, data, where="annotations"):
        for k in data:
            if k not in ("params", "exclude_calls", "functions") and not k.startswith("_"):
                raise AnnotationError(f"{where}: unknown key {k!r}")
        self.params.update(data.get("params", {}))
        self.exclude.update(data.get("exclude_calls", []))
        for fn, spec in data.get("functions", {}).items():
            if fn.startswith("_doc"):
                continue
            d = self.funcs.setdefault(fn, {"loops": [], "indirect_jumps": [], "indirect_calls": []})
            for k in spec:
                if k not in d and not k.startswith("_"):
                    raise AnnotationError(f"{where}: function {fn}: unknown key {k!r}")
            for k in ("loops", "indirect_jumps", "indirect_calls"):
                d[k].extend(spec.get(k, []))
        return self

    def canonical(self, img):
        """Copy with the function names of `img` (aliases merge)."""
        a = Annotations()
        a.params = dict(self.params)
        a.exclude = {img.canonical(n) for n in self.exclude}
        for fn, d in self.funcs.items():
            t = a.funcs.setdefault(img.canonical(fn), {"loops": [], "indirect_jumps": [], "indirect_calls": []})
            for k in t:
                t[k].extend(d[k])
        return a

    def loops(self, fn):
        return self.funcs.get(fn, {}).get("loops", [])

    def indirect_jumps(self, fn):
        return self.funcs.get(fn, {}).get("indirect_jumps", [])

    def indirect_calls(self, fn):
        return self.funcs.get(fn, {}).get("indirect_calls", [])
