# Benchmark protocol and acceptance boundary

## 1. Question before metric

The current experiment asks whether replacing a heap root reduces selection overhead when replaying K individually sorted feeds. It does not ask which language is fastest, whether a strategy makes money, or whether a server meets an exchange latency target. A batch merge and a streaming merge have different information and memory contracts; comparisons must state which is being tested.

## 2. Executed batch experiment

`tools/generate.py` generates public synthetic inputs using fixed SplitMix64 seed 1701. Patterns are uniform increments, all-timestamp ties, 64-event bursts, and highly skewed feed sizes. Feed counts are 1, 4, 16 and 64. The requested total is 65,536, divided into a per-feed count. **Skew intentionally changes the actual total**: non-first feeds get only one percent of the per-feed count. Always use the recorded actual event count; never plot skew as a constant-N scaling experiment.

Each method gets two warm-ups and nine timed repetitions. Method order is deterministically randomized between repetitions. Timed code includes merge/output allocation and excludes fixture generation/loading, input validation, output destruction and full-vector checking. Every measured output is compared to the full-batch oracle after timing. The CLI conformance script adds an independent Python integer-key oracle and checks complete canonical output, not just count or a collision-prone digest.

```sh
python3 tools/run_bench.py --patterns uniform ties bursty skew --feeds 1 4 16 64 --total 65536
```

Run from a known clean checkout. The script currently overwrites the top-level `evidence/` smoke results; preserve the supplied evidence before rerunning or use an isolated worktree. A server follow-up should add an explicit run directory and binary/build metadata arguments rather than overwrite history. The large fixtures are deleted after hashing; regenerate with the exact pattern/feed/seed/per-feed count and verify the stored SHA-256.

Raw elapsed nanoseconds are batch elapsed times. Dividing by N estimates batch service cost per event. Percentiles of these batch samples are **not p99 event latency**. Nine runs are a smoke sample, not a narrow confidence interval. Preserve all observations, including slow outliers and cases where the proposed optimization loses.

## 3. Controlled server extension

Record the source revision and dirty state, compiler and standard library, optimization flags, executable hash, kernel, CPU model/topology, NUMA placement, RAM, virtualization, process/thread affinity, governor/turbo state if observable without elevated changes, background load, input hashes, warm-up policy and repetition seed. Do not change system-wide governors, reserve huge pages, install drivers, reboot or run privileged tuning without explicit approval.

Use at least 30 interleaved samples for a chosen stable workload and multiple independent process launches. Report raw samples, medians and dispersion; estimate uncertainty at the independent run level rather than pretending every event is independent. Compare GCC and Clang and the actual supported Rust toolchains. Keep total N fixed for a separate scaling experiment; vary K, skew, ties, record width and input size across cache/RAM boundaries deliberately.

For memory, measure peak resident size and allocations separately from the throughput run. Do not infer O(K) total memory from the heap capacity: the seed owns O(N) input and output. Use allocation counters and `perf stat`/sampling only when available; missing permissions should block those counters, not all correctness or timing work.

A candidate is accepted only when its benefit survives the relevant workload, does not break the exact output contract, and its complexity is justified. If stable sort wins for the real batch consumer, keep it. If one head dominates, investigate a small-K specialization only after measuring it. Avoid optimizing the worst possible reference while omitting strong alternatives.

## 4. Streaming and queue experiments — not yet implemented or measured

Define input completeness before emitting: one head per active feed, an explicit EOF, or a proven watermark. Buffer capacity, producer rate, consumer rate, overflow/drop policy, cancellation, reconnect identity, partial batches and failure propagation are part of the contract. Strict ordering on arbitrary out-of-order arrivals without any completeness bound is not something a heap alone supplies.

For a queue benchmark, specify SPSC/MPSC/MPMC, capacity, payload size, producer/consumer placement, batches, idle behavior and close/cancel semantics. Count attempted, accepted, consumed, rejected and discarded events. Require `accepted = consumed + explicitly_discarded` after quiescence and per-stream ordering where promised. The current C++ queue is a blocking mutex reference; the Rust std channel is not an identical MPMC/close implementation.

Measure sustained throughput and per-event end-to-end latency in different experiments. A latency experiment should record intended release time as well as actual enqueue/dequeue/completion time, so a blocked producer does not hide offered-load delay. State open-loop versus closed-loop operation and include rejected or delayed events in the result. Queueing delay, execution service time, backpressure and transport delay are distinct. Do not claim a tail percentile without adequate event samples and clock-overhead checks.

## 5. Financial correctness oracle

A later order-book/execution slice should use synthetic, redistributable events and explicit exchange/session rules. Assert quantity/position/cash/fee conservation, partial-fill increments, cancel/replace/reject behavior, duplicate-response handling within the chosen protocol, sequence-gap failure, and deterministic recovery. A same-day equity sell rule must not be copied from a futures/crypto engine into an A-share simulator without the appropriate settlement model. No live orders are permitted in this lab.

## 6. ASC/HPC acceptance

First identify the actual competition application, year, source revision/license, input assets and redistribution rights, allowed hardware/power constraints, numerical acceptance and original build/run command. This handoff contains no verified ASC source or official score. Do not label a synthetic replay or standalone matrix multiplication benchmark as an ASC result.

Profile the application before choosing SIMD, layout, tiling, NUMA, OpenMP or MPI work. Separate setup, IO, compute, synchronization and communication. Preserve accepted numerical error criteria and the baseline implementation; time to accepted solution and full-application performance outrank a microkernel-only speedup. Retain scaling saturation and regressions in the report.
