# Tables 6.5, 6.6 and 6.7 (ORT/FNS, Ch. 6).
#
#   make          Synthetic-Application-D and DCT-Verify (seconds), check against reference.json
#   make car      CAR with PF x 100 (hours; run it on the simulation server)

PYTHON  ?= python3
RTTOOLS := $(abspath ../../orca-rt-tools)
BUILD   ?= build
JOBS    ?= 4
# network-interface model of the link schedule (RTTOOLS_NI,
# orca-rt-tools/rttools/modules/routing/router.py): off, the model of the
# stored references (runs up to tag r11-rc5); the default of rttools (tt)
# is the model of experiments/tt
NI      ?= off
RUN      = RTTOOLS_NI=$(NI) PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.ch6

.PHONY: all run check car clean

all: run check

run:
	$(RUN) run --config config.json --out $(BUILD)/results --jobs $(JOBS)

check:
	$(RUN) check $(BUILD)/results/metrics.json reference.json

car:
	$(RUN) run --config config.json --out $(BUILD)/car --apps car --jobs $(JOBS)

clean:
	rm -rf $(BUILD)
