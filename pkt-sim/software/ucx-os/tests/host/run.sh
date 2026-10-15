#!/bin/sh
# Compiles and runs the host tests (gcc, AddressSanitizer, UBSan).
# Usage: tests/host/run.sh [test...]   (default: test_ddma test_noc test_noc_nesting test_weird_a test_car_v
# test_car_full test_car_full_tt test_tick_release test_noc_tt)
# test_car_full (time-triggered application) builds lib/noc.c with -DUCX_NOC_LATEST;
# test_car_full_tt (tick hook with TT_TICK) builds it with -DUCX_NOC_LATEST -DUCX_NOC_TT at the clock of the table;
# test_tick_release (release by tick) builds lib/noc.c and app/weird_a.c with -DUCX_TICK_RELEASE;
# test_noc_nesting is test_noc.c with -DUCX_ISR_NESTING (handlers of the kernel up to r11);
# test_noc_tt (time-triggered injection) builds lib/noc.c and lib/noc_tt.c with -DUCX_NOC_TT.
set -e
H=$(cd "$(dirname "$0")" && pwd)
U=$(cd "$H/../.." && pwd)
OUT=${OUT:-$H/build}
mkdir -p "$OUT"
CFLAGS="-std=gnu11 -g -O0 -no-pie -fno-pie -fsanitize=address,undefined -fno-sanitize-recover=all -Wno-format"
SRC="$H/stubs.c $U/device/ddma.c $U/lib/noc.c $U/lib/noc_tt.c $U/lib/queue.c"
for t in ${*:-test_ddma test_noc test_noc_nesting test_weird_a test_car_v test_car_full test_car_full_tt test_tick_release test_noc_tt}; do
	DEFS=
	C=$t
	[ "$t" = test_car_full ] && DEFS=-DUCX_NOC_LATEST
	[ "$t" = test_car_full_tt ] && DEFS="-DUCX_NOC_LATEST -DUCX_NOC_TT -DF_CPU=477952000"
	[ "$t" = test_tick_release ] && DEFS=-DUCX_TICK_RELEASE
	[ "$t" = test_noc_nesting ] && { DEFS=-DUCX_ISR_NESTING; C=test_noc; }
	[ "$t" = test_noc_tt ] && DEFS=-DUCX_NOC_TT
	gcc $CFLAGS $DEFS -I"$H/stub" -I"$H" -I"$U/include" $SRC "$H/$C.c" -o "$OUT/$t"
	ASAN_OPTIONS=detect_leaks=0 "$OUT/$t"
done
