# Table 7.1 (ORT/GCM and ORT/GDE)

| Command | Effect |
|---|---|
| `make` | Graphs with \|V\| = 20 to 100 (`graphs/`): metrics of the input, collapse to N clusters with MIN-COMM and MAX-PROC, metrics of the output, comparison with Table 7.1 and check against `reference.json` (seconds) |
| `make graphs` | Unpacks the 17 graphs of the table (`graphs/10_<|V|>.txt` and `graphs/10_200-900.tar.xz`) into `build/graphs` and checks their SHA-256 (`graphs/SHA256SUMS`) |
| `make full` | The 17 graphs (about 20 minutes; \|V\| = 900 alone takes 7 to 9 minutes) and check against `reference_full.json` |
| `make car` | CAR (`apps/shi-2010/shi-2010.txt`) on 16 clusters: reference mapping of Shi et al. (`shi2010-ONTO-hermes4x4.map`) and the four criteria; application E (`apps/synthetic-app-e/synthetic-app-e.txt`) on 4 clusters with the four criteria and the criterion with the lowest M2; check against `reference_car.json` (`car.json` holds the inputs) |
| `make n16` | \|V\| = 20 to 100 with N = 16 |

The 17 graphs come from `tp-tools/apps/var-nnodes/10_<|V|>.txt` of commit 4e43483 (commit aa7b97d removed the directory). The generator of that commit draws the values and the endpoints without a seed, so it cannot regenerate the files: `graphs/` keeps the nine graphs with \|V\| <= 100 as text (262 KB) and the eight graphs with \|V\| = 200 to 900 in `graphs/10_200-900.tar.xz` (8.6 MB; 22.8 MB unpacked). `python -m rttools.paper.graphs pack` writes the archive from the text files (fixed member order, owner and time).

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

## Outputs (`build/car`)

| File | Content |
|---|---|
| `car/metrics.json`, `car.csv`, `appe.csv` | Inter-cluster edges, NoC volume, M1, M2, M3, largest load and loads above the capacity of each clustering of CAR; M2, clusters and NoC volume of each criterion for application E |
| `car/tab-car-rows.tex` | Rows of the CAR table (Reference, MAX-PROC, MIN-COMM) |
