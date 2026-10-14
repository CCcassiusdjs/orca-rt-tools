#!/bin/bash
# Simulates the experiment of Ch. 8 (application E, weird_a.c) with
# ModelSim/Questa and writes the transcript and the extracted events.
#
#   simulate.sh <out_dir> [<sim_ns> [<app> [<mesh>]]]
#
# <sim_ns>: time of manycore_top in ns (default 20000000 = 20 ms). The
# clock runs at or above F_CLK, so <sim_ns> covers at least <sim_ns> of
# platform time (cycles / F_CLK).
# <app>:    application of pkt-sim/software/ucx-os (Makefile target and
#           app/<app>.c; default weird_a, application E of run F). An
#           application of rttools.ucxgen has app/<app>.sim with MESH and
#           RELEASE_MASK, which this script passes to manycore_top
#           (vsim -g).
# <mesh>:   WxH of manycore_top (NOC_DIM_X x NOC_DIM_Y); default MESH of
#           app/<app>.sim, otherwise 2x2.
# app/weird_a.sim (release by tick: RELEASE_MASK=15) gives the default
# application its mask; the application of runs A to H is weird_a_data
# (no setup file: 2x2, no -g option at 500 MHz, the vsim command of run F,
# tag exp23-F). TICK_RELEASE=1 in app/<app>.sim marks an application with
# the release by tick (pkt-sim/software/ucx-os/lib/tick_release.c);
# RUN_INFO then has release=tick, otherwise release=data.
# The script copies pkt-sim to <out_dir>/pkt-sim, builds the software there
# (build_sw.sh: riscv64-elf toolchain, ARCH=riscv/hf-riscv-e), adds the packet monitor
# (rtl/pe_checker.sv, rtl/chk_binds.sv) and runs vsim in batch mode.
#
# Environment:
#   ENV_SETUP   shell commands run before the builds and vsim, e.g.
#               "module load riscv64-elf/12.2.0 questa/2025.3"
#   MONITOR     1 (default) binds the packet monitor; 0 runs without it
#               (then the log has no $printtimescale lines; pass --unit to
#               the analysis)
#   F_CLK       clock frequency in Hz (default 500000000, run F). The
#               script derives from it, for the build and for vsim:
#               F_CLK and F_TICK = 1 / RELEASE_NS of the software
#               (arch.mak; tick of F_CLK / F_TICK cycles, hal.c);
#               CLOCK_HALF_PERIOD_FS = floor(1e15 / (2 F_CLK)) of
#               manycore_top.sv (timescale 1ns/1fs; the clock runs at
#               1e15 / (2 CLOCK_HALF_PERIOD_FS) Hz, at or above F_CLK);
#               RELEASE_CYCLES = RELEASE_NS F_CLK and WARMUP_CYCLES =
#               WARMUP_NS F_CLK of the release generator (manycore_pe.sv).
#               F_CLK RELEASE_NS / 1e9 must be a multiple of 16 (TIMER1
#               counts steps of 16 cycles): with T = 0.5 ms, F_CLK is a
#               multiple of 32000 Hz. F_CLK below 1 GHz (the analysis
#               recovers the clock edges from $time in ns)
#   RELEASE_NS  release period T of the source task in ns (default 500000,
#               config.json release_period_s)
#   WARMUP_NS   instant of the first release in ns of platform time
#               (default 3000000, config.json warmup_s)
#   RELEASE_MASK
#               overrides the value of app/<app>.sim (release generator of
#               manycore_pe.sv: bit k of the mask, decimal, = PE with node
#               index k = y * W + x)
#   RUN_DO      optional .do file that vsim runs after it loads the design,
#               in place of `run -all` (diagnostic runs that stop at chosen
#               instants and examine signals, e.g.
#               experiments/multiapp/diag_pe.do); RUN_INFO records it
#   VSIM_OPTS   extra options of the vsim command (e.g. -voptargs=+acc,
#               which keeps the internal signals that a RUN_DO examines);
#               RUN_INFO records them
#   ISR_NESTING 1 builds the kernel with -DUCX_ISR_NESTING (build_sw.sh):
#               the handlers enable interrupts before the return of _isr,
#               the image of the runs up to r11; 0 (default) the kernel that
#               leaves them disabled in every handler. RUN_INFO has
#               isr=nesting or isr=no_nesting (a RUN_INFO without the line
#               is of the runs up to r11, isr=nesting)
#   REQUIRE_CLEAN
#               1 stops before the build unless the source is a clean git
#               checkout at a tag or a `git archive` of a commit (see
#               RUN_INFO below); use it for the run that a paper reports
#
# Outputs in <out_dir>: sim.log (transcript), events.txt (lines used by
# the analysis), build_sw.log, build_boot.log, gcc.txt, time.log, RUN_INFO;
# the image of ucx-os and its listing in
# pkt-sim/software/ucx-os/build/target/image.{elf,lst}.
#
# RUN_INFO identifies the source of the run:
#   repo_commit  commit hash: from git when the repository root is a git
#                work tree; from VERSION when the tree comes from
#                `git archive` (export-subst); "unknown" otherwise
#   repo_state   clean (git, no change to tracked files and no untracked
#                file), dirty (git, with changes; `git status --porcelain`
#                goes to RUN_INFO.status), archive (git archive, clean by
#                construction) or nogit (copy without git metadata)
#   repo_tag     tag at the commit (git describe --tags --exact-match), or none
#   src_sha256   SHA-256 of the sorted `sha256sum` lines of the simulated
#                sources (pkt-sim, rtl/, simulate.sh, build_sw.sh), relative to the
#                repository root; identifies the input also in a copy
#                without git
# and the clock of the run (read by rttools.paper.exp23):
#   f_clk_hz, f_tick_hz, clock_half_period_fs, clock_hz_exact,
#   release_cycles, warmup_cycles
# and the release rule of the tasks (rttools.paper.phasecheck):
#   release      tick (TICK_RELEASE=1 in app/<app>.sim) or data
set -euo pipefail

