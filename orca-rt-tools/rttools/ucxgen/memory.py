"""Heap demand of each PE of a generated application against the heap of
the built image.

Every allocation of UCX-OS goes through ucx_malloc (lib/malloc.c,
first fit), which adds a block header (struct mem_block_s) and rounds the
size up to 4 bytes. Allocations of one PE (sizes of rv32e, gcc 13.2
-march=rv32e -mabi=ilp32e: struct tcb_s 112, struct rt_s 12, struct
queue_s 24, struct mem_block_s 8, noc_packet_t header 12 bytes):

| Owner | Allocation (kernel/ucx.c, lib/noc.c, lib/queue.c) |
|---|---|
| Each task, IDLE included | tcb_s, rt_s and a stack of DEFAULT_STACK_SIZE (2048, hal.h) |
| Each task with a port (all but IDLE) | queue_s and 8 pointers (MAX_PKT_QUEUE_SLOTS of noc.h) |
| Each output edge | one persistent packet: header + payload |
| Each input edge from another PE | `in_flight` received packets at the same time (irq2_handler; freed after the receive) |

`in_flight` = 2 by default: in run F, one execution of a task serves two
iterations (two packets of one flow in the queue). The heap of the image
is _heap_size of image.map (linker script hf-risc.ld: from the end of
.bss to the 2 KiB stack of main); ucx_heap_init keeps two block headers
(first block and end mark), so the usable heap is _heap_size - 16.
"""
from __future__ import annotations

import re

SIZES = {"tcb": 112, "rt": 12, "queue": 24, "block": 8, "pkt_header": 12,
         "stack": 2048, "queue_slots": 8, "pointer": 4}


def align4(n):
    return (n + 3) // 4 * 4


def block(n, sizes=SIZES):
    return align4(n) + sizes["block"]


def pe_demand(manifest, in_flight=2, payload_divisor=None, sizes=SIZES):
    """{node: {"bytes", "tasks", "out_packets", "in_packets"}}. With
    payload_divisor, the payloads are csv_bytes // payload_divisor
    (instead of the bytes of the manifest)."""
    flows = manifest["flows"]

    def payload(f):
        return f["bytes"] if payload_divisor is None else f["csv_bytes"] // payload_divisor

    out = {}
    for node in sorted({t["pe"] for t in manifest["tasks"]}):
        ts = [t for t in manifest["tasks"] if t["pe"] == node]
        task_bytes = (len(ts) + 1) * (block(sizes["tcb"]) + block(sizes["rt"]) + block(sizes["stack"]))
        task_bytes += len(ts) * (block(sizes["queue"]) + block(sizes["queue_slots"] * sizes["pointer"]))
        outs = [f for f in flows if f["src_pe"] == node]
        ins = [f for f in flows if f["dst_pe"] == node and not f["local"]]
        out_b = sum(block(sizes["pkt_header"] + payload(f)) for f in outs)
        in_b = in_flight * sum(block(sizes["pkt_header"] + payload(f)) for f in ins)
        out[node] = {"bytes": task_bytes + out_b + in_b, "tasks": task_bytes,
                     "out_packets": out_b, "in_packets": in_b}
    return out


def heap_size(image_map):
    """_heap_size of the image.map of the linker."""
    with open(image_map) as f:
        for line in f:
            m = re.search(r"0x([0-9a-fA-F]+)\s+_heap_size\s*=", line)
            if m:
                return int(m[1], 16)
    raise ValueError(f"{image_map}: no _heap_size")


def usable(heap, sizes=SIZES):
    return None if heap is None else heap - 2 * sizes["block"]


def report(manifest, heap, in_flight=2, divisors=(1,)):
    """Worst PE and margin (usable heap - demand) for each payload divisor
    (relative to the payloads of the CSV)."""
    rows = []
    free = usable(heap)
    for d in divisors:
        dem = pe_demand(manifest, in_flight, d)
        node = max(dem, key=lambda n: dem[n]["bytes"])
        rows.append({"divisor": d, "worst_pe": node, "bytes": dem[node]["bytes"],
                     "heap": heap, "margin": None if heap is None else free - dem[node]["bytes"],
                     "fits": None if heap is None else dem[node]["bytes"] <= free,
                     "largest_payload": max(f["csv_bytes"] // d for f in manifest["flows"])})
    return rows
