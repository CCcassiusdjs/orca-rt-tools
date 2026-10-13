# Artifact

This repository holds the RTL of the 2x2 manycore (Hermes NoC, RV32E cores, DDMA), the UCX-OS kernel with application E, the ORCA RT-Tools Python package and the pipelines that compute the numbers of the paper from stored inputs and stored simulation logs. License: GNU AGPL v3 (`LICENSE`).

## Contents

| Path | Content |
|---|---|
| `pkt-sim/hw` | RTL: Hermes router and NoC (VHDL), RV32E core, DDMA, PE (SystemVerilog) |
| `pkt-sim/manycore_modelsim` | Top level and the Questa/ModelSim script of the 2x2 manycore |
| `pkt-sim/software/ucx-os` | UCX-OS kernel; application E in `app/weird_a.c` |
| `orca-rt-tools/rttools` | ORCA RT-Tools; `rttools/paper` holds the pipelines |
| `apps` | Task graphs, mappings and platforms (application E in `apps/synthetic-app-e`, CAR in `apps/shi-2010`) |
| `experiments/ch7` | Contraction criteria on the random graphs (ORT/GCM, ORT/GDE); clustering of CAR and application E |
| `experiments/exp23` | Application E: stored Questa log, analysis and check; `make paper` simulates again |
| `experiments/figures` | Data of the article visuals (contraction criteria, Gantt, response per iteration, flow table) |
| `experiments/zll` | Zero-load latency testbench of the Hermes NoC (GHDL) |

## Requirements

| Use | Software |
|---|---|
| Pipelines (`make -C experiments`) and Python tests | Python 3.10 or later with `orca-rt-tools/requirements.txt`; pytest for the tests; GHDL 4 (tested with 4.1.0, mcode backend) for the zero-load latency (`zll`) |
| New RTL simulation (`make -C experiments/exp23 paper`) | Questa Sim (tested with 2025.3) or ModelSim, riscv64-elf-gcc 12.2.0, GNU make |

## Reproduction

| Command | Output | Time |
|---|---|---|
| `make -C experiments PYTHON=<python>` | `experiments/*/build`; each Python pipeline prints `match`; `zll` writes `experiments/zll/build/{8x3,2x2}/zll.csv` and prints `192 of 192` and `64 of 64` points that satisfy L0 = 6(m+1) + p + 1 | about 40 s |
| `make -C experiments/ch7 car` | `experiments/ch7/build/car`: CAR on 16 clusters and the criterion of application E | seconds |
| `make -C experiments/ch7 graphs full stats` | `experiments/ch7/build/{full,stats}`: all graphs and the summary of Table 7.1 | about 20 min |
| `make -C experiments/exp23 paper ENV_SETUP="..."` | `experiments/exp23/build/sim` (transcript, events, `RUN_INFO`), then the analysis of the new log against `reference_head.json` | about 6 min of simulation |
| `make -C experiments/exp23 paper-flow ENV_SETUP="..."` | The same at the minimum frequency of the flow (`F_CLK` = 434.912 MHz, `experiments/exp23/build/sim-flow`), checked against `reference_flow.json`; `make sim F_CLK=<Hz>` sets any other clock | about 5 min of simulation (estimate) |
| `cd orca-rt-tools && python -m pytest -q` | Python, C host and RTL tests (the RTL tests skip without Verilator or GHDL) | about 1 min |

## Measured times

Each time below comes from one run of the command.

| Machine | Hardware and software |
|---|---|
| Container | 2 vCPU Intel Xeon 2.1 GHz, Python 3.13.16, GHDL |
| Simulation host | Intel Core i9-7940X (14 cores, 28 threads), 128 GB, Rocky Linux 8.10, Questa Sim-64 2025.3, riscv64-elf-gcc 12.2.0 |

| Command | Time | Machine |
|---|---|---|
| `make -C experiments` (`ch7`, `exp23`, `figures`, `zll` and their checks) | 37.6 s (`zll` alone 27.3 s) | Container |
| `make -C experiments/ch7` (\|V\| = 20 to 100) | 2.3 s | Container |
| `make -C experiments/ch7 car` | 0.5 s | Container |
| `make -C experiments/ch7 graphs full` (17 graphs) | 21 min 32 s wall clock, 17 min 1 s user time (\|V\| = 900 alone 560 s) | Container |
| `make -C experiments/exp23` (with `frequency`) | 2.3 s | Container |
| `make -C experiments/exp23 frequency` | 0.6 s | Container |
| `make -C experiments figures` | 1.2 s | Container |
| `make -C experiments/exp23 paper` | `vsim` alone: 5 min 46 s wall clock, 343.6 s user time, 54 MB of resident memory, for 20 ms of simulated time (`experiments/exp23/logs/F.time.txt`); the builds were not timed | Simulation host |

