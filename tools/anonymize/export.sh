#!/bin/bash
# Anonymized copy of the repository for double-anonymous review.
#
#   export.sh <out_dir> [<ref>]
#
# Writes the tree of commit <ref> (default HEAD) to <out_dir> with
# `git archive` (no history, no uncommitted change), applies the rules of
# anonymize.py and searches the copy for identifying strings. The report
# goes to <out_dir>.report.txt (outside the copy).
#
# Environment:
#   FORCE=1          replace a non-empty <out_dir>
#   CHECK_PYTHON     interpreter with orca-rt-tools/requirements.txt: runs
#                    `make -C experiments` in the copy, requires `match` from
#                    every pipeline and no thesis output, then cleans the builds
#   CHECK_TESTS=1    with CHECK_PYTHON, also runs pytest in the copy
#
# Exit code: 0 when the copy has no unexpected identifying string and the
# checks pass; 1 otherwise (the copy stays for inspection).
set -euo pipefail

OUT=${1:?usage: export.sh <out_dir> [<ref>]}
REF=${2:-HEAD}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(git -C "$HERE" rev-parse --show-toplevel)
PY=${PYTHON3:-python3}

if [ -e "$OUT" ] && [ -n "$(ls -A "$OUT" 2>/dev/null)" ]; then
	[ "${FORCE:-0}" = 1 ] || { echo "$OUT is not empty (FORCE=1 replaces it)" >&2; exit 2; }
	rm -rf "$OUT"
fi
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
REPORT="$OUT.report.txt"

commit=$(git -C "$REPO" rev-parse --verify "$REF^{commit}")
if [ "$REF" = HEAD ] && [ -n "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]; then
	echo "note: the work tree has uncommitted changes; the copy holds HEAD only" >&2
fi
git -C "$REPO" archive --format=tar "$commit" | tar -x -C "$OUT"

{
	echo "anonymized export of $REF"
	echo "== apply"
	"$PY" -I "$HERE/anonymize.py" apply "$OUT" --repo "$REPO" --overlay "$HERE/overlay"
	echo "== verify"
} > "$REPORT"
rc=0
"$PY" -I "$HERE/anonymize.py" verify "$OUT" --repo "$REPO" >> "$REPORT" || rc=1

if [ -n "${CHECK_PYTHON:-}" ]; then
	echo "== check (make -C experiments)" >> "$REPORT"
	(cd "$OUT" && find . -type f | LC_ALL=C sort) > "$OUT.files"
	(cd "$OUT" && find . -type d | LC_ALL=C sort) > "$OUT.dirs"
	if make -C "$OUT/experiments" PYTHON="$CHECK_PYTHON" > "$OUT.make.log" 2>&1; then
		echo "make: $(grep -c '^match$' "$OUT.make.log") pipelines print match" >> "$REPORT"
	else
		echo "make: FAILED (see $OUT.make.log)" >> "$REPORT"; rc=1
	fi
	leaks=$(cd "$OUT/experiments" && { find . -path '*/build/*' -iname '*thesis*'; \
		grep -rl --include=metrics.json -i '"thesis' . || true; })
	if [ -n "$leaks" ]; then
		echo "thesis outputs in the builds:" >> "$REPORT"; echo "$leaks" >> "$REPORT"; rc=1
	else
		echo "thesis outputs in the builds: none" >> "$REPORT"
	fi
	if [ "${CHECK_TESTS:-0}" = 1 ]; then
		if (cd "$OUT/orca-rt-tools" && PYTHONPATH="$OUT/orca-rt-tools" "$CHECK_PYTHON" -m pytest -q -p no:cacheprovider) \
			> "$OUT.pytest.log" 2>&1; then
			echo "pytest: $(tail -1 "$OUT.pytest.log")" >> "$REPORT"
		else
			echo "pytest: FAILED: $(tail -1 "$OUT.pytest.log") (see $OUT.pytest.log)" >> "$REPORT"; rc=1
		fi
	fi
	# remove every file and directory that the checks created
	(cd "$OUT" && find . -type f | LC_ALL=C sort | comm -13 "$OUT.files" - | while IFS= read -r f; do rm -f "$f"; done)
	(cd "$OUT" && find . -type d | LC_ALL=C sort | comm -13 "$OUT.dirs" - | LC_ALL=C sort -r \
		| while IFS= read -r d; do rmdir "$d" 2>/dev/null || true; done)
	rm -f "$OUT.files" "$OUT.dirs"
fi

grep -E "^(identifying strings|removed thesis|word 'thesis'|make:|thesis outputs|pytest:)" "$REPORT"
echo "report: $REPORT"
exit $rc
