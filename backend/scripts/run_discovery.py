"""CLI to try the Discovery agent without the API.

Usage:
    python -m scripts.run_discovery "AI memory chip demand"
"""
from __future__ import annotations

import sys

from app.discovery import discover


def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or "AI memory chip demand"
    result = discover(query)

    print(f"\nQuery: {result.query}")
    print(f"Found {result.count} items, skipped {len(result.skipped)} source(s).\n")

    for s in result.skipped:
        print(f"  [skipped] {s.source_type.value}: {s.reason}")
    if result.skipped:
        print()

    for i, item in enumerate(result.items, 1):
        tag = item.source_type.value.upper()
        segs = f", {len(item.segments)} segments" if item.segments else ""
        print(f"{i:>2}. [{tag}] {item.title}")
        print(f"     {item.url}")
        print(f"     {len(item.text)} chars{segs}\n")


if __name__ == "__main__":
    main()
