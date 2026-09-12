"""CLI contract test for `qsl bench` argument handling; wired into ctest."""
from __future__ import annotations
import argparse
import csv
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

FIXTURE = "".join(
    f"{i}\t{i % 2}\t{i // 2}\t{i - 5}\t{100 + i % 3}\t{1 + i % 7}\n" for i in range(16)
)
HEADER = ["repetition", "method", "events", "elapsed_ns"]


def run(binary: Path, fixture: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(binary), "bench", str(fixture), *args],
                          capture_output=True, text=True, timeout=120, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    args = parser.parse_args()
    failures: list[str] = []
    checks = 0
    with tempfile.TemporaryDirectory(prefix="qsl-bench-cli-") as directory:
        fixture = Path(directory) / "bench.tsv"
        fixture.write_text(FIXTURE)
        for label, cli, expect_rows, expect_exit in [
            ("reps-5", ["--reps", "5"], 20, 0),
            ("reps-5-no-warmups", ["--warmups", "0", "--reps", "5"], 20, 0),
            ("reps-0", ["--reps", "0"], None, 1),
            ("reps-garbage", ["--reps", "abc"], None, 1),
            ("reps-missing-value", ["--reps"], None, 1),
            ("unknown-option", ["--bogus"], None, 1),
        ]:
            checks += 1
            result = run(args.binary, fixture, cli)
            if result.returncode != expect_exit:
                failures.append(f"{label}: exit {result.returncode}, expected {expect_exit}: {result.stderr.strip()[:160]}")
                continue
            if expect_rows is None:
                continue
            rows = list(csv.DictReader(io.StringIO(result.stdout)))
            if not rows or list(rows[0].keys()) != HEADER:
                failures.append(f"{label}: unexpected CSV header {result.stdout.splitlines()[:1]}")
            elif len(rows) != expect_rows:
                failures.append(f"{label}: {len(rows)} rows, expected {expect_rows}")
            elif any(row["events"] != "16" for row in rows):
                failures.append(f"{label}: event count not reported as 16")
            elif any(not row["elapsed_ns"].isdigit() for row in rows):
                failures.append(f"{label}: non-numeric elapsed_ns")
    print(json.dumps({"checks": checks, "overall": "FAIL" if failures else "PASS", "failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
