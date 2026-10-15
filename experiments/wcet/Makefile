# Static task costs t(v) (rttools.wcet) against the stored RTL runs, and
# application WCET-E (application E with input-dependent bodies).
#
#   make analyze   static analysis of the stored images (E: listing of run H; CAR-V and WCET-E:
#                  images/*.elf; bodies: pkt-sim/tests/rtl/wcet_bodies.elf), comparison with the
#                  stored runs H and CV2 and the GHDL trace logs/bodies.trace.txt, flow of E with the
#                  static costs (rttools.paper.frequency --costs); into $(BUILD)
#   make check     metrics against reference.json; the stored wcet_e.{c,json,sim} match a new
#                  generation (default target: analyze check)
#   make app       write pkt-sim/software/ucx-os/app/wcet_e.{c,json,sim} from apps/wcet-e and wcet_e_tt.h
#                  (rttools.ucxgen tt at F_CLK: injection instants of the time-triggered injection)
#   make csv       write t(v) of $(BUILD)/WCET-E/costs.json into the Capacity column of
#                  apps/wcet-e/wcet-e.csv (after analyze), then `make app`
#   make images    build car_v (F_CLK 380 MHz, the clock of run CV2) and wcet_e with
#                  ../exp23/build_sw.sh (riscv64-elf toolchain; ENV_SETUP) into images/
#   make bodies    build pkt-sim/tests/rtl/wcet_bodies.{elf,lst,hex} (CC, default riscv64-elf-gcc)
#   make trace     GHDL run of tb_cpu_trace.vhd on wcet_bodies.hex into logs/bodies.trace.txt
#   make sim       RTL simulation of wcet_e (Questa and riscv64-elf; ENV_SETUP as in exp23) at F_CLK:
#                  F_CLK=$(F_CLK) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) wcet_e 2x2
#   make run-analyze  static costs of the image of a run against its log ($(LOG), default the stored
#                  run W1, logs/W1.events.txt with logs/W1.image.elf; after `make sim`,
#                  LOG=$(BUILD)/sim/events.txt and the image of build/sim): CPU per PE and per task,
#                  and the phase-model analysis of rtlapp with the static t(v) of that image
#                  (rttools.paper.wcet run-log) into $(OUTDIR)
#   make check-run compare $(OUTDIR)/metrics.json with $(REF) (default reference_W1.json)
#   make analyze-r11c  the analysis of `make analyze` on the runs of tag r11-rc3 (release by tick,
#                  kernel without nested interrupts; config_r11c.json): E on the image and the log
#                  of run TH (../exp23/logs/TH.*), CAR-V on run TCV (../car-v-rtl/logs/TCV.*),
#                  WCET-E on run W2 (logs/W2.*), flow of E with the static costs of the image of
#                  TH; into $(BUILD)/r11c (metrics.json, values.tex with the macro names of
#                  $(BUILD)/values.tex)
#   make check-r11c  $(BUILD)/r11c/metrics.json against reference_r11c.json
#   make analyze-r11e  the same analysis on the runs of tag r11-rc5 (crt0.s with the return test of
#                  _isr and the read back of _interrupt_set(0), crt0=guard_readback; config_r11e.json):
#                  E on run UH (../exp23/logs/UH.*), CAR-V on run UCV (../car-v-rtl/logs/UCV.*),
#                  WCET-E on run W3 (logs/W3.*), flow of E with the static costs of the image of UH;
#                  into $(BUILD)/r11e (metrics.json, values.tex with the macro names of $(BUILD)/values.tex)
#   make check-r11e  $(BUILD)/r11e/metrics.json against reference_r11e.json
#   make analyze-r11f  the same analysis on the runs of tag r11-rc7 (time-triggered injection; config_r11f.json):
#                  E on run VH (../exp23/logs/VH.*), CAR-V on run VCV (../car-v-rtl/logs/VCV.*), WCET-E on
#                  run W5 (logs/W5.*), flow of E with the static costs of the image of VH; into $(BUILD)/r11f
#   make check-r11f  $(BUILD)/r11f/metrics.json against reference_r11f.json
#   make analyze-tt  the images with the time-triggered injection (config_tt.json; images/tt: riscv64-elf-gcc
#                  12.2.0, images/tt13: riscv64-unknown-elf-gcc 13.2.0, images/*/BUILD.txt): t(v) of E,
#                  CAR-V, WCET-E, CARV-E and CAR-FULL (every task of every image of round r11f) with
#                  t(V_k) per PE against the CSV, and the terms of the network
#                  interface of every image (inject, rx_size, rx_end) against their constants in
#                  rttools/modules/routing/router.py (NI_INJECT_CYCLES, NI_RX_SIZE_CYCLES,
#                  NI_RX_END_CYCLES; w_NI = NI_WAIT_CYCLES); into $(BUILD)/tt
#   make check-tt  $(BUILD)/tt/metrics.json against reference_tt.json, every term within its constant, and
#                  the costs files of costs/tt equal to the analysis
#   make costs-tt  write costs/tt/<image>.json (static t(v) of every task and scheduler_cycles of each image of
#                  images/tt, rttools/wcet/costs.py): the costs that the analysis flow of the runs with the
#                  time-triggered injection takes as max(CSV, static) (experiments/tt); and
#                  costs/tt/<image>.handlers.json (handlers of one packet event and the handler cycles in t(v)
#                  of each task: the charge of the handlers that run inside another job)
#   make images-tt  build the images of images/tt and images/tt13 with ../exp23/build_sw.sh (the compiler
#                  of ENV_SETUP; copy each set by hand into the directory of its compiler)
#
# Run W1 (logs/W1.*): wcet_e of tag r11-wcet-rc1 (git archive), Questa 2025.3, riscv64-elf-gcc 12.2.0,
# 10 ms at 500 MHz (make sim); W1.image.elf and W1.image.lst are the image of the run.
# Run W2 (logs/W2.*, reference_W2.json): wcet_e of tag r11-rc3 (release by tick, kernel without
# nested interrupts), same tools, clock and duration: make run-analyze check-run LOG=logs/W2.events.txt
# REF=reference_W2.json.
# Run W3 (logs/W3.*, reference_W3.json): wcet_e of tag r11-rc5 (as W2, crt0=guard_readback), same tools,
# clock and duration: make run-analyze check-run LOG=logs/W3.events.txt REF=reference_W3.json
# Runs W4 and W5 (logs/W4.*, logs/W5.*, reference_W4.json, reference_W5.json): wcet_e of tag r11-rc7
# (as W3 with the time-triggered injection, table wcet_e_tt.h of t(v) = max(CSV, static); 10.5 ms at
# 500 MHz and at 220.416 MHz, the clock of the flow with these costs): make run-analyze check-run
# LOG=logs/W5.events.txt REF=reference_W5.json SPEC=specs/wcet_e_tt_rc7.json (image of tag r11-rc7, images/tt-rc7); rtlapp of run-log takes the
# model of the RUN_INFO (network-interface model tt, t(v) = max(CSV, static)).
# (`make check` runs W1 to W5, check-r11c, check-r11e and check-r11f).
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
# clocks of wcet_e_tt.h: the clock of the flow with t(v) = max(CSV, static) (experiments/tt, run W5) and
# 500 MHz (run W4); TT_COSTS: static t(v) of the image (costs/tt)
TT_CLOCKS ?= 234656000 500000000
TT_COSTS ?= costs/tt/wcet_e.json
SIM_NS  ?= 10000000
LOG     ?= logs/W1.events.txt
REF     ?= reference_W1.json
# spec of the image of the run (specs/wcet_e_tt.json for the runs of the time-triggered injection)
SPEC    ?= specs/wcet_e.json
OUTDIR  ?= $(BUILD)/run_$(firstword $(subst ., ,$(notdir $(LOG))))
# image of the run: logs/<run>.image.elf next to a stored log, else the build of simulate.sh
IMAGE   ?= $(if $(filter logs/%.events.txt,$(LOG)),$(patsubst %.events.txt,%.image.elf,$(LOG)),$(dir $(LOG))pkt-sim/software/ucx-os/build/target/image.elf)
CC_BODIES ?= riscv64-elf-gcc
RTL     := ../../pkt-sim/tests/rtl
UCX_IMG := pkt-sim/software/ucx-os/build/target

