# Tables 6.5, 6.6 and 6.7 (ORT/FNS)

`make` runs the AGS backend for Synthetic-Application-D and DCT-Verify with the criteria LSTF, MBCF and MCPF and PF = 10, 20 and 40 (threshold = PF, Sec. 6.5), writes the tables with the thesis value next to the value of the run and checks the run against `reference.json`. `make car` runs CAR with PF and threshold multiplied by 100 (hours per configuration).

| Table | Input | Quantity |
|---|---|---|
| 6.5, 6.6 | `rttools/modules/backend/ags/problem_*.py` (instances of the thesis: Synthetic-Application-D = `problem_syntheticA`, HP 55; DCT-Verify, HP 78,651; CAR, HP 2,000,000) | `hsearch.entered` (visited) and `hsearch.ignored` (skipped) of `search3.py` |
| 6.7 | Application, mapping and NoC files of `apps/` and `arch/` | Frequency returned by `rttools/modules/frequency/search.py` from 2 MHz with tolerance 5000 Hz, in Hz |

## Result of the current code

The code follows the thesis since `fix/art-fns-search`: occupancy L0 = 6(m+1) + p + 1 with the 12-byte kernel header in p, criteria of Eqs. 6.2 and 6.3 (MCPF takes the most critical packet first), AGS of Fig. 6.6 (reset, threshold across resets, truncation at the maximum release) and a bisection that keeps the feasible upper bound.

| Table | Agreement with the thesis |
|---|---|
| 6.5 (visited) | Synthetic-D: 4 of 9 cells (6 visits in every configuration; the thesis prints 6 for MCPF PF 10 and 20 and for LSTF and MBCF PF 40). DCT-Verify: 6 of 9 (LSTF and MBCF); MCPF gives 8 instead of 214, 111 and 60 |
| 6.6 (skipped) | Synthetic-D: 2 of 9 (LSTF and MBCF PF 40). DCT-Verify: MBCF 3 of 3; LSTF gives the MBCF values (416, 209, 105), since with one period per application Eqs. 6.2 and 6.3 give the same order; MCPF gives 314, 158 and 80, the values the thesis prints for LSTF with PF 10 and 20 swapped |
| 6.7 | No cell. Synthetic-D: 3906.25 Hz for every criterion and PF; the absolute tolerance of 5000 Hz stops the bisection on (0, 3906.25] (with `relative_tolerance` 0.02 the search ends at 104.9 Hz). DCT-Verify: 78,125 Hz for every criterion and PF. The thesis prints 793 to 1707 "MHz" |

The CAR rows of Tables 6.5 and 6.6 and the CAR frequencies of Table 6.7 come from `make car`.

## Outputs (`build/results`)

| File | Content |
|---|---|
| `tab65.tex/.csv`, `tab66.tex/.csv` | Thesis value, value of the run, agreement and number of discarded packets per cell |
| `tab67.tex/.csv` | Value printed in the thesis, frequency of the run in Hz, lowest feasible frequency among the attempts and number of attempts |
| `metrics.json` | All values; `make check` compares it with `reference.json` |
