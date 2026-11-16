# CAR-full: CAR (apps/shi-2010: 33 tasks, 38 flows, periods 0.04 to 1 s, two
# cycles) on the time scale of CAR-V, with the general phase model of the
# analysis flow (rttools/bench_t/multirate.py), and its UCX-OS application for
# the 4x4 manycore (rttools.ucxgen, time-triggered tasks).
#
#   make          app + run + check + ucx-check + analyze + check-run of run CF + check-cf2, cf4, cf5, cf6 (seconds)
#   make app      compare apps/car-full/car-full.{csv,map} with the generator (fails when they differ)
#   make generate write apps/car-full/car-full.{csv,map} from apps/shi-2010 and config.json
#   make run      CPU test (ORT/BENCH over the hyperperiod), frequency search, network at the clock,
#                 data age of every chain, packets and heap per PE for every candidate of config.json;
#                 outputs in $(BUILD)
#   make check    compare $(BUILD)/metrics.json with reference.json
#   make ucx      write pkt-sim/software/ucx-os/app/$(NAME).{c,json,sim} (rttools.ucxgen) and
#                 $(NAME)_tt.h (rttools.ucxgen tt at F_CLK: injection instants of the time-triggered injection)
#   make ucx-check  the stored $(NAME).{c,json,sim} and $(NAME)_tt.h match a new generation; heap per PE
#                 against HEAP
#   make build    build $(NAME) in $(BUILD)/pkt-sim (riscv64-elf toolchain); heap per PE against the image
#   make sim      RTL simulation at F_CLK (Questa and riscv64-elf; ENV_SETUP as in exp23):
#                 F_CLK=$(F_CLK) RELEASE_NS=$(PHASE_NS) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) $(NAME) 4x4
#   make analyze  analysis of $(LOG) against the general phase model (rttools.paper.rtlapp, which calls
#                 rttools.paper.rtlmr): jobs, progress, jobs per phase, reads, CPU per phase, data age per
#                 chain, packets; into $(OUTDIR)
#   make check-run  compare $(OUTDIR)/metrics.json with $(REF)
#   make check-cf2  analyze + check-run of the stored run CF2 (logs/CF2.*, reference_CF2.json) into
#                 $(BUILD)/results_CF2
#   make check-cf4  analyze + check-run of the stored run CF4 (logs/CF4.*, reference_CF4.json) into
#                 $(BUILD)/results_CF4
#   make check-cf5  analyze + check-run of the stored run CF5 (logs/CF5.*, reference_CF5.json) into
#                 $(BUILD)/results_CF5
#   make check-cf6  analyze + check-run of the stored run CF6 (logs/CF6.*, reference_CF6.json) into
#                 $(BUILD)/results_CF6
#
# LOG, REF and OUTDIR default to run CF (logs/CF.*, reference_CF.json): car_full of tag
# r11-multirate-rc1 (48bb43a) at 432 MHz, 64 ms. In run CF five PEs (0-1, 0-2, 1-2, 2-0, 3-0) stop
# (kernel halt or a task that does not finish its job): an interrupt inside the return of another one
# (handlers that enable interrupts before they return, _isr returns through a5, which it does not save;
# pkt-sim/tests/rtl/tb_cpu_irq.vhd); the kernel of this tree leaves interrupts disabled in every handler
# (the image of CF is the kernel with -DUCX_ISR_NESTING; RUN_INFO without the line isr). In run CF2 (tag
# r11-rc3) six tasks (TPMS, VIBS, DIRC, BFE3, FDF1, OBMG; the same as in CF) loop on the jalr of the
# return of _isr: yield() resumes a task that the tick preempted, through that return with interrupts
# disabled, and an interrupt pending then comes before the jump (logs/CF2.*, reference_CF2.json: crt0.s
# up to r11-rc3, clock.crt0 = plain). Run CF3 (tag r11-rc4) has the return test of _isr in car_full only
# (crt0 guard); the crt0.s of this tree has it in every image, with the read back of IRQ_STATUS in
# _interrupt_set(0) (crt0 guard_readback; pkt-sim/software/ucx-os/Makefile). Run CF4 (tag r11-rc5,
# logs/CF4.*, reference_CF4.json: crt0 guard_readback, the same clock, phase and duration) completes
# its 2,945 jobs: no task stops, no job begun twice in a phase, no read older than the model, no phase
# above the busy time of the model, 34 of 34 chains measured and none above its bound. Run CF5 (tag
# r11-rc7, logs/CF5.*, reference_CF5.json: time-triggered injection, t(v) = max(CSV, static), 478.336 MHz,
# 64 ms) meets every check of the injection but 5 of its 2,945 jobs end after F of the model: jobs 3, 13,
# 23, 33 and 43 of USOS (PE 0-1, phase 10 of each hyperperiod), by up to 106,282 cycles. The first job of
# OBDB ends before the tick of phase 11, USOS starts in the rest of phase 10, and the round robin gives
# that tick to OBMG (the task after USOS) for a whole phase, while the model, where OBDB runs to the
# tick, dispatches USOS there. The kernel of tag r11-rc8 starts the search of the scheduler at each tick
# at the position of the model (TT_TICK of app/car_full_tt.h, rttools/bench/ucx.py). Run CF6 (tag r11-rc9,
# logs/CF6.*, reference_CF6.json: the deadline model tick, 526.08 MHz, 64 ms) ends all 2,945 jobs at or before
# F of the model, keeps 34 of 34 chains within their bound and meets every check of the injection. After `make sim`:
#   make analyze LOG=$(BUILD)/sim/events.txt OUTDIR=$(BUILD)/results_sim
#
# F_CLK: the clock of the flow with the model of the time-triggered injection, t(v) = max(CSV,
# static) and the deadline of each packet at the release tick of its reader (experiments/tt, run CF6
# of tag r11-rc9): f_NoC 526.056 MHz (f_CPU 477.952 MHz), on the grid of 64 kHz of the phase of
# 0.25 ms, 526.08 MHz, a phase of 131,520 cycles (a multiple of the 16-cycle step of TIMER1; run CF5 of
# tag r11-rc7 ran at 478.336 MHz). The runs CF to CF4
# ran at 432 MHz, f_CPU of the chosen candidate with the costs of the CSV (reference.json
# chosen.cpu.f_cpu_hz).
# SIM_NS: first release at 3 ms + the largest data age (36.0 ms at 432 MHz, chain POSI-OBMG-OBDB-NAVC-DIRC)
# + two hyperperiods (25 ms) = 64 ms; at F_CLK the bound of that chain is 28.5 ms.

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
APPS    := $(abspath ../../apps)
ARCH    := $(abspath ../../arch/hermes-4x4.gml)
BUILD   ?= build
# network-interface model of the link schedule (RTTOOLS_NI,
# orca-rt-tools/rttools/modules/routing/router.py): off, the model of the
# stored references (runs up to tag r11-rc5); the default of rttools (tt)
# is the model of experiments/tt
NI      ?= off
RUN      = RTTOOLS_NI=$(NI) PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.carfull
GEN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.ucxgen
APP_DIR := ../../pkt-sim/software/ucx-os/app
NAME    ?= car_full
CSV     ?= ../../apps/car-full/car-full.csv
MAP     ?= ../../apps/car-full/car-full-ONTO-hermes4x4.map
MESH    ?= 4x4
# _heap_size of the image of car_full built with riscv64-unknown-elf-gcc 13.2, crt0.s of this tree,
# time-triggered injection (INJECTION=tt; 48168 with INJECTION=finish, 48216 for the image of run
# CF3, crt0 guard; 44720 for the image of riscv64-elf-gcc 12.2.0); make build reads the value of the
# toolchain in use
HEAP    ?= 44624
IN_FLIGHT ?= 2
F_CLK   ?= 526080000
# t(v) = max(CSV, static t(v) of the image, experiments/wcet costs/tt) in the link schedule of car_full_tt.h
TT_COSTS ?= ../wcet/costs/tt/car_full.json
PHASE_NS ?= 250000
SIM_NS  ?= 64000000
LOG     ?= logs/CF.events.txt
REF     ?= reference_CF.json
OUTDIR  ?= $(BUILD)/results_CF