.PHONY: all analyze check app csv images bodies trace sim run-analyze check-run analyze-r11c check-r11c analyze-r11e check-r11e
.PHONY: analyze-r11f check-r11f clean
.PHONY: analyze-tt check-tt images-tt costs-tt

all: analyze check

analyze:
	$(RUN) analyze --config config.json --out $(BUILD)

check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/metrics.json reference.json
	$(GEN) check $(GENARGS)
	$(GEN) tt-check $(CSV) $(MAP) --arch ../../arch/hermes-2x2.gml --name $(NAME) $(foreach f,$(TT_CLOCKS),--clock $(f)) --costs $(TT_COSTS) --out $(APP_DIR)
	$(MAKE) run-analyze check-run
	$(MAKE) run-analyze check-run LOG=logs/W2.events.txt REF=reference_W2.json
	$(MAKE) run-analyze check-run LOG=logs/W3.events.txt REF=reference_W3.json
	$(MAKE) run-analyze check-run LOG=logs/W4.events.txt REF=reference_W4.json SPEC=specs/wcet_e_tt_rc7.json
	$(MAKE) run-analyze check-run LOG=logs/W5.events.txt REF=reference_W5.json SPEC=specs/wcet_e_tt_rc7.json
	$(MAKE) analyze-r11c check-r11c
	$(MAKE) analyze-r11e check-r11e
	$(MAKE) analyze-r11f check-r11f
	$(MAKE) analyze-tt check-tt

