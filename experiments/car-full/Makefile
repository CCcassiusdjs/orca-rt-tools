# CAR-full: CAR (apps/shi-2010: 33 tasks, 38 flows, periods 0.04 to 1 s, two
# cycles) on the time scale of CAR-V, with the general phase model of the
# analysis flow (rttools/bench_t/multirate.py).
#
#   make          app + run + check (seconds)
#   make app      compare apps/car-full/car-full.{csv,map} with the generator (fails when they differ)
#   make generate write apps/car-full/car-full.{csv,map} from apps/shi-2010 and config.json
#   make run      CPU test (ORT/BENCH over the hyperperiod), frequency search, network at the clock,
#                 data age of every chain, packets and heap per PE for every candidate of config.json;
#                 outputs in $(BUILD)
#   make check    compare $(BUILD)/metrics.json with reference.json

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
APPS    := $(abspath ../../apps)
ARCH    := $(abspath ../../arch/hermes-4x4.gml)
BUILD   ?= build
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.carfull

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
