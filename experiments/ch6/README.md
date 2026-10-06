# Tables 6.5, 6.6 and 6.7 (ORT/FNS)

`make` runs the AGS backend for Synthetic-Application-D and DCT-Verify with the criteria LSTF, MBCF and MCPF and PF = 10, 20 and 40 (threshold = PF, Sec. 6.5), writes the tables with the thesis value next to the value of the run and checks the run against `reference.json`. `make car` runs CAR with PF and threshold multiplied by 100 (hours per configuration).

| Table | Input | Quantity |
|---|---|---|
| 6.5, 6.6 | `rttools/modules/backend/ags/problem_*.py` (instances of the thesis: Synthetic-Application-D = `problem_syntheticA`, HP 55; DCT-Verify, HP 78,651; CAR, HP 2,000,000) | `hsearch.entered` (visited) and `hsearch.ignored` (skipped) of `search3.py` |
| 6.7 | Application, mapping and NoC files of `apps/` and `arch/` | Frequency returned by `rttools/modules/frequency/search.py` from 2 MHz with tolerance 5000 Hz, in Hz |

## Result of the current code

| Table | Agreement with the thesis |
|---|---|
| 6.5 (visited) | Synthetic-D: 4 of 9 cells (PF 20 for all criteria, MCPF PF 10); PF 40 gives no schedule. DCT-Verify: 6 of 9 (LSTF and MBCF); MCPF gives 8 instead of 214, 111 and 60 |
| 6.6 (skipped) | Synthetic-D: 4 of 9. DCT-Verify: MBCF 3 of 3; LSTF gives 314 and 158 for PF 10 and 20, the thesis prints 158 and 314; MCPF 0 of 3 |
| 6.7 | No cell. Synthetic-D: 3906.25 Hz for every criterion and PF. DCT-Verify: 79,376 Hz (LSTF; MCPF with PF 40) and 112,164 Hz (MBCF; MCPF with PF 10 and 20). The thesis prints 793 to 1707 "MHz" |

The CAR rows of Tables 6.5 and 6.6 and the CAR frequencies of Table 6.7 come from `make car`.

## Outputs (`build/results`)

| File | Content |
|---|---|
| `tab65.tex/.csv`, `tab66.tex/.csv` | Thesis value, value of the run, agreement and number of discarded packets per cell |
| `tab67.tex/.csv` | Value printed in the thesis, frequency of the run in Hz, lowest feasible frequency among the attempts and number of attempts |
| `metrics.json` | All values; `make check` compares it with `reference.json` |
