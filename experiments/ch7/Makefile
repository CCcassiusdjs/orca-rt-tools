# Table 7.1 (ORT/GCM, ORT/GDE, Ch. 7).
#
#   make          |V| = 20 to 100 from graphs/ (seconds), check against reference.json
#   make graphs   unpack the 17 graphs (graphs/*.txt and graphs/10_200-900.tar.xz) into $(BUILD)/graphs
#                 and check their SHA-256 (graphs/SHA256SUMS)
#   make full     all 17 graphs (about 20 minutes); `make graphs` first
#   make n16      |V| = 20 to 100 with N = 16, the value the thesis states

PYTHON   ?= python3
RTTOOLS  := $(abspath ../../orca-rt-tools)
BUILD    ?= build
ENV       = PYTHONPATH=$(RTTOOLS) $(PYTHON)
RUN       = $(ENV) -m rttools.paper.ch7
ALL       = 20 30 40 50 60 70 80 90 100 200 300 400 500 600 700 800 900

.PHONY: all run check graphs full n16 clean

all: run check

run:
	$(RUN) run --config config.json --graphs graphs --out $(BUILD)/results

check:
	$(RUN) check $(BUILD)/results/metrics.json reference.json

graphs:
	$(ENV) -m rttools.paper.graphs extract --src graphs --out $(BUILD)/graphs

full:
	$(RUN) run --config config.json --graphs $(BUILD)/graphs --out $(BUILD)/full --sizes $(shell echo $(ALL) | tr ' ' ',')
	$(RUN) check $(BUILD)/full/metrics.json reference_full.json

n16:
	$(RUN) run --config config.json --graphs graphs --out $(BUILD)/n16 --n 16

clean:
	rm -rf $(BUILD)
