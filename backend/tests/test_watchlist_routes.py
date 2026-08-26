"""Watchlist HTTP routes, with the repository monkeypatched away.

`main.py` imports the repository helpers by name, so patching must target the attribute on
`app.main` rather than `app.db.repository` (same reason as tests/test_youtube_ingest.py).
"""

import pytest


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app import main

    return TestClient(main.app)


@pytest.fixture
def calls(monkeypatch):
    """Record what the route hands the repository, and echo back plausible rows."""
    from app import main
    from app.db.repository import WatchlistOverride

    seen: list[list[str]] = []

    def fake_bulk(tickers: list[str]) -> list[WatchlistOverride]:
        seen.append(tickers)
        unique = list(dict.fromkeys(tickers))
        return [WatchlistOverride(ticker=t, enabled=True, deleted=True) for t in unique]

    monkeypatch.setattr(main, "delete_watchlist_entries", fake_bulk)
    return seen


def _post(client, tickers):
    return client.post("/api/watchlists/bulk-delete", json={"tickers": tickers})


def test_bulk_delete_tombstones_each_ticker(client, calls):
    res = _post(client, ["NVDA", "AMD"])
    assert res.status_code == 200
    assert res.json() == [
        {"ticker": "NVDA", "enabled": True, "deleted": True},
        {"ticker": "AMD", "enabled": True, "deleted": True},
    ]
    assert calls == [["NVDA", "AMD"]]


def test_bulk_delete_normalises_case_and_dollar_prefix(client, calls):
    res = _post(client, ["$nvda", " amd ", "$TSM"])
    assert res.status_code == 200
    assert calls == [["NVDA", "AMD", "TSM"]]


def test_bulk_delete_drops_blank_entries(client, calls):
    res = _post(client, ["NVDA", "", "  ", "$"])
    assert res.status_code == 200
    assert calls == [["NVDA"]]


def test_bulk_delete_collapses_duplicates(client, calls):
    """`$nvda` and `NVDA` are the same row — the response must not report it twice."""
    res = _post(client, ["$nvda", "NVDA"])
    assert res.status_code == 200
    assert [e["ticker"] for e in res.json()] == ["NVDA"]


def test_bulk_delete_with_no_tickers_is_a_noop(client, calls):
    res = _post(client, [])
    assert res.status_code == 200
    assert res.json() == []
    assert calls == [[]]
