#!/usr/bin/env python3
"""Drive the frontend's "Discover" pipeline over a whole ticker list, one by one.

For each ticker in the list file this replays exactly what the dashboard's
Discover button does (frontend `discoverAndProcess`):
    POST /discover         {query, mode: "auto_proceed", max_results}  -> DiscoveryResult
    POST /dataeng/process  <that DiscoveryResult>                      -> clean+label+persist+council

It runs sequentially (one ticker at a time), isolates failures so one bad ticker
never stops the run, and is resumable: completed tickers are recorded in a
progress file and skipped on re-run.

Usage (targets the PROD backend by default — read from frontend/.env.local):
    python -m scripts.discover_tickers

Env overrides:
    BASE_URL          backend base URL (default: prod Cloud Run from .env.local)
    TICKERS_FILE      path to the ticker CSV (default: repo-root "complete list stock tickers 2026 (1)")
    QUERY_TEMPLATE    per-ticker query, {name}/{ticker} placeholders
                      (default: "{name} ({ticker}) stock news and outlook")
    MAX_RESULTS       max sources per ticker discovery (1..50, default 10)
    SLEEP             seconds to wait between tickers (default 3)
    PROGRESS_FILE     where completed tickers are tracked (default backend/discover_tickers_progress.json)
    LIMIT             process at most this many (remaining) tickers, for a smoke test
    DRY_RUN           if set, just print the plan and exit
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent  # backend/scripts -> backend -> repo root


def _default_base_url() -> str:
    """Prefer an explicit BASE_URL, else the URL the local frontend is pointed at."""
    env_local = _REPO_ROOT / "frontend" / ".env.local"
    if env_local.exists():
        for line in env_local.read_text().splitlines():
            line = line.strip()
            if line.startswith("NEXT_PUBLIC_API_URL="):
                return line.split("=", 1)[1].strip()
    return "http://127.0.0.1:8000"


BASE_URL = os.environ.get("BASE_URL", _default_base_url()).rstrip("/")
TICKERS_FILE = Path(
    os.environ.get("TICKERS_FILE", _REPO_ROOT / "complete list stock tickers 2026 (1)")
)
QUERY_TEMPLATE = os.environ.get(
    "QUERY_TEMPLATE", "{name} ({ticker}) stock news and outlook"
)
MAX_RESULTS = int(os.environ.get("MAX_RESULTS", "10"))
SLEEP = float(os.environ.get("SLEEP", "3"))
PROGRESS_FILE = Path(
    os.environ.get("PROGRESS_FILE", _HERE.parent / "discover_tickers_progress.json")
)
LIMIT = int(os.environ["LIMIT"]) if os.environ.get("LIMIT") else None
DRY_RUN = bool(os.environ.get("DRY_RUN"))


def _parse_tickers(path: Path) -> list[tuple[str, str]]:
    """Return [(ticker, name)] from the CSV, skipping the header and blank lines."""
    out: list[tuple[str, str]] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.lower().startswith("ticker,"):
            continue
        ticker, _, name = line.partition(",")
        ticker, name = ticker.strip(), name.strip()
        if ticker:
            out.append((ticker, name or ticker))
    return out


def _post_json(path: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"done": [], "failed": {}}


def _save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def _discover_one(ticker: str, name: str) -> dict:
    """Frontend's discoverAndProcess: POST /discover (auto_proceed) -> POST /dataeng/process."""
    query = QUERY_TEMPLATE.format(ticker=ticker, name=name)
    discovery = _post_json(
        "/discover",
        {"query": query, "mode": "auto_proceed", "max_results": MAX_RESULTS},
        timeout=300,
    )
    if "questions" in discovery:
        raise RuntimeError("discovery returned clarifying questions (unexpected in auto_proceed)")
    n_items = len(discovery.get("items", []))
    report = _post_json("/dataeng/process", discovery, timeout=3600)
    return {"found": n_items, "report": report}


def main() -> None:
    if not TICKERS_FILE.exists():
        sys.exit(f"Ticker file not found: {TICKERS_FILE}")

    tickers = _parse_tickers(TICKERS_FILE)
    progress = _load_progress()
    done = set(progress["done"])
    remaining = [(t, n) for (t, n) in tickers if t not in done]
    if LIMIT is not None:
        remaining = remaining[:LIMIT]

    print(f"Backend:      {BASE_URL}")
    print(f"Ticker file:  {TICKERS_FILE}")
    print(f"Query:        {QUERY_TEMPLATE!r}  (max_results={MAX_RESULTS})")
    print(f"Total:        {len(tickers)}  |  already done: {len(done)}  |  this run: {len(remaining)}")
    print(f"Progress:     {PROGRESS_FILE}\n")

    if DRY_RUN:
        for t, n in remaining:
            print(f"  would discover: {t:<10} {QUERY_TEMPLATE.format(ticker=t, name=n)!r}")
        print("\nDRY_RUN set — nothing sent.")
        return

    for i, (ticker, name) in enumerate(remaining, 1):
        print(f"[{i}/{len(remaining)}] {ticker} — {name}")
        try:
            res = _discover_one(ticker, name)
            rep = res["report"]
            print(
                f"    found {res['found']} sources -> persisted {rep.get('persisted')}, "
                f"failed {rep.get('failed')}"
            )
            progress["done"].append(ticker)
            progress["failed"].pop(ticker, None)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:300]
            print(f"    HTTP {exc.code} FAILED: {body}")
            progress["failed"][ticker] = f"HTTP {exc.code}: {body}"
        except Exception as exc:  # noqa: BLE001 - isolate so one bad ticker never stops the run
            print(f"    FAILED: {exc}")
            progress["failed"][ticker] = str(exc)

        _save_progress(progress)
        if i < len(remaining) and SLEEP > 0:
            time.sleep(SLEEP)

    print(
        f"\nDone. completed total: {len(progress['done'])}  |  failed: {len(progress['failed'])}"
    )
    if progress["failed"]:
        print("Failed tickers (re-run to retry — completed ones are skipped):")
        for t, why in list(progress["failed"].items())[:20]:
            print(f"  - {t}: {why}")


if __name__ == "__main__":
    main()
