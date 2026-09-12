# Server benchmark runs — 2026-09-12

Three independent process invocations of `tools/run_bench.py --reps 30` on the operator's
Linux server (Intel Xeon E5-2696 v4, 88 logical CPUs, one NUMA node, `schedutil`, GCC 15.2.0,
CMake Release, no CPU pinning, no thermal/frequency isolation). Each run covers the full
4-pattern × 4-feed matrix with 2 warm-ups and 30 interleaved timed repetitions per
configuration (16 configurations × 4 methods × 30 = 1,920 timed observations per run).

## Contents

| Path | What it is |
| --- | --- |
| `run1/`, `run2/`, `run3/benchmark-summary.csv` | per-configuration summary: median/min/max/stdev ns per emitted event over the 30 interleaved repetitions, plus the fixture SHA-256, the exact generation and bench commands and wall seconds |
| `run1/`, `run2/`, `run3/run-metadata.json` | run id, UTC start, source revision + tree + dirty state, binary SHA-256, compiler, CPU model, affinity, NUMA nodes, scaling governor, repetition/warm-up counts, exact runner command |
| `comparison.csv` | median of the three per-run medians, min/max across runs, and the cross-run spread percent per configuration/method |

## Provenance notes

- Committed copies normalize absolute operator paths (`<repo>`, `<run-dir>`, `python3`); the
  unmodified originals remain in the private handoff package. Values, hashes and timestamps are
  unchanged (see `../README.md` for the substitution table and verification statement).
- All three runs measured the same C++ binary,
  `sha256 a7eed7bcdc8efbbeb4703289af6ed1e543e4bf5919b89a776dad8ce9ae4cfb28`, built from the
  runner/CLI commit series whose dirty paths are recorded in each `run-metadata.json`
  (`cpp/src/main.cpp`, `CMakeLists.txt`, `tools/run_bench.py`, `tools/test_bench_cli.py`,
  `.github/workflows/ci.yml`); the same content is committed in this repository's history.
  The runs predate the commit, so each metadata file reports `source_dirty: true` with the
  exact dirty paths — the binary hash is the binding identifier for the measured code.
- Per-repetition raw CSVs (120 rows each) are retained in the operator's local evidence store
  (`_workspace/evidence/qsl/20260912-bench/run{1,2,3}/raw-bench-*.csv`) and are exactly
  reproducible from the recorded binary hash, fixture SHA-256 and commands; they are not
  duplicated here to keep the repository reviewable.
- `tools/run_bench.py` regenerates the large fixtures deterministically and deletes them after
  hashing, so the recorded `fixture_sha256` plus `generate_command` reconstruct every input.

## Limits (read before quoting any number)

- Batch elapsed time normalized per emitted event; **not** per-event latency, not a p99, and
  not an exchange/network measurement.
- The host is shared and unpinned; cross-run spread reaches 47% on small-K configurations
  (absolute values are single-digit nanoseconds there) and 43% for `scan` at K=64. Only large
  factor differences are actionable here.
- Numbers from this server are not comparable with the authoring container's earlier table
  (different CPU and compiler); each environment keeps its own table.
- `skew` intentionally changes the actual event total; use the recorded
  `events` column, never an assumed constant N.
