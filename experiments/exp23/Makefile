# Experiment of Ch. 8 (exp-23): simulation, analysis and check.
#
#   make sim       simulate (needs Questa/ModelSim and riscv64-elf; see ENV_SETUP in simulate.sh)
#   make analyze   tables, figure and metrics from $(LOG)
#   make check     compare the metrics with $(REF)
#   make all       analyze + check (default; stored log of run F against reference_head.json) + frequency
#                  + frequency-l0 + tick
#   make tick      tick of the UCX-OS (arch.mak, hal.c, peripherals_minimal.vhd) against the release
#                  period of A (manycore_pe.sv, config.json): tick = T x F_CLK cycles (tick_period.py code;
#                  make paper-flow also checks it at the clock of the flow, --f-clk)
#   make tick-log  release_to_dispatch, request_to_dispatch and spacing of the dispatches of A in $(LOG);
#                  passes when the spacing equals the tick and request_to_dispatch is constant
#   make frequency minimum frequency of application E (CLI input apps/synthetic-app-e): f*, f_CPU and
#                  max(f*, f_CPU) with the .map file and with the Spiral Mapping, link occupancy
#                  o_i = L0 + 20 (m + 1) (header wait bound of the Hermes, make -C ../zll contention;
#                  the default of rttools); check against reference_frequency.json
#   make frequency-l0  the same with o_i = L0 (--header-wait off); check against
#                  reference_frequency_l0.json
#   make paper     sim + software-without + analyze + check (simulation of this tree against
#                  reference_head.json), both builds at F_CLK
#   make software  build of simulate.sh (build_sw.sh) into $(SW)/with and the same build with
#                  -DUCX_NO_INSTRUMENTATION into $(SW)/without (needs riscv64-elf; ENV_SETUP)
#   make instrumentation
#                  software + analyze + check with the listings of these builds: the bound of
#                  the instrumentation writes from the image of this tree (rttools/paper/
#                  instrumentation.py); check against $(REF)
#   make flow-clock  clock of a run at the minimum frequency of the flow (after `make frequency`):
#                  F_CLK = first multiple of 32 kHz at or above it (T F_CLK in steps of 16
#                  cycles of TIMER1), half period floor(1e15 / (2 F_CLK)) fs; writes
#                  $(BUILD)/frequency/clock.json
#   make paper-flow  sim at that F_CLK in $(BUILD)/sim-flow, analyze into $(BUILD)/results-flow,
#                  check against reference_flow.json (model at that clock, no measured value)
#   make runs      analyze the eight stored runs (logs/A..H) into build/runs and check G and H  (anon:drop-line)
#                  against reference_G.json and reference_H.json  (anon:drop-line)
#   make check-run analyze + check + phase-check of the stored runs of the release by tick, TG
#                  (500 MHz) and TH (434.912 MHz) of tag r11-rc3, UG (500 MHz) and UH (434.912 MHz)
#                  of tag r11-rc5, VG (500 MHz) and VH (434.912 MHz) of tag r11-rc7 (time-triggered
#                  injection), against reference_<run>.json, into $(BUILD)/results_<run>
#                  (values.tex of each run there)
#   make info      print the source identification that `make sim` writes to RUN_INFO
#   make tt        write pkt-sim/software/ucx-os/app/weird_a_tt.h: the injection instants of the
#                  packets between PEs in the link schedule of E at TT_CLOCKS (rttools.ucxgen tt,
#                  model of the time-triggered injection: the network interface of each PE as a
#                  resource, o_i = L0 + 20 (m + 1) + w_NI)
#   make tt-check  weird_a_tt.h equals a new generation (part of `make all`)
#   make phase-check  conformance of $(OUTDIR)/metrics.json with the phase model (after analyze):
#                  no task twice in a phase, no execution before phase j + n(v), CPU per phase at
#                  most t(V_k) (rttools.paper.phasecheck; exit 1 otherwise). The stored runs A to H
#                  are of weird_a_data (release rule data: RELEASE=data) and do not conform (run H:
#                  32 of 33 phases with a task twice)
#
# Release rule (RELEASE, --release of the analysis): auto takes the line `release` of the
# RUN_INFO (simulate.sh writes release=tick for weird_a, the application with the release by
# tick, app/weird_a.sim; release=data for weird_a_data); the stored logs A to H have no such line
# and are of the release rule data, the code of weird_a_data (pkt-sim/software/ucx-os/Makefile);
# TG, TH, UG, UH, VG and VH have release=tick.
#
# Interrupt rule (clock.isr of metrics.json, line isr of the RUN_INFO): the stored logs are of the
# kernel whose handlers enable interrupts before the return of _isr (nesting; ISR_NESTING=1 in
# simulate.sh builds it); the kernel of this tree leaves them disabled (no_nesting).
#
# The run that a paper reports: make paper REQUIRE_CLEAN=1 from a clean
# checkout at a tag (or from `git archive <tag>`); simulate.sh stops
# otherwise. RUN_INFO then holds repo_commit, repo_state, repo_tag and
# src_sha256 (see simulate.sh).
#
# LOG and REF default to run F (logs/F.events.txt, reference_head.json): the
# log of `make paper` on this tree (tag exp23-F), the source of the numbers
# of the paper.
# Run D: make LOG=logs/D.events.txt REF=reference_D.json OUTDIR=build/results_D  (anon:drop-line)
# Run E: make LOG=logs/E.events.txt REF=reference_E.json OUTDIR=build/results_E  (anon:drop-line)
# Run G (r10-rc1, 500 MHz): make LOG=logs/G.events.txt REF=reference_G.json OUTDIR=build/results_G
# Run H (r10-rc1, clock of the flow, 434.912 MHz): make LOG=logs/H.events.txt REF=reference_H.json
#   OUTDIR=build/results_H
# Runs TG and TH (r11-rc3: weird_a with the release by tick, kernel without nested interrupts,
#   logs/{TG,TH}.{events.txt,RUN_INFO,image.lst,noinstr.lst,time.txt}; TH.image.elf for
#   experiments/wcet): make check-run, or make LOG=logs/TH.events.txt REF=reference_TH.json
#   OUTDIR=build/results_TH analyze check
# Runs UG and UH (r11-rc5: the same application, clocks and duration as TG and TH, crt0.s with the
#   return test of _isr and the read back of _interrupt_set(0), crt0=guard_readback;
#   logs/{UG,UH}.{events.txt,RUN_INFO,image.lst,noinstr.lst,time.txt}; UH.image.elf for
#   experiments/wcet): make check-run, or make LOG=logs/UH.events.txt REF=reference_UH.json
#   OUTDIR=build/results_UH analyze check
# Runs VG and VH (r11-rc7: the same application, clocks and duration as UG and UH, the time-
#   triggered injection, injection=tt, with the table weird_a_tt.h of t(v) = max(CSV, static),
#   costs=max_csv_static in RUN_INFO; logs/{VG,VH}.{events.txt,RUN_INFO,image.lst,noinstr.lst,
#   time.txt}; VH.image.elf for experiments/wcet): make check-run, or make LOG=logs/VH.events.txt
#   REF=reference_VH.json OUTDIR=build/results_VH analyze check. The analysis takes the model of the
#   RUN_INFO (network-interface model tt and the costs file, whatever NI) and checks each packet,
#   job end and enqueue (metrics.json tt).
# After `make sim`, use LOG=build/sim/events.txt (make paper does it).
#
# Clock: F_CLK (Hz) sets the clock of the simulation (simulate.sh: F_CLK of
# the software, half period of manycore_top, release period T F_CLK cycles);
# default 500 MHz, the clock of run F. `make sim F_CLK=435200000` runs at
# 435.2 MHz. The analysis reads the clock from the RUN_INFO next to the log
# (else config.json clock_hz).
#
# LISTING and LISTING_WITHOUT: objdump listings (image.lst of build_sw.sh) of
# the image with and without the instrumentation writes, for the bound of
# their cycles in the measured CPU time (metrics.json `instrumentation`,
# values.tex). Run F keeps them in logs/F.image.lst and logs/F.noinstr.lst
# (logs/F.software.txt), runs G and H in logs/G.* and logs/H.* (the image.lst
# of the build of the run); make paper and make instrumentation build them.
# Other logs: no listing, no bound.

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
BUILD   ?= build
SIM_NS  ?= 20000000
LOG     ?= logs/F.events.txt
REF     ?= reference_head.json
# join rule of J: the stored logs A to E come from weird_a.c before 379f388
# (J joins any three packets); a new simulation of this tree, per producer
OLD_APP_LOGS := $(foreach r,A B C D E,logs/$(r).events.txt)
JOIN    ?= $(if $(filter $(OLD_APP_LOGS),$(LOG)),any3,per_producer)
OUTDIR  ?= $(BUILD)/results
# network-interface model of the link schedule (RTTOOLS_NI,
# orca-rt-tools/rttools/modules/routing/router.py): off, the model of the
# stored references (runs up to tag r11-rc5); the default of rttools (tt)
# is the model of experiments/tt
NI      ?= off
RUN      = RTTOOLS_NI=$(NI) PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23
# release rule of LOG (auto: RUN_INFO line `release`; data for a RUN_INFO without it, the stored
# logs A to H; tick for TG, TH, UG, UH, VG and VH)
RELEASE ?= auto
APP_E   := ../../apps/synthetic-app-e
ARCH    := ../../arch/hermes-2x2.gml
# first frequency of the search of the flow (rttools CLI), not the clock of the simulation
F0      ?= 500000000
# clock of the simulation (Hz) and its output directory
F_CLK   ?= 500000000
# tick of the software (Hz): 1 / T, the default of simulate.sh (RELEASE_NS = 500000)
F_TICK  ?= 2000
SIMDIR  ?= $(BUILD)/sim
PAPER_REF ?= reference_head.json
CLOCK   := $(BUILD)/frequency/clock.json
# clocks of the injection table of weird_a (the clocks of runs UG/VG and UH/VH)
TT_CLOCKS ?= 434912000 500000000
# t(v) = max(CSV, static t(v) of the image, experiments/wcet costs/tt) in the link schedule of the table
TT_COSTS ?= ../wcet/costs/tt/weird_a.json
TT_ARGS  = $(APP_E)/synthetic-app-e.csv $(APP_E)/synthetic-app-e-ONTO-hermes2x2.map --arch $(ARCH) \
	--name weird_a $(foreach f,$(TT_CLOCKS),--clock $(f)) --style named --costs $(TT_COSTS) \
	--out ../../pkt-sim/software/ucx-os/app

