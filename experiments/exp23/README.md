# Experiment of Ch. 8 (exp-23)

Application E (`pkt-sim/software/ucx-os/app/weird_a.c`) on the 2x2 manycore: simulation with ModelSim/Questa, analysis of the log and check against reference values. The analysis writes the tables and the figure of Ch. 8 in real cycles and milliseconds.

## Commands

| Command | Effect | Needs |
|---|---|---|
| `make` | Analyzes the stored log of run F (`logs/F.events.txt`, the simulation of this tree) and checks it against `reference_head.json`; these are the numbers of the paper | Python with `orca-rt-tools/requirements.txt` |
| `make frequency` | Minimum frequency of application E with the analysis flow (CLI input `apps/synthetic-app-e/synthetic-app-e.csv`, `arch/hermes-2x2.gml`, first frequency 500 MHz): f* of the network bisection, f_CPU of the CPU test, the network check at f_CPU and the minimum frequency, with the `.map` file and with the Spiral Mapping; check against `reference_frequency.json` (also part of `make`) | Python |
| `make LOG=logs/D.events.txt REF=reference_D.json OUTDIR=build/results_D` | The same for run D (`E` and `reference_E.json` for run E) | Python <!-- anon:drop-line --> |
| `make runs` | Analyzes the six stored runs into `build/runs/{A,B,C,D,E,F}` (join rule `any3` for A to E, `per_producer` for F) | Python <!-- anon:drop-line --> |
| `make sim` | Simulates this tree (`simulate.sh build/sim`) | Questa or ModelSim, `riscv64-elf` toolchain |
| `make paper` | `sim`, then analysis and check against `reference_head.json` | Questa or ModelSim, toolchain, Python |
| `make paper REQUIRE_CLEAN=1` | The same, but `simulate.sh` stops unless the tree is a clean git checkout at a tag or a `git archive` of a commit | Same as `make paper`, git |
| `make info` | Prints the source identification that `make sim` writes to `RUN_INFO` | git (optional) |

`ENV_SETUP` holds the shell commands that put the simulator and the toolchain on the `PATH`, for example `make paper ENV_SETUP="module load riscv64-elf/12.2.0 questa/2025.3"`.
<!-- anon:drop-begin -->
On the GAPH server: `make paper ENV_SETUP="source /soft64/source_gaph; module load riscv64-elf/12.2.0 questa/2025.3"` (run it under the simulation area, not under `/home`).
<!-- anon:drop-end -->

## Run identification (`RUN_INFO`)

`simulate.sh` writes `build/sim/RUN_INFO` before the build:

| Field | Content |
|---|---|
| `repo_commit` | Commit hash from git when the repository root is a git work tree; from `VERSION` when the tree comes from `git archive` (the `export-subst` attribute writes the hash there); `unknown` for a copy without git metadata |
| `repo_state` | `clean` (git, no change to tracked files and no untracked file), `dirty` (git with changes; the list goes to `RUN_INFO.status`), `archive` (`git archive`, clean by construction) or `nogit` |
| `repo_tag` | Tag at the commit, or `none` |
| `src_sha256` | SHA-256 over the `sha256sum` lines of the simulated sources (`pkt-sim`, `rtl/`, `simulate.sh`), sorted by path; equal in a clean checkout, in a `git archive` of the same commit and in a copy without git |
| `sim_ns`, `monitor`, `vsim`, `gcc`, `date` | Simulation length, packet monitor, simulator and compiler versions, UTC date |

A copy of a work tree without its git metadata (for example a copy of a `git worktree`, whose `.git` file points to a directory that does not exist on the simulation server) gives `repo_commit=unknown` and `repo_state=nogit`. The run that a paper reports comes from a tagged clean checkout:

```
git clone <repository> orca && cd orca && git checkout <tag>
make -C experiments/exp23 paper REQUIRE_CLEAN=1 ENV_SETUP="..."
```

or, on a server without access to the repository, from an archive of the tag: `git archive --prefix=orca/ -o orca.tar <tag>`, copy and unpack `orca.tar`, then the same `make` command. Store `build/sim/RUN_INFO`, `build/sim/events.txt` and `build/sim/time.log` with the results.

## Outputs (`build/results`)

