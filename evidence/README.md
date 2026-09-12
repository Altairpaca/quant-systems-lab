# Evidence index

Raw measurements and test transcripts for this repository. Nothing here is a
performance claim for a different environment than the one recorded in the file, and
nothing here substitutes for the oracle-based conformance suites (`tools/crosscheck.py`,
`tools/crosscheck_book.py`).

## Authoring-container evidence (pre-publication seed)

`benchmark-run.txt`, `benchmark-summary.csv`, `raw-bench-*.csv`, `environment.json`,
`fixture-sha256.txt`, `measured-source-sha256.json`, `cpp-cli-conformance.json`,
`clang-cli-conformance.json`, the `configure-*.txt` and `test-*.txt` transcripts were produced in
the original authoring container (AMD EPYC 9V74, GCC 14.2/Clang 17) before this repository
existed. They are kept as the historical raw record of the seed's 576-sample smoke experiment and
the sanitizer/TSan/Clang test runs. Their timings are not comparable with the server numbers.

## `server-2026-09-12/`

Three independent process runs of `tools/run_bench.py --reps 30` (30 interleaved repetitions × 4
methods × 16 configurations per run) plus `comparison.csv` and per-run `run-metadata.json`. See
that directory's `README.md` for provenance, limits and the raw-CSV location.

## Publication normalization (2026-09-12)

Before first publication, absolute paths belonging to the authoring container or the operator's
home directory were replaced with stable placeholders in the committed copies:

| Original prefix | Placeholder |
| --- | --- |
| `/mnt/data/github-quant-audit/quant-systems-lab` | `<authoring-checkout>` |
| `/home/altair/projects/finance/active/quant-systems-lab` | `<repo>` |
| `/home/altair/projects/_workspace/evidence/qsl/20260912-bench/run{1,2,3}` | `<run-dir>` |
| `/home/altair/.local/opt/miniforge3/bin/python3` | `python3` |

Only those path strings changed: timings, counts, statuses, fixture SHA-256 values and
timestamps are byte-identical, verified by re-parsing every affected CSV/JSON before and after
the substitution. The unmodified originals remain in the private handoff package. Commit ids
quoted inside `server-2026-09-12/*/run-metadata.json` were rewritten once during pre-publication
history normalization; the recorded `source_tree` hashes pin the measured content and are
unchanged.

## Reproducing

Every server run regenerates from its recorded binary SHA-256, fixture SHA-256 values and
commands (see `server-2026-09-12/README.md`). The conformance suites rebuild from source with the
commands in the top-level `README.md`.
