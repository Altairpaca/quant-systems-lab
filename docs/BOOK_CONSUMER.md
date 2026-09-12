# L2 book-state replay consumer — protocol v1

**Status: executable specification for the Rust `qsl-rust book` command.** Rust is the single
production path for this consumer; the C++ implementation stays scoped to the generic replay
core (`dump`) so the project does not permanently maintain two complete trading systems. The
canonical fixtures in `fixtures/` are shared with the replay conformance suite, and the book
output is cross-checked byte-for-byte against an independent Python reference in
`tools/book_oracle.py` (no shared code between the two implementations).

## 1. What this consumer is

A deterministic mapper from an availability-ordered, per-feed L2 price-level update stream to
observable book state: best bid/offer (BBO) and every price level's quantity after each applied
event. It is not an order book matcher, not an OMS, and it does not do risk or execution. It
applies the same availability-ordering contract as the replay component (`Replay` in
`rust/src/lib.rs`): the identical `(available_ns, feed_id, seq)` order policy over the same
canonical fixture family. The book layer carries `u64` quantities beyond the replay event's
`i64` projection, so its own merge is implemented locally in `rust/src/book.rs`.

The venue timestamp (`venue_ns`) is payload only. Ordering never uses it; the information
available to the consumer at event time is exactly `(available_ns, feed_id, seq)`.

## 2. Input: book fixture format

TSV, one event per line, comment lines begin with `#`, blank lines are skipped:

```
available_ns  feed_id  session  seq  venue_ns  side  price_ticks  qty
```

| column | type | meaning |
|---|---|---|
| `available_ns` | u64 | time at which this event becomes available to the consumer |
| `feed_id` | u64, `0..=4095` | feed identity |
| `session` | u64 | session identity for the feed; a session increase clears that feed's book |
| `seq` | u64 | event sequence **within the session**, contiguous (`+1` per event) |
| `venue_ns` | i64 | venue timestamp; payload only |
| `side` | `B` \| `A` \| `R` | bid level, ask level, or explicit reset event |
| `price_ticks` | i64 `>= 0` | price level in integer ticks |
| `qty` | u64 | **absolute** quantity at the level after this event; `0` removes the level |

Semantics of a level update: `qty` is the new resting quantity at `price_ticks` on `side`.
It is not a delta. `qty = 0` deletes the level. Levels are per `(feed_id, side)`.

An explicit reset event (`side = R`) clears the whole book of its feed and must carry
`price_ticks = 0` and `qty = 0`.

## 3. Ordering and per-feed rules

1. Within a feed, `available_ns` must be non-decreasing and `seq` strictly increasing — this is
   enforced by the shared replay component (`Replay::new`).
2. Within a session, `seq` must be contiguous: the first event of a session establishes the
   expected sequence; every following event must be exactly `expected`, after which
   `expected += 1`. A gap, duplicate, or out-of-order sequence is a **protocol violation**.
3. A session increase for a feed clears that feed's book before the event is applied and emits
   kind `B` ("session boundary"). A session **decrease** or repeat after a boundary is a
   protocol violation.
4. Events are applied in the replay merge order `(available_ns, feed_id, seq)`; ties on
   `available_ns` resolve by `feed_id` then `seq` — a reproducibility policy, not a claim about
   venue information.

Any protocol violation aborts the run with a diagnostic naming the feed, session, expected and
received sequence. State never silently drifts: either the whole stream replays, or the run
fails with a specific error.

## 4. Output: state lines

One line per applied event, stdout, TSV, deterministic across runs and languages:

```
i  feed  session  seq  kind  best_bid_px  best_bid_qty  best_ask_px  best_ask_qty  bid_levels  ask_levels
```

- `i` — 0-based index in merge order.
- `kind` — `U` update applied to the current book; `R` explicit reset event; `B` session
  boundary (book cleared before this event's update). Precedence: `B` > `R` > `U`.
- `best_bid_px` / `best_ask_px` — best price, or `-1` when that side is empty;
  `best_bid_qty` / `best_ask_qty` — `0` when that side is empty.
- `bid_levels` — `px:qty` pairs, descending price, comma-joined, `-` when empty.
- `ask_levels` — `px:qty` pairs, ascending price, comma-joined, `-` when empty.

The oracle in `tools/book_oracle.py` produces the identical byte stream from the same fixture
using an independent implementation.

## 5. CLI and exit codes

```
qsl-rust book FIXTURE
```

| exit | meaning |
|---:|---|
| 0 | stream replayed, state lines written |
| 2 | usage error or unreadable input (includes malformed fixture rows: column count, non-numeric fields, invalid side, out-of-range feed, negative price, reset with nonzero payload) |
| 4 | protocol violation: sequence gap, duplicate, out-of-order sequence, or session decrease |

Usage errors print to stderr with the concrete line number and a message that names the violated
rule. The invalid fixtures in `tools/crosscheck_book.py` pin these codes.

## 6. Verification

- `python3 tools/crosscheck_book.py` — generates the canonical and randomized fixtures, replays
  them through `qsl-rust book` and the independent Python oracle, and requires byte-equal output
  on every valid fixture; then requires each invalid fixture to fail with its exact exit code and
  diagnostic.
- `cargo test --manifest-path rust/Cargo.toml` — unit tests for the book layer (gap / duplicate /
  session boundary / reset / removal / limits).
- `python3 tools/crosscheck.py` — the pre-existing replay conformance suite (both languages),
  unaffected by this consumer.

## 7. Explicit non-claims

- Synthetic inputs only; no venue data, no employer data, no live connectivity.
- Not a latency study: this is batch replay over files.
- No claim that heap-based merging is optimal for streaming; see
  `docs/BENCHMARK_PROTOCOL.md` §4.
