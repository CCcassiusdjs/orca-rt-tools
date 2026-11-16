# Pipelines, each checked against its stored reference:
#   make          every directory of DIRS (exp23 and figures: stored log of
#                 run E, and exp23 check-run: runs TG, TH, UG, UH, VG and VH; zll: GHDL testbench of the NoC, about 30 s; car-v:
#                 generation of CAR-V and its analysis flow, seconds; car-full:
#                 CAR with four periods and two cycles, general phase model,
#                 about 10 s; wcet: static t(v) against the stored runs H and
#                 CV2, about 1 min)
#   make <dir>    one directory of DIRS, for example make zll
# Each directory has its own Makefile with the long targets (CAR, all
# random graphs of Section 5 of the paper, Questa simulation of exp23).

PYTHON ?= python3
GHDL   ?= ghdl
DIRS   := ch7 exp23 figures zll car-v car-full wcet
DIRS   += ch6# anon:drop-line
# multiapp: CAR-V and application E on one NoC (rttools.multiapp), about 20 s
DIRS   += multiapp
# tt: model of the runs of round r11g (time-triggered injection, defaults of rttools), seconds
DIRS   += tt
# cputime: CPU time of the stored runs with the kernel work in idle slices, seconds
DIRS   += cputime
# car-v-rtl: analysis of the stored RTL runs of CAR-V (CV, CV2, TCV, UCV, VCV), about 10 s
DIRS   += car-v-rtl
# ablation: terms of the flow and the event-triggered baseline (reads the job tables of exp23, wcet,
# multiapp and car-v-rtl for the beta of the runs), about 1 min
DIRS   += ablation
# automotive: engine-control workload (Kramer et al., WATERS 2015), general phase model, about 10 s
DIRS   += automotive

.PHONY: all clean $(DIRS)

all: $(DIRS)

# exp23: also the stored runs TG, TH, UG, UH, VG and VH of the release by tick (check-run)
$(DIRS):
	$(MAKE) -C $@ PYTHON=$(PYTHON) GHDL=$(GHDL) $(if $(filter exp23,$@),all check-run)

# ablation reads the job tables of the runs (beta of the runs) that these directories build
ablation: exp23 wcet multiapp car-v-rtl

clean:
	for d in $(DIRS); do $(MAKE) -C $$d clean; done