SW      ?= $(BUILD)/sw
UCX_IMG := pkt-sim/software/ucx-os/build/target
# stored run of LOG (logs/<run>.events.txt) and its listings, when logs/ has them (F, G, H)
LOG_RUN := $(patsubst logs/%.events.txt,%,$(filter logs/%.events.txt,$(LOG)))
LISTING ?= $(if $(LOG_RUN),$(wildcard logs/$(LOG_RUN).image.lst))
LISTING_WITHOUT ?= $(if $(LOG_RUN),$(wildcard logs/$(LOG_RUN).noinstr.lst))
INSTR_ARGS = $(if $(LISTING),--listing $(LISTING) --listing-without $(LISTING_WITHOUT))

.PHONY: all sim analyze check frequency tick tick-log frequency-l0 paper flow-clock paper-flow software
.PHONY: software-without
.PHONY: instrumentation info clean phase-check check-run tt tt-check

all: analyze check frequency frequency-l0 tick tt-check

sim:
	F_CLK=$(F_CLK) ./simulate.sh $(SIMDIR) $(SIM_NS)

analyze:
	$(RUN) analyze $(LOG) --config config.json --join $(JOIN) --out $(OUTDIR) $(INSTR_ARGS) --release $(RELEASE) \
		--arch $(ARCH) --map $(APP_E)/synthetic-app-e-ONTO-hermes2x2.map

