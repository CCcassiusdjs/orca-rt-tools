# Reproduction of the thesis results that run in seconds (Ch. 6, 7 and 8).
# Each directory has its own Makefile with the long targets (CAR, all
# graphs of Table 7.1, Questa simulation of Ch. 8).

PYTHON ?= python3
DIRS   := ch6 ch7 exp23

.PHONY: all clean $(DIRS)

all: $(DIRS)

$(DIRS):
	$(MAKE) -C $@ PYTHON=$(PYTHON)

clean:
	for d in $(DIRS); do $(MAKE) -C $$d clean; done
