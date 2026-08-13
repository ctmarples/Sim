"""Offline grouped review of the automatic playtime bug JSONL log.

Usage:
  python bug_log_report.py
  python bug_log_report.py --kind idle_assigned
  python bug_log_report.py --limit 20
  python bug_log_report.py --path /path/to/bug_log.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def _default_path() -> Path:
    # Prefer project saves/ without importing pygame via save_load.
    root = Path(__file__).resolve().parents[1]
    candidate = root / "saves" / "bug_log.jsonl"
    if candidate.parent.is_dir() or not (root / "environment_sandbox").is_dir():
        return candidate
    return Path(__file__).resolve().parent / "saves" / "bug_log.jsonl"


def load_events(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    events: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"skip line {line_no}: {exc}", file=sys.stderr)
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize bug_log.jsonl by kind")
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="JSONL path (default: saves/bug_log.jsonl)",
    )
    parser.add_argument(
        "--kind",
        type=str,
        default=None,
        help="Only show this event kind (e.g. idle_assigned)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max events to print per kind (default 50)",
    )
    parser.add_argument(
        "--counts-only",
        action="store_true",
        help="Print kind counts only",
    )
    args = parser.parse_args()
    path = args.path or _default_path()
    events = load_events(path)
    if not events:
        print(f"No events in {path}")
        return 0

    if args.kind:
        events = [e for e in events if e.get("kind") == args.kind]

    counts = Counter(e.get("kind", "?") for e in events)
    print(f"{path} — {len(events)} event(s)")
    print("Counts by kind:")
    for kind, count in counts.most_common():
        print(f"  {kind}: {count}")
    if args.counts_only:
        return 0

    by_kind: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        by_kind[str(event.get("kind", "?"))].append(event)

    for kind in sorted(by_kind):
        group = by_kind[kind]
        print()
        print(f"=== {kind} ({len(group)}) ===")
        for event in group[-args.limit :]:
            summary = event.get("summary", "")
            day = event.get("calendar_day")
            season = event.get("season")
            save = event.get("save_name") or "-"
            wall = event.get("wall_time", "")
            eid = event.get("id", "")
            print(f"  [{wall}] day={day} {season} save={save}")
            print(f"    {eid}")
            print(f"    {summary}")
            hints = event.get("hints") or []
            if hints:
                print(f"    hints: {', '.join(str(h) for h in hints[:8])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
