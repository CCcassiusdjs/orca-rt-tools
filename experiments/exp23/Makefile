# Experiment of Ch. 8 (exp-23): simulation, analysis and check.
#
#   make sim       simulate (needs Questa/ModelSim and riscv64-elf; see ENV_SETUP in simulate.sh)
#   make analyze   tables, figure and metrics from $(LOG)
#   make check     compare the metrics with $(REF) (reference_D.json; make paper uses reference_head.json)
#   make all       analyze + check (default; uses the stored log of run D)
#   make paper     sim + analyze + check
#   make runs      analyze the five stored runs (logs/A..E) into build/runs
#
# LOG defaults to logs/D.events.txt (fixed RTL, `timescale 1ns/100ps).
# After `make sim`, use LOG=build/sim/events.txt (make paper does it).

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
BUILD   ?= build
SIM_NS  ?= 20000000
LOG     ?= logs/D.events.txt
REF     ?= reference_D.json
OUTDIR  ?= $(BUILD)/results
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23

.PHONY: all sim analyze check paper runs clean

all: analyze check

sim:
	./simulate.sh $(BUILD)/sim $(SIM_NS)

analyze:
	$(RUN) analyze $(LOG) --config config.json --out $(OUTDIR)

check:
	$(RUN) check $(OUTDIR)/metrics.json $(REF)

paper:
	$(MAKE) sim
	$(MAKE) analyze check LOG=$(BUILD)/sim/events.txt REF=reference_head.json

runs:
	for r in A B C D E; do $(RUN) analyze logs/$$r.events.txt --config config.json --out $(BUILD)/runs/$$r || exit 1; done

clean:
	rm -rf $(BUILD)
