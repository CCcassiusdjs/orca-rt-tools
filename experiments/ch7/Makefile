# Table 7.1 (ORT/GCM, ORT/GDE, Ch. 7).
#
#   make          |V| = 20 to 100 from graphs/ (seconds), check against reference.json
#   make full     all 17 graphs (about 18 minutes); `make graphs` first
#   make graphs   extract the 17 graphs of commit 4e43483 from the git history into $(BUILD)/graphs
#   make n16      |V| = 20 to 100 with N = 16, the value the thesis states

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
BUILD   ?= build
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.ch7
ALL      = 20 30 40 50 60 70 80 90 100 200 300 400 500 600 700 800 900

.PHONY: all run check graphs full n16 clean

all: run check

run:
	$(RUN) run --config config.json --graphs graphs --out $(BUILD)/results

check:
	$(RUN) check $(BUILD)/results/metrics.json reference.json

graphs:
	mkdir -p $(BUILD)/graphs
	for n in $(ALL); do git show 4e43483:tp-tools/apps/var-nnodes/10_$$n.txt > $(BUILD)/graphs/10_$$n.txt || exit 1; done

full:
	$(RUN) run --config config.json --graphs $(BUILD)/graphs --out $(BUILD)/full --sizes $(shell echo $(ALL) | tr ' ' ',')
	$(RUN) check $(BUILD)/full/metrics.json reference_full.json

n16:
	$(RUN) run --config config.json --graphs graphs --out $(BUILD)/n16 --n 16

clean:
	rm -rf $(BUILD)
