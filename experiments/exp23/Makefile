# Experiment of Ch. 8 (exp-23): simulation, analysis and check.
#
#   make sim       simulate (needs Questa/ModelSim and riscv64-elf; see ENV_SETUP in simulate.sh)
#   make analyze   tables, figure and metrics from $(LOG)
#   make check     compare the metrics with $(REF)
#   make all       analyze + check (default; stored log of run F against reference_head.json) + frequency
#                  + frequency-l0
#   make frequency minimum frequency of application E (CLI input apps/synthetic-app-e): f*, f_CPU and
#                  max(f*, f_CPU) with the .map file and with the Spiral Mapping, link occupancy
#                  o_i = L0 + 20 (m + 1) (header wait bound of the Hermes, make -C ../zll contention;
#                  the default of rttools); check against reference_frequency.json
#   make frequency-l0  the same with o_i = L0 (--header-wait off); check against
#                  reference_frequency_l0.json
#   make paper     sim + analyze + check (simulation of this tree against reference_head.json)
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

.PHONY: all sim analyze check frequency frequency-l0 paper info clean

all: analyze check frequency frequency-l0

sim:
	./simulate.sh $(BUILD)/sim $(SIM_NS)

analyze:
	$(RUN) analyze $(LOG) --config config.json --join $(JOIN) --out $(OUTDIR)

check:
	$(RUN) check $(OUTDIR)/metrics.json $(REF)

frequency:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.frequency run --app $(APP_E)/synthetic-app-e.csv \
		--arch $(ARCH) --map $(APP_E)/synthetic-app-e-ONTO-hermes2x2.map --map spiral --f0 $(F0) \
		--config config.json --header-wait bound --out $(BUILD)/frequency
	$(RUN) check $(BUILD)/frequency/metrics.json reference_frequency.json

frequency-l0:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.frequency run --app $(APP_E)/synthetic-app-e.csv \
		--arch $(ARCH) --map $(APP_E)/synthetic-app-e-ONTO-hermes2x2.map --map spiral --f0 $(F0) \
		--config config.json --header-wait off --out $(BUILD)/frequency_l0
	$(RUN) check $(BUILD)/frequency_l0/metrics.json reference_frequency_l0.json

paper:
	$(MAKE) sim
	$(MAKE) analyze check LOG=$(BUILD)/sim/events.txt REF=reference_head.json

# anon:drop-begin
.PHONY: runs
runs:
	for r in A B C D E; do $(RUN) analyze logs/$$r.events.txt --config config.json --join any3 --out $(BUILD)/runs/$$r || exit 1; done
	$(RUN) analyze logs/F.events.txt --config config.json --join per_producer --out $(BUILD)/runs/F
# anon:drop-end

info:
	@./source_info.sh ../.. /dev/stdout

clean:
	rm -rf $(BUILD)
