# Experiment of Ch. 8 (exp-23): simulation, analysis and check.
#
#   make sim       simulate (needs Questa/ModelSim and riscv64-elf; see ENV_SETUP in simulate.sh)
#   make analyze   tables, figure and metrics from $(LOG)
#   make check     compare the metrics with $(REF)
#   make all       analyze + check (default; stored log of run F against reference_head.json) + frequency
#   make frequency minimum frequency of application E (CLI input apps/synthetic-app-e): f*, f_CPU and
#                  max(f*, f_CPU) with the .map file and with the Spiral Mapping; check against
#                  reference_frequency.json
#   make paper     sim + software-without + analyze + check (simulation of this tree against
#                  reference_head.json)
#   make software  build of simulate.sh (build_sw.sh) into $(SW)/with and the same build with
#                  -DUCX_NO_INSTRUMENTATION into $(SW)/without (needs riscv64-elf; ENV_SETUP)
#   make instrumentation
#                  software + analyze + check with the listings of these builds: the bound of
#                  the instrumentation writes from the image of this tree (rttools/paper/
#                  instrumentation.py); check against $(REF)
#   make runs      analyze the six stored runs (logs/A..F) into build/runs  (anon:drop-line)
#   make info      print the source identification that `make sim` writes to RUN_INFO
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
# After `make sim`, use LOG=build/sim/events.txt (make paper does it).
#
# LISTING and LISTING_WITHOUT: objdump listings (image.lst of build_sw.sh) of
# the image with and without the instrumentation writes, for the bound of
# their cycles in the measured CPU time (metrics.json `instrumentation`,
# values.tex). Run F keeps them in logs/F.image.lst and logs/F.noinstr.lst
# (logs/F.software.txt); make paper and make instrumentation build them.
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
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23
APP_E   := ../../apps/synthetic-app-e
ARCH    := ../../arch/hermes-2x2.gml
F0      ?= 500000000
SW      ?= $(BUILD)/sw
UCX_IMG := pkt-sim/software/ucx-os/build/target
F_LOG   := logs/F.events.txt
LISTING ?= $(if $(filter $(F_LOG),$(LOG)),logs/F.image.lst)
LISTING_WITHOUT ?= $(if $(filter $(F_LOG),$(LOG)),logs/F.noinstr.lst)
INSTR_ARGS = $(if $(LISTING),--listing $(LISTING) --listing-without $(LISTING_WITHOUT))

.PHONY: all sim analyze check frequency paper software software-without instrumentation info clean

all: analyze check frequency

sim:
	./simulate.sh $(BUILD)/sim $(SIM_NS)

analyze:
	$(RUN) analyze $(LOG) --config config.json --join $(JOIN) --out $(OUTDIR) $(INSTR_ARGS)

check:
	$(RUN) check $(OUTDIR)/metrics.json $(REF)

frequency:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.frequency run --app $(APP_E)/synthetic-app-e.csv \
		--arch $(ARCH) --map $(APP_E)/synthetic-app-e-ONTO-hermes2x2.map --map spiral --f0 $(F0) \
		--config config.json --out $(BUILD)/frequency
	$(RUN) check $(BUILD)/frequency/metrics.json reference_frequency.json

paper:
	$(MAKE) sim software-without
	$(MAKE) analyze check LOG=$(BUILD)/sim/events.txt REF=reference_head.json \
		LISTING=$(BUILD)/sim/$(UCX_IMG)/image.lst LISTING_WITHOUT=$(SW)/without/$(UCX_IMG)/image.lst

software: software-without
	./build_sw.sh $(SW)/with

software-without:
	UCX_CFLAGS=-DUCX_NO_INSTRUMENTATION ./build_sw.sh $(SW)/without

instrumentation: software
	$(MAKE) analyze check LISTING=$(SW)/with/$(UCX_IMG)/image.lst \
		LISTING_WITHOUT=$(SW)/without/$(UCX_IMG)/image.lst

# anon:drop-begin
.PHONY: runs
runs:
	for r in A B C D E; do $(RUN) analyze logs/$$r.events.txt --config config.json --join any3 --out $(BUILD)/runs/$$r || exit 1; done
	$(RUN) analyze logs/F.events.txt --config config.json --join per_producer --out $(BUILD)/runs/F \
		--listing logs/F.image.lst --listing-without logs/F.noinstr.lst
# anon:drop-end

info:
	@./source_info.sh ../.. /dev/stdout

clean:
	rm -rf $(BUILD)
