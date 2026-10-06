# Experiments

`make` in this directory reproduces the results that run in seconds and checks them against the stored references. The long runs have their own targets.

| Directory | Thesis | `make` | Long targets |
|---|---|---|---|
| `ch6` | Tables 6.5, 6.6, 6.7 (ORT/FNS) | Synthetic-Application-D and DCT-Verify | `make car` (hours) |
| `ch7` | Table 7.1 (ORT/GCM, ORT/GDE) | Graphs with \|V\| = 20 to 100 | `make graphs full` (about 18 minutes) |
| `exp23` | Ch. 8: Tables 8.2, 8.3, iterations, Fig. 8.12 | Stored Questa log of run D | `make paper` (Questa and riscv64-elf) |

Each run writes LaTeX tables, CSV files and `metrics.json` under `build/` of its directory; `make check` compares `metrics.json` with the reference of the directory. The README of each directory lists the agreement with the thesis.

Requirements: Python with `orca-rt-tools/requirements.txt`. The Python code lives in `orca-rt-tools/rttools/paper`.
