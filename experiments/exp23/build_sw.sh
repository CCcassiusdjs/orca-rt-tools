#!/bin/bash
# Builds the software of the experiment of Ch. 8 (application E, weird_a.c,
# or the application APP) the way simulate.sh does: copies pkt-sim to
# <out_dir>/pkt-sim and builds ucx-os (ARCH=riscv/hf-riscv-e) and the boot
# code there.
#
#   build_sw.sh <out_dir>
#
# Environment:
#   ENV_SETUP   shell commands run before the build, e.g.
#               "module load riscv64-elf/12.2.0"
#   UCX_CFLAGS  extra compiler flags for ucx-os (empty by default, the
#               build of simulate.sh). -DUCX_NO_INSTRUMENTATION removes the
#               writes to the instrumentation registers (device/cacc.h);
#               `make software` builds both variants for the bound of the
#               instrumentation cost (rttools/paper/instrumentation.py)
#   APP         application of pkt-sim/software/ucx-os (Makefile target and
#               app/<APP>.c; default weird_a, application E of run F)
#   F_CLK, F_TICK
#               clock and tick of the software in Hz (make F_CLK= F_TICK=;
#               unset: the defaults of arch.mak, 500000000 and 2000, the
#               build of run F); simulate.sh passes the clock of the run
#
# Outputs in <out_dir>: pkt-sim/ (sources and build), build_sw.log,
# build_boot.log, gcc.txt (first line of riscv64-elf-gcc --version). The
# image of ucx-os is pkt-sim/software/ucx-os/build/target/image.elf, with
# the listing of the build (objdump --disassemble -Mno-aliases) in
# image.lst.
set -euo pipefail

OUT=${1:?usage: build_sw.sh <out_dir>}
APP=${APP:-weird_a}
[[ "$APP" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || { echo "invalid application name: $APP" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)

if [ -n "${ENV_SETUP:-}" ]; then
	set +u
	eval "$ENV_SETUP" > /dev/null 2>&1
	set -u
fi
for tool in riscv64-elf-gcc make; do
	command -v "$tool" > /dev/null || { echo "missing $tool (set ENV_SETUP)" >&2; exit 2; }
done

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
rm -rf "$OUT/pkt-sim"
cp -a "$REPO/pkt-sim" "$OUT/pkt-sim"
mkdir -p "$OUT/pkt-sim/logs"

if [ -n "${UCX_CFLAGS:-}" ]; then
	set -- CC="riscv64-elf-gcc $UCX_CFLAGS"
else
	set --
fi
# clock of the software, for the build of the application only
CLK=()
for v in F_CLK F_TICK; do
	if [ -n "${!v:-}" ]; then
		[[ "${!v}" =~ ^[1-9][0-9]*$ ]] || { echo "$v must be a positive integer: ${!v}" >&2; exit 2; }
		CLK+=("$v=${!v}")
	fi
done
( cd "$OUT/pkt-sim/software/ucx-os" && make -s ARCH=riscv/hf-riscv-e "$@" incl \
	&& make -s "$@" "$APP" ${CLK[@]+"${CLK[@]}"} ) > "$OUT/build_sw.log" 2>&1 \
	|| { tail -20 "$OUT/build_sw.log" >&2; echo "build of $APP failed" >&2; exit 4; }
( cd "$OUT/pkt-sim/software/hfrisc-software" && make -s boot_sim ) > "$OUT/build_boot.log" 2>&1
riscv64-elf-gcc --version | head -1 > "$OUT/gcc.txt"
