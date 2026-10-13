#!/bin/bash
# Simulates the experiment of Ch. 8 (application E, weird_a.c) with
# ModelSim/Questa and writes the transcript and the extracted events.
#
#   simulate.sh <out_dir> [<sim_ns> [<app> [<mesh>]]]
#
# <sim_ns>: time of manycore_top in ns (default 20000000 = 20 ms).
# <app>:    application of pkt-sim/software/ucx-os (Makefile target and
#           app/<app>.c; default weird_a, application E of run F). An
#           application of rttools.ucxgen has app/<app>.sim with MESH and
#           RELEASE_MASK, which this script passes to manycore_top
#           (vsim -g).
# <mesh>:   WxH of manycore_top (NOC_DIM_X x NOC_DIM_Y); default MESH of
#           app/<app>.sim, otherwise 2x2.
# With the defaults (weird_a, 2x2, no app/weird_a.sim) the vsim command is
# the one of run F (tag exp23-F): no -g option.
# The script copies pkt-sim to <out_dir>/pkt-sim, builds the software there
# (riscv64-elf toolchain, ARCH=riscv/hf-riscv-e), adds the packet monitor
# (rtl/pe_checker.sv, rtl/chk_binds.sv) and runs vsim in batch mode.
#
# Environment:
#   ENV_SETUP   shell commands run before the builds and vsim, e.g.
#               "module load riscv64-elf/12.2.0 questa/2025.3"
#   MONITOR     1 (default) binds the packet monitor; 0 runs without it
#               (then the log has no $printtimescale lines; pass --unit to
#               the analysis)
#   RELEASE_MASK
#               overrides the value of app/<app>.sim (release generator of
#               manycore_pe.sv: bit k of the mask, decimal, = PE with node
#               index k = y * W + x)
#   REQUIRE_CLEAN
#               1 stops before the build unless the source is a clean git
#               checkout at a tag or a `git archive` of a commit (see
#               RUN_INFO below); use it for the run that a paper reports
#
# Outputs in <out_dir>: sim.log (transcript), events.txt (lines used by
# the analysis), build_sw.log, build_boot.log, time.log, RUN_INFO.
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
#                sources (pkt-sim, rtl/, simulate.sh), relative to the
#                repository root; identifies the input also in a copy
#                without git
set -euo pipefail

OUT=${1:?usage: simulate.sh <out_dir> [<sim_ns> [<app> [<mesh>]]]}
SIM_NS=${2:-20000000}
APP=${3:-weird_a}
MESH_ARG=${4:-}
MONITOR=${MONITOR:-1}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

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
rm -rf "$OUT/pkt-sim"
cp -a "$REPO/pkt-sim" "$OUT/pkt-sim"
mkdir -p "$OUT/pkt-sim/logs"

( cd "$OUT/pkt-sim/software/ucx-os" && make -s ARCH=riscv/hf-riscv-e incl && make -s "$APP" ) \
	> "$OUT/build_sw.log" 2>&1 || { tail -20 "$OUT/build_sw.log" >&2; echo "build of $APP failed" >&2; exit 4; }
( cd "$OUT/pkt-sim/software/hfrisc-software" && make -s boot_sim ) > "$OUT/build_boot.log" 2>&1

SIM="$OUT/pkt-sim/manycore_modelsim"
cd "$SIM"
# sim.do of the repository up to the vsim command, then this run
sed -n '1,/^vsim /p' sim.do | sed '$d' > run.do
if [ "$MONITOR" = 1 ]; then
	cat >> run.do <<EOD
vlog -mixedsvvh -sv -work work $HERE/rtl/pe_checker.sv
vlog -mixedsvvh -sv -work work $HERE/rtl/chk_binds.sv
vsim -c work.manycore_top work.chk_binds +RUN_NS=$SIM_NS$APP_GENERICS
quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1
run -all
quit -f
EOD
else
	cat >> run.do <<EOD
vsim -c work.manycore_top$APP_GENERICS
quietly set StdArithNoWarnings 1
quietly set StdVitalGlitchNoWarnings 1
run ${SIM_NS}ns
quit -f
EOD
fi

{
	echo "sim_ns=$SIM_NS monitor=$MONITOR"
	echo "app=$APP mesh=${DIM_X}x${DIM_Y} generics=${APP_GENERICS# }"
	echo "vsim=$(vsim -version 2>/dev/null | head -1)"
	echo "gcc=$(riscv64-elf-gcc --version | head -1)"
	echo "date=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$OUT/RUN_INFO"

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
echo "events: $(grep -c . "$OUT/events.txt") lines; $(head -2 "$OUT/RUN_INFO" | tr '\n' ' ')"
