# Pipelines that run in seconds, each checked against its stored reference:
#   make          every directory of DIRS (exp23: stored log of run E)
#   make zll      zero-load latency of the Hermes NoC (GHDL, about 30 s)
# Each directory has its own Makefile with the long targets (CAR, all
# graphs of Table 7.1, Questa simulation of exp23).

PYTHON ?= python3
GHDL   ?= ghdl
DIRS   := ch7 exp23
DIRS   += ch6# anon:drop-line

.PHONY: all clean zll $(DIRS)

all: $(DIRS)

$(DIRS):
	$(MAKE) -C $@ PYTHON=$(PYTHON)

zll:
	$(MAKE) -C zll GHDL=$(GHDL)

clean:
	for d in $(DIRS) zll; do $(MAKE) -C $$d clean; done
