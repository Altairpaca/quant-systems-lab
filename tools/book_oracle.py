"""Independent reference for the L2 book consumer output; shares no code with the Rust implementation."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

SIDES = ("B", "A", "R")


def parse(path: Path) -> list[dict]:
    events: list[dict] = []
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip() or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 8:
            raise SystemExit(f"malformed fixture: row {line_no} has {len(fields)} columns, expected 8")
        try:
            e = {
                "available_ns": int(fields[0]), "feed": int(fields[1]), "session": int(fields[2]),
                "seq": int(fields[3]), "venue_ns": int(fields[4]), "side": fields[5],
                "price": int(fields[6]), "qty": int(fields[7]), "line": line_no,
            }
        except ValueError:
            raise SystemExit(f"malformed fixture: row {line_no} has a non-integer field")
        if min(e["available_ns"], e["feed"], e["session"], e["seq"], e["qty"]) < 0:
            raise SystemExit(f"malformed fixture: row {line_no} has a negative unsigned field")
        if e["feed"] > 4095:
            raise SystemExit(f"malformed fixture: row {line_no} feed exceeds 4095")
        if e["side"] not in SIDES:
            raise SystemExit(f"malformed fixture: row {line_no} invalid side {e['side']}")
        if e["price"] < 0:
            raise SystemExit(f"malformed fixture: row {line_no} negative price")
        if e["side"] == "R" and (e["price"] != 0 or e["qty"] != 0):
            raise SystemExit(f"malformed fixture: row {line_no} reset event must carry price 0 and qty 0")
        events.append(e)
    return events


def replay(events: list[dict]) -> list[str]:
    feeds: dict[int, dict] = {}
    lines: list[str] = []
    for index, e in enumerate(sorted(events, key=lambda x: (x["available_ns"], x["feed"], x["session"], x["seq"]))):
        st = feeds.setdefault(e["feed"], {"session": None, "expected": 0, "B": {}, "A": {}})
        kind = "U"
        if st["session"] is None:
            st["session"] = e["session"]
        elif e["session"] > st["session"]:
            st["B"].clear()
            st["A"].clear()
            st["session"], kind = e["session"], "B"
        elif e["seq"] != st["expected"]:
            raise SystemExit(f"protocol violation: feed {e['feed']} session {e['session']} expected seq {st['expected']} got {e['seq']}")
        if e["side"] == "R":
            st["B"].clear()
            st["A"].clear()
            if kind != "B":
                kind = "R"
        else:
            book = st[e["side"]]
            if e["qty"] == 0:
                book.pop(e["price"], None)
            else:
                book[e["price"]] = e["qty"]
        st["expected"] = e["seq"] + 1
        bids = ",".join(f"{p}:{q}" for p, q in sorted(st["B"].items(), reverse=True)) or "-"
        asks = ",".join(f"{p}:{q}" for p, q in sorted(st["A"].items())) or "-"
        bb = next(iter(sorted(st["B"], reverse=True)), -1)
        ba = next(iter(sorted(st["A"])), -1)
        lines.append("\t".join(map(str, [
            index, e["feed"], e["session"], e["seq"], kind, bb, st["B"].get(bb, 0),
            ba, st["A"].get(ba, 0), bids, asks,
        ])))
    return lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    args = parser.parse_args()
    for line in replay(parse(args.fixture)):
        sys.stdout.write(line + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
