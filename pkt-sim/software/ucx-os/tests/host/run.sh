#!/bin/sh
# Compiles and runs the host tests (gcc, AddressSanitizer, UBSan).
# Usage: tests/host/run.sh [test...]   (default: test_ddma test_noc test_weird_a test_car_v test_car_full
# test_tick_release)
# test_car_full (time-triggered application) builds lib/noc.c with -DUCX_NOC_LATEST;
# test_tick_release (release by tick) builds lib/noc.c and app/weird_a.c with -DUCX_TICK_RELEASE.
set -e
H=$(cd "$(dirname "$0")" && pwd)
U=$(cd "$H/../.." && pwd)
OUT=${OUT:-$H/build}
mkdir -p "$OUT"
CFLAGS="-std=gnu11 -g -O0 -no-pie -fno-pie -fsanitize=address,undefined -fno-sanitize-recover=all -Wno-format"
SRC="$H/stubs.c $U/device/ddma.c $U/lib/noc.c $U/lib/queue.c"
for t in ${*:-test_ddma test_noc test_weird_a test_car_v test_car_full test_tick_release}; do
	DEFS=
	[ "$t" = test_car_full ] && DEFS=-DUCX_NOC_LATEST
	[ "$t" = test_tick_release ] && DEFS=-DUCX_TICK_RELEASE
	gcc $CFLAGS $DEFS -I"$H/stub" -I"$H" -I"$U/include" $SRC "$H/$t.c" -o "$OUT/$t"
	ASAN_OPTIONS=detect_leaks=0 "$OUT/$t"
done
