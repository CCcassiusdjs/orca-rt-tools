# CPU time of each PE in the stored runs of tag r11-rc9 (VH, VG, VCV, VMA, W4, W5) with the kernel
# work that runs while the idle task holds the CPU (rttools/paper/cputime.py): the tick handler up to
# the next dispatch (measured), and the static WCETs of the injection, receive and release handlers
# that start in an idle slice; windows of phi(v_last) + 1 releases from r_{phi(v_last)}.
#
#   make          analyze and check against reference.json (seconds)
#   make analyze  $(BUILD)/metrics.json and the summary of each run
#   make check    $(BUILD)/metrics.json against reference.json ("match")
#   make clean

PYTHON  ?= python3
BUILD   ?= build
RTTOOLS := ../../orca-rt-tools
RUN      = PYTHONPATH=$(RTTOOLS) $(PYTHON) -m rttools.paper.cputime

.PHONY: all analyze check clean

all: analyze check

analyze:
	$(RUN) analyze --config config.json --out $(BUILD)

check:
	$(RUN) check $(BUILD)/metrics.json reference.json

clean:
	rm -rf $(BUILD)
