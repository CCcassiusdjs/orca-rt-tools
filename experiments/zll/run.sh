#!/bin/sh
# Zero-load latency of the Hermes NoC with GHDL (tb_zll.vhd).
#
#   run.sh <out_dir>
#
# Environment (defaults in parentheses):
#   GHDL    GHDL executable (ghdl)
#   XR, YR  mesh size (8, 3)
#   SRCS    source nodes (0 and XR*YR-1, two opposite corners)
#   PS      payload sizes in flits (1 4 16 64)
#
# For every source, every destination and every payload size, the script
# simulates one packet on the idle mesh and writes <out_dir>/zll.csv:
#   src_x,src_y,dst_x,dst_y,m,p,latency,model,match
# with model = 6(m+1) + p + 1, and <out_dir>/zll_table.txt with the latency
# per (m, p) and, in parentheses, the number of routes. It prints and writes
# <out_dir>/zll_summary.txt and exits with 1 if a point does not match the
# model, a packet does not arrive intact or a simulation gives no result.
set -eu

OUT=${1:?usage: run.sh <out_dir>}
GHDL=${GHDL:-ghdl}
XR=${XR:-8}
YR=${YR:-3}
N=$((XR * YR))
SRCS=${SRCS:-"0 $((N - 1))"}
PS=${PS:-"1 4 16 64"}
HERE=$(cd "$(dirname "$0")" && pwd)
HERMES=$(cd "$HERE/../../pkt-sim/hw/router/hermes" && pwd)

command -v "$GHDL" > /dev/null || { echo "missing $GHDL" >&2; exit 2; }
mkdir -p "$OUT/work"
OUT=$(cd "$OUT" && pwd)
W="$OUT/work"
FLAGS="--workdir=$W -fsynopsys -fexplicit"

for f in Hermes_package Hermes_buffer Hermes_switchcontrol Hermes_crossbar RouterCC TopNOC; do
	$GHDL -a $FLAGS "$HERMES/$f.vhd" > "$W/analysis.log" 2>&1 || { cat "$W/analysis.log" >&2; exit 1; }
done
$GHDL -a $FLAGS "$HERE/tb_zll.vhd"
$GHDL -e $FLAGS tb_zll

CSV="$OUT/zll.csv"
RAW="$OUT/zll_raw.txt"
: > "$RAW"
for s in $SRCS; do
	d=0
	while [ "$d" -lt "$N" ]; do
		for p in $PS; do
			(cd "$W" && $GHDL -r $FLAGS tb_zll -gXR="$XR" -gYR="$YR" -gSRC="$s" -gDST="$d" -gP="$p" \
				--ieee-asserts=disable --stop-time=100us 2>&1) | grep "ZLL " | sed 's/.*ZLL /ZLL /' >> "$RAW"
		done
		d=$((d + 1))
	done
done

echo "src_x,src_y,dst_x,dst_y,m,p,latency,model,match" > "$CSV"
EXPECT=$(( $(echo $SRCS | wc -w) * N * $(echo $PS | wc -w) ))
if awk -v XR="$XR" -v EXPECT="$EXPECT" -v CSV="$CSV" -v TAB="$OUT/zll_table.txt" '
	{
		for (i = 2; i <= NF; i++) { split($i, kv, "="); v[kv[1]] = kv[2] }
		model = 6 * (v["m"] + 1) + v["p"] + 1
		ok = (v["latency"] == model && v["bad"] == 0 && v["flits"] == v["p"] + 2)
		printf "%d,%d,%d,%d,%d,%d,%d,%d,%s\n", v["src"] % XR, int(v["src"] / XR), v["dst"] % XR, int(v["dst"] / XR), \
			v["m"], v["p"], v["latency"], model, ok ? "yes" : "no" >> CSV
		n++; if (ok) good++
		if (v["m"] > mmax) mmax = v["m"]
		key = v["m"] SUBSEP v["p"]
		cnt[key]++
		if (!(key in lmin) || v["latency"] < lmin[key]) lmin[key] = v["latency"]
		if (!(key in lmax) || v["latency"] > lmax[key]) lmax[key] = v["latency"]
		if (!(v["p"] in seenp)) { seenp[v["p"]] = 1; ps[++np] = v["p"] }
	}
	END {
		# latency per (m, p): one value when every route with m hops gives the same latency
		line = "m"
		for (j = 1; j <= np; j++) line = line "\tp=" ps[j]
		print line > TAB
		for (m = 0; m <= mmax; m++) {
			line = m
			for (j = 1; j <= np; j++) {
				key = m SUBSEP ps[j]
				if (!(key in cnt)) cell = "-"
				else if (lmin[key] == lmax[key]) cell = lmin[key] " (" cnt[key] ")"
				else cell = lmin[key] ".." lmax[key] " (" cnt[key] ")"
				line = line "\t" cell
			}
			print line > TAB
		}
		printf "zll: %d of %d points satisfy L0 = 6(m+1) + p + 1 (m = 0 to %d hops)\n", good, EXPECT, mmax
		exit (n == EXPECT && good == n) ? 0 : 1
	}' "$RAW" > "$OUT/zll_check.txt"; then rc=0; else rc=1; fi
{
	echo "Hermes zero-load latency: GHDL $($GHDL --version | head -1 | cut -d' ' -f2), mesh ${XR}x${YR}, sources $SRCS, p in {$PS}"
	echo "m = hops, p = payload flits; latency in cycles from the header at the source to the last flit at the destination"
	echo "latency per (m, p), number of routes in parentheses:"
	cat "$OUT/zll_table.txt"
	cat "$OUT/zll_check.txt"
} > "$OUT/zll_summary.txt"
rm -f "$OUT/zll_check.txt"
cat "$OUT/zll_summary.txt"
exit $rc