| File | Content |
|---|---|
| `tab83.tex`, `tab83.csv` | CPU time per iteration of each cluster, measured in the log and estimated by ORT/BENCH (Tab. 8.3) |
| `iterations.tex`, `iterations.csv` | Response time per release in the hyperperiod and the maximum against the deadline |
| `tab82.tex`, `tab82.csv` | Flow characterization (Tab. 8.2) and the packet latency measured in the log |
| `thesis.tex`, `thesis.csv` | Values printed in the thesis next to the values of the run |
| `values.tex` | LaTeX macros (`\ExpAbdfMeasured`, `\ExpMeanOverestimation`, `\ExpMaxResponseMs`, `\ExpCpuFrequencyMhz`, `\ExpResponseBoundMs`, ...) for the text |
| `fig812.pdf`, `fig812.svg` | Gantt of the first complete hyperperiod (Fig. 8.12) |
| `metrics.json` | Every value above; `make check` reads it |
| `build/frequency/metrics.json`, `frequency.csv`, `values.tex` | `make frequency`: per mapping, CPU demand per node, f_CPU, f*, the attempts of the bisection, the network check at f_CPU (`final_check`: verdict, packets, skipped packets, hyperperiod) and the minimum frequency; macros `\ExpFrequencyMapNetworkMhz`, `\ExpFrequencyMapCpuMhz`, `\ExpFrequencyMapMinimumMhz`, `\ExpFrequencyMapCpuNetwork`, `\ExpFrequencyMapCpuPackets`, `\ExpFrequencyMapCpuSkipped` and the same for `Spiral` |

## Definitions

| Quantity | Definition |
|---|---|
| Time unit | Read from the `$printtimescale` lines of the monitor (`rtl/chk_binds.sv`); `--unit 100ps` or `--unit 1ns` when the log has none. Commit 4c299fc prints the PE time in units of 100 ps; the fixed RTL in ns. |
| Hyperperiod | 4 releases of A (2 ms), from `first_hyperperiod_s` (4 ms, the window of Fig. 8.12) to the end of the log |
| CPU time per iteration (measured) | Non-IDLE time of the PE of the cluster in each hyperperiod, divided by 4, and the mean over the complete hyperperiods; the analysis reports whether all hyperperiods give the same value. The log counts ns and a cycle lasts 2 ns, so a slice can end on half a cycle and a value per iteration on a multiple of 1/8 cycle; the tables print one decimal. In run F, GJ gives 176 457.125 cycles in the first hyperperiod (4 to 6 ms: G runs 85 724.4 cycles per iteration while PE 1-1 settles into its pattern of two phases) and 182 647.75 or 182 648.5 in the other six, so the mean is 181 763.589, printed 181 763.6 |
| CPU time per iteration (estimated) | CPU demand of the PE: sum of the characterized costs of the cluster in `rttools/bench_t/main.py` (thesis scale), divided by 10 |
| Dispatch order (`sequences`) | Kernel rule (`rttools/bench_t/estimate.py`, `dispatch_order`; `kernel/ucx.c:20-48`, `kernel/sched.c:94-109`): round robin over the tasks of the PE in creation order, from the idle task; a task is ready at the tick when its predecessors on the PE have a lower phase index and otherwise after its last predecessor of the same phase. The creation order comes from the creation rows of the CSV (config `application`), the order of `ucx_task_add` in `app_main` of `weird_a.c`; `pe_tasks` must follow it (the analysis stops otherwise). Result: A, B, D, F; C; E, H, I; J, G (J of phase 3 and G of phase 1 are both ready at the tick, and J comes first in the queue). Log F: E, H, I in every phase; J, G in the phases in which J is ready at the tick and G, J in the others, in which the packets of I reach J after the tick |
| Sequence per PE | Start and finish of each task: ORT/BENCH (`rttools/bench_t/estimate.py`, round robin, one job per task, quantum = largest cost) on the costs of the cluster in the dispatch order, divided by 10; the start includes the scheduler cost |
| CPU frequency (`cpu.f_cpu_hz`) | Largest CPU demand per iteration divided by the release period (0.5 ms); computed once, independent of the frequency of the link schedule |
| Minimum frequency (`make frequency`) | `python -m rttools <app> <map> <arch> 500000000`: the CPU test once (f_CPU, the row above, from the task capacities of the CSV = characterized costs / 10), then the bisection of the network schedule with the phase model of the flows (f*), result max(f*, f_CPU). When f_CPU > f*, the network is evaluated once more at f_CPU (the phase length T f moves the packet windows, so feasibility at f* does not imply feasibility at f_CPU); when it is not feasible there, the search continues above f_CPU (doubling, then bisection on (f_CPU, upper]) and the result is the first feasible frequency. f* = 327.6 MHz is the lowest frequency whose phase holds the window of I->J (finish of I 173 370 in the sequence E, H, I, start of J 11 000 in the next phase in the sequence J, G, occupancy 1 434 cycles); at f_CPU = 434.9 MHz the network is feasible (5 packets, 0 skipped, hyperperiod 217 450 cycles), so f_CPU is the result |
| Response bound (`response_bound`) | phi(v) P + finish of v in its sequence, for the last task of the iteration (J): phi(v) counts the edges between PEs on the longest path to v (config `task_graph`; an edge inside a PE counts one phase when the target runs before the source in the dispatch order), P = 250 000 cycles. With J, G on GJ: phi(J) = 3 (from I and H), phi(G) = 1, so J of iteration k runs first in phase 3 and G of the same iteration ran in phase 1; R^ = 3 P + c^(J) = 857 570 cycles (1.715 ms), below the measured 1.861 ms, which closes at the exit of J after the two iterations that one slice of J serves |
| Response time | From the first dispatch of A after each release (`TRIGGER` line) to the exit of J from the CPU after J has the packets of iteration k. Rule `per_producer` (config `join.rule`, the application of this tree): `weird_a.c` runs iteration k of J after the k-th packet of each producer (G, H, I; one packet per iteration, FIFO), so iteration k ends with the exit of J after the latest of the k-th `<- TAG` of each tag of J (8900, 5670, 1230) at PE 1-1. Rule `any3` (`--join any3`): the application before the fix made J consume any three packets, so iteration k ended with the 3k-th packet; the Makefiles select it for the stored logs A to E. Both rules give the same responses for run E |
| Release to dispatch, response from the release | `iterations.release_to_dispatch`: cycles from the release (`TRIGGER`) to the first dispatch of A over the complete iterations; `release_to_dispatch_all_releases`: the same over every release of the log; `response_from_release_max`: largest time from the release to the exit of J. Run F: 1 396 to 1 891 cycles (1 396 to 1 924 over the 34 releases); 932 143 cycles (1.864 ms) from the release, 930 585 cycles (1.861 ms) from the dispatch |
| End of the log | The parser ends the last slice of each PE at the end of the log; only that slice, which no `scheduled` event closes, leaves the response. A slice of J closed by an event at the last instant counts (run F: iterations 31 and 32 end at 19 865 063 ns) |
| Packet pairing | `->` and `<-` lines pair by tag in FIFO order. Tag 1230 is shared by A->C (PE 0-0 to 0-1) and G->J (local on PE 1-1); `packet_pairs.unexpected` in `metrics.json` counts the pairs between different PEs that are not a flow of the config (0 in runs A to E). E->I uses tag 9010 in this tree (3450, the tag of D->F, before) |
| Tab. 8.2 release and deadline | Release: finish of the source task in its sequence. Deadline: start of the target task in its sequence plus one phase (the target receives the packet in the phase after the source phase). Both count cycles from the start of the source phase |
| Packet monitor | `rtl/pe_checker.sv` compares the flits each DDMA sends and writes with the memory; `errors` adds every mismatch. `rtl/chk_binds.sv` binds one monitor to every `manycore_pe` (simulation only; the RTL does not change); the monitor reads the router port, the DDMA command and DDMA memory port signals and the RAM of the PE. Send: at each rising edge of `send_cmd_in`, the monitor compares the flits that the router accepts from the DDMA (destination, size, payload) with the packet in memory. Receive: each payload flit that the router delivers gives an expected write (address, data), and the next DDMA write to memory must match it; a write without a flit counts as spurious. The `CHKSUM` line of each PE gives `send_pkts`, `recv_pkts` and the error counters (`send_err`, `send_incomplete`, `recv_err`, `recv_spurious`, `recv_missing`); `errors` in `metrics.json` (`monitor`) is their sum |

