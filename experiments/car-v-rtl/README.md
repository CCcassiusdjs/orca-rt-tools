# CAR-V on the 4x4 manycore (RTL)

CAR-V is the vision subgraph of CAR (23 tasks, 23 flows, one release period) at the time scale of application E. This directory generates its UCX-OS application with `rttools.ucxgen` and runs its RTL simulation on a 4x4 mesh with `experiments/exp23/simulate.sh`.

| Target | Action | Requirements |
|---|---|---|
| `make check` (default) | `pkt-sim/software/ucx-os/app/car_v.{c,json,sim}` match a new generation from `CSV` and `MAP`; heap demand of each PE against `HEAP`; `analyze` and `check-run` of the stored runs CV and CV2 | Python |
| `make analyze [LOG=<events.txt>] [OUTDIR=<dir>]` | Analysis of a run against the phase model (`python -m rttools.paper.rtlapp`; default `LOG=logs/CV.events.txt`, `OUTDIR=build/results_CV`; the `RUN_INFO` next to the log gives the clock) | Python |
| `make check-run [REF=<reference>]` | `metrics.json` of `OUTDIR` against `REF` (default `reference_CV.json`) | Python |
| `make app CSV=<csv> MAP=<map>` | Writes the three files | Python |
| `make build` | Builds `car_v` in `build/pkt-sim`; heap demand against `_heap_size` of `image.map` | Python, riscv64-elf toolchain |
| `make sim` | `F_CLK=$(F_CLK) ../exp23/simulate.sh build/sim $(SIM_NS) car_v 4x4` (default `F_CLK` 500 MHz) | Questa, riscv64-elf toolchain (`ENV_SETUP` as in exp23) |
| `make flow-clock` | `make -C ../car-v run`, then `F_CLK` of the minimum frequency of the CAR-V flow (chosen candidate): first multiple of 32 kHz at or above it (`rttools.paper.exp23.flow_clock`); 380.0 MHz gives 380 000 000 Hz | Python |
| `make sim-flow` | The same simulation at that `F_CLK` in `build/sim-flow` | Same as `make sim` |

## Inputs

| File | Content | Source |
|---|---|---|
| `input/car-v.csv` | Tasks (Capacity = c(v) in cycles), flows (payload in bytes, period 0.5 ms), `scheduler_cycles` 11,000 | Provisional: variant `vscaled` of the r9 analysis of CAR (cost of Shi et al. x 0.04 x 8 + 11,000 cycles; payload / 16) |
| `input/car-v.map` | Node of each task (node index y * 4 + x of `arch/hermes-4x4.gml`), MAX-PROC clustering and Spiral Mapping | Provisional: the same r9 run |

The Makefile and the tests take `apps/car-v/car-v.csv` and `apps/car-v/car-v-ONTO-hermes4x4.map` (the CAR-V analysis flow, `rttools.paper.carv`) when they exist, and `input/` otherwise. When the source changes, `make check` fails until `make app` writes `car_v.{c,json,sim}` again; the generator holds no number of CAR-V.

## Generated files

| File | Content |
|---|---|
| `car_v.c` | One task per vertex (weird_a.c pattern; release by tick with `-DUCX_TICK_RELEASE`, the Makefile rule: every task waits for the tick of phase k + n(v) before iteration k, `TASK_PHASE`; without the macro, the code of runs CV and CV2): source tasks wait for the release interrupt; joins wait for the k-th packet of each input edge; `ucx_sleep((c(v) - 11,000) / 10)`; one `ucx_noc_send` per edge with tag = flow x 1024 + (k mod 1024); iteration markers `ITER_BEGIN(letter, k)` when the task has the input of iteration k and `ITER_END(letter, k)` after its last send (after the work for a task without output edge); creation order of each PE (`ucx_task_add`) = creation order of the model (sequence row, else creation row, else the `.map` line); the kernel dispatches it in the order of the model |
| `car_v.json` | Manifest: PE, port, kernel id, letter of the iteration markers (`iter_letter`, A to W in CSV order), workload and edges of each task; flows with source and target PE, payload, tag base; release mask; `pe_tasks` in the format of `experiments/exp23/config.json` (IDLE and the creation order); `pe_dispatch` (dispatch order of the model) |
| `car_v.sim` | `MESH`, `RELEASE_MASK` (the 16 PEs, release by tick; runs CV and CV2: 2494, the PEs of the sources) and `TICK_RELEASE=1` for `simulate.sh` (period 0.5 ms and first release at 3 ms: defaults of the release generator) |

## Log of a run

