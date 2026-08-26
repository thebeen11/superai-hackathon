"""Daily crawl: window math, pipeline chaining, timer scheduling, endpoint validation."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import HTTPException

from app import crawl
from app.models import DataEngReport, DiscoveryResult


# --- window helpers ---

def test_crawl_window_covers_the_whole_day():
    start, end = crawl.crawl_window(date(2026, 7, 6))
    assert start == "2026-07-06T00:00:00.000Z"
    assert end == "2026-07-06T23:59:59.999Z"


def test_default_crawl_day_is_yesterday_utc():
    today = datetime.now(timezone.utc).date()
    assert (today - crawl.default_crawl_day()).days == 1


# --- run_daily_crawl chains discover -> process -> council with the day window ---

def test_run_daily_crawl_passes_window_and_chains(monkeypatch):
    calls: dict = {}

    def fake_discover(query, max_results=None, emit=None, *, start_published_date=None,
                      end_published_date=None):
        calls["discover"] = (query, max_results, start_published_date, end_published_date)
        return DiscoveryResult(query=query)

    def fake_process(result, emit=None):
        calls["process"] = result
        return DataEngReport(persisted=3)

    monkeypatch.setattr(crawl, "discover", fake_discover)
    monkeypatch.setattr(crawl, "process_discovery_result", fake_process)
    monkeypatch.setattr(crawl, "run_council", lambda emit=None: calls.setdefault("council", True))

    report = crawl.run_daily_crawl(date(2026, 7, 6))

    assert report.persisted == 3
    query, max_results, start, end = calls["discover"]
    assert query == crawl.settings.daily_crawl_query
    assert max_results == crawl.settings.daily_crawl_max_results
    assert start == "2026-07-06T00:00:00.000Z"
    assert end == "2026-07-06T23:59:59.999Z"
    assert calls["council"] is True


def test_run_daily_crawl_survives_council_failure(monkeypatch):
    monkeypatch.setattr(crawl, "discover", lambda q, **kw: DiscoveryResult(query=q))
    monkeypatch.setattr(
        crawl, "process_discovery_result", lambda r, emit=None: DataEngReport(persisted=1)
    )

    def boom(emit=None):
        raise RuntimeError("council down")

    monkeypatch.setattr(crawl, "run_council", boom)
    report = crawl.run_daily_crawl(date(2026, 7, 6))  # must not raise
    assert report.persisted == 1


# --- timer scheduling math (no sleeping) ---

def test_seconds_until_next_run_later_today():
    now = datetime(2026, 7, 8, 0, 30, tzinfo=timezone.utc)
    assert crawl._seconds_until_next_run(now, hour_utc=1) == 30 * 60


def test_seconds_until_next_run_rolls_to_tomorrow():
    now = datetime(2026, 7, 8, 1, 0, 0, 1, tzinfo=timezone.utc)  # just past 01:00
    secs = crawl._seconds_until_next_run(now, hour_utc=1)
    assert 0 < secs < 24 * 3600
    assert secs == pytest.approx(24 * 3600, abs=1)


# --- POST /crawl/daily validation ---

def test_endpoint_parses_day_and_delegates(monkeypatch):
    from app import main

    seen: list = []
    monkeypatch.setattr(main, "run_daily_crawl", lambda d: (seen.append(d), DataEngReport())[1])
    main.crawl_daily(day="2026-07-06")
    main.crawl_daily(day=None)
    assert seen == [date(2026, 7, 6), None]


def test_endpoint_rejects_malformed_day():
    from app import main

    with pytest.raises(HTTPException) as exc:
        main.crawl_daily(day="July 6th")
    assert exc.value.status_code == 422


# --- the daily crawl pushes the macro-indicator report after the council ---

def _stub_pipeline(monkeypatch):
    monkeypatch.setattr(crawl, "discover", lambda q, **kw: DiscoveryResult(query=q))
    monkeypatch.setattr(
        crawl, "process_discovery_result", lambda r, emit=None: DataEngReport(persisted=1)
    )


def test_run_daily_crawl_sends_the_telegram_report_after_the_council(monkeypatch):
    order: list[str] = []
    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(crawl, "run_council", lambda emit=None: order.append("council"))
    monkeypatch.setattr(
        crawl, "send_daily_indicator_report", lambda emit=None: order.append("telegram")
    )

    crawl.run_daily_crawl(date(2026, 7, 6))
    assert order == ["council", "telegram"]


def test_run_daily_crawl_survives_a_failing_telegram_report(monkeypatch):
    _stub_pipeline(monkeypatch)
    monkeypatch.setattr(crawl, "run_council", lambda emit=None: None)

    def boom(emit=None):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(crawl, "send_daily_indicator_report", boom)
    report = crawl.run_daily_crawl(date(2026, 7, 6))  # must not raise
    assert report.persisted == 1
