# Data of the tables and figures of the article that come from the contraction
# example graph and from the RTL log of application E (seconds).
#
#   make              contraction + exp23 + check (default)
#   make contraction  contraction criteria on $(GRAPH) with N = $(N): rows of the criteria table,
#                     panels of the contraction figure
#   make exp23        Gantt of one hyperperiod, response of each iteration and flow table from $(LOG)
#   make check        compare the metrics with reference_contraction.json and reference_exp23.json
#
# CAR, the criterion of application E and the summary of Table 7.1 come from
# experiments/ch7 (make car, make graphs full stats).

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
APPS    := ../../apps
EXP23   := ../exp23
GRAPH   ?= $(APPS)/sample-graph-a/sample_graph.txt
N       ?= 4
LOG     ?= $(EXP23)/logs/F.events.txt
# join rule of J (experiments/exp23/Makefile): any3 for the stored logs A to E
JOIN    ?= $(if $(filter $(foreach r,A B C D E,$(EXP23)/logs/$(r).events.txt),$(LOG)),any3,per_producer)
BUILD   ?= build
ENV      = PYTHONPATH=$(RTTOOLS) $(PYTHON)
FIG      = $(ENV) -m rttools.paper.figures

.PHONY: all contraction exp23 check clean

all: contraction exp23 check

contraction:
	$(FIG) contraction --graph $(GRAPH) --n $(N) --out $(BUILD)/contraction

exp23:
	$(FIG) exp23 $(LOG) --config $(EXP23)/config.json --flows config.json --join $(JOIN) --out $(BUILD)/exp23

check:
	$(ENV) -m rttools.paper.exp23 check $(BUILD)/contraction/contraction.json reference_contraction.json
	$(ENV) -m rttools.paper.exp23 check $(BUILD)/exp23/metrics.json reference_exp23.json

clean:
	rm -rf $(BUILD)
