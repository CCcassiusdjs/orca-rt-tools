# Pipelines, each checked against its stored reference:
#   make          every directory of DIRS (exp23 and figures: stored log of
#                 run E; zll: GHDL testbench of the NoC, about 30 s; car-v:
#                 generation of CAR-V and its analysis flow, seconds; car-full:
#                 CAR with four periods and two cycles, general phase model,
#                 about 10 s; wcet: static t(v) against the stored runs H and
#                 CV2, about 1 min)
#   make <dir>    one directory of DIRS, for example make zll
# Each directory has its own Makefile with the long targets (CAR, all
# graphs of Table 7.1, Questa simulation of exp23).

PYTHON ?= python3
GHDL   ?= ghdl
DIRS   := ch7 exp23 figures zll car-v car-full wcet
DIRS   += ch6# anon:drop-line

.PHONY: all clean $(DIRS)

all: $(DIRS)

$(DIRS):
	$(MAKE) -C $@ PYTHON=$(PYTHON) GHDL=$(GHDL)

clean:
	for d in $(DIRS); do $(MAKE) -C $$d clean; done
