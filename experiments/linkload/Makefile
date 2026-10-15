# Workloads in which the contention of packets sets f_NoC: E and CAR-V with the cost of every task divided
# by a factor (rttools/paper/linkload.py), analysis only: f_CPU, the minimum frequency of the flow
# and of the links alone, the lowest frequency at which each packet alone fits its window.
#
#   make          run and check against reference.json (about 20 s)
#   make run      $(BUILD)/metrics.json, $(BUILD)/timing.json (time of each search, not checked)
#   make check    $(BUILD)/metrics.json against reference.json ("match")
#   make clean

PYTHON  ?= python3
BUILD   ?= build
RTTOOLS := ../../orca-rt-tools
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.linkload

.PHONY: all run check clean

all: run check

run:
	$(RUN) run --config config.json --out $(BUILD)

check:
	$(RUN) check $(BUILD)/metrics.json reference.json

clean:
	rm -rf $(BUILD)
