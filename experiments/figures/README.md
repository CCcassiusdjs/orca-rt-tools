# Data of the tables and figures (contraction example and application E)

| Command | Effect |
|---|---|
| `make` | `contraction`, `exp23` and `check` (seconds) |
| `make contraction` | Contracts `GRAPH` (default `apps/sample-graph-a/sample_graph.txt`, 10 tasks, 11 edges) to `N` = 4 clusters with the four criteria of ORT/GCM (`GraphICC.collapse`) |
| `make exp23` | Reads the RTL log `LOG` (default `experiments/exp23/logs/F.events.txt`, run F) with the functions of `rttools.paper.exp23` and writes the Gantt of the first complete hyperperiod, the response of each iteration and the flow table |
| `make check` | Compares `build/*/metrics.json` with `reference_contraction.json` and `reference_exp23.json` |

`config.json` holds the constants of the flow table: packet header (12 bytes, `noc_packet_t`), flit width (4 bytes), router constants of $L_0 = 6(m+1) + p + 1$ and the phase of the deadline (the phase after the source phase).

## Outputs

| File | Content |
|---|---|
| `contraction/contraction.json`, `criteria.csv` | Largest cluster demand, M2 (population standard deviation of the cluster demands), payload between clusters, clusters and step of each contracted edge, for MIN-COMM, MAX-COMM, MIN-PROC, MAX-PROC |
| `contraction/tab-criteria-rows.tex` | Rows of the criteria table |
| `contraction/fig-contraction-body.tex` | TikZ panels (a) MIN-COMM and (b) MAX-PROC of the contraction figure |
| `exp23/metrics.json` | Every number below |
| `exp23/gantt.csv`, `fig-gantt-body.tex` | RTL bars (non-IDLE slices), ORT/BENCH estimate bars (`cpu_sequence`, one sequence per release phase), releases, deadline and two response brackets; busy time per iteration of each cluster (equal to `tab83.csv` of `experiments/exp23`) |
| `exp23/iterations.csv`, `fig-iterations-coords.tex` | Release instant of A and response of each iteration; maximum and its share of the deadline |
| `exp23/flows.csv`, `tab-flows-rows.tex` | Per flow: payload, hops $m$ (XY routing), flits $p$, $L_0$, latency min and max (packets paired per flow in send order), model release and deadline, send offsets and maximum arrival offset from the start of the phase of the send |

The CAR table, the choice of the criterion of application E, the Spiral Mapping of CAR (`python -m rttools.paper.figures spiral` on the output of `make car`) and the summary of the random graphs come from `experiments/ch7` (`make car`, `make graphs full stats`).
