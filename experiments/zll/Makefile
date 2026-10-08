# Zero-load latency of the Hermes NoC (GHDL).
#
#   make        same as make zll
#   make zll    8x3 mesh from two opposite corners to every node, p in {1, 4, 16, 64};
#               2x2 mesh (the platform of exp23) from every node to every node
#   make clean
#
# Outputs in $(BUILD)/<mesh>/: zll.csv (one line per packet), zll_table.txt
# (latency per hop count m and payload size p) and zll_summary.txt. The
# target fails if a measured latency differs from L0 = 6(m+1) + p + 1.

GHDL  ?= ghdl
BUILD ?= build

.PHONY: all zll clean

all: zll

zll:
	GHDL=$(GHDL) XR=8 YR=3 SRCS="0 23" PS="1 4 16 64" ./run.sh $(BUILD)/8x3
	GHDL=$(GHDL) XR=2 YR=2 SRCS="0 1 2 3" PS="1 4 16 64" ./run.sh $(BUILD)/2x2

clean:
	rm -rf $(BUILD)