| Line | Meaning |
|---|---|
| `TRIGGER: workflow iteration at <t> ns.` | Release acknowledged by the lowest PE of the mask (PE 1 for the provisional mapping); the analysis of exp23 reads it as the release of an iteration |
| `TRIGGER-PE <x>-<y>: release acknowledged at <t> ns` | The same release on another PE of the mask |
| `<t> <x>-<y> scheduled <id>` | Dispatch; `id` = position in `pe_tasks` of the manifest |
| `<t> <x>-<y> -> TAG <tag>`, `<- TAG <tag>` | Send and receive of a packet; flow = tag div 1024, iteration = tag mod 1024 (from 1) |
| `<t> <x>-<y> ITER begin\|end <letter> <k>` | Begin and end of iteration k of the task with that letter (`car_v.c` with iteration markers: run CV2 has 758; run CV has none) |
| `FLIT TX\|RX ...` | Flit times of the packet monitor (`rtl/pe_checker.sv`): header and last flit at the LOCAL ports of the source and destination routers, stall and gap, decoded tag |

## Stored runs CV and CV2

| File | Content |
|---|---|
| `logs/CV.events.txt` | Events of the Questa transcript (`simulate.sh`): `car_v.c` of tag r10-rc1 (no ITER lines), F_CLK = 380 MHz (the minimum frequency of the CAR-V flow), 11.5 ms, 17 releases, 16 CHKSUM lines with 0 errors |
| `logs/CV.RUN_INFO` | Source (`git archive` of r10-rc1, commit xxxxxxx), simulator, compiler, clock (half period 1,315,789 fs, 190,000 cycles per release) |
| `logs/CV.time.txt` | `time -v` of `vsim` (14 min 25 s, 73 MB) |
| `reference_CV.json` | Values of `make analyze` on the stored log; `make check-run` compares them |
| `logs/CV2.events.txt` | The same setup with `car_v.c` of tag r10-rc2 (the `car_v.c` of this tree, iteration markers): 758 ITER lines (379 begin, 379 end; 14 `ITER end W` of OBMG), 16 CHKSUM lines with 0 errors |
| `logs/CV2.RUN_INFO` | Source (`git archive` of r10-rc2, commit xxxxxxx), simulator, compiler, clock |
| `logs/CV2.time.txt` | `time -v` of `vsim` (14 min 30 s, 73 MB) |
| `reference_CV2.json` | Values of `make analyze LOG=logs/CV2.events.txt OUTDIR=build/results_CV2`; `make check` compares CV and CV2 |

## Analysis (`rttools.paper.rtlapp`)

| Quantity | Definition |
|---|---|
| Model | At the clock of the run: P = T F_CLK cycles; s^(v), f^(v) and phi(v) of the phase model on the costs c(v) of the CSV; R(v) = phi(v) P + f^(v) for each output task, R_bound = max; t(V_k) = sum of c(v) of PE k; window [r, d] = [f^(u), P + s^(v)] of each flow; L0 = 6 (m + 1) + p + 1, o_i = L0 + 20 (m + 1); link schedule of the AGS backend at F_CLK (`--arch`) |
| r_k | k-th `TRIGGER:` line |
| Iteration of a packet | From its tag (k mod 1024, unwrapped in time order per flow) |
| End of iteration k of a task | ITER end marker; without markers, the last send of iteration k; for an output task without markers, the exit of the task from the CPU after it has the packets of iteration k: exact when the run serves no later iteration, an upper bound otherwise (`exact`; `lower_cycles` = start of the run) |
| Response of iteration k | r_k to the end of iteration k of every output task (the largest) |
| CPU per PE | Non-IDLE time in windows of phi(v_last) + 1 releases from r_{phi(v_last) + 1}, divided by phi(v_last) + 1; per task, the CPU time of its runs up to the end of its last complete iteration divided by the iterations (`cpu_attributed`); busy time of each phase (`phase_busy_max`) |
| Packets | Send and receive in cycles from r_k + phi(u) P against [r, d]; slack = d - arrival |
| Network | TX and RX FLIT lines paired by source, destination and tag; header - 6 (m + 1), latency - L0, stall, gap; contenders = packets that hold a link of the XY route while the header waits |

| Output (`OUTDIR`) | Content |
|---|---|
| `metrics.json` | Every number of the analysis |
| `responses.csv` | Response of each iteration, `exact`, lower bound |
| `cpu.csv`, `tasks.csv` | CPU per PE (windows and attributed); per task: end against the model finish, observed phase, CPU per iteration, iterations served in the run of the previous one |
| `flows.csv`, `packets.csv` | Per flow and per packet against [r, d]; start of the link schedule |
| `network.csv`, `network_packets.csv` | Per flow and per packet: latency, L0, header wait, stall, contenders |
