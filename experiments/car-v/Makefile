# CAR-V (vision subgraph of CAR on the time scale of application E): generation
# of the application from apps/shi-2010 and the analysis flow of the paper on
# the 4x4 mesh, without RTL (rttools/paper/carv.py).
#
#   make          app + run + check (seconds)
#   make app      compare apps/car-v/car-v.csv with the generator (fails when they differ)
#   make generate write apps/car-v/car-v.csv from apps/shi-2010 and config.json
#   make run      ORT/GCM (N = 16, four criteria, smallest M2), Spiral Mapping, f_CPU, frequency
#                 search, network check at the clock, R_bound, flow windows, packets and heap per PE
#                 for every candidate of config.json; outputs in $(BUILD)
#   make check    compare $(BUILD)/metrics.json with reference.json

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
APPS    := $(abspath ../../apps)
ARCH    := $(abspath ../../arch/hermes-4x4.gml)
BUILD   ?= build
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.carv

.PHONY: all app generate run check clean

all: app run check

app:
	$(RUN) generate --config config.json --apps $(APPS) --check

generate:
	$(RUN) generate --config config.json --apps $(APPS)

run:
	$(RUN) run --config config.json --apps $(APPS) --arch $(ARCH) --out $(BUILD)

check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/metrics.json reference.json

clean:
	rm -rf $(BUILD)
