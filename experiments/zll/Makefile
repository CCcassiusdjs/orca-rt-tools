# Zero-load latency of the Hermes NoC (GHDL).
#
#   make        same as make zll
#   make zll    8x3 mesh from two opposite corners to every node, p in {1, 4, 16, 64};
#               2x2 mesh (the platform of exp23) from every node to every node
#   make contention  header wait at one router: 3x3 mesh, five packets that cross
#               router 4 on disjoint links, 2624 runs (subsets, injection offsets,
#               p in {1, 4, 16, 64}); check against reference_contention.json
#               (about 2 to 5 min)
#   make check  zll and contention
#   make clean
#
# Outputs in $(BUILD)/<mesh>/: zll.csv (one line per packet), zll_table.txt
# (latency per hop count m and payload size p) and zll_summary.txt. The
# target fails if a measured latency differs from L0 = 6(m+1) + p + 1.
# Outputs in $(BUILD)/contention/: contention.csv, contention_summary.txt and
# metrics.json. The target fails if a header waits more than 5 cycles per
# competing header, if a flit arrives with an error or if metrics.json differs
# from reference_contention.json.

GHDL   ?= ghdl
PYTHON ?= python3
BUILD  ?= build

.PHONY: all zll contention check clean

all: zll

check: zll contention

zll:
	GHDL=$(GHDL) XR=8 YR=3 SRCS="0 23" PS="1 4 16 64" ./run.sh $(BUILD)/8x3
	GHDL=$(GHDL) XR=2 YR=2 SRCS="0 1 2 3" PS="1 4 16 64" ./run.sh $(BUILD)/2x2

contention:
	$(PYTHON) contention.py $(BUILD)/contention --ghdl $(GHDL) --reference reference_contention.json

clean:
	rm -rf $(BUILD)
