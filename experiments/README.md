# Experiments

`make` in this directory runs the pipelines of `DIRS` (Python pipelines that take seconds and the zero-load latency testbench of the NoC, about 30 s) and checks each result against the reference stored in its directory; `make <dir>` runs one of them. The long runs have their own targets. `ARTIFACT.md` at the root of the repository maps the numbers of the paper to these commands.

| Directory | Content | `make` | Long targets |
|---|---|---|---|
| `ch6` | Tables 6.5, 6.6, 6.7 (ORT/FNS) | Synthetic-Application-D and DCT-Verify | `make car` (hours) <!-- anon:drop-line --> |
| `ch7` | Contraction criteria (ORT/GCM, ORT/GDE) on the random graphs; clustering of CAR and of application E | Graphs with \|V\| = 20 to 100 | `make graphs full` (about 20 minutes), then `make stats`; `make car` (seconds) |
| `exp23` | Application E on the 2x2 manycore: CPU time per iteration, response time, flows, Gantt | Stored Questa log of run E against `reference_head.json` | `make paper` (Questa and riscv64-elf) |
| `figures` | Data of the article visuals: contraction criteria on the example graph; Gantt, response per iteration and flow table of application E from the stored log of run E | Both, against `reference_contraction.json` and `reference_exp23.json` | |
| `zll` | Zero-load latency of the Hermes NoC, L0 = 6(m+1) + p + 1 | 8x3 and 2x2 meshes (GHDL, about 30 s) | |

Each pipeline writes LaTeX tables, CSV files and `metrics.json` under `build/` of its directory; `make check` compares `metrics.json` with the reference of the directory and prints `match` or the differing values.

The README of each directory lists the agreement with the thesis. <!-- anon:drop-line -->

Requirements: Python with `orca-rt-tools/requirements.txt` and GHDL for `make`; `make ch7 exp23 figures` runs without GHDL. The Python code lives in `orca-rt-tools/rttools/paper`. `make PYTHON=<interpreter>` selects the interpreter.
