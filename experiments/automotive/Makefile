# Engine-control workload from the application characteristics of Kramer, Ziegenbein and Hamann
# (WATERS 2015) and the analysis flow with the general phase model on the 4x4 mesh, without RTL
# (rttools/paper/automotive.py): the generated CSV, f_CPU and the minimum frequency, the data age
# bound of each cause-effect chain against its end-to-end constraint (the sum of its periods), and
# simulations of each PE with the tick table and execution times between BCET and WCET.
#
#   make          run and check against reference.json (about 10 s)
#   make run      $(BUILD)/metrics.json, $(BUILD)/automotive.csv
#   make check    $(BUILD)/metrics.json against reference.json ("match")
#   make clean

PYTHON  ?= python3
BUILD   ?= build
RTTOOLS := ../../orca-rt-tools
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.automotive

.PHONY: all run check clean

all: run check

run:
	$(RUN) run --config config.json --out $(BUILD)

check:
	$(RUN) check $(BUILD)/metrics.json reference.json

clean:
	rm -rf $(BUILD)
