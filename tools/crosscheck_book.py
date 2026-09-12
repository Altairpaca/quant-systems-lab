"""Byte-equality cross-check of qsl-rust book vs the independent oracle, plus invalid-fixture exit codes."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = ("uniform", "ties", "bursty", "sessions")
FEED_COUNTS = (1, 4, 16)

INVALID = {
    "gap": ("0 0 0 0 0 B 100 5\n1 0 0 2 0 B 101 7\n", 4, "expected seq 1, got 2"),
    "duplicate": ("0 0 0 0 0 B 100 5\n1 0 0 0 0 B 101 7\n", 4, "expected seq 1, got 0"),
    "available_ns_decrease": ("5 0 0 0 0 B 100 5\n4 0 0 1 0 B 101 7\n", 4, "available_ns"),
    "session_decrease": ("0 0 1 0 0 B 100 5\n1 0 0 0 0 B 101 7\n", 4, "session"),
    "column_count": ("0 0 0 0 0 B 100\n", 2, "columns"),
    "non_integer": ("0 0 0 x 0 B 100 5\n", 2, "integer"),
    "bad_side": ("0 0 0 0 0 X 100 5\n", 2, "side"),
    "negative_price": ("0 0 0 0 0 B -1 5\n", 2, "price"),
    "reset_payload": ("0 0 0 0 0 R 100 5\n", 2, "reset"),
    "feed_bound": ("0 4096 0 0 0 B 100 5\n", 2, "feed"),
    "unsigned_overflow": ("18446744073709551616 0 0 0 0 B 100 5\n", 2, "integer"),
}


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)


def first_difference(a: str, b: str) -> str:
    for index, (left, right) in enumerate(zip(a.splitlines(), b.splitlines())):
        if left != right:
            return f"line {index + 1}: rust={left[:120]!r} oracle={right[:120]!r}"
    return f"line count differs: rust={len(a.splitlines())} oracle={len(b.splitlines())}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rust", type=Path, default=ROOT / "rust/target/release/qsl-rust")
    args = parser.parse_args()
    if not args.rust.is_file():
        print(json.dumps({"rust": "UNEXECUTED_MISSING_BINARY", "overall": "FAIL"}, indent=2))
        return 2
    result = {"valid_fixtures": 0, "invalid_fixtures": 0, "lines_compared": 0, "rust": "NOT_RUN", "overall": "FAIL"}
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="qsl-book-") as directory:
        tmp = Path(directory)
        fixtures = [ROOT / "fixtures/book-conformance.tsv"]
        for pattern in PATTERNS:
            for feeds in FEED_COUNTS:
                path = tmp / f"book-{pattern}-{feeds}.tsv"
                generated = run([sys.executable, str(ROOT / "tools/generate_book.py"), str(path),
                                 "--feeds", str(feeds), "--events", "129", "--seed", "1701", "--pattern", pattern])
                if generated.returncode:
                    failures.append(f"generator failed for {pattern}/{feeds}: {generated.stderr[:200]}")
                    continue
                fixtures.append(path)
        limits = tmp / "book-limits.tsv"
        limits.write_text("18446744073709551615\t0\t18446744073709551615\t0\t-9223372036854775808\tB\t9223372036854775807\t18446744073709551615\n"
                          "18446744073709551615\t1\t0\t0\t0\tA\t0\t0\n")
        fixtures.append(limits)
        for fixture in fixtures:
            rust = run([str(args.rust), "book", str(fixture)])
            oracle = run([sys.executable, str(ROOT / "tools/book_oracle.py"), str(fixture)])
            if oracle.returncode:
                failures.append(f"{fixture.name}: oracle failed: {oracle.stderr[:200]}")
            elif rust.returncode:
                failures.append(f"{fixture.name}: rust exit {rust.returncode}: {rust.stderr[:200]}")
            elif rust.stdout != oracle.stdout:
                failures.append(f"{fixture.name}: {first_difference(rust.stdout, oracle.stdout)}")
            else:
                result["valid_fixtures"] += 1
                result["lines_compared"] += len(rust.stdout.splitlines())
        for name, (text, code, needle) in INVALID.items():
            path = tmp / f"invalid-{name}.tsv"
            path.write_text(text)
            rust = run([str(args.rust), "book", str(path)])
            if rust.returncode != code:
                failures.append(f"invalid/{name}: exit {rust.returncode}, expected {code}: {rust.stderr[:160]}")
            elif needle not in rust.stderr:
                failures.append(f"invalid/{name}: stderr missing {needle!r}: {rust.stderr[:160]}")
            else:
                result["invalid_fixtures"] += 1
    if failures:
        print(json.dumps({**result, "failures": failures}, indent=2))
        return 1
    result["rust"] = "PASS"
    result["overall"] = "PASS"
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
