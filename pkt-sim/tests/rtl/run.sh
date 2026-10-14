#!/bin/sh
# RTL tests with open-source simulators (Verilator, GHDL, Icarus).
# Usage: pkt-sim/tests/rtl/run.sh [test...]
# Each test prints "PASS <name>" when it passes.
set -e
T=$(cd "$(dirname "$0")" && pwd)
PK=$(cd "$T/../.." && pwd)
HW=$PK/hw
MC=$PK/manycore_modelsim
OUT=${OUT:-$T/build}
mkdir -p "$OUT"

vl() { # vl <top> <arquivos...>
	top=$1; shift
	verilator --binary -j 0 --timing -Wno-fatal -Wno-lint -Wno-style \
		--x-assign unique --x-initial unique \
		-I"$MC" --top-module "$top" --Mdir "$OUT/obj_$top" -o "V$top" "$@" > "$OUT/$top.build.log" 2>&1 \
		|| { cat "$OUT/$top.build.log"; exit 1; }
	"$OUT/obj_$top/V$top" +verilator+rand+reset+2 +verilator+seed+7
}

ghdl_hermes() { # ghdl_hermes <nome> <generics...>
	name=$1; shift
	W="$OUT/ghdl_hermes"
	mkdir -p "$W"
	for f in Hermes_package Hermes_buffer Hermes_switchcontrol Hermes_crossbar RouterCC TopNOC; do
		ghdl -a --workdir="$W" -fsynopsys -fexplicit "$HW/router/hermes/$f.vhd" 2>/dev/null
	done
	ghdl -a --workdir="$W" -fsynopsys -fexplicit "$T/tb_hermes_local.vhd"
	ghdl -e --workdir="$W" -fsynopsys -fexplicit tb_hermes_local
	(cd "$W" && ghdl -r --workdir="$W" -fsynopsys -fexplicit tb_hermes_local "$@" --stop-time=700ns 2>&1) \
		| grep -E "PASS|FAIL|wrong" | sed 's/.*(report note): //' || true
}

ghdl_timer1() { # ghdl_timer1 <CTC> <expected tick in cycles>
	W="$OUT/ghdl_timer1"
	mkdir -p "$W"
	ghdl -a --workdir="$W" -fsynopsys -fexplicit "$HW/peripherals/peripherals_minimal.vhd"
	ghdl -a --workdir="$W" -fsynopsys -fexplicit "$T/tb_timer1.vhd"
	ghdl -e --workdir="$W" -fsynopsys -fexplicit tb_timer1
	(cd "$W" && ghdl -r --workdir="$W" -fsynopsys -fexplicit tb_timer1 -gCTC="$1" -gEXPECT="$2" 2>&1) \
		| grep -E "TICK|PASS|FAIL" | sed 's/.*(report note): //' || true
}

ghdl_cpu() { # cycles per instruction of the HF-RISC core (tb_cpu_cycles.vhd)
	W="$OUT/ghdl_cpu"
	mkdir -p "$W"
	for f in bshifter alu reg_bank control int_control datapath cpu; do
		ghdl -a --workdir="$W" -fsynopsys -fexplicit "$HW/cpu/core_rv32e/$f.vhd" 2>/dev/null
	done
	ghdl -a --workdir="$W" -fsynopsys -fexplicit "$T/tb_cpu_cycles.vhd"
	ghdl -e --workdir="$W" -fsynopsys -fexplicit tb_cpu_cycles
	(cd "$W" && ghdl -r --workdir="$W" -fsynopsys -fexplicit tb_cpu_cycles -gHEX="$T/cpu_cycles.hex" \
		--stop-time=1ms 2>&1) | grep -E "^(CPI|PASS|FAIL)" || true
}

ghdl_trace() { # cycle trace of wcet_bodies.hex (tb_cpu_trace.vhd): MARK and DONE lines
	W="$OUT/ghdl_trace"
	mkdir -p "$W"
	for f in bshifter alu reg_bank control int_control datapath cpu; do
		ghdl -a --workdir="$W" -fsynopsys -fexplicit "$HW/cpu/core_rv32e/$f.vhd" 2>/dev/null
	done
	ghdl -a --workdir="$W" -fsynopsys -fexplicit "$T/tb_cpu_trace.vhd"
	ghdl -e --workdir="$W" -fsynopsys -fexplicit tb_cpu_trace
	(cd "$W" && ghdl -r --workdir="$W" -fsynopsys -fexplicit tb_cpu_trace -gHEX="${TRACE_HEX:-$T/wcet_bodies.hex}" \
		--stop-time=20ms 2>&1) | grep -E "^(MARK|DONE|TIMEOUT)" || true
}

