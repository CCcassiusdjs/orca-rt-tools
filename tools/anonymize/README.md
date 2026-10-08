# Anonymized export

`export.sh <out_dir> [<ref>]` writes the tree of commit `<ref>` (default `HEAD`) to `<out_dir>` for double-anonymous review and writes the report to `<out_dir>.report.txt`.

| Step | Effect |
|---|---|
| `git archive` | Tracked files of the commit only: no history, no author or committer, no uncommitted change |
| Deletion | `tools/anonymize`, `experiments/ch6` and its code and test, the stored runs A to D of `exp23` and `reference_D.json`, LibreOffice lock files, object files of `porca`, the Maven build output of `kprofiler`, the ModelSim temporary file |
| Overlay | Files of `overlay/` replace files of the tree (`experiments/ch7/README.md`) |
| Markers | Lines between `anon:drop-begin` and `anon:drop-end`, and lines with `anon:drop-line`, leave the copy (in any comment syntax; in Markdown tables, the marker goes inside the last cell as an HTML comment) |
| Comparison with the thesis | `exp23` writes no `thesis.tex`, `thesis.csv` nor `thesis_comparison`; the configuration of `ch7` names the stored values `reference_rows`; `make n16` leaves; tests that read removed files leave |
| Identity | Names, e-mail addresses, user names, host names, site paths, laboratory and institution names of the authors (`IDENTITY` in `anonymize.py`) |
| Commit hashes | Hashes of commits of this repository (7 to 40 hex digits) in documentation, data and code files become `xxxxxxx` |
| Verification | Search of every file, text and binary, for the identifying strings and for commit hashes; hits in third-party headers (`ALLOWED`) are listed apart; exit code 1 on any other hit |

| Variable | Effect |
|---|---|
| `FORCE=1` | Replaces a non-empty `<out_dir>` |
| `CHECK_PYTHON=<python>` | Runs `make -C experiments` in the copy, requires `match`, checks that no build output mentions the thesis, then removes every file the check created |
| `CHECK_TESTS=1` | With `CHECK_PYTHON`, also runs pytest in the copy |

Third-party headers stay: the copyright and author lines of HF-RISC, UCX-OS and the toolchain script (author e-mail address at the institution of the third-party author), and the credit line of the KProfiler about dialog.
