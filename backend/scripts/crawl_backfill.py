"""Time-bucketed backfill driver.

Crawls ~N articles per month over a date range by calling the LOCAL running API:
  - GET  /discover         (per month, with a published-date window)
  - POST /dataeng/process  (once, over the merged corpus -> clean+label+persist+council)

Discovery uses the plain GET endpoint (no LLM query refinement) so each month's
query stays exact. Processing is done in a single batch so the council (Tiers 3-5)
runs once over the whole backfill rather than once per month.

Usage (server must be running on $BASE_URL, default http://127.0.0.1:8000):
    python -m scripts.crawl_backfill
Env overrides:
    BACKFILL_QUERY, BACKFILL_PER_MONTH, BACKFILL_START (YYYY-MM), BACKFILL_END (YYYY-MM),
    BASE_URL
"""
from __future__ import annotations

import calendar
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
QUERY = os.environ.get(
    "BACKFILL_QUERY",
    "stock market investing news: AI, semiconductors, energy, and the economy",
)
PER_MONTH = int(os.environ.get("BACKFILL_PER_MONTH", "20"))
START = os.environ.get("BACKFILL_START", "2025-06")  # inclusive, YYYY-MM
END = os.environ.get("BACKFILL_END", "2026-06")       # inclusive, YYYY-MM


def _months(start: str, end: str) -> list[tuple[int, int]]:
    sy, sm = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out: list[tuple[int, int]] = []
    y, m = sy, sm
    while (y, m) <= (ey, em):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def _window(y: int, m: int) -> tuple[str, str]:
    """First instant of the month .. last instant (clamped to today for current month)."""
    last_day = calendar.monthrange(y, m)[1]
    start = f"{y:04d}-{m:02d}-01T00:00:00.000Z"
    end_date = date(y, m, last_day)
    today = date.today()
    if end_date > today:
        end_date = today
    end = f"{end_date:%Y-%m-%d}T23:59:59.999Z"
    return start, end


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=180) as resp:
        return json.loads(resp.read().decode())


def _post_json(url: str, payload: dict, timeout: int = 3600) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    months = _months(START, END)
    print(f"Backfill: {QUERY!r}")
    print(f"Range: {START} .. {END} ({len(months)} months), target {PER_MONTH}/month\n")

    merged_items: list[dict] = []
    seen_urls: set[str] = set()
    skipped: list[dict] = []

    for (y, m) in months:
        start, end = _window(y, m)
        params = urllib.parse.urlencode(
            {
                "query": QUERY,
                "max_results": PER_MONTH,
                "start_published_date": start,
                "end_published_date": end,
            }
        )
        url = f"{BASE_URL}/discover?{params}"
        try:
            result = _get_json(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  {y}-{m:02d}: discover FAILED: {exc}")
            continue

        items = result.get("items", [])
        new = 0
        for it in items:
            u = it.get("url")
            if u and u not in seen_urls:
                seen_urls.add(u)
                merged_items.append(it)
                new += 1
        skipped.extend(result.get("skipped", []))
        print(f"  {y}-{m:02d}: {len(items)} found, {new} new (running total {len(merged_items)})")

    print(f"\nDiscovery complete: {len(merged_items)} unique articles across {len(months)} months.")
    if not merged_items:
        print("Nothing to process. Exiting.")
        sys.exit(1)

    merged = {
        "query": QUERY,
        "items": merged_items,
        "skipped": skipped,
        "original_query": QUERY,
        "refinement_note": f"backfill {START}..{END}, {PER_MONTH}/month",
    }

    # Persist the merged discovery payload for auditing / re-runs.
    out_path = os.path.join(os.path.dirname(__file__), "..", "backfill_discovery.json")
    with open(out_path, "w") as fh:
        json.dump(merged, fh)
    print(f"Saved merged discovery payload -> {os.path.abspath(out_path)}")

    print(f"\nProcessing {len(merged_items)} items via POST /dataeng/process "
          f"(clean + label + theme + persist, then council). This is the slow part...")
    report = _post_json(f"{BASE_URL}/dataeng/process", merged)
    print("\n=== Data Engineering report ===")
    print(f"  persisted: {report.get('persisted')}")
    print(f"  failed:    {report.get('failed')}")
    for f in report.get("failures", [])[:10]:
        print(f"    - {f.get('source_url')}: {f.get('reason')}")
    print("\nDone.")


if __name__ == "__main__":
    main()