TODO(re-measure on the workstation): the container times come from a shared container; measure every command again on the simulation host.

## Numbers of the paper

| Research question or result | Pipeline |
|---|---|
| RQ1: contraction criteria on the random graphs and on CAR | `experiments/ch7` |
| RQ2 (CPU time per iteration), RQ3 (response time and flows), f* (f_NoC in the paper) and f_CPU of application E | `experiments/exp23` |
| Rows and coordinates of the criteria table, the Gantt, the response per iteration and the flow table | `experiments/figures` |
| L0 = 6(m+1) + p + 1 at 256 points of the Hermes RTL (GHDL) | `experiments/zll` |

| Item of the paper | Source | Command |
|---|---|---|
| CPU time per iteration, measured and estimated, per cluster; Gantt of one hyperperiod; response time per iteration; flows with release, deadline and measured latency | `experiments/exp23/logs/F.events.txt` (stored log of the RTL simulation of tag exp23-F; `F.RUN_INFO`, `F.time.txt`) | `make -C experiments/exp23`; tables, `values.tex` and `metrics.json` in `build/results` |
| Gantt of one hyperperiod, response per iteration and flow table (rows and coordinates of the article visuals); contraction criteria on the example graph | `experiments/exp23/logs/F.events.txt`, `apps/sample-graph-a/sample_graph.txt` | `make -C experiments figures` |
| CAR clustering (Reference, MAX-PROC, MIN-COMM) and the criterion of application E | `apps/shi-2010/shi-2010.txt`, `apps/synthetic-app-e/synthetic-app-e.txt` | `make -C experiments/ch7 car` |
| Minimum frequency of application E: f* (network), f_CPU (CPU test) and max(f*, f_CPU), with the mapping file and with the Spiral Mapping | `apps/synthetic-app-e/synthetic-app-e.csv` (phase model, characterized costs), `arch/hermes-2x2.gml` | `make -C experiments/exp23 frequency`; the same numbers from `python -m rttools apps/synthetic-app-e/synthetic-app-e.csv <map or spiral> arch/hermes-2x2.gml 500000000` |
| Zero-load latency L0 = 6(m+1) + p + 1 | Hermes RTL in `pkt-sim/hw/router/hermes` | `make -C experiments zll` |
| Contraction criteria on the random graphs (\|V\| = 20 to 900) | `experiments/ch7/graphs` | `make -C experiments/ch7` (\|V\| up to 100); `make -C experiments/ch7 graphs full` (all graphs) |
| Platform and setup (clock, tick, compiler, simulator); tick equal to the release period T of A (250 000 cycles) | `pkt-sim/software/ucx-os/arch/riscv/hf-riscv-e/arch.mak`, `hal.c`, `pkt-sim/hw/peripherals/peripherals_minimal.vhd`, `experiments/exp23/README.md` | `make -C experiments/exp23 tick` (from the sources); `pkt-sim/tests/rtl/run.sh tb_timer1` (GHDL) |

## Simulation runs

`make paper` writes `RUN_INFO` with the commit, the state of the work tree (`clean`, `dirty`, `archive`, `nogit`), the tag and a SHA-256 of the simulated sources (`experiments/exp23/README.md`). The run that the paper reports comes from a clean checkout at a tag:

```
git checkout <tag>
make -C experiments/exp23 paper REQUIRE_CLEAN=1 ENV_SETUP="<commands that load Questa and riscv64-elf-gcc>"
```

With `REQUIRE_CLEAN=1`, `simulate.sh` stops before the build when the tree has changes or no tag. A simulation server without access to the repository receives `git archive --prefix=orca/ -o orca.tar <tag>`; the archive carries the commit hash in `experiments/exp23/VERSION`, and `RUN_INFO` records `repo_state=archive`.

<!-- anon:drop-begin -->
## Anonymized copy for double-anonymous review

`tools/anonymize/export.sh <out_dir> [<ref>]` writes a copy of commit `<ref>` (default `HEAD`) without git history, author names, institution and laboratory names, site paths, commit hashes of this repository and the outputs that compare results with the thesis, then searches the copy for the identifying strings and lists what remains. `tools/anonymize/README.md` describes the rules.
<!-- anon:drop-end -->
