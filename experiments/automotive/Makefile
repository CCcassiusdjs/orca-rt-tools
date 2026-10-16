# Engine-control workload from the application characteristics of Kramer, Ziegenbein and Hamann
# (WATERS 2015) and the analysis flow with the general phase model on the 4x4 mesh, without RTL
# (rttools/paper/automotive.py): the generated CSV, f_CPU and the minimum frequency, the data age
# bound of each cause-effect chain against its end-to-end constraint (the sum of its periods), and
# simulations of each PE with the tick table and execution times between BCET and WCET.
#
#   make          run and check against reference.json (about 10 s)
#   make run      $(BUILD)/metrics.json, $(BUILD)/automotive.csv
#   make check    $(BUILD)/metrics.json against reference.json ("match")
#   make seeds    seeds 1 to 10 of the generator: one row per seed and the ranges ($(BUILD)/seeds/seeds.json;
#                 reference_seeds.json; about 25 min on 2 cores)
#   make setter   minimum frequency of seeds 1 to 10 without the handler charge, with w_NI = 0 and without
#                 the chain constraints ($(BUILD)/setter/setter.json; reference_setter.json; about 45 min)
#   make clean

PYTHON  ?= python3
BUILD   ?= build
RTTOOLS := ../../orca-rt-tools
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.automotive

.PHONY: all run check seeds setter clean

all: run check

run:
	$(RUN) run --config config.json --out $(BUILD)

check:
	$(RUN) check $(BUILD)/metrics.json reference.json

seeds:
	$(RUN) seeds --config config.json --out $(BUILD)/seeds --first 1 --last 10 --jobs 2

setter:
	$(RUN) setter --config config.json --out $(BUILD)/setter --first 1 --last 10 --jobs 2

clean:
	rm -rf $(BUILD)