.PHONY: all app generate run check ucx ucx-check build sim analyze check-run check-cf2 check-cf4 check-cf5 check-cf6 clean

all: app run check ucx-check analyze check-run check-cf2 check-cf4 check-cf5 check-cf6

app:
	$(RUN) generate --config config.json --apps $(APPS) --check

generate:
	$(RUN) generate --config config.json --apps $(APPS)

run:
	$(RUN) run --config config.json --apps $(APPS) --arch $(ARCH) --out $(BUILD)

check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/metrics.json reference.json

ucx:
	$(GEN) generate $(CSV) $(MAP) --name $(NAME) --mesh $(MESH) --out $(APP_DIR)
	$(GEN) tt $(CSV) $(MAP) --arch $(ARCH) --name $(NAME) --clock $(F_CLK) --costs $(TT_COSTS) --out $(APP_DIR)

ucx-check:
	$(GEN) check $(CSV) $(MAP) --name $(NAME) --mesh $(MESH) --out $(APP_DIR)
	$(GEN) tt-check $(CSV) $(MAP) --arch $(ARCH) --name $(NAME) --clock $(F_CLK) --costs $(TT_COSTS) --out $(APP_DIR)
	$(GEN) memory $(APP_DIR)/$(NAME).json --heap $(HEAP) --in-flight $(IN_FLIGHT)

