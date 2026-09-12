"""Independent full-output oracle. Rust is required unless explicitly scoped out."""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

METHODS = ("sort", "scan", "heap", "heap-replace")
ROOT = Path(__file__).resolve().parents[1]


def invoke(binary: Path, fixture: Path, method: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(binary), "dump", str(fixture), method],
                          capture_output=True, text=True, timeout=30, check=False)


def oracle(path: Path) -> str:
    rows = [tuple(map(int, line.split())) for line in path.read_text().splitlines()
            if line and not line.startswith("#")]
    return "".join("\t".join(map(str, row)) + "\n"
                   for row in sorted(rows, key=lambda row: row[:3]))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpp", type=Path, default=ROOT / "build/qsl")
    parser.add_argument("--rust", type=Path, default=ROOT / "rust/target/release/qsl-rust")
    parser.add_argument("--allow-cpp-only", action="store_true",
                        help="Explicit partial validation; never reports cross-language PASS.")
    args = parser.parse_args()
    if not args.cpp.is_file():
        parser.error("C++ executable is missing; build it first")
    rust_present = args.rust.is_file()
    binaries = {"cpp": args.cpp.resolve()}
    if rust_present:
        binaries["rust"] = args.rust.resolve()
    result = {"cpp": "NOT_RUN", "rust": "NOT_RUN" if rust_present else "UNEXECUTED_MISSING_BINARY",
              "cross_language": "NOT_RUN" if rust_present else "UNEXECUTED", "valid_fixtures": 0,
              "rejected_fixtures": 0, "successful_invocations": 0}
    with tempfile.TemporaryDirectory(prefix="qsl-conformance-") as directory:
        tmp = Path(directory)
        fixtures = [ROOT / "fixtures/conformance.tsv"]
        for pattern in ("uniform", "ties", "bursty", "skew"):
            for feeds in (0, 1, 4, 16):
                path = tmp / f"{pattern}-{feeds}.tsv"
                subprocess.run([sys.executable, str(ROOT / "tools/generate.py"), str(path),
                                "--feeds", str(feeds), "--events", "129", "--seed", "1701",
                                "--pattern", pattern], check=True, timeout=30)
                fixtures.append(path)
        extreme = tmp / "limits.tsv"
        extreme.write_text("18446744073709551615\t0\t18446744073709551615\t-9223372036854775808\t9223372036854775807\t-1\n"
                           "18446744073709551615\t1\t0\t0\t0\t0\n")
        fixtures.append(extreme)
        expected_golden = (ROOT / "fixtures/expected.tsv").read_text()
        if oracle(fixtures[0]) != expected_golden:
            raise AssertionError("committed golden differs from independent integer-key oracle")
        for path in fixtures:
            expected = oracle(path)
            for language, binary in binaries.items():
                for method in METHODS:
                    actual = invoke(binary, path, method)
                    if actual.returncode or actual.stdout != expected:
                        raise AssertionError(f"{language}/{method}/{path.name}: mismatch or error: {actual.stderr[:500]}")
                    result["successful_invocations"] += 1
            result["valid_fixtures"] += 1
        invalid = {
            "negative_unsigned": "-1 0 0 0 1 1\n",
            "unsigned_overflow": "18446744073709551616 0 0 0 1 1\n",
            "feed_bound": "0 4096 0 0 1 1\n",
            "duplicate_sequence": "1 0 1 0 1 1\n1 0 1 0 1 1\n",
            "decreasing_timestamp": "2 0 0 0 1 1\n1 0 1 0 1 1\n",
            "trailing_field": "0 0 0 0 1 1 extra\n",
            "signed_overflow": "0 0 0 0 9223372036854775808 1\n",
        }
        for name, text in invalid.items():
            path = tmp / f"invalid-{name}.tsv"
            path.write_text(text)
            for language, binary in binaries.items():
                actual = invoke(binary, path, "heap-replace")
                if actual.returncode == 0:
                    raise AssertionError(f"{language} accepted invalid fixture: {name}")
            result["rejected_fixtures"] += 1
    result["cpp"] = "PASS"
    if rust_present:
        result["rust"] = "PASS"
        result["cross_language"] = "PASS"
    result["overall"] = "PASS" if rust_present else "CPP_ONLY_PARTIAL"
    print(json.dumps(result, indent=2))
    return 0 if rust_present or args.allow_cpp_only else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, OSError, subprocess.SubprocessError) as exc:
        print(f"conformance failure: {exc}", file=sys.stderr)
        raise SystemExit(1)
