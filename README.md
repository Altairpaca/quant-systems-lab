# Quant Systems Lab — replay correctness and performance seed

**Status: unpublished implementation seed, not a trading platform.** This project tests a narrow quantitative-systems problem: deterministically merge individually ordered feed events using the time at which an event becomes available to the consumer. It includes an independent reference, candidate algorithms, bounded-queue reference behavior, malformed-input tests, synthetic fixtures and raw smoke measurements. No employer data, trading strategy, credentials or brokerage connector is included.

## What is implemented and what is verified

| Component | Implementation | Executed evidence in this handoff |
| --- | --- | --- |
| C++20 replay | Batch stable sort, K-head scan, priority-queue pop/push, root-replacement heap | 200 full-vector differential cases, invalid and integer-limit cases; GCC 14.2 / Clang 17 Release, GCC ASan+UBSan and separate GCC TSan runs passed |
| C++ bounded queue | Mutex/condition-variable blocking reference; close drains, cancel discards | Four producers/two consumers, 40,000 items checked exactly once; close/cancel cases passed |
| Independent CLI conformance | Python integer-key oracle, complete canonical output comparison | Each of GCC and Clang: 18 valid fixtures × 4 C++ methods = 72 successful runs; 7 invalid fixtures rejected |
| Rust replay | Matching reference/scan/BinaryHeap/PeekMut variants; std bounded-channel tests | **Not compiled or executed:** Rust toolchain is absent from the authoring container |
| Cross-language conformance | One script invokes both binaries on identical fixtures and compares full outputs | **Not executed.** The default script exits nonzero when Rust is missing |
| Benchmark | Four patterns × four feed counts × four C++ methods × nine timed repetitions | 576 timed observations, with complete output checks after each run; raw CSV retained |
| GitHub Actions | Proposed portable test, sanitizer and Rust/conformance workflow | **Template only; not executed or attached to a published repository** |

The concurrency tests exercise particular schedules; they are not a proof of linearizability or exhaustive race freedom. No queue-latency benchmark has been executed. The Rust std channel and the C++ queue also have different ownership/close APIs; they are not advertised as an interchangeable cross-language queue contract.

## Build and check

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j2
ctest --test-dir build --output-on-failure
./build/qsl dump fixtures/conformance.tsv heap-replace
python3 tools/crosscheck.py --allow-cpp-only

# Execute these on the server with Rust installed; not yet run in this handoff.
cargo test --manifest-path rust/Cargo.toml
cargo build --release --manifest-path rust/Cargo.toml
python3 tools/crosscheck.py  # fails if either implementation is absent

cmake -S . -B build-asan -DCMAKE_BUILD_TYPE=Debug -DQSL_SANITIZE=ON
cmake --build build-asan -j2
ctest --test-dir build-asan --output-on-failure
cmake -S . -B build-tsan -DCMAKE_BUILD_TYPE=Debug -DQSL_TSAN=ON
cmake --build build-tsan -j2
ctest --test-dir build-tsan --output-on-failure
```

CMake 3.16+, a C++20 compiler, threads and Python 3.10+ suffice for the C++ lane. The Rust manifest declares 1.74, but its minimum-version compatibility has not been verified. Compile/test both that toolchain and stable before calling the declaration a tested support policy. The crate is `publish = false`. Select and record the project's redistribution license before first public publication; third-party source is not vendored here.

## Event and ordering contract

Input rows have six integer fields: `available_ns feed_id sequence venue_ns price_ticks qty`. Unsigned availability time, feed ID and sequence use decimal digits only. Payload fields are signed 64-bit integers. Input feed IDs are limited to 0–4095 as a fixture-loader safety boundary. For each feed, availability time must be nondecreasing and sequence strictly increasing; descending or duplicate sequence is rejected, not repaired. The ordering key is `(available_ns, feed_id, sequence)`.

`venue_ns` is payload and must not override knowledge availability. Feed-ID tie breaking is an explicit deterministic policy, **not a claim of true cross-venue causal ordering**. Integer price/quantity fields are generic payload here, not validated exchange order semantics. Reconnects, sequence resets, duplicate ingestion, session boundaries, out-of-order network data and watermark completeness are future policies, not implicit support.

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

The candidate beats the ordinary heap in these samples, but does not always beat stable sort or scanning. The authoring environment was a shared Linux x86-64 container reporting an AMD EPYC 9V74 and GCC 14.2.0, with CMake Release `-O3 -DNDEBUG`, no CPU pinning and no frequency/thermal isolation. These observations motivate a controlled server experiment; they are not a universal speedup, a C++–Rust comparison or an exchange latency claim. See `evidence/environment.json`, `benchmark-summary.csv`, `raw-bench-*.csv` and `docs/BENCHMARK_PROTOCOL.md`.

## Next acceptance gates

First compile Rust and run the shared full-output oracle. Then investigate the actual consumer before adding a streaming API, order-book simulator or another abstraction. For streaming, require bounded refill and a completeness rule for every feed, queue/backpressure accounting, error propagation and deterministic replay. A future queue optimization must retain the blocking reference and compare equivalent semantics. Do not build a custom lock-free queue solely to advertise lock-free code.

After server verification, create one dedicated repository rather than placing this code in a profile repository, a competition archive or Clausula. Keep raw evidence and counterexamples. No repository, release or upstream PR has been created for this seed in the current handoff.