check:
	$(RUN) check $(OUTDIR)/metrics.json $(REF)

frequency:
	RTTOOLS_NI=$(NI) PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.frequency run --app $(APP_E)/synthetic-app-e.csv \
		--arch $(ARCH) --map $(APP_E)/synthetic-app-e-ONTO-hermes2x2.map --map spiral --f0 $(F0) \
		--config config.json --header-wait bound --out $(BUILD)/frequency
	$(RUN) check $(BUILD)/frequency/metrics.json reference_frequency.json

frequency-l0:
	RTTOOLS_NI=$(NI) PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.frequency run --app $(APP_E)/synthetic-app-e.csv \
		--arch $(ARCH) --map $(APP_E)/synthetic-app-e-ONTO-hermes2x2.map --map spiral --f0 $(F0) \
		--config config.json --header-wait off --out $(BUILD)/frequency_l0
	$(RUN) check $(BUILD)/frequency_l0/metrics.json reference_frequency_l0.json

tick:
	$(PYTHON) tick_period.py code

tt:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.ucxgen tt $(TT_ARGS)

tt-check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.ucxgen tt-check $(TT_ARGS)

tick-log:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) tick_period.py log $(LOG)

paper:
	$(MAKE) sim software-without
	$(MAKE) analyze check LOG=$(SIMDIR)/events.txt REF=$(PAPER_REF) \
		LISTING=$(SIMDIR)/$(UCX_IMG)/image.lst LISTING_WITHOUT=$(SW)/without/$(UCX_IMG)/image.lst

