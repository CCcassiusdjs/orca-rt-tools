# Table 7.1 (ORT/GCM and ORT/GDE)

| Command | Effect |
|---|---|
| `make` | Graphs with \|V\| = 20 to 100 (`graphs/`): metrics of the input, collapse to N clusters with MIN-COMM and MAX-PROC, metrics of the output, comparison with Table 7.1 and check against `reference.json` (seconds) |
| `make graphs` | Extracts the 17 graphs of the table (`tp-tools/apps/var-nnodes/10_<|V|>.txt`, commit 4e43483) from the git history into `build/graphs` |
| `make full` | The 17 graphs (about 18 minutes; \|V\| = 900 alone takes 7 minutes) and check against `reference_full.json` |
| `make n16` | \|V\| = 20 to 100 with N = 16 |

`graphs/` keeps the nine smaller graphs of commit 4e43483; commit aa7b97d removed the directory from the repository.

## Result

| Item | Result |
|---|---|
| N = 4 | The 204 cells of the 17 rows agree (\|E\|, M1, M2, M3 of the input and of both outputs; `make full`, 18 minutes on one core) |
| N = 16 (value stated in the thesis, 4x4 mesh) | Row 1 gives \|E\| = 220 (MIN-COMM) and 222 (MAX-PROC); the table prints 55 and 180 |
| Value range of the graphs | [2000; 20000] in vertices and edges; the thesis states [200; 2000] |
| Rounding | Input M1, M2 and M3 with 3 decimals: rows 1 to 15 truncate, rows 16 and 17 round. Output M1 and M2 truncated to integers (the note of the table says "rounded up"); output M3 rounded to 3 decimals |

## Outputs (`build/results`)

| File | Content |
|---|---|
| `tab71.tex`, `tab71.csv` | Table in the layout of the thesis, with the values of the run |
| `metrics.json` | Values of each graph, thesis row and agreement per cell |
