# Zero-load latency of the Hermes NoC

`tb_zll.vhd` injects one packet (header, size flit, `p` payload flits) at the LOCAL port of a source router of an idle mesh built from `pkt-sim/hw/router/hermes` and measures, at the LOCAL port of the destination (sink that always accepts), the cycles from the acceptance of the header at the source to the consumption of the last flit. The sink checks the order and the content of every flit. `m` is the number of hops (Manhattan distance with XY routing).

## Commands

| Command | Effect | Needs |
|---|---|---|
| `make` or `make zll` | 8x3 mesh: from nodes (0,0) and (7,2) to every node; 2x2 mesh: from every node to every node; `p` in {1, 4, 16, 64}; fails if a point differs from the model | GHDL (tested with GHDL 4.1.0, mcode backend), about 30 s |
| `./run.sh <out>` | One sweep; `XR`, `YR`, `SRCS`, `PS` and `GHDL` select the mesh, the sources, the payload sizes and the simulator | GHDL |

## Outputs (`build/<mesh>/`)

| File | Content |
|---|---|
| `zll.csv` | `src_x,src_y,dst_x,dst_y,m,p,latency,model,match`, one line per packet; `model` = 6(m+1) + p + 1 |
| `zll_table.txt` | Latency per (`m`, `p`) and the number of routes measured |
| `zll_summary.txt` | Table and the number of points that satisfy the model |

## Result

Every measured point satisfies

L0 = 6(m + 1) + p + 1 cycles

(8x3: 192 of 192 points, m = 0 to 9; 2x2: 64 of 64 points, m = 0 to 2). Each of the m + 1 routers on the path (source and destination included) adds 6 cycles to the header; the size flit and the payload follow at one flit per cycle.
