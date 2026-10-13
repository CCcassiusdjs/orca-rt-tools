"""UCX-OS application from the task graph, the clustering and the mapping.

    python -m rttools.ucxgen generate <app.csv> <app.map> --name <name> --mesh 4x4 --out <dir>
    python -m rttools.ucxgen memory <dir>/<name>.json [--image-map image.map | --heap BYTES]

The generator writes the application that application E has by hand
(pkt-sim/software/ucx-os/app/weird_a.c) for any graph of the analysis
flow: the CSV of the application (tasks, flows, #parameters) and the .map
file of the flow (node index y * width + x of arch/hermes-*.gml).

| Element of weird_a.c | Generated application |
|---|---|
| One function per task | One function per vertex of the CSV, which calls run_task with the descriptor of the task |
| ucx_sleep(TASK_*_WORKLOAD) | ucx_sleep(workload), workload = (c(v) - reserve) / cycles_per_count; c(v) = Capacity of the CSV, reserve = scheduler_cycles of #parameters, cycles_per_count = 10 (ucx_sleep of kernel/ucx.c, measured in run F) |
| Task A blocks until irq4_handler (kernel/sched.c, PE 0) | Every task without input edge blocks until the irq4_handler of the application, which releases the source tasks of its PE |
| One ucx_noc_send per edge, tag = payload | One ucx_noc_send per edge; tag = flow * tag_mod + (k mod tag_mod), flow = index of the edge in the CSV (from 1), k = iteration (from 1); tag_mod = 1 gives one tag per flow |
| Edge inside a PE: ucx_noc_send to the same CPU | The same: lib/noc.c puts the packet in the local queue of the target task |
| Join of J: k-th packet of each producer | The same rule for every task with more than one input edge (source port of the packet) |
| ucx_task_add per PE in app_main | Creation order of each PE as the model reads it (rttools/modules/instances/release.py, pe_sequences): sequence row of the CSV, otherwise creation row, otherwise the order of the .map line; the kernel dispatches it by the rule of rttools/bench_t/estimate.py (dispatch_order) |

Outputs in <dir>: <name>.c (application), <name>.json (manifest: tasks,
flows, PE of each task, ports, tags, release mask; the input of the
analysis of a run), <name>.sim (MESH and RELEASE_MASK for
experiments/exp23/simulate.sh).
"""
