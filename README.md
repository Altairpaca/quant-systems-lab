# Quant Systems Lab — replay correctness and performance seed

**Status: server-verified implementation seed heading to its first public repository; not a trading platform.** This project tests a narrow quantitative-systems problem: deterministically merge individually ordered feed events using the time at which an event becomes available to the consumer, and replay L2 price-level updates into observable book state. It includes an independent reference, candidate algorithms, a bounded-queue reference, independent Python oracles for both the replay core and the book consumer, malformed-input tests, synthetic fixtures and raw measurements. No employer data, trading strategy, credentials or brokerage connector is included.

## What is implemented and what is verified

| Component | Implementation | Executed evidence in this handoff |
| --- | --- | --- |
| C++20 replay | Batch stable sort, K-head scan, priority-queue pop/push, root-replacement heap | 200 full-vector differential cases, invalid and integer-limit cases (server GCC 15.2 via ctest); GCC 14.2 / Clang 17 Release, GCC ASan+UBSan and separate GCC TSan runs passed in the authoring container |
| C++ bounded queue | Mutex/condition-variable blocking reference; close drains, cancel discards | Four producers/two consumers, 40,000 items checked exactly once; close/cancel cases passed |
| Independent CLI conformance | Python integer-key oracle, complete canonical output comparison | Server 2026-09-12: C++ and Rust binaries, 18 valid fixtures × 4 methods = 144 invocations byte-equal to the oracle; 7 invalid fixtures rejected (`tools/crosscheck.py`, exit 0) |
| Rust replay | Matching reference/scan/BinaryHeap/PeekMut variants; std bounded-channel tests | Compiled and 13/13 tests pass on stable 1.98.1 and on MSRV 1.74.0; release binary built |
| L2 book consumer | `qsl-rust book FIXTURE`: availability-ordered L2 updates → BBO and every level quantity, session-aware merge | RED→GREEN: `tools/crosscheck_book.py` PASS — 14 valid fixtures byte-equal to the independent oracle (11,638 state lines), 11/11 invalid fixtures rejected with exact exit codes |
| Benchmark runner | Run-id output directories, binary/source-revision hashes, strict argument and metric validation | 30 interleaved repetitions × 3 independent processes on the server (1,920 timed observations per run) with per-repetition full-vector checks; summaries, metadata and cross-run comparison committed |
| GitHub Actions | Portable test, sanitizer and Rust/conformance workflow (`cpp`, `sanitizers`, `rust-and-conformance`, including the `bench_cli` ctest and both crosscheck scripts) | **Template still unexecuted** — the first exact-head run happens after the repository is published |

The concurrency tests exercise particular schedules; they are not a proof of linearizability or exhaustive race freedom. No queue-latency benchmark has been executed. The Rust std channel and the C++ queue also have different ownership/close APIs; they are not advertised as an interchangeable cross-language queue contract.

## Build and check

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure          # replay/queue differential + bench CLI contract
./build/qsl dump fixtures/conformance.tsv heap-replace

cargo test --manifest-path rust/Cargo.toml          # stable 1.98.1 and 1.74 MSRV verified on the server
cargo build --release --manifest-path rust/Cargo.toml
./rust/target/release/qsl-rust book fixtures/book-conformance.tsv
python3 tools/crosscheck.py                         # both languages required; exit 0 = PASS
python3 tools/crosscheck_book.py                    # book consumer vs the independent oracle
python3 tools/run_bench.py --reps 30                # isolated evidence/runs/<run-id> output

cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DQSL_SANITIZE=ON
cmake --build build-asan -j2
ctest --test-dir build-asan --output-on-failure
cmake -S . -B build-tsan -DCMAKE_BUILD_TYPE=Debug -DQSL_TSAN=ON
cmake --build build-tsan -j2
ctest --test-dir build-tsan --output-on-failure
```

CMake 3.16+, a C++20 compiler, threads and Python 3.10+ suffice for the C++ lane. The Rust manifest declares 1.74 and that minimum has now been exercised on the server together with stable; both record as tested support levels in the `rust-and-conformance` job. The crate stays `publish = false`. The project is MIT-licensed (`LICENSE`); no third-party source is vendored.

## Event and ordering contract

Input rows have six integer fields: `available_ns feed_id sequence venue_ns price_ticks qty`. Unsigned availability time, feed ID and sequence use decimal digits only. Payload fields are signed 64-bit integers. Input feed IDs are limited to 0–4095 as a fixture-loader safety boundary. For each feed, availability time must be nondecreasing and sequence strictly increasing; descending or duplicate sequence is rejected, not repaired. The ordering key is `(available_ns, feed_id, sequence)`.

`venue_ns` is payload and must not override knowledge availability. Feed-ID tie breaking is an explicit deterministic policy, **not a claim of true cross-venue causal ordering**. Integer price/quantity fields are generic payload here, not validated exchange order semantics. Reconnects, duplicate ingestion and out-of-order network data remain future policies, not implicit support. The L2 book fixtures extend the format with `session` and `side` columns; their session-reset, gap and duplicate policies and the `(available_ns, feed_id, session, sequence)` order key are specified in `docs/BOOK_CONSUMER.md`.

All implementations currently materialize inputs and output. Their total storage is **O(N)**. Heap selection has O(K) auxiliary storage; this does not make the entire program bounded streaming. There is no order book, OMS, risk engine, durable journal, fill simulator or live trading connector.

## Why four algorithms remain

A full-batch stable sort is a strong practical baseline when all data is already in memory. A head scan may win for a small number of feeds. The ordinary heap incurs pop plus push work per event; the root-replacement candidate uses one downward sift when a sorted feed advances. Removing the ordinary heap or the stable-sort baseline would hide the trade-off the experiment is intended to measure.

### Recorded C++ smoke result, uniform workload

Median elapsed nanoseconds per emitted event, 65,536 events per configuration. This is a batch-throughput normalization, **not per-event latency**.

| Feeds | Full-batch stable sort | Head scan | Ordinary heap | Root replacement |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 21.08 | 2.26 | 22.14 | 13.18 |
| 4 | 28.49 | 19.13 | 35.35 | 15.62 |
| 16 | 38.96 | 76.09 | 49.99 | 26.27 |
| 64 | 40.07 | 274.81 | 58.13 | 43.42 |

The candidate beats the ordinary heap in these samples, but does not always beat stable sort or scanning. The authoring environment was a shared Linux x86-64 container reporting an AMD EPYC 9V74 and GCC 14.2.0, with CMake Release `-O3 -DNDEBUG`, no CPU pinning and no frequency/thermal isolation. These observations motivated a controlled server experiment; they are not a universal speedup, a C++–Rust comparison or an exchange latency claim. See `evidence/environment.json`, `benchmark-summary.csv`, `raw-bench-*.csv` and `docs/BENCHMARK_PROTOCOL.md`.

### Server run, 2026-09-12 — 3 independent processes × 30 interleaved repetitions

Median of the three per-run medians, nanoseconds per emitted event, uniform pattern, 65,536
requested events, Intel Xeon E5-2696 v4 (88 logical CPUs, one NUMA node, `schedutil`), GCC
15.2.0, CMake Release, no CPU pinning:

| Feeds | Full-batch stable sort | Head scan | Ordinary heap | Root replacement |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 80.07 | 8.94 | 36.07 | 25.94 |
| 4 | 66.83 | 18.44 | 37.59 | 18.78 |
| 16 | 68.90 | 83.48 | 48.50 | 24.90 |
| 64 | 69.94 | 321.15 | 63.03 | 35.96 |

The K=1 scan advantage and the mixed K=64 ordering replicate the authoring observation that no
single structure always wins; scan degrades from 8.94 to 321.15 ns/event as K grows while root
replacement stays between 18 and 36. Cross-run spread reaches 47% on small-K configurations and
43% for `scan` at K=64, so only large factor differences are actionable on this shared,
unpinned host. Summaries, metadata and the cross-run comparison are committed under
`evidence/server-2026-09-12/`; per-repetition raw CSVs are retained in the operator's local
evidence store and regenerate exactly from the recorded binary hash, fixture hashes and
commands (see that directory's README). No Rust timing, tail latency, RSS or allocation
measurement is claimed.

## Next acceptance gates

Rust compilation, the shared full-output oracle and the first real consumer (the L2 book replay above) are done. Before adding a streaming API, order-book matcher or another abstraction, require a concrete consumer: bounded refill and a completeness rule for every feed, queue/backpressure accounting, error propagation and deterministic replay. A future queue optimization must retain the blocking reference and compare equivalent semantics. Do not build a custom lock-free queue solely to advertise lock-free code.

Server verification is complete. The next step is the first dedicated public repository with
reviewed PRs (conformance core first, then the book consumer and the hardened runner), keeping
raw evidence and counterexamples; no repository, release or PR existed at the time of writing
and none is auto-merged.
