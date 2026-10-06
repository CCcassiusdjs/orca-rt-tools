# ORCA RT-Tools

Welcome to the ORCA RT-Tools repository. In this repository you will find the following assets:

- Minizinc constraint models for optimizing real-time traffic in networks-on-chip
- A single data model, used for all applications and noc architectures
- A python program suite that automates the optmization process, which we call "rt_tools"
- An RTL simulator written for the Hermes NoC

## Requirements and Installation

We've tested RT_TOOLS in CentOS 7, Ubuntu 20.4, and Debian 11 packages, although it may work out-of-the-box in most linux distributions. The following packages are required for RT_TOOLS to run in a linux environment. 

- python3 (3.8+)
- python3-devel
- graphviz
- graphviz-devel

RT_TOOLS depends on some python packages, enlisted below. 

- networkx==2.7.1
- pyparsing==2.4.7
- pygraphviz==1.9
- matplotlib==3.5.1

In addition to the aforementioned packages, you must install Minizinc, following the instruction provided in their own website. Please visit https://www.minizinc.org/ for more information.

For the RTL simulator, you must have ModelSim (or Questa) installed in your system. Please note that the simulation may work with other simulation tools with minimal effort, although we have not tested it yet. 

## How to use it 

Before using rt_tools, you must provide three models: application, architecture, and mapping. See the provided example models to learn the syntax of each model. Once you've done modeling, you can use rt_tools to generate the input model for minizinc, using the command `python3 __main__.py pkt <A> <B> <C>` replacing A, B and C by your application, architecture, and mapping model files. Be careful to provide files in the right sequence.

The output must show a couple of debugging information, followed by a section named `OCCUPANCY MATRICES (MINIZINC)`. The content of this section must be saved into a file (minizinc uses \*.dnz extension). Run minizinc passing both the \*.dnz file along with the provided \*.mnz file, and its done! You command line should look like `minizinc --solver Gecode <dnz> <mnz> > output.txt`.

## ...in a nutshell
1) `python3 rt_tools/__main__.py pkt applications/app.gml mappings/map.gml architectures/arch.gml > output.dnz`
2) `minizinc minizinc/DM/dmxxx.dmz output.dnz`

## Terminal user interface

`python -m rttools.tui` (run from `orca-rt-tools/`) opens a terminal user interface with four tabs. It runs over SSH on the simulation server; with `pip install textual-dev`, `textual serve "python -m rttools.tui"` serves the same interface to a web browser.

| Tab | Content |
|---|---|
| Trace | Gantt of RTL logs (ModelSim/Questa transcript or extracted events), `rttools.bench` output, KProfiler `.sch` and CSV. Cursor and mark with the interval in raw units, cycles, ns, µs and ms; raw unit presets for the RTL (100 ps for commit 4c299fc, 1 ns); time per task and utilization per lane; bursts between passes through IDLE; latency of the packets (`->`/`<-` TAG lines); comparison of two runs with a time scale; export to SVG, PNG and CSV |
| Bench | Task set editor; ORT/BENCH simulation (RM, DM, EDF, RR) with configurable quantum; utilization, Liu-Layland, hyperbolic, response time (also with release jitter equal to the quantum) and EDF processor demand tests; observed response times |
| Network | Application, mapping and NoC (or an example of `apps/`); flows at a frequency (hops, flits, network time); frequency search in a child process with live progress and cancel; link schedule, link utilization, packets with slack, independent validation of the schedule |
| Graphs | Task graph in ORCA format: GDE metrics, GCPA cost and critical path, layers, GCM clustering (MAX_PROC with 4 clusters on `apps/sample-graph-b` gives ABDF, C, EHI and GJ) |

The Help tab (F1) lists the keys. Commands without the interface, for batch use:

| Command | Output |
|---|---|
| `python -m rttools.tui stats <trace> [--unit 100ps] [--display cycles]` | Lane metrics, bursts and packet latency as Markdown tables |
| `python -m rttools.tui export <trace> <out.svg\|out.png\|out.csv> [--display ms]` | Gantt or CSV |
| `python -m rttools.tui compare <A> <B> [--scale-b 10]` | Comparison per lane; exit code 0 when identical |

## Tests

The repository includes regression tests for the Python tools, the UCX-OS NoC driver and the RTL of the DDMA, the Hermes crossbar, the TCD and the manycore PE.

| Part | Location | Tools |
|---|---|---|
| Python tools (`rttools`, bench, gff, rgg, log2gannt, appparser, TUI) | `orca-rt-tools/tests` | Python 3.10+, `orca-rt-tools/requirements.txt`, pytest |
| UCX-OS driver (`lib/noc.c`, `device/ddma.c`) on the host | `pkt-sim/software/ucx-os/tests/host` | gcc with AddressSanitizer and UBSan |
| RTL (DDMA, Hermes crossbar, TCD, manycore PE) | `pkt-sim/tests/rtl` | Verilator 5, GHDL 4 |

Run all tests:

```
pip install -r orca-rt-tools/requirements.txt pytest
cd orca-rt-tools && python -m pytest -q
```

The RTL tests skip when Verilator or GHDL is missing. `pkt-sim/software/ucx-os/tests/host/run.sh` and `pkt-sim/tests/rtl/run.sh` run the C and RTL tests without pytest.

## Command-line options added by the fixes

| Tool | Option |
|---|---|
| `python -m rttools <app> <map> <arch> [<freq>] [<pruning factor>] [<fail threshold>] [<optimize True\|False>]` | All optional arguments work; the exit code is 1 on errors |
| `python -m rttools.bench <file> <mode> <RR\|RM\|DM\|EDF> [<horizon>]` | Scheduling policy and simulation horizon. The ORCA graph format accepts `label wcet [period [deadline]]` |
| `python -m rttools.rgg <a> <b> <c> <x> <y> <z> <ofile> [<seed>]` | Seed for reproducible graphs |
| `python -m rttools.log2gannt <log> [--map <json>] [--out <png>] [--units-per-ms <n>] [--swap-xy]` | Task map, output file, time unit, and X-Y order of the log |

## Time unit of the RTL logs

`pkt-sim/manycore_modelsim/manycore_pe.sv` declares `` `timescale 1ns/100ps ``, so the simulation logs (`scheduled`, `TAG`, `TRIGGER`) report time in ns. Commit 4c299fc ran without this directive; in that configuration the simulator assigns 100 ps to the PE, and the logs of that commit report time in units of 100 ps (`log2gannt --units-per-ms 10000000`). Logs produced before the fix of `addr_x()`/`addr_y()` print X and Y swapped (`log2gannt --swap-xy` reads logs of the fixed RTL with the default map).