build:
	rm -rf $(BUILD)/pkt-sim
	mkdir -p $(BUILD)
	cp -a ../../pkt-sim $(BUILD)/pkt-sim
	cd $(BUILD)/pkt-sim/software/ucx-os && $(MAKE) -s ARCH=riscv/hf-riscv-e incl && $(MAKE) -s $(NAME)
	$(GEN) memory $(APP_DIR)/$(NAME).json --image-map $(BUILD)/pkt-sim/software/ucx-os/build/target/image.map \
		--in-flight $(IN_FLIGHT) --json $(BUILD)/memory.json

sim:
	F_CLK=$(F_CLK) RELEASE_NS=$(PHASE_NS) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) $(NAME) $(MESH)

analyze:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.rtlapp analyze $(LOG) --manifest $(APP_DIR)/$(NAME).json \
		--csv $(CSV) --map $(MAP) --arch $(ARCH) --out $(OUTDIR)

check-run:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(OUTDIR)/metrics.json $(REF)

check-cf2:
	$(MAKE) --no-print-directory analyze check-run LOG=logs/CF2.events.txt REF=reference_CF2.json \
		OUTDIR=$(BUILD)/results_CF2

check-cf4:
	$(MAKE) --no-print-directory analyze check-run LOG=logs/CF4.events.txt REF=reference_CF4.json \
		OUTDIR=$(BUILD)/results_CF4

# CF5 ran with a table that the generator built before the release guard of the link schedule
# (rttools/modules/routing/router.py, release_guard), which places flow 7 later at its clock
check-cf5:
	RTTOOLS_RELEASE_GUARD=off $(MAKE) --no-print-directory analyze check-run LOG=logs/CF5.events.txt \
		REF=reference_CF5.json OUTDIR=$(BUILD)/results_CF5

check-cf6:
	$(MAKE) --no-print-directory analyze check-run LOG=logs/CF6.events.txt REF=reference_CF6.json \
		OUTDIR=$(BUILD)/results_CF6

clean:
	rm -rf $(BUILD)