ghdl_cpu_irq() { # interrupt return of _isr of crt0.s on the HF-RISC core (tb_cpu_irq.vhd)
	W="$OUT/ghdl_cpu_irq"
	mkdir -p "$W"
	for f in bshifter alu reg_bank control int_control datapath cpu; do
		ghdl -a --workdir="$W" -fsynopsys -fexplicit "$HW/cpu/core_rv32e/$f.vhd" 2>/dev/null
	done
	ghdl -a --workdir="$W" -fsynopsys -fexplicit "$T/tb_cpu_irq.vhd"
	ghdl -e --workdir="$W" -fsynopsys -fexplicit tb_cpu_irq
	# MODE 0: handlers leave interrupts disabled (UCX_ISR_NO_NESTING): must pass
	(cd "$W" && ghdl -r --workdir="$W" -fsynopsys -fexplicit tb_cpu_irq -gHEX="$T/cpu_irq.hex" -gMODE=0 \
		-gCOUNT=400 --stop-time=20ms 2>&1) | grep -E "^(PASS|FAIL)" || true
	# MODE 1: handlers enable interrupts before they return (_ei, _interrupt_tick):
	# the second interrupt of a pair corrupts the return; printed as NESTED
	(cd "$W" && ghdl -r --workdir="$W" -fsynopsys -fexplicit tb_cpu_irq -gHEX="$T/cpu_irq.hex" -gMODE=1 \
		-gCOUNT=400 --stop-time=20ms 2>&1) | grep -E "^(PASS|FAIL)" | sed 's/^FAIL/NESTED/; s/^PASS/NESTED-NOT-REPRODUCED/' || true
}

DDMA_SRC="$MC/orca_pkg.sv $HW/ddma/interface_router_port.sv $HW/ddma/interface_ddma.sv \
	$HW/memory/interface_memory.sv $HW/memory/dual_port_ram.sv $HW/ddma/ddma.sv"

PE_SRC="$MC/orca_pkg.sv $HW/ddma/interface_router_port.sv $HW/ddma/interface_ddma.sv \
	$HW/memory/interface_memory.sv $HW/memory/dual_port_ram.sv $HW/memory/single_port_ram.sv \
	$HW/ddma/ddma.sv $HW/router/interface_router.sv $HW/cpu/interface_core_rv32e.sv \
	$HW/peripherals/interface_peripherals.sv $HW/tcd/interface_tcd.sv $HW/interface_pe.sv \
	$T/pe_stubs.sv $MC/manycore_pe.sv"

for t in ${*:-tb_ddma_send tb_ddma_recv tb_hermes_local tb_tcd tb_manycore_pe tb_timer1 tb_release tb_cpu_cycles tb_release_mask tb_release_mask_4x5 tb_cpu_irq}; do
	case $t in
	tb_ddma_*) vl "$t" $DDMA_SRC "$T/$t.sv" ;;
	tb_tcd) vl tb_tcd "$T/legacy_ddma_if.svh" "$HW/tcd/interface_tcd.sv" "$HW/tcd/tcd.sv" "$T/tb_tcd.sv" ;;
	tb_manycore_pe)
		# lint of the read block: no COMBDLY or LATCH in manycore_pe.sv
		verilator --lint-only -Wall -Wno-fatal -I"$MC" --top-module manycore_pe \
			-GMEMORY_WIDTH=32 -GFLIT_WIDTH=32 -GRAM_MSIZE=4096 -GBOOT_MSIZE=4096 -GADDRESS=0 \
			-GINTERLEAVING_GRAIN=10 -GNOC_DIM_X=2 -GNOC_DIM_Y=2 $PE_SRC > "$OUT/pe_lint.log" 2>&1 || true
		if grep -E "Warning-(COMBDLY|LATCH).*manycore_pe.sv" "$OUT/pe_lint.log"; then
			echo "FAIL lint manycore_pe (COMBDLY/LATCH)"
		else
			echo "lint manycore_pe: no COMBDLY or LATCH"
		fi
		mkdir -p "$OUT/pe_run/sim" "$OUT/logs"
		(cd "$OUT/pe_run/sim" && mkdir -p ../logs && vl tb_manycore_pe $PE_SRC "$T/tb_manycore_pe.sv") ;;
	tb_release)
		# release generator of PE 0-0 at 500 MHz and at 435.2 MHz (half period in fs)
		for h in 1000000 1148897; do
			(mkdir -p "$OUT/rel_$h" && cd "$OUT/rel_$h" && OUT="$OUT/rel_$h" vl tb_release $PE_SRC "$T/tb_release.sv" -GHALF_FS=$h)
		done ;;
	tb_release_mask)
		mkdir -p "$OUT/mask_run/sim" "$OUT/mask_run/logs"
		(cd "$OUT/mask_run/sim" && vl tb_release_mask $PE_SRC "$MC/manycore_top.sv" "$T/tb_release_mask.sv") ;;
	tb_release_mask_4x5)
		# 4x5 mesh of the composition of CAR-V and E (experiments/multiapp)
		mkdir -p "$OUT/mask45_run/sim" "$OUT/mask45_run/logs"
		(cd "$OUT/mask45_run/sim" && vl tb_release_mask_4x5 $PE_SRC "$MC/manycore_top.sv" "$T/tb_release_mask_4x5.sv") ;;
	tb_hermes_local)
		ghdl_hermes A -gSRC=4 -gDST=4 -gP=4 -gM=0 -gNAME=A
		ghdl_hermes B -gSRC=0 -gDST=8 -gP=4 -gM=4 -gNAME=B ;;
	tb_timer1)
		# TB_TIMER1_CTC, TB_TIMER1_EXPECT: TIMER1CTC and the expected tick
		# (default: hal.c at 500 MHz and F_TICK = 2000, 250000 cycles)
		ghdl_timer1 "${TB_TIMER1_CTC:-15624}" "${TB_TIMER1_EXPECT:-250000}" ;;
	tb_cpu_cycles) ghdl_cpu ;;
	tb_cpu_trace) ghdl_trace ;;
	tb_cpu_irq) ghdl_cpu_irq ;;
	*) echo "unknown test: $t"; exit 2 ;;
	esac
done
