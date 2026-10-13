#!/bin/sh
# Compiles and runs the host tests (gcc, AddressSanitizer, UBSan).
# Usage: tests/host/run.sh [test...]   (default: test_ddma test_noc test_weird_a test_car_v)
set -e
H=$(cd "$(dirname "$0")" && pwd)
U=$(cd "$H/../.." && pwd)
OUT=${OUT:-$H/build}
mkdir -p "$OUT"
CFLAGS="-std=gnu11 -g -O0 -no-pie -fno-pie -fsanitize=address,undefined -fno-sanitize-recover=all -Wno-format"
SRC="$H/stubs.c $U/device/ddma.c $U/lib/noc.c $U/lib/queue.c"
for t in ${*:-test_ddma test_noc test_weird_a test_car_v}; do
	gcc $CFLAGS -I"$H/stub" -I"$H" -I"$U/include" $SRC "$H/$t.c" -o "$OUT/$t"
	ASAN_OPTIONS=detect_leaks=0 "$OUT/$t"
done
