SHELL := /bin/bash

OUT_MODULE := $(shell command -v module 2> /dev/null)
OUT_VSIM := $(shell command -v vsim 2> /dev/null)

CMD := 

ifndef OUT_MODULE
	CMD := $(CMD) source /path/to/site-setup.sh ;
endif
ifndef OUT_VSIM
	CMD := $(CMD) module load modelsim ;
endif
CMD := $(CMD) vsim -do sim.do

all:
	$(CMD)


clean: 
	rm -rf ./work
	rm -rf ./modelsim.ini
	rm -rf ./transcript
	rm -rf ./vsim.dbg
	rm -rf ./vsim.wlf
	rm -rf ./vsim_stacktrace.vstf
