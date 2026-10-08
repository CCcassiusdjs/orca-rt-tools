# Experiments

`make` in this directory runs the pipelines that take seconds and checks each result against the reference stored in its directory. `make zll` runs the zero-load latency testbench of the NoC. The long runs have their own targets. `ARTIFACT.md` at the root of the repository maps the numbers of the paper to these commands.

| Directory | Content | `make` | Long targets |
|---|---|---|---|
| `ch6` | Tables 6.5, 6.6, 6.7 (ORT/FNS) | Synthetic-Application-D and DCT-Verify | `make car` (hours) <!-- anon:drop-line --> |
| `ch7` | Contraction criteria (ORT/GCM, ORT/GDE) on the random graphs | Graphs with \|V\| = 20 to 100 | `make graphs full` (about 20 minutes) |
| `exp23` | Application E on the 2x2 manycore: CPU time per iteration, response time, flows, Gantt | Stored Questa log of run E against `reference_head.json` | `make paper` (Questa and riscv64-elf) |
| `zll` | Zero-load latency of the Hermes NoC, L0 = 6(m+1) + p + 1 | `make zll` from this directory (GHDL, about 30 s) | |

Each pipeline writes LaTeX tables, CSV files and `metrics.json` under `build/` of its directory; `make check` compares `metrics.json` with the reference of the directory and prints `match` or the differing values.

The README of each directory lists the agreement with the thesis. <!-- anon:drop-line -->

Requirements: Python with `orca-rt-tools/requirements.txt` for `make`; GHDL for `make zll`. The Python code lives in `orca-rt-tools/rttools/paper`. `make PYTHON=<interpreter>` selects the interpreter.