<!-- anon:drop-begin -->
## Stored logs (`logs/`)

The files keep only the lines that the analysis reads (`grep` of the transcript, the same command as `simulate.sh`).

| Run | Hardware | Software | Unit | Result |
|---|---|---|---|---|
| A | 4c299fc | 4c299fc | 100 ps | Same events as B and D |
| B | fixed (b920605) | 4c299fc | 100 ps | Same events as A |
| C | fixed (b920605) | fixed (b920605) | 100 ps | `noc.c` fix delays the events by 446 to 870 cycles |
| D | fixed with `timescale 1ns/100ps (6a049b5) | 4c299fc | 1 ns | Same events as A with times divided by 10 |
| E | 0b02861 (`make paper`) | 0b02861 | 1 ns | Differs from C by up to 2 cycles of CPU time per iteration and 2 to 6 cycles of packet latency; the only change to the simulated software after b920605 is the zero-size check of `ddma.c` (828835f). J joins any three packets; E->I with tag 3450. `reference_E.json` |
| F | this tree (tag exp23-F, 69d9cc5) | this tree | 1 ns | `weird_a.c` with the per-producer join of J and E->I with tag 9010. Against E: ABDF, C equal; EHI +3 cycles; GJ 181 763.6 (E 183 086); packet latencies within 2 cycles of E, except the maximum of F4 (2 993, E 3 164); responses 1.3605 to 1.8612 ms (E 1.1793 to 1.8607 ms). 0 monitor errors in 166 packets; `packet_pairs.unexpected` 0 |

<!-- anon:drop-end -->
`reference_head.json` (for `make paper`) holds the values of run F: simulation (`simulate.sh`) of a `git archive` of tag exp23-F (`repo_state=archive`), Questa 2025.3, riscv64-elf-gcc 12.2.0. `logs/F.RUN_INFO` and `logs/F.time.txt` keep the source identification and the time of `vsim` (5 min 46 s wall clock, 343.6 s user time, 54 MB of resident memory). In run F, the packet monitor recorded 166 sent and 166 received packets and 0 errors (`monitor` in `build/results/metrics.json`).
