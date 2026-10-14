# Static task costs t(v) (rttools.wcet) against the stored RTL runs, and
# application WCET-E (application E with input-dependent bodies).
#
#   make analyze   static analysis of the stored images (E: listing of run H; CAR-V and WCET-E:
#                  images/*.elf; bodies: pkt-sim/tests/rtl/wcet_bodies.elf), comparison with the
#                  stored runs H and CV2 and the GHDL trace logs/bodies.trace.txt, flow of E with the
#                  static costs (rttools.paper.frequency --costs); into $(BUILD)
#   make check     metrics against reference.json; the stored wcet_e.{c,json,sim} match a new
#                  generation (default target: analyze check)
#   make app       write pkt-sim/software/ucx-os/app/wcet_e.{c,json,sim} from apps/wcet-e
#   make csv       write t(v) of $(BUILD)/WCET-E/costs.json into the Capacity column of
#                  apps/wcet-e/wcet-e.csv (after analyze), then `make app`
#   make images    build car_v (F_CLK 380 MHz, the clock of run CV2) and wcet_e with
#                  ../exp23/build_sw.sh (riscv64-elf toolchain; ENV_SETUP) into images/
#   make bodies    build pkt-sim/tests/rtl/wcet_bodies.{elf,lst,hex} (CC, default riscv64-elf-gcc)
#   make trace     GHDL run of tb_cpu_trace.vhd on wcet_bodies.hex into logs/bodies.trace.txt
#   make sim       RTL simulation of wcet_e (Questa and riscv64-elf; ENV_SETUP as in exp23) at F_CLK:
#                  F_CLK=$(F_CLK) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) wcet_e 2x2
#   make run-analyze  static costs of the image of that run against its log ($(LOG), default
#                  $(BUILD)/sim/events.txt): CPU per PE and per task (rttools.paper.wcet run-log)
#                  into $(BUILD)/run, and the phase-model analysis of rtlapp into $(BUILD)/run-rtlapp
#
# SIM_NS: release delay 3 ms + 14 releases of 0.5 ms (rtlapp cpu_windows takes windows of
# n(J) + 1 = 4 releases from the release of iteration 4) = 10 ms.

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
BUILD   ?= build
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.wcet
GEN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.ucxgen
APP_DIR := ../../pkt-sim/software/ucx-os/app
APPS    := ../../apps/wcet-e
CSV     := $(APPS)/wcet-e.csv
MAP     := $(APPS)/wcet-e-ONTO-hermes2x2.map
BODIES  := $(APPS)/wcet-e.bodies.json
NAME    := wcet_e
MESH    := 2x2
GENARGS  = $(CSV) $(MAP) --name $(NAME) --mesh $(MESH) --bodies $(BODIES) --out $(APP_DIR)
F_CLK   ?= 500000000
SIM_NS  ?= 10000000
LOG     ?= $(BUILD)/sim/events.txt
IMAGE   ?= $(dir $(LOG))pkt-sim/software/ucx-os/build/target/image.elf
CC_BODIES ?= riscv64-elf-gcc
RTL     := ../../pkt-sim/tests/rtl
UCX_IMG := pkt-sim/software/ucx-os/build/target

.PHONY: all analyze check app csv images bodies trace sim run-analyze clean

all: analyze check

analyze:
	$(RUN) analyze --config config.json --out $(BUILD)

check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/metrics.json reference.json
	$(GEN) check $(GENARGS)

app:
	$(GEN) generate $(GENARGS)

csv:
	$(RUN) set-csv $(BUILD)/WCET-E/costs.json $(CSV)

images:
	F_CLK=380000000 APP=car_v ../exp23/build_sw.sh $(BUILD)/img/car_v
	APP=wcet_e ../exp23/build_sw.sh $(BUILD)/img/wcet_e
	for a in car_v wcet_e; do cp $(BUILD)/img/$$a/$(UCX_IMG)/image.elf images/$$a.elf; \
		cp $(BUILD)/img/$$a/$(UCX_IMG)/image.lst images/$$a.lst; done
	{ cat $(BUILD)/img/car_v/gcc.txt; echo "car_v: F_CLK=380000000 APP=car_v experiments/exp23/build_sw.sh"; \
	  echo "wcet_e: APP=wcet_e experiments/exp23/build_sw.sh (F_CLK 500000000)"; } > images/BUILD.txt

bodies:
	CC=$(CC_BODIES) $(RTL)/build_wcet_bodies.sh

trace:
	OUT=$(abspath $(BUILD))/rtl sh $(RTL)/run.sh tb_cpu_trace > logs/bodies.trace.txt
	grep -q '^DONE' logs/bodies.trace.txt

sim:
	F_CLK=$(F_CLK) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) $(NAME) $(MESH)

run-analyze:
	$(RUN) run-log $(LOG) --spec specs/wcet_e.json --image $(IMAGE) --manifest $(APP_DIR)/$(NAME).json \
		--csv $(CSV) --map $(MAP) --out $(BUILD)/run
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.rtlapp analyze $(LOG) --manifest $(APP_DIR)/$(NAME).json \
		--csv $(CSV) --map $(MAP) --arch ../../arch/hermes-2x2.gml --out $(BUILD)/run-rtlapp

clean:
	rm -rf $(BUILD)
