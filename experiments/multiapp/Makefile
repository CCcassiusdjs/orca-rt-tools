# Several applications on one NoC (rttools.multiapp): CAR-V (16 PEs) and
# application E (4 PEs) on the 4x5 mesh, each one on its own PEs, sharing
# routers and links. The flow builds one link schedule for the union of the
# packets of both applications and one clock for the platform.
#
#   make           run + check + maps-check + app-check (default; about 20 s)
#   make run       analysis flow on composition.json (f_CPU per application, f_NoC of the union,
#                  frequency of the platform, R_bound per application, shared links, collisions of
#                  the schedules of each application alone), the other order (composition-e-first.json),
#                  1,000 random placements and each application alone against the flow of one
#                  application; outputs in $(BUILD)
#   make check     compare $(BUILD)/metrics.json with reference.json
#   make maps      write maps/CARV.map and maps/E.map from the placement of composition.json
#   make maps-check  the stored maps equal the placement
#   make app       write pkt-sim/software/ucx-os/app/$(NAME).{c,json,sim} (rttools.ucxgen compose)
#   make app-check the stored $(NAME).{c,json,sim} match a new composition; heap demand of each
#                  PE (rttools.ucxgen.memory) against HEAP
#   make build     build $(NAME) in $(BUILD)/pkt-sim (riscv64-elf toolchain); heap demand against
#                  _heap_size of the image
#   make sim       RTL simulation (Questa and riscv64-elf; ENV_SETUP as in exp23) at F_CLK:
#                  F_CLK=$(F_CLK) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) $(NAME)
#                  (mesh 4x5 and RELEASE_MASK from app/$(NAME).sim)
#   make analyze   analysis of $(LOG) for each application (rttools.paper.rtlapp --app, link
#                  schedule of the union with --composition) into $(OUTDIR)/CARV and $(OUTDIR)/E
#   make check-run compare $(OUTDIR)/<app>/metrics.json with reference_$(RUN)_<app>.json
#   make phase-check  conformance of $(OUTDIR)/<app>/metrics.json with the phase model
#                  (rttools.paper.phasecheck; exit 1 otherwise)
#
# Release rule (RELEASE, --release of rtlapp): carv_e.c of this tree has the release by tick
# (app/carv_e.sim: TICK_RELEASE=1, RELEASE_MASK of the 20 PEs); run MA is of the data-driven
# release (carv_e.c of r11-multiapp-rc1 = `rttools.ucxgen compose --release data`): analyze it
# with RELEASE=data. auto (default) reads the line `release` of the RUN_INFO.
#
# F_CLK: the clock of the platform from the flow, 434.9 MHz (f_CPU of E), on
# the grid of 32 kHz of the release period (exp23.flow_clock): 434.912 MHz,
# metrics.json rtl.clock. SIM_NS: 3 ms + (n(v_last) of CAR-V = 4 + 8 measured
# iterations - 1) T + R_bound of CAR-V (2.218 ms) + T = 11.22 ms (metrics.json
# rtl.sim_ns_min), rounded up to 11.5 ms, the duration of the CAR-V runs.
# After `make sim`: make analyze LOG=$(BUILD)/sim/events.txt.

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
APP_DIR := ../../pkt-sim/software/ucx-os/app
BUILD   ?= build
NAME    ?= carv_e
MESH    ?= 4x5
ARCH    := ../../arch/hermes-4x5.gml
CARV_CSV := ../../apps/car-v/car-v.csv
E_CSV   := ../../apps/synthetic-app-e/synthetic-app-e.csv
APPS     = --app CARV:$(CARV_CSV):maps/CARV.map --app E:$(E_CSV):maps/E.map
F_CLK   ?= 434912000
SIM_NS  ?= 11500000
# _heap_size of the image of carv_e built with riscv64-unknown-elf-gcc 13.2,
# release by tick (TR_DEFS; 49924 for the image of run MA); make build
# reads the value of the toolchain in use
HEAP    ?= 48836
# received packets in flight per input edge between PEs in the heap model
# (rttools/ucxgen/memory.py). With 2 (the value of experiments/car-v-rtl),
# PE 9 (G and J of application E: inputs F->G, H->J, I->J, 21,370 bytes of
# payload) needs 50,808 bytes, 900 bytes above the usable heap of the image;
# application E alone in the image of weird_a.c needs the same 50,808 bytes
# against 50,716 usable bytes, and runs F, G and H printed no "out of
# memory". With 1, the worst PE is 13 (36,224 bytes). The run checks the
# allocations: grep "out of memory" in pkt-sim/logs/output-*.txt.
IN_FLIGHT ?= 1
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.multiapp
GEN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.ucxgen
ANALYZE  = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.rtlapp
CHECK    = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check
LOG     ?= $(BUILD)/sim/events.txt
OUTDIR  ?= $(BUILD)/results_sim
RUN_ID  ?= MA
RELEASE ?= auto

.PHONY: all run check maps maps-check app app-check build sim analyze check-run clean phase-check

all: run check maps-check app-check

run:
	$(RUN) run --config config.json --out $(BUILD)

check:
	$(CHECK) $(BUILD)/metrics.json reference.json

maps:
	$(RUN) maps --config config.json

maps-check:
	$(RUN) maps --config config.json --check

app:
	$(GEN) compose $(APPS) --name $(NAME) --mesh $(MESH) --out $(APP_DIR)

app-check:
	$(GEN) compose-check $(APPS) --name $(NAME) --mesh $(MESH) --out $(APP_DIR)
	$(GEN) memory $(APP_DIR)/$(NAME).json --heap $(HEAP) --in-flight $(IN_FLIGHT)

build:
	rm -rf $(BUILD)/pkt-sim
	mkdir -p $(BUILD)
	cp -a ../../pkt-sim $(BUILD)/pkt-sim
	cd $(BUILD)/pkt-sim/software/ucx-os && $(MAKE) -s ARCH=riscv/hf-riscv-e incl && $(MAKE) -s $(NAME)
	$(GEN) memory $(APP_DIR)/$(NAME).json --image-map $(BUILD)/pkt-sim/software/ucx-os/build/target/image.map \
		--in-flight $(IN_FLIGHT) --json $(BUILD)/memory.json

sim:
	F_CLK=$(F_CLK) ../exp23/simulate.sh $(BUILD)/sim $(SIM_NS) $(NAME)

analyze:
	$(ANALYZE) analyze $(LOG) --manifest $(APP_DIR)/$(NAME).json --app CARV --csv $(CARV_CSV) \
		--map maps/CARV.map --arch $(ARCH) --composition composition.json --out $(OUTDIR)/CARV --release $(RELEASE)
	$(ANALYZE) analyze $(LOG) --manifest $(APP_DIR)/$(NAME).json --app E --csv $(E_CSV) \
		--map maps/E.map --arch $(ARCH) --composition composition.json --out $(OUTDIR)/E --release $(RELEASE)

check-run:
	$(CHECK) $(OUTDIR)/CARV/metrics.json reference_$(RUN_ID)_CARV.json
	$(CHECK) $(OUTDIR)/E/metrics.json reference_$(RUN_ID)_E.json

phase-check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.phasecheck $(OUTDIR)/CARV/metrics.json \
		$(OUTDIR)/E/metrics.json --rows 5

clean:
	rm -rf $(BUILD)
