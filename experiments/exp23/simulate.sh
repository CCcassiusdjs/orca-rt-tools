#!/bin/bash
# Simulates the experiment of Ch. 8 (application E, weird_a.c) with
# ModelSim/Questa and writes the transcript and the extracted events.
#
#   simulate.sh <out_dir> [<sim_ns>]
#
# <sim_ns>: time of manycore_top in ns (default 20000000 = 20 ms).
# The script copies pkt-sim to <out_dir>/pkt-sim, builds the software there
# (riscv64-elf toolchain, ARCH=riscv/hf-riscv-e), adds the packet monitor
# (rtl/pe_checker.sv, rtl/chk_binds.sv) and runs vsim in batch mode.
#
# Environment:
#   ENV_SETUP   shell commands run before the builds and vsim, e.g.
#               "source /soft64/source_gaph; module load riscv64-elf/12.2.0 questa/2025.3"
#   MONITOR     1 (default) binds the packet monitor; 0 runs without it
#               (then the log has no $printtimescale lines; pass --unit to
#               the analysis)
#
# Outputs in <out_dir>: sim.log (transcript), events.txt (lines used by
# the analysis), build_sw.log, build_boot.log, time.log, RUN_INFO.
set -euo pipefail

OUT=${1:?usage: simulate.sh <out_dir> [<sim_ns>]}
SIM_NS=${2:-20000000}
MONITOR=${MONITOR:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

if [ -n "${ENV_SETUP:-}" ]; then
	set +u
	eval "$ENV_SETUP" > /dev/null 2>&1
	set -u
fi
for tool in vsim riscv64-elf-gcc make; do
	command -v "$tool" > /dev/null || { echo "missing $tool (set ENV_SETUP)" >&2; exit 2; }
done

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
rm -rf "$OUT/pkt-sim"
cp -a "$REPO/pkt-sim" "$OUT/pkt-sim"
mkdir -p "$OUT/pkt-sim/logs"

( cd "$OUT/pkt-sim/software/ucx-os" && make -s ARCH=riscv/hf-riscv-e incl && make -s weird_a ) \
	> "$OUT/build_sw.log" 2>&1
( cd "$OUT/pkt-sim/software/hfrisc-software" && make -s boot_sim ) > "$OUT/build_boot.log" 2>&1

SIM="$OUT/pkt-sim/manycore_modelsim"
cd "$SIM"
# sim.do of the repository up to the vsim command, then this run
sed -n '1,/^vsim /p' sim.do | sed '$d' > run.do
if [ "$MONITOR" = 1 ]; then
	cat >> run.do <<EOD
vlog -mixedsvvh -sv -work work $HERE/rtl/pe_checker.sv
vlog -mixedsvvh -sv -work work $HERE/rtl/chk_binds.sv
vsim -c work.manycore_top work.chk_binds +RUN_NS=$SIM_NS
quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1
run -all
quit -f
EOD
else
	cat >> run.do <<EOD
vsim -c work.manycore_top
quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1
run ${SIM_NS}ns
quit -f
EOD
fi

{
	echo "repo_commit=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)$(git -C "$REPO" diff --quiet 2>/dev/null || echo -dirty)"
	echo "sim_ns=$SIM_NS monitor=$MONITOR"
	echo "vsim=$(vsim -version 2>/dev/null | head -1)"
	echo "gcc=$(riscv64-elf-gcc --version | head -1)"
	echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$OUT/RUN_INFO"

if command -v /usr/bin/time > /dev/null; then
	/usr/bin/time -v vsim -batch -do run.do > "$OUT/sim.log" 2> "$OUT/time.log"
else
	vsim -batch -do run.do > "$OUT/sim.log" 2> "$OUT/time.log"
fi

grep -E "Time scale of|TRIGGER|scheduled|-> TAG|<- TAG|CHKSUM|^# END at" "$OUT/sim.log" > "$OUT/events.txt" || true
if grep -qE "\*\* (Error|Fatal)" "$OUT/sim.log"; then
	grep -E "\*\* (Error|Fatal)" "$OUT/sim.log" | head -5 >&2
	exit 1
fi
echo "events: $(grep -c . "$OUT/events.txt") lines; $(cat "$OUT/RUN_INFO" | head -1)"
