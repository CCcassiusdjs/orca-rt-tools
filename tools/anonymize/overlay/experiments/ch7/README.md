# Contraction criteria on random graphs (ORT/GCM and ORT/GDE)

For each random graph `10_<|V|>.txt` (ORCA format, vertex and edge values in [2000; 20000]), the pipeline computes |E|, M1 (population standard deviation of the edge values), M2 (of the vertex values) and M3 (sum of vertex values divided by the sum of edge values), collapses the graph to N = 4 clusters with MIN-COMM and with MAX-PROC, and computes the same metrics on each result.

| Command | Effect |
|---|---|
| `make` | Graphs with \|V\| = 20 to 100 (`graphs/`), check against `reference.json` (seconds) |
| `make graphs full` | The 17 graphs (\|V\| = 20 to 900) into `build/graphs`, then the same pipeline and the check against `reference_full.json` (about 20 minutes on one core) |
| `make stats` | Summary over the graphs of `build/full` (after `make graphs full`): share of edges kept, NoC payload share, M1 and M2 ratios, M3, cluster sizes; check against `reference_stats.json` |
| `make car` | CAR (`apps/shi-2010/shi-2010.txt`) on 16 clusters: reference mapping (`shi2010-ONTO-hermes4x4.map`) and the four criteria; application E on 4 clusters with the four criteria and the criterion with the lowest M2; check against `reference_car.json` (seconds) |

The Makefile lists the other targets. `make check` prints `match` when every value of `metrics.json` equals the reference.

## Rounding

Input M1, M2 and M3 with 3 decimals (truncated for |V| = 20 to 700, rounded for |V| = 800 and 900); output M1 and M2 truncated to integers; output M3 rounded to 3 decimals.

## Outputs (`build/results`)

| File | Content |
|---|---|
| `tab71.tex`, `tab71.csv` | Metrics of the input graphs and of the graphs collapsed by MIN-COMM and MAX-PROC |
| `metrics.json` | Values of each graph and agreement of each cell with the reference values (`reference_rows` of `config.json`) |
