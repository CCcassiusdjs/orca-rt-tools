# Table 7.1 (ORT/GCM, ORT/GDE, Ch. 7) and the clustering of CAR and application E.
#
#   make          |V| = 20 to 100 from graphs/ (seconds), check against reference.json
#   make graphs   unpack the 17 graphs (graphs/*.txt and graphs/10_200-900.tar.xz) into $(BUILD)/graphs
#                 and check their SHA-256 (graphs/SHA256SUMS)
#   make full     all 17 graphs (20 to 25 minutes); `make graphs` first
#   make stats    derived quantities of Table 7.1 (min, mean, max, cluster sizes) from $(STATS_IN)
#   make car      CAR on 16 clusters, the criterion choice of application E, the Spiral Mapping
#                 of CAR on the 4x4 mesh and the body of its figure (seconds)
#   make n16      |V| = 20 to 100 with N = 16, the value the thesis states

PYTHON   ?= python3
RTTOOLS  := $(abspath ../../orca-rt-tools)
APPS     := $(abspath ../../apps)
BUILD    ?= build
STATS_IN ?= $(BUILD)/full
ENV       = PYTHONPATH=$(RTTOOLS) $(PYTHON)
RUN       = $(ENV) -m rttools.paper.ch7
ALL       = 20 30 40 50 60 70 80 90 100 200 300 400 500 600 700 800 900

.PHONY: all run check graphs full stats car n16 clean

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

stats:
	$(ENV) -m rttools.paper.figures table71 $(STATS_IN)/metrics.json --graphs $(BUILD)/graphs --out $(BUILD)/stats
	$(ENV) -m rttools.paper.exp23 check $(BUILD)/stats/metrics.json reference_stats.json

car:
	$(ENV) -m rttools.paper.car --config car.json --apps $(APPS) --out $(BUILD)/car
	$(ENV) -m rttools.paper.figures spiral $(BUILD)/car/metrics.json --out $(BUILD)/car
	$(ENV) -m rttools.paper.exp23 check $(BUILD)/car/metrics.json reference_car.json
	$(ENV) -m rttools.paper.exp23 check $(BUILD)/car/fig-spiral.json reference_spiral_fig.json

n16:
	$(RUN) run --config config.json --graphs graphs --out $(BUILD)/n16 --n 16

clean:
	rm -rf $(BUILD)
