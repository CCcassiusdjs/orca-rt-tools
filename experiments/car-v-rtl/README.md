# CAR-V on the 4x4 manycore (RTL)

CAR-V is the vision subgraph of CAR (23 tasks, 23 flows, one release period) at the time scale of application E. This directory generates its UCX-OS application with `rttools.ucxgen` and runs its RTL simulation on a 4x4 mesh with `experiments/exp23/simulate.sh`.

| Target | Action | Requirements |
|---|---|---|
| `make check` (default) | `pkt-sim/software/ucx-os/app/car_v.{c,json,sim}` match a new generation from `CSV` and `MAP`; heap demand of each PE against `HEAP` | Python |
| `make app CSV=<csv> MAP=<map>` | Writes the three files | Python |
| `make build` | Builds `car_v` in `build/pkt-sim`; heap demand against `_heap_size` of `image.map` | Python, riscv64-elf toolchain |
| `make sim` | `../exp23/simulate.sh build/sim $(SIM_NS) car_v 4x4` | Questa, riscv64-elf toolchain (`ENV_SETUP` as in exp23) |

## Inputs

| File | Content | Source |
|---|---|---|
| `input/car-v.csv` | Tasks (Capacity = c(v) in cycles), flows (payload in bytes, period 0.5 ms), `scheduler_cycles` 11,000 | Provisional: variant `vscaled` of the r9 analysis of CAR (cost of Shi et al. x 0.04 x 8 + 11,000 cycles; payload / 16) |
| `input/car-v.map` | Node of each task (node index y * 4 + x of `arch/hermes-4x4.gml`), MAX-PROC clustering and Spiral Mapping | Provisional: the same r9 run |

The analysis flow of CAR-V writes the final CSV and `.map`; `make app CSV=... MAP=...` regenerates the application from them, and the generator does not hold any number of CAR-V.

## Generated files

| File | Content |
|---|---|
| `car_v.c` | One task per vertex (weird_a.c pattern): source tasks wait for the release interrupt; joins wait for the k-th packet of each input edge; `ucx_sleep((c(v) - 11,000) / 10)`; one `ucx_noc_send` per edge with tag = flow x 1024 + (k mod 1024); creation order of each PE = dispatch order of the model |
| `car_v.json` | Manifest: PE, port, kernel id, workload and edges of each task; flows with source and target PE, payload, tag base; release mask; `pe_tasks` in the format of `experiments/exp23/config.json` |
| `car_v.sim` | `MESH`, `RELEASE_MASK`, `RELEASE_PERIOD_NS`, `RELEASE_DELAY_NS` for `simulate.sh` |

## Log of a run

| Line | Meaning |
|---|---|
| `TRIGGER: workflow iteration at <t> ns.` | Release acknowledged by the lowest PE of the mask (PE 1 for the provisional mapping); the analysis of exp23 reads it as the release of an iteration |
| `TRIGGER-PE <x>-<y>: release acknowledged at <t> ns` | The same release on another PE of the mask |
| `<t> <x>-<y> scheduled <id>` | Dispatch; `id` = position in `pe_tasks` of the manifest |
| `<t> <x>-<y> -> TAG <tag>`, `<- TAG <tag>` | Send and receive of a packet; flow = tag div 1024, iteration = tag mod 1024 (from 1) |
