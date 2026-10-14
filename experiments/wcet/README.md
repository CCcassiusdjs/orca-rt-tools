# Static task costs t(v)

The analysis flow takes the cost t(v) of each task as an input (Section 6.1): the demand c(v) plus the kernel work of v on its PE. This pipeline derives t(v) from the program image with a static WCET analysis (`orca-rt-tools/rttools/wcet`) and compares it with the stored RTL runs.

| Command | Output |
|---|---|
| `make PYTHON=<python>` | `build/metrics.json`, `values.tex` (`\ExpWcet...`), `tasks.csv`, `clusters.csv`, `bodies.csv`, `<app>/costs.json` and `costs.csv` per application, `frequency/` (flow of E with the static costs) and `frequency_measured/` (with the costs of the CSV); check against `reference.json` and of the generated `wcet_e.{c,json,sim}` |
| `make images` | `images/car_v.{elf,lst}` and `images/wcet_e.{elf,lst}` (riscv64-elf toolchain; `ENV_SETUP` as in exp23) |
| `make bodies trace` | `pkt-sim/tests/rtl/wcet_bodies.{elf,lst,hex}` (`CC_BODIES`, default riscv64-elf-gcc) and the GHDL trace `logs/bodies.trace.txt` |
| `make sim F_CLK=500000000 ENV_SETUP="..."` | RTL simulation of application WCET-E (`build/sim`, 10 ms) |
| `make run-analyze check-run` | static costs of the image of a run against its log (default the stored run W1: `logs/W1.events.txt`, `logs/W1.image.elf`) and the phase-model analysis of `rttools.paper.rtlapp` with these costs, into `build/run_W1`, checked against `reference_W1.json` (`make check` runs both); after `make sim`, `LOG=build/sim/events.txt REF=<reference>` |
| `make app`, `make csv` | `wcet_e.{c,json,sim}` from `apps/wcet-e`; t(v) of `build/WCET-E/costs.json` into the Capacity column of `apps/wcet-e/wcet-e.csv` |

## Analysis

| Step | Module | Content |
|---|---|---|
| Image | `rttools/wcet/image.py` | ELF (pyelftools) or objdump listing; `.wcet_bounds` of `WCET_LOOP_BOUND` and `WCET_LOOP_TOTAL` (`pkt-sim/software/ucx-os/include/lib/wcet.h`) |
| Decoder | `decode.py` | RV32I/RV32E; the core has no M and no C extension |
| CFG | `cfg.py` | basic blocks, calls, jump tables of an ELF image, dominators, natural loops |
| Values | `value.py`, `loopbound.py` | constant propagation (call contexts, branch outcomes, read-only data), counted and shift loops, bound expressions of the annotations |
| Timing | `timing.py` | ALU 1, load and store 3, taken branch and jump 3, branch not taken 1 cycle (`pkt-sim/tests/rtl/tb_cpu_cycles.vhd`); 3 cycles per interrupt entry |
| Path | `ipet.py` | IPET (Li and Malik, 1995) with `scipy.optimize.milp` |
| t(v) | `ucx.py` | job of the task (from the return of `ucx_task_yield` to its next call: body, send, receive), dispatch, send and receive interrupt handlers per edge, tick handler, release handler (source tasks; every task of an image with the release by tick, `lib/tick_release.c`, whose release interrupt counts the phases on every PE and whose tick handler calls the tick hook) |
| Flow facts | `pkt-sim/software/ucx-os/wcet/ucx-os.json`, `ucxgen.json`, `annotations/*.json` | loop bounds of the kernel, targets of the indirect calls of the interrupt handlers, calls on error paths, params `tcb`, `heap_blocks`, `ddma_wait` |

## Inputs

| Application | Image | Run |
|---|---|---|
| E (`weird_a.c`) | `../exp23/logs/H.image.lst` (riscv64-elf-gcc 12.2.0; the targets of the jump table of `irq0_handler` in `annotations/H.image.json`) | `../exp23/logs/H.events.txt` (434.912 MHz) |
| CAR-V (`car_v.c`) | `images/car_v.elf` (riscv64-unknown-elf-gcc 13.2.0, `images/BUILD.txt`) | `../car-v-rtl/logs/CV2.events.txt` (gcc 12.2.0, 380 MHz) |
| WCET-E (`wcet_e.c`, `apps/wcet-e`) | `images/wcet_e.elf`; for run W1, `logs/W1.image.elf` (riscv64-elf-gcc 12.2.0) | `logs/W1.events.txt` (tag r11-wcet-rc1, git archive, Questa 2025.3, 10 ms at 500 MHz; `W1.RUN_INFO`, `W1.time.txt`) |
| Bodies of WCET-E (`pkt-sim/tests/rtl/wcet_bodies.c`) | `pkt-sim/tests/rtl/wcet_bodies.elf` | `logs/bodies.trace.txt` (GHDL, `tb_cpu_trace.vhd`) |

`images/tick` holds the images of `weird_a` (release by tick), `weird_a_data` (the code of runs A to H) and `car_v` (release by tick) built with gcc 13.2 (`images/tick/BUILD.txt`), for the static t(v) of the release by tick (`tests/test_tick_release.py`); the stored runs and `reference.json` use the images of the data-driven release.

Application WCET-E keeps the task graph, payloads, release period and mapping of E; its tasks sort, search or loop over a count read from the data (`apps/wcet-e/wcet-e.bodies.json`, `rttools.ucxgen --bodies`). The source task fills its data from the iteration number, and every other task combines the payload of its packets into its data, so the paths change from one iteration to the next.
