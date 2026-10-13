# Zero-load latency of the Hermes NoC

`tb_zll.vhd` injects one packet (header, size flit, `p` payload flits) at the LOCAL port of a source router of an idle mesh built from `pkt-sim/hw/router/hermes` and measures, at the LOCAL port of the destination (sink that always accepts), the cycles from the acceptance of the header at the source to the consumption of the last flit. The sink checks the order and the content of every flit. `m` is the number of hops (Manhattan distance with XY routing).

## Commands

| Command | Effect | Needs |
|---|---|---|
| `make` or `make zll` | 8x3 mesh: from nodes (0,0) and (7,2) to every node; 2x2 mesh: from every node to every node; `p` in {1, 4, 16, 64}; fails if a point differs from the model | GHDL (tested with GHDL 4.1.0, mcode backend), about 30 s |
| `./run.sh <out>` | One sweep; `XR`, `YR`, `SRCS`, `PS` and `GHDL` select the mesh, the sources, the payload sizes and the simulator | GHDL |
| `make contention` | Header wait at one router (`tb_cont.vhd`, `contention.py`): 2624 runs, check against `reference_contention.json` | GHDL and Python 3 (standard library), 2 to 6 min on 2 vCPU (`--jobs` = number of CPUs) |
| `make check` | `zll` and `contention` | GHDL and Python 3 |

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

## Header wait at one router (`make contention`)

`tb_cont.vhd` builds a 3x3 mesh and sends five packets whose XY routes cross router 4 (x = 1, y = 1): 3→5 and 5→3 (horizontal), 1→7 and 7→1 (vertical), each with m = 2, and 4→4 (LOCAL to LOCAL, m = 0). Each packet enters router 4 by its own input port and leaves by its own output port, so the packets share no link and compete only for the SwitchControl of router 4. `contention.py` runs every nonempty subset of the five packets for p in {1, 4, 16, 64} with fixed offsets (124 runs) and 2500 runs with a random subset, random injection offsets (0 to 12 cycles, 0 to 18 for the LOCAL packet) and a random p (seed 1). The wait of a header is the latency minus L0.

| File (`build/contention/`) | Content |
|---|---|
| `contention.csv` | `p,en,n_active,offs,k,m,latency,l0,extra,bad`, one line per packet; `extra` = latency − L0 |
| `contention_summary.txt` | Largest wait per number n of headers that cross router 4 |
| `metrics.json` | The numbers that the target compares with `reference_contention.json` |

| Headers at router 4 (n) | Samples | Largest wait (cycles) |
|---|---|---|
| 1 | 432 | 0 |
| 2 | 1644 | 5 |
| 3 | 2619 | 10 |
| 4 | 1644 | 15 |
| 5 | 430 | 20 |

6769 packets arrive with 0 flits in error. The largest wait is 5 (n − 1) cycles: the SwitchControl routes one header at a time in five states (S1, S2, S3, one of S4/S5/S6, S7; `pkt-sim/hw/router/hermes/Hermes_switchcontrol.vhd:126-141`) and selects the next input port in round-robin order from the last port served (`:44-78`). A router has five input ports, so a header waits for at most the four headers of the other ports, 20 cycles per router. `rttools/modules/routing/router.py` (`HEADER_WAIT_CYCLES`) uses this value for the occupancy o_i = L0 + 20 (m + 1), the default of rttools; `RTTOOLS_HEADER_WAIT=off` or `--header-wait off` (`rttools.paper.frequency`) selects o_i = L0.
