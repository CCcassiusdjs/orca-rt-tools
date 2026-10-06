# Experiment of Ch. 8 (exp-23)

Application E (`pkt-sim/software/ucx-os/app/weird_a.c`) on the 2x2 manycore: simulation with ModelSim/Questa, analysis of the log and check against reference values. The analysis writes the tables and the figure of Ch. 8 in real cycles and milliseconds.

## Commands

| Command | Effect | Needs |
|---|---|---|
| `make` | Analyzes the stored log of run D and checks it against `reference_D.json` | Python with `orca-rt-tools/requirements.txt` |
| `make runs` | Analyzes the four stored runs into `build/runs/{A,B,C,D}` | Python |
| `make sim` | Simulates this tree (`simulate.sh build/sim`) | Questa or ModelSim, `riscv64-elf` toolchain |
| `make paper` | `sim`, then analysis and check against `reference_head.json` | Questa or ModelSim, toolchain, Python |

On the GAPH server: `make paper ENV_SETUP="source /soft64/source_gaph; module load riscv64-elf/12.2.0 questa/2025.3"` (run it under the simulation area, not under `/home`).

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

## Stored logs (`logs/`)

The files keep only the lines that the analysis reads (`grep` of the transcript, the same command as `simulate.sh`).

| Run | Hardware | Software | Unit | Result |
|---|---|---|---|---|
| A | 4c299fc | 4c299fc | 100 ps | Same events as B and D |
| B | fixed (b920605) | 4c299fc | 100 ps | Same events as A |
| C | fixed (b920605) | fixed (b920605) | 100 ps | `noc.c` fix delays the events by 446 to 870 cycles |
| D | fixed with `timescale 1ns/100ps (6a049b5) | 4c299fc | 1 ns | Same events as A with times divided by 10 |

`reference_head.json` (for `make paper`) comes from run C in cycles. A simulation of this tree confirms it.
