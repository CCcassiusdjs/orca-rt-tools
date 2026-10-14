# CAR-full: CAR (apps/shi-2010: 33 tasks, 38 flows, periods 0.04 to 1 s, two
# cycles) on the time scale of CAR-V, with the general phase model of the
# analysis flow (rttools/bench_t/multirate.py), and its UCX-OS application for
# the 4x4 manycore (rttools.ucxgen, time-triggered tasks).
#
#   make          app + run + check + ucx-check (seconds)
#   make app      compare apps/car-full/car-full.{csv,map} with the generator (fails when they differ)
#   make generate write apps/car-full/car-full.{csv,map} from apps/shi-2010 and config.json
#   make run      CPU test (ORT/BENCH over the hyperperiod), frequency search, network at the clock,
#                 data age of every chain, packets and heap per PE for every candidate of config.json;
#                 outputs in $(BUILD)
#   make check    compare $(BUILD)/metrics.json with reference.json
#   make ucx      write pkt-sim/software/ucx-os/app/$(NAME).{c,json,sim} (rttools.ucxgen)
#   make ucx-check  the stored $(NAME).{c,json,sim} match a new generation; heap per PE against HEAP
#   make build    build $(NAME) in $(BUILD)/pkt-sim (riscv64-elf toolchain); heap per PE against the image
#   make sim      RTL simulation at F_CLK (Questa and riscv64-elf; ENV_SETUP as in exp23):
#                 F_CLK=$(F_CLK) RELEASE_NS=$(PHASE_NS) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) $(NAME) 4x4
#   make analyze  analysis of $(LOG) against the general phase model (rttools.paper.rtlapp, which calls
#                 rttools.paper.rtlmr): jobs, reads, CPU per phase, data age per chain, packets; into $(OUTDIR)
#
# F_CLK: f_CPU of the chosen candidate (432 MHz, reference.json chosen.cpu.f_cpu_hz); the phase of
# 0.25 ms is then 108,000 cycles, a multiple of the 16-cycle step of TIMER1.
# SIM_NS: first release at 3 ms + the largest data age at F_CLK (36.0 ms, chain POSI-OBMG-OBDB-NAVC-DIRC)
# + two hyperperiods (25 ms) = 64 ms.

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
APPS    := $(abspath ../../apps)
ARCH    := $(abspath ../../arch/hermes-4x4.gml)
BUILD   ?= build
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.carfull
GEN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.ucxgen
APP_DIR := ../../pkt-sim/software/ucx-os/app
NAME    ?= car_full
CSV     ?= ../../apps/car-full/car-full.csv
MAP     ?= ../../apps/car-full/car-full-ONTO-hermes4x4.map
MESH    ?= 4x4
# _heap_size of the image of car_full built with riscv64-unknown-elf-gcc 13.2
# (make build reads the value of the toolchain in use)
HEAP    ?= 48280
IN_FLIGHT ?= 2
F_CLK   ?= 432000000
PHASE_NS ?= 250000
SIM_NS  ?= 64000000
LOG     ?= $(BUILD)/sim/events.txt
OUTDIR  ?= $(BUILD)/results_sim

.PHONY: all app generate run check ucx ucx-check build sim analyze clean

all: app run check ucx-check

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

ucx-check:
	$(GEN) check $(CSV) $(MAP) --name $(NAME) --mesh $(MESH) --out $(APP_DIR)
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
		--csv $(CSV) --map $(MAP) --out $(OUTDIR)

clean:
	rm -rf $(BUILD)
