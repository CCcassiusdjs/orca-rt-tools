# Experiment of Ch. 8 (exp-23)

Application E (`pkt-sim/software/ucx-os/app/weird_a.c`) on the 2x2 manycore: simulation with ModelSim/Questa, analysis of the log and check against reference values. The analysis writes the tables and the figure of Ch. 8 in real cycles and milliseconds.

## Commands

| Command | Effect | Needs |
|---|---|---|
| `make` | Analyzes the stored log of run E (`logs/E.events.txt`, the simulation of this tree) and checks it against `reference_head.json`; these are the numbers of the paper | Python with `orca-rt-tools/requirements.txt` |
| `make LOG=logs/D.events.txt REF=reference_D.json OUTDIR=build/results_D` | The same for run D | Python <!-- anon:drop-line --> |
| `make runs` | Analyzes the five stored runs into `build/runs/{A,B,C,D,E}` | Python <!-- anon:drop-line --> |
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
| `values.tex` | LaTeX macros (`\ExpAbdfMeasured`, `\ExpMeanOverestimation`, `\ExpMaxResponseMs`, ...) for the text |
| `fig812.pdf`, `fig812.svg` | Gantt of the first complete hyperperiod (Fig. 8.12) |
| `metrics.json` | Every value above; `make check` reads it |

## Definitions

| Quantity | Definition |
|---|---|
| Time unit | Read from the `$printtimescale` lines of the monitor (`rtl/chk_binds.sv`); `--unit 100ps` or `--unit 1ns` when the log has none. Commit 4c299fc prints the PE time in units of 100 ps; the fixed RTL in ns. |
| Hyperperiod | 4 releases of A (2 ms), from `first_hyperperiod_s` (4 ms, the window of Fig. 8.12) to the end of the log |
| CPU time per iteration (measured) | Non-IDLE time of the PE of the cluster in each hyperperiod, divided by 4; the analysis reports whether all hyperperiods give the same value |
| CPU time per iteration (estimated) | Sum of the WCETs of the cluster in `rttools/bench_t/main.py` (thesis scale), divided by 10 |
| Response time | From the first dispatch of A after each release (`TRIGGER` line) to the exit of J from the CPU after the 3k-th packet that reaches J. `weird_a.c` makes J consume any three packets, so the iteration k ends with the 3k-th packet. |
| Tab. 8.2 release and deadline | Finish of the source task and start of the target task in the `bench_t` sequence of their clusters, divided by 10 |
| Packet monitor | `rtl/pe_checker.sv` compares the flits each DDMA sends and writes with the memory; `errors` adds every mismatch |

<!-- anon:drop-begin -->
## Stored logs (`logs/`)

The files keep only the lines that the analysis reads (`grep` of the transcript, the same command as `simulate.sh`).

| Run | Hardware | Software | Unit | Result |
|---|---|---|---|---|
| A | 4c299fc | 4c299fc | 100 ps | Same events as B and D |
| B | fixed (b920605) | 4c299fc | 100 ps | Same events as A |
| C | fixed (b920605) | fixed (b920605) | 100 ps | `noc.c` fix delays the events by 446 to 870 cycles |
| D | fixed with `timescale 1ns/100ps (6a049b5) | 4c299fc | 1 ns | Same events as A with times divided by 10 |
| E | this tree (`make paper`) | this tree | 1 ns | Differs from C by up to 2 cycles of CPU time per iteration and 2 to 6 cycles of packet latency; the only change to the simulated software after b920605 is the zero-size check of `ddma.c` (828835f) |

<!-- anon:drop-end -->
`reference_head.json` (for `make paper`) holds the values of run E: `make paper` on the GAPH server, Questa 2025.3, riscv64-elf-gcc 12.2.0, 6 minutes of simulation.