OUT=${1:?usage: simulate.sh <out_dir> [<sim_ns> [<app> [<mesh>]]]}
SIM_NS=${2:-20000000}
APP=${3:-weird_a}
MESH_ARG=${4:-}
MONITOR=${MONITOR:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
F_CLK=${F_CLK:-500000000}
RELEASE_NS=${RELEASE_NS:-500000}
WARMUP_NS=${WARMUP_NS:-3000000}

# clock of the run (before any tool check, so a wrong value stops at once)
for v in F_CLK RELEASE_NS WARMUP_NS; do
	[[ "${!v}" =~ ^[1-9][0-9]*$ ]] || { echo "$v must be a positive integer: ${!v}" >&2; exit 2; }
done
fail_clock() { echo "F_CLK=$F_CLK RELEASE_NS=$RELEASE_NS WARMUP_NS=$WARMUP_NS: $*" >&2; exit 2; }
(( F_CLK < 1000000000 )) || fail_clock "F_CLK must be below 1 GHz"
(( 1000000000 % RELEASE_NS == 0 )) || fail_clock "1e9 / RELEASE_NS (F_TICK) is not an integer"
F_TICK=$(( 1000000000 / RELEASE_NS ))
(( F_CLK * RELEASE_NS % 1000000000 == 0 )) || fail_clock "RELEASE_NS F_CLK is not a whole number of cycles"
RELEASE_CYCLES=$(( F_CLK * RELEASE_NS / 1000000000 ))
(( RELEASE_CYCLES % 16 == 0 )) || fail_clock "release period of $RELEASE_CYCLES cycles is not a multiple of 16 (TIMER1)"
(( F_CLK * WARMUP_NS % 1000000000 == 0 )) || fail_clock "WARMUP_NS F_CLK is not a whole number of cycles"
WARMUP_CYCLES=$(( F_CLK * WARMUP_NS / 1000000000 ))
HALF_FS=$(( 500000000000000 / F_CLK ))
F_EXACT=$(awk -v h="$HALF_FS" 'BEGIN { printf "%.3f", 1e15 / (2 * h) }')
# -g options only for values that differ from the defaults of
# manycore_top.sv (the clock of run F): at 500 MHz the vsim command is the
# one of run F
GENERICS=""
[ "$HALF_FS" != 1000000 ] && GENERICS="$GENERICS -gCLOCK_HALF_PERIOD_FS=$HALF_FS"
[ "$RELEASE_CYCLES" != 250000 ] && GENERICS="$GENERICS -gRELEASE_CYCLES=$RELEASE_CYCLES"
[ "$WARMUP_CYCLES" != 1500000 ] && GENERICS="$GENERICS -gWARMUP_CYCLES=$WARMUP_CYCLES"
echo "clock: F_CLK $F_CLK Hz, half period $HALF_FS fs ($F_EXACT Hz), release every $RELEASE_CYCLES cycles, first at cycle $WARMUP_CYCLES, F_TICK $F_TICK Hz"

# setup of the application (key=value lines of app/<app>.sim; read, not run)
UCX_APP="$REPO/pkt-sim/software/ucx-os/app"
if ! [[ "$APP" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
	echo "invalid application name: $APP" >&2; exit 2
fi
setup() { # setup <key>: value of <key> in app/<app>.sim, or empty
	if [ -f "$UCX_APP/$APP.sim" ]; then
		sed -n "s/^$1=\([0-9x]*\)\$/\1/p" "$UCX_APP/$APP.sim" | tail -1
	fi
}
MESH=${MESH_ARG:-$(setup MESH)}
MESH=${MESH:-2x2}
if ! [[ "$MESH" =~ ^([1-9][0-9]*)x([1-9][0-9]*)$ ]]; then
	echo "invalid mesh: $MESH (WxH)" >&2; exit 2
fi
DIM_X=${BASH_REMATCH[1]}
DIM_Y=${BASH_REMATCH[2]}
R_MASK=${RELEASE_MASK:-$(setup RELEASE_MASK)}
if [ -n "$R_MASK" ] && ! [[ "$R_MASK" =~ ^[1-9][0-9]*$ ]]; then
	echo "invalid RELEASE_MASK: $R_MASK (positive decimal integer)" >&2; exit 2
fi
# -g options only for values that differ from the defaults of manycore_top.sv
APP_GENERICS=""
[ "$DIM_X" != 2 ] && APP_GENERICS="$APP_GENERICS -gNOC_DIM_X=$DIM_X"
[ "$DIM_Y" != 2 ] && APP_GENERICS="$APP_GENERICS -gNOC_DIM_Y=$DIM_Y"
[ -n "$R_MASK" ] && [ "$R_MASK" != 1 ] && APP_GENERICS="$APP_GENERICS -gRELEASE_MASK=$R_MASK"

RUN_CMD="run -all"
VSIM_EXTRA=${VSIM_OPTS:+ $VSIM_OPTS}
if [ -n "${RUN_DO:-}" ]; then
	[ -f "$RUN_DO" ] || { echo "RUN_DO: no file $RUN_DO" >&2; exit 2; }
	RUN_DO=$(cd "$(dirname "$RUN_DO")" && pwd)/$(basename "$RUN_DO")
	RUN_CMD="do $RUN_DO"
fi

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

# source identification (before the build, so a failed build keeps it)
rm -f "$OUT/RUN_INFO.status"
"$HERE/source_info.sh" "$REPO" "$OUT/RUN_INFO" "$OUT/RUN_INFO.status"
if [ "${REQUIRE_CLEAN:-0}" = 1 ]; then
	state=$(sed -n 's/^repo_state=//p' "$OUT/RUN_INFO")
	tag=$(sed -n 's/^repo_tag=//p' "$OUT/RUN_INFO")
	if [ "$state" != archive ] && { [ "$state" != clean ] || [ "$tag" = none ]; }; then
		echo "REQUIRE_CLEAN=1: source is $state, tag $tag (need a clean checkout at a tag or a git archive)" >&2
		exit 3
	fi
fi
# copy of pkt-sim and build of the software (build_sw.sh: application
# $APP) at the clock of the run (F_CLK, F_TICK), always with the
# instrumentation writes (UCX_CFLAGS empty)
APP="$APP" F_CLK="$F_CLK" F_TICK="$F_TICK" UCX_CFLAGS= "$HERE/build_sw.sh" "$OUT"

SIM="$OUT/pkt-sim/manycore_modelsim"
cd "$SIM"
# sim.do of the repository up to the vsim command, then this run
sed -n '1,/^vsim /p' sim.do | sed '$d' > run.do
if [ "$MONITOR" = 1 ]; then
	cat >> run.do <<EOD
vlog -mixedsvvh -sv -work work $HERE/rtl/pe_checker.sv
vlog -mixedsvvh -sv -work work $HERE/rtl/chk_binds.sv
vsim -c work.manycore_top work.chk_binds +RUN_NS=$SIM_NS$GENERICS$APP_GENERICS$VSIM_EXTRA
quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1
$RUN_CMD
quit -f
EOD
else
	cat >> run.do <<EOD
vsim -c work.manycore_top$GENERICS$APP_GENERICS$VSIM_EXTRA
quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1
run ${SIM_NS}ns
quit -f
EOD
fi

{
	echo "sim_ns=$SIM_NS monitor=$MONITOR"
	ALL_GENERICS="$GENERICS$APP_GENERICS"
	echo "app=$APP mesh=${DIM_X}x${DIM_Y} generics=${ALL_GENERICS# }"
	if [ -n "${RUN_DO:-}" ]; then echo "run_do=$RUN_DO"; fi
	if [ -n "${VSIM_OPTS:-}" ]; then echo "vsim_opts=$VSIM_OPTS"; fi
	echo "vsim=$(vsim -version 2>/dev/null | head -1)"
	echo "gcc=$(riscv64-elf-gcc --version | head -1)"
	echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
	echo "f_clk_hz=$F_CLK"
	echo "f_tick_hz=$F_TICK"
	echo "clock_half_period_fs=$HALF_FS"
	echo "clock_hz_exact=$F_EXACT"
	echo "release_cycles=$RELEASE_CYCLES"
	echo "warmup_cycles=$WARMUP_CYCLES"
	if [ "$(setup TICK_RELEASE)" = 1 ]; then echo "release=tick"; else echo "release=data"; fi
	if [ "${ISR_NESTING:-0}" = 1 ]; then echo "isr=nesting"; else echo "isr=no_nesting"; fi
} >> "$OUT/RUN_INFO"

if command -v /usr/bin/time > /dev/null; then
	/usr/bin/time -v vsim -batch -do run.do > "$OUT/sim.log" 2> "$OUT/time.log"
else
	vsim -batch -do run.do > "$OUT/sim.log" 2> "$OUT/time.log"
fi

grep -E "Time scale of|TRIGGER|scheduled|-> TAG|<- TAG| ITER (begin|end) |CHKSUM|FLIT (TX|RX) |^# END at" "$OUT/sim.log" > "$OUT/events.txt" || true
if grep -qE "\*\* (Error|Fatal)" "$OUT/sim.log"; then
	grep -E "\*\* (Error|Fatal)" "$OUT/sim.log" | head -5 >&2
	exit 1
fi
echo "events: $(grep -c . "$OUT/events.txt") lines; $(head -2 "$OUT/RUN_INFO" | tr '\n' ' ')"
