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
| `cd orca-rt-tools && python -m pytest -q` | Python, C host and RTL tests (the RTL tests skip without Verilator or GHDL) | about 1 min |

## Numbers of the paper

| Item of the paper | Source | Command |
|---|---|---|
| CPU time per iteration, measured and estimated, per cluster; Gantt of one hyperperiod; response time per iteration; flows with release, deadline and measured latency | `experiments/exp23/logs/E.events.txt` (stored log of the RTL simulation) | `make -C experiments/exp23`; tables, `values.tex` and `metrics.json` in `build/results` |
| Gantt of one hyperperiod, response per iteration and flow table (rows and coordinates of the article visuals); contraction criteria on the example graph | `experiments/exp23/logs/E.events.txt`, `apps/sample-graph-a/sample_graph.txt` | `make -C experiments figures` |
| CAR clustering (Reference, MAX-PROC, MIN-COMM) and the criterion of application E | `apps/shi-2010/shi-2010.txt`, `apps/synthetic-app-e/synthetic-app-e.txt` | `make -C experiments/ch7 car` |
| Zero-load latency L0 = 6(m+1) + p + 1 | Hermes RTL in `pkt-sim/hw/router/hermes` | `make -C experiments zll` |
| Contraction criteria on the random graphs (\|V\| = 20 to 900) | `experiments/ch7/graphs` | `make -C experiments/ch7` (\|V\| up to 100); `make -C experiments/ch7 graphs full` (all graphs) |
| Platform and setup (clock, tick, compiler, simulator) | `pkt-sim/software/ucx-os/arch/riscv/hf-riscv-e/arch.mak`, `experiments/exp23/README.md` | none |

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