app:
	$(GEN) generate $(GENARGS)
	$(GEN) tt $(CSV) $(MAP) --arch ../../arch/hermes-2x2.gml --name $(NAME) $(foreach f,$(TT_CLOCKS),--clock $(f)) --costs $(TT_COSTS) --out $(APP_DIR)

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
	$(RUN) run-log $(LOG) --spec $(SPEC) --image $(IMAGE) --manifest $(APP_DIR)/$(NAME).json \
		--csv $(CSV) --map $(MAP) --arch ../../arch/hermes-2x2.gml --out $(OUTDIR)

check-run:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(OUTDIR)/metrics.json $(REF)

analyze-r11c:
	$(RUN) analyze --config config_r11c.json --out $(BUILD)/r11c

check-r11c:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/r11c/metrics.json reference_r11c.json

analyze-r11e:
	$(RUN) analyze --config config_r11e.json --out $(BUILD)/r11e

check-r11e:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/r11e/metrics.json reference_r11e.json

analyze-r11f:
	$(RUN) analyze --config config_r11f.json --out $(BUILD)/r11f

check-r11f:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/r11f/metrics.json reference_r11f.json

analyze-tt:
	$(RUN) analyze --config config_tt.json --out $(BUILD)/tt

TT_COST_FILES := E:weird_a CAR-V:car_v WCET-E:wcet_e CARV-E:carv_e CAR-FULL:car_full

costs-tt: analyze-tt
	mkdir -p costs/tt
	for p in $(TT_COST_FILES); do cp $(BUILD)/tt/$${p%%:*}/costs_file.json costs/tt/$${p##*:}.json; \
		cp $(BUILD)/tt/$${p%%:*}/costs_file.handlers.json costs/tt/$${p##*:}.handlers.json; done

check-tt:
	for p in $(TT_COST_FILES); do cmp $(BUILD)/tt/$${p%%:*}/costs_file.json costs/tt/$${p##*:}.json || exit 1; \
		cmp $(BUILD)/tt/$${p%%:*}/costs_file.handlers.json costs/tt/$${p##*:}.handlers.json || exit 1; done
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/tt/metrics.json reference_tt.json
	$(PYTHON) -c "import json, sys; m = json.load(open('$(BUILD)/tt/metrics.json')); \
		sys.exit(0 if m['ni_within_bound'] else 'a term of the network interface exceeds its constant')"

images-tt:
	F_CLK=449152000 APP=weird_a ../exp23/build_sw.sh $(BUILD)/img-tt/weird_a
	F_CLK=441088000 APP=car_v ../exp23/build_sw.sh $(BUILD)/img-tt/car_v
	F_CLK=500000000 APP=wcet_e ../exp23/build_sw.sh $(BUILD)/img-tt/wcet_e
	F_CLK=457600000 APP=carv_e ../exp23/build_sw.sh $(BUILD)/img-tt/carv_e
	F_CLK=526080000 F_TICK=4000 APP=car_full ../exp23/build_sw.sh $(BUILD)/img-tt/car_full
	for a in weird_a car_v wcet_e carv_e car_full; do ls -l $(BUILD)/img-tt/$$a/$(UCX_IMG)/image.elf; done

clean:
	rm -rf $(BUILD)
