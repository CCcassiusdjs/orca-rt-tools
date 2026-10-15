# Ablation of the terms of the analysis flow (w_h, w_NI, the handlers of Eq. (9)) and the baseline
# with event-triggered injection (WCTT by the recursive calculus of round-robin wormhole networks),
# on the models of the runs of round r11g (../tt/config.json): rttools/paper/ablation.py.
#
#   make          run and check against reference.json (about 20 s)
#   make run      $(BUILD)/metrics.json and one line per application
#   make check    $(BUILD)/metrics.json against reference.json ("match")
#   make clean

PYTHON  ?= python3
BUILD   ?= build
RTTOOLS := ../../orca-rt-tools
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.ablation

.PHONY: all run check clean

all: run check

run:
	$(RUN) run --config config.json --out $(BUILD)

check:
	$(RUN) check $(BUILD)/metrics.json reference.json

clean:
	rm -rf $(BUILD)