flow-clock: frequency
	$(RUN) clock $(BUILD)/frequency/metrics.json --config config.json --out $(CLOCK)

paper-flow: flow-clock
	$(PYTHON) tick_period.py code --f-clk $$($(RUN) clock $(BUILD)/frequency/metrics.json --config config.json --field f_clk_hz)
	$(MAKE) sim software-without F_CLK=$$($(RUN) clock $(BUILD)/frequency/metrics.json --config config.json --field f_clk_hz) \
		SIMDIR=$(BUILD)/sim-flow SW=$(BUILD)/sw-flow
	$(MAKE) analyze check LOG=$(BUILD)/sim-flow/events.txt OUTDIR=$(BUILD)/results-flow REF=reference_flow.json \
		LISTING=$(BUILD)/sim-flow/$(UCX_IMG)/image.lst LISTING_WITHOUT=$(BUILD)/sw-flow/without/$(UCX_IMG)/image.lst

phase-check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.phasecheck $(OUTDIR)/metrics.json --rows 5

TICK_RUNS ?= TG TH UG UH VG VH
check-run:
	for r in $(TICK_RUNS); do $(MAKE) --no-print-directory analyze check phase-check LOG=logs/$$r.events.txt \
		REF=reference_$$r.json OUTDIR=$(BUILD)/results_$$r || exit 1; done

software: software-without
	F_CLK=$(F_CLK) F_TICK=$(F_TICK) ./build_sw.sh $(SW)/with

software-without:
	F_CLK=$(F_CLK) F_TICK=$(F_TICK) UCX_CFLAGS=-DUCX_NO_INSTRUMENTATION ./build_sw.sh $(SW)/without

instrumentation: software
	$(MAKE) analyze check LISTING=$(SW)/with/$(UCX_IMG)/image.lst \
		LISTING_WITHOUT=$(SW)/without/$(UCX_IMG)/image.lst

# anon:drop-begin
.PHONY: runs
runs:
	for r in A B C D E; do $(RUN) analyze logs/$$r.events.txt --config config.json --join any3 --out $(BUILD)/runs/$$r \
		--release data || exit 1; done
	for r in F G H; do $(RUN) analyze logs/$$r.events.txt --config config.json --join per_producer \
		--out $(BUILD)/runs/$$r --listing logs/$$r.image.lst --listing-without logs/$$r.noinstr.lst \
		--release data || exit 1; done
	$(RUN) check $(BUILD)/runs/G/metrics.json reference_G.json
	$(RUN) check $(BUILD)/runs/H/metrics.json reference_H.json
# anon:drop-end

info:
	@./source_info.sh ../.. /dev/stdout

clean:
	rm -rf $(BUILD)
