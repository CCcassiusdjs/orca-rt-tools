#!/bin/sh
# Checks of the packet monitor with Verilator (no Questa):
#   1. lint of the bind: manycore_top and manycore_pe with the stubs of
#      pkt-sim/tests/rtl/pe_stubs.sv (router, core and peripherals are VHDL
#      in the DUT), pe_checker.sv and chk_binds.sv;
#   2. tb_pe_checker.sv: two PE stubs, synthetic handshakes on the LOCAL
#      ports, FLIT and CHKSUM lines on stdout.
#
#   run.sh [<out_dir>]      (default: experiments/exp23/build/rtl_test)
#
# Prints "lint bind: ok" and the output of the testbench; exits with 1 if a
# step fails. tests/test_exp23_flit_monitor.py checks the FLIT lines.
set -eu
T=$(cd "$(dirname "$0")" && pwd)
RTL=$(cd "$T/.." && pwd)
REPO=$(cd "$T/../../../.." && pwd)
OUT=${1:-$REPO/experiments/exp23/build/rtl_test}
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
PK=$REPO/pkt-sim
HW=$PK/hw
MC=$PK/manycore_modelsim
ST=$PK/tests/rtl
command -v verilator > /dev/null || { echo "missing verilator" >&2; exit 2; }

PE_SRC="$MC/orca_pkg.sv $HW/ddma/interface_router_port.sv $HW/ddma/interface_ddma.sv \
	$HW/memory/interface_memory.sv $HW/memory/dual_port_ram.sv $HW/memory/single_port_ram.sv \
	$HW/ddma/ddma.sv $HW/router/interface_router.sv $HW/cpu/interface_core_rv32e.sv \
	$HW/peripherals/interface_peripherals.sv $HW/tcd/interface_tcd.sv $HW/interface_pe.sv \
	$ST/pe_stubs.sv $MC/manycore_pe.sv $MC/manycore_top.sv"

# 1. bind (top: manycore_top and chk_binds side by side, as in simulate.sh)
printf 'module lint_top;\n  manycore_top manycore_top();\n  chk_binds chk_binds();\nendmodule\n' > "$OUT/lint_top.sv"
# shellcheck disable=SC2086
verilator --lint-only --timing -Wno-fatal -Wno-lint -Wno-style -Wno-TIMESCALEMOD -I"$MC" \
	$PE_SRC "$RTL/pe_checker.sv" "$RTL/chk_binds.sv" "$OUT/lint_top.sv" --top-module lint_top \
	> "$OUT/lint_bind.log" 2>&1 || { cat "$OUT/lint_bind.log" >&2; exit 1; }
if grep -q "%Error" "$OUT/lint_bind.log"; then cat "$OUT/lint_bind.log" >&2; exit 1; fi
echo "lint bind: ok"

# 2. testbench of the flit times
verilator --binary --timing -Wno-fatal -Wno-lint -Wno-style --top-module tb_pe_checker \
	--Mdir "$OUT/obj_tb" -o Vtb_pe_checker "$RTL/pe_checker.sv" "$T/tb_pe_checker.sv" \
	> "$OUT/tb_build.log" 2>&1 || { cat "$OUT/tb_build.log" >&2; exit 1; }
"$OUT/obj_tb/Vtb_pe_checker"
