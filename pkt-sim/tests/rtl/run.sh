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

DDMA_SRC="$MC/orca_pkg.sv $HW/ddma/interface_router_port.sv $HW/ddma/interface_ddma.sv \
	$HW/memory/interface_memory.sv $HW/memory/dual_port_ram.sv $HW/ddma/ddma.sv"

for t in ${*:-tb_ddma_send tb_ddma_recv tb_hermes_local tb_tcd tb_manycore_pe tb_timer1}; do
	case $t in
	tb_ddma_*) vl "$t" $DDMA_SRC "$T/$t.sv" ;;
	tb_tcd) vl tb_tcd "$T/legacy_ddma_if.svh" "$HW/tcd/interface_tcd.sv" "$HW/tcd/tcd.sv" "$T/tb_tcd.sv" ;;
	tb_manycore_pe)
		PE_SRC="$MC/orca_pkg.sv $HW/ddma/interface_router_port.sv $HW/ddma/interface_ddma.sv \
			$HW/memory/interface_memory.sv $HW/memory/dual_port_ram.sv $HW/memory/single_port_ram.sv \
			$HW/ddma/ddma.sv $HW/router/interface_router.sv $HW/cpu/interface_core_rv32e.sv \
			$HW/peripherals/interface_peripherals.sv $HW/tcd/interface_tcd.sv $HW/interface_pe.sv \
			$T/pe_stubs.sv $MC/manycore_pe.sv"
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
	tb_hermes_local)
		ghdl_hermes A -gSRC=4 -gDST=4 -gP=4 -gM=0 -gNAME=A
		ghdl_hermes B -gSRC=0 -gDST=8 -gP=4 -gM=4 -gNAME=B ;;
	tb_timer1)
		# TB_TIMER1_CTC, TB_TIMER1_EXPECT: TIMER1CTC and the expected tick
		# (default: hal.c at 500 MHz and F_TICK = 2000, 250000 cycles)
		ghdl_timer1 "${TB_TIMER1_CTC:-15624}" "${TB_TIMER1_EXPECT:-250000}" ;;
	*) echo "unknown test: $t"; exit 2 ;;
	esac
done
