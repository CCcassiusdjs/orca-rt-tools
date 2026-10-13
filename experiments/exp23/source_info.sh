#!/bin/bash
# Writes the source identification of a simulation run (first lines of
# RUN_INFO; simulate.sh documents the fields).
#
#   source_info.sh <repo_root> <run_info> [<status_file>]
#
# <run_info> is overwritten. With git and changes, <status_file> receives
# `git status --porcelain`.
set -euo pipefail

REPO=$(cd "${1:?usage: source_info.sh <repo_root> <run_info> [<status_file>]}" && pwd -P)
INFO=${2:?usage: source_info.sh <repo_root> <run_info> [<status_file>]}
STATUS=${3:-/dev/null}
HERE=$(cd "$(dirname "$0")" && pwd -P)
SOURCES=(pkt-sim experiments/exp23/rtl experiments/exp23/simulate.sh experiments/exp23/build_sw.sh)

commit=unknown
state=nogit
tag=none
# git only counts when REPO itself is the root of a work tree (a copy of
# the repository inside another repository, or a worktree whose .git file
# points to a missing directory, falls through to VERSION)
top=$(git -C "$REPO" rev-parse --show-toplevel 2>/dev/null || true)
if [ -n "$top" ] && [ "$(cd "$top" && pwd -P)" = "$REPO" ]; then
	commit=$(git -C "$REPO" rev-parse HEAD)
	changes=$(git -C "$REPO" status --porcelain --untracked-files=normal)
	if [ -n "$changes" ]; then
		state=dirty
		printf '%s\n' "$changes" > "$STATUS"
	else
		state=clean
	fi
	tag=$(git -C "$REPO" describe --tags --exact-match HEAD 2>/dev/null || echo none)
	files() { git -C "$REPO" ls-files -co --exclude-standard -- "${SOURCES[@]}"; }
else
	# VERSION carries $Format:%H$, which `git archive` replaces (export-subst)
	v=$(sed -n 's/^commit=//p' "$HERE/VERSION" 2>/dev/null || true)
	if [[ "$v" =~ ^[0-9a-f]{40}$ ]]; then
		commit=$v
		state=archive
		d=$(sed -n 's/^describe=//p' "$HERE/VERSION")
		# describe gives the bare tag only when the commit is tagged
		if [ -n "$d" ] && [[ ! "$d" =~ -[0-9]+-g[0-9a-f]+$ ]]; then tag=$d; fi
	fi
	files() { (cd "$REPO" && find "${SOURCES[@]}" -type f); }
fi

src=$(cd "$REPO" && files | LC_ALL=C sort | while IFS= read -r f; do
	if [ -f "$f" ]; then sha256sum "$f"; fi
done | sha256sum | cut -d' ' -f1)

{
	echo "repo_commit=$commit"
	echo "repo_state=$state"
	echo "repo_tag=$tag"
	echo "src_sha256=$src"
} > "$INFO"
