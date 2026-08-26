"""Telegram daily report: HTML formatting, message splitting, skip guards, transport retries."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models import CouncilReport, Evidence, MacroIndicator
from app.notify import daily_report
from app.notify import telegram as tg
from app.notify.daily_report import format_indicator_report, send_daily_indicator_report


def _indicator(name="Inflation Trajectory", score=0.45, band="Positive",
               rationale="Cooling core CPI gives the Fed room.", urls=()) -> MacroIndicator:
    return MacroIndicator(
        name=name, score=score, band=band, rationale=rationale,
        evidence=[Evidence(quote="q", source_url=u) for u in urls],
    )


def _report(indicators=None, generated_at=None, source_count=42) -> CouncilReport:
    return CouncilReport(
        indicators=list(indicators if indicators is not None else [_indicator()]),
        source_count=source_count,
        generated_at=generated_at or datetime.now(timezone.utc),
    )


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    """Credentials present and the feature on, so each test opts *out* of what it tests."""
    monkeypatch.setattr(daily_report.settings, "telegram_daily_report_enabled", True)
    monkeypatch.setattr(daily_report.settings, "telegram_bot_token", "123:abc")
    monkeypatch.setattr(daily_report.settings, "telegram_chat_id", "@wtaf")
    monkeypatch.setattr(daily_report.settings, "telegram_report_max_age_hours", 24)


@pytest.fixture
def sent(monkeypatch):
    """Record what would have gone to Telegram instead of sending it."""
    messages: list[str] = []
    monkeypatch.setattr(daily_report, "send_message", messages.append)
    return messages


# --- formatting ---------------------------------------------------------------

def test_formats_band_icon_signed_score_and_rationale():
    (message,) = format_indicator_report(_report())
    assert "🟢" in message
    assert "<b>Inflation Trajectory</b>" in message
    assert "+0.45 · Positive" in message
    assert "Cooling core CPI gives the Fed room." in message
    assert "1 indicator · 42 sources" in message


def test_negative_and_neutral_bands_get_their_own_icons():
    report = _report([
        _indicator(name="Growth", score=-0.6, band="Negative"),
        _indicator(name="Liquidity", score=0.05, band="Neutral"),
    ])
    (message,) = format_indicator_report(report)
    assert "🔴 <b>Growth</b>  -0.60 · Negative" in message
    assert "⚪ <b>Liquidity</b>  +0.05 · Neutral" in message


def test_escapes_html_in_model_generated_text():
    """An unescaped `&` or `<` makes Telegram reject the whole message with 400."""
    report = _report([_indicator(name="AI Capex & <Fed> Policy", rationale="a < b & c")])
    (message,) = format_indicator_report(report)
    assert "AI Capex &amp; &lt;Fed&gt; Policy" in message
    assert "a &lt; b &amp; c" in message
    assert "<Fed>" not in message


def test_renders_one_and_many_citations():
    (one,) = format_indicator_report(_report([_indicator(urls=["https://a.test/x"])]))
    assert '<a href="https://a.test/x">source</a>' in one

    (many,) = format_indicator_report(
        _report([_indicator(urls=["https://a.test/x", "https://b.test/y", "https://c.test/z"])])
    )
    assert '<a href="https://a.test/x">src 1</a>' in many
    assert '<a href="https://b.test/y">src 2</a>' in many
    assert "https://c.test/z" not in many  # capped at two links


def test_indicator_without_evidence_still_renders():
    """Pre-citation snapshots migrate their evidence into `rationale` and carry no links."""
    (message,) = format_indicator_report(_report([_indicator(urls=())]))
    assert "<a href=" not in message
    assert "Inflation Trajectory" in message


def test_no_indicators_formats_to_no_messages():
    assert format_indicator_report(_report([])) == []


# --- splitting ----------------------------------------------------------------

def test_splits_into_messages_within_the_telegram_limit():
    indicators = [
        _indicator(name=f"Indicator {n}", rationale="x" * 300) for n in range(40)
    ]
    messages = format_indicator_report(_report(indicators))

    assert len(messages) > 1
    assert all(len(m) <= tg.MAX_MESSAGE_CHARS for m in messages)
    for page, message in enumerate(messages[1:], 2):
        assert f"({page}/{len(messages)})" in message
    # Every indicator survives the split, none cut in half.
    joined = "".join(messages)
    assert all(f"Indicator {n}</b>" in joined for n in range(40))


def test_oversized_rationale_is_truncated_not_dropped():
    report = _report([_indicator(name="Wall of text", rationale="y" * 9000)])
    (message,) = format_indicator_report(report)
    assert len(message) <= tg.MAX_MESSAGE_CHARS
    assert "Wall of text" in message
    assert "…" in message


# --- send + skip guards -------------------------------------------------------

def test_sends_every_chunk_and_reports_success(sent):
    assert send_daily_indicator_report(_report()) is True
    assert len(sent) == 1
    assert "Inflation Trajectory" in sent[0]


def test_reads_the_latest_snapshot_when_no_report_is_passed(monkeypatch, sent):
    monkeypatch.setattr("app.council.latest_council", lambda: _report())
    assert send_daily_indicator_report() is True
    assert len(sent) == 1


@pytest.mark.parametrize(
    "setting,value",
    [("telegram_daily_report_enabled", False),
     ("telegram_bot_token", ""),
     ("telegram_chat_id", "")],
)
def test_skips_when_unconfigured(monkeypatch, sent, setting, value):
    monkeypatch.setattr(daily_report.settings, setting, value)
    assert send_daily_indicator_report(_report()) is False
    assert sent == []


def test_skips_when_there_is_no_snapshot(monkeypatch, sent):
    monkeypatch.setattr("app.council.latest_council", lambda: None)
    assert send_daily_indicator_report() is False
    assert sent == []


def test_skips_when_the_snapshot_has_no_indicators(sent):
    assert send_daily_indicator_report(_report([])) is False
    assert sent == []


def test_skips_a_stale_snapshot(sent):
    """A failed council leaves yesterday's snapshot as 'latest' — don't re-send it."""
    old = datetime.now(timezone.utc) - timedelta(hours=30)
    assert send_daily_indicator_report(_report(generated_at=old)) is False
    assert sent == []


def test_max_age_zero_disables_the_staleness_check(monkeypatch, sent):
    monkeypatch.setattr(daily_report.settings, "telegram_report_max_age_hours", 0)
    old = datetime.now(timezone.utc) - timedelta(days=9)
    assert send_daily_indicator_report(_report(generated_at=old)) is True
    assert len(sent) == 1


def test_records_the_reason_it_skipped(monkeypatch, sent):
    monkeypatch.setattr(daily_report.settings, "telegram_bot_token", "")
    events: list[tuple] = []

    def emit(stage, message="", *, status="info", **data):
        events.append((stage, status, data.get("reason", "")))

    send_daily_indicator_report(_report(), emit=emit)
    assert events and events[-1][0] == "notify.telegram"
    assert events[-1][1] == "skip"
    assert "TELEGRAM_BOT_TOKEN" in events[-1][2]


# --- fault isolation ----------------------------------------------------------

@pytest.mark.parametrize(
    "exc",
    [tg.TelegramError("bad request", status=400),
     tg.TelegramUnavailable("bot is not an admin"),
     RuntimeError("socket exploded")],
)
def test_a_failed_send_never_propagates(monkeypatch, exc):
    def boom(_message):
        raise exc

    monkeypatch.setattr(daily_report, "send_message", boom)
    assert send_daily_indicator_report(_report()) is False  # must not raise


# --- transport ----------------------------------------------------------------

class _Response:
    def __init__(self, status_code, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = str(self._body)

    def json(self):
        return self._body


@pytest.fixture
def _keyed(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_bot_token", "123:abc")
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "@wtaf")
    monkeypatch.setattr(tg.settings, "telegram_api_base_url", "https://tg.test")


def _stub_httpx(monkeypatch, responses: list):
    calls: list[dict] = []

    def request(method, url, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return responses[min(len(calls) - 1, len(responses) - 1)]

    import httpx

    monkeypatch.setattr(httpx, "request", request)
    monkeypatch.setattr(tg.time, "sleep", lambda _s: None)
    return calls


def test_send_message_posts_html_to_the_configured_chat(_keyed, monkeypatch):
    calls = _stub_httpx(monkeypatch, [_Response(200, {"ok": True})])
    tg.send_message("hello")

    assert len(calls) == 1
    assert calls[0]["url"] == "https://tg.test/bot123:abc/sendMessage"
    assert calls[0]["json"] == {
        "chat_id": "@wtaf", "text": "hello",
        "parse_mode": "HTML", "disable_web_page_preview": True,
    }


def test_send_message_retries_a_rate_limit(_keyed, monkeypatch):
    calls = _stub_httpx(monkeypatch, [
        _Response(429, {"ok": False, "description": "Too Many Requests",
                        "parameters": {"retry_after": 2}}),
        _Response(200, {"ok": True}),
    ])
    tg.send_message("hello")
    assert len(calls) == 2


def test_send_message_gives_up_on_a_persistent_rate_limit(_keyed, monkeypatch):
    _stub_httpx(monkeypatch, [_Response(429, {"description": "Too Many Requests"})])
    with pytest.raises(tg.TelegramError):
        tg.send_message("hello")


@pytest.mark.parametrize("status", [401, 403, 404])
def test_credential_failures_mark_the_channel_unavailable(_keyed, monkeypatch, status):
    _stub_httpx(monkeypatch, [_Response(status, {"description": "nope"})])
    with pytest.raises(tg.TelegramUnavailable):
        tg.send_message("hello")


def test_other_errors_are_telegram_errors(_keyed, monkeypatch):
    _stub_httpx(monkeypatch, [_Response(400, {"description": "can't parse entities"})])
    with pytest.raises(tg.TelegramError):
        tg.send_message("hello")


def test_missing_credentials_raise_unavailable(monkeypatch):
    monkeypatch.setattr(tg.settings, "telegram_bot_token", None)
    with pytest.raises(tg.TelegramUnavailable, match="TELEGRAM_BOT_TOKEN"):
        tg.send_message("hello")

    monkeypatch.setattr(tg.settings, "telegram_bot_token", "123:abc")
    monkeypatch.setattr(tg.settings, "telegram_chat_id", "   ")
    with pytest.raises(tg.TelegramUnavailable, match="TELEGRAM_CHAT_ID"):
        tg.send_message("hello")
