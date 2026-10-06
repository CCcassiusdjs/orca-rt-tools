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

DDMA_SRC="$MC/orca_pkg.sv $HW/ddma/interface_router_port.sv $HW/ddma/interface_ddma.sv \
	$HW/memory/interface_memory.sv $HW/memory/dual_port_ram.sv $HW/ddma/ddma.sv"

for t in ${*:-tb_ddma_send tb_ddma_recv}; do
	case $t in
	tb_ddma_*) vl "$t" $DDMA_SRC "$T/$t.sv" ;;
	*) echo "unknown test: $t"; exit 2 ;;
	esac
done
