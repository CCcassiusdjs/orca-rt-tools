# Model of the runs of round r11g (images with the time-triggered injection): the analysis flow with
# the defaults of rttools, the network-interface model tt (o_i = L0 + 20 (m + 1) + w_NI, RTTOOLS_NI
# unset) and the cost rule max, t(v) = max(CSV, static t(v) of the image of each run, ../wcet/costs/tt),
# for every application of config.json (rttools/paper/ttflow.py).
#
#   make run      per application: costs per task and per PE (source csv or static), f_CPU, f_NoC, the
#                 minimum frequency, the clock of each run (lowest F_CLK at or above the minimum with
#                 the phase a multiple of 16 cycles; E and WCET-E also at 500 MHz), the period P in
#                 cycles, S and F of every task, R_bound (data age of every chain for CAR-full), the
#                 length of the simulation against SIM_NS, the injection table app/<image>_tt.h of each
#                 clock with the costs file; for CAR-FULL also P_min, the utilization-bound frequency, the
#                 phase-rule frequency, chains, flows on one PE, packets per hyperperiod and the largest data
#                 age; into $(BUILD)/metrics.json and $(BUILD)/values.tex (macros \ExpTt...)
#   make check    $(BUILD)/metrics.json against reference.json (default target: run check)
#   make tables   the link schedule and the finish of every job of each run, the tables of the
#                 check of run_r11g.sh (rttools.paper.ttflow tables), into $(BUILD)/tables
#
# The models of the runs up to tag r11-rc5 (stored logs, references of ch6, ch7, figures, exp23,
# car-v, multiapp, wcet and car-full) set the network-interface model off in their own targets
# (NI ?= off, RTTOOLS_NI=$(NI)) and take the costs of the CSV; the analysis of a stored run takes the
# model of its RUN_INFO (injection=tt: tt; otherwise off; rttools/paper/ttcheck.py, run_ni).

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
BUILD   ?= build
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.ttflow

.PHONY: all run check tables clean

all: run check

run:
	$(RUN) run --config config.json --out $(BUILD)

check:
	PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.exp23 check $(BUILD)/metrics.json reference.json

tables:
	$(RUN) tables --config config.json --out $(BUILD)/tables

clean:
	rm -rf $(BUILD)
