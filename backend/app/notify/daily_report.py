"""The daily macro-indicator report pushed to Telegram.

Domain layer over `telegram.py`: turns the Chairman's `MacroIndicator` list (Tier 5, see
PROJECT_GUIDANCE §8) into HTML messages and sends them. Called at the end of
`crawl.run_daily_crawl`, once the council has written a fresh snapshot — in prod that is the
Cloud Scheduler `daily-crawl` job, so no separate schedule exists for the report.

Two conventions from the rest of the backend are load-bearing here:

* **Graceful skip with a recorded reason, never a crash.** Every reason the report cannot be
  sent (no credentials, no snapshot, no indicators, a stale snapshot) is emitted as a `skip`
  event and logged, exactly as a missing discovery key is.
* **Fault isolation.** `send_daily_indicator_report` never raises. A Telegram outage must not
  fail the crawl that produced the data, the same posture as `crawl.run_council_safe`.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timedelta, timezone

from ..config import settings
from ..events import Emit, noop_emit
from ..models import CouncilReport, MacroIndicator
from .telegram import MAX_MESSAGE_CHARS, TelegramError, TelegramUnavailable, send_message

logger = logging.getLogger(__name__)

_STAGE = "notify.telegram"

_TITLE = "<b>WTAF Fund — Macro Indicators</b>"

# The three values `chairman._band()` guarantees; anything else falls back to the neutral dot.
_BAND_ICON = {"Positive": "🟢", "Neutral": "⚪", "Negative": "🔴"}

# Room reserved on top of the body for the title and a " (2/3)" continuation marker.
_HEADER_ALLOWANCE = 16

_BLOCK_SEP = "\n\n"

# How many citations to link per indicator. Winston can attach several; two is enough to
# make the claim checkable without turning the message into a link dump.
_MAX_LINKS = 2


def _escape(text: str) -> str:
    """HTML-escape model-generated text.

    Not cosmetic: an indicator named `AI Capex & <Fed> Policy` renders as invalid HTML and
    Telegram rejects the *entire* message with 400, losing the whole report.
    """
    return html.escape(text or "", quote=False)


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC — a JSONB round-trip can drop the offset."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _links(indicator: MacroIndicator) -> str:
    """The indicator's citations as anchor tags, or "" when it carries none.

    Pre-citation snapshots migrate their old free-text evidence into `rationale` (see
    `MacroIndicator._migrate_legacy_evidence`), so an empty list here is expected, not a bug.
    """
    urls = [e.source_url for e in indicator.evidence if e.source_url][:_MAX_LINKS]
    if not urls:
        return ""
    if len(urls) == 1:
        return f'<a href="{html.escape(urls[0], quote=True)}">source</a>'
    return " · ".join(
        f'<a href="{html.escape(url, quote=True)}">src {n}</a>'
        for n, url in enumerate(urls, 1)
    )


def _indicator_block(indicator: MacroIndicator, budget: int) -> str:
    """One indicator rendered as HTML, trimmed to `budget` characters if it overruns.

    Trimming happens on the rationale *before* rendering rather than on the finished string:
    cutting rendered HTML can land inside a tag and take the message down with it.
    """
    icon = _BAND_ICON.get(indicator.band, "⚪")
    score = f"{indicator.score:+.2f}"
    head = f"{icon} <b>{_escape(indicator.name)}</b>  {score} · {_escape(indicator.band)}"
    links = _links(indicator)

    fixed = len(head) + (len(links) + 1 if links else 0)
    rationale = indicator.rationale or ""
    room = budget - fixed - 1  # -1 for the newline before the rationale
    if rationale and len(rationale) > room:
        rationale = rationale[: max(0, room - 1)].rstrip() + "…" if room > 1 else ""

    lines = [head]
    if rationale:
        lines.append(_escape(rationale))
    if links:
        lines.append(links)
    return "\n".join(lines)


def format_indicator_report(report: CouncilReport) -> list[str]:
    """Render `report.indicators` as Telegram-ready HTML messages.

    Returns one string per message, each within Telegram's 4096-character limit, split on
    indicator boundaries so no indicator is ever cut in half across two messages. An empty
    list means there was nothing to say.
    """
    if not report.indicators:
        return []

    generated = _as_utc(report.generated_at)
    count = len(report.indicators)
    meta = (
        f"{generated:%d %b %Y} · {count} indicator{'s' if count != 1 else ''}"
        f" · {report.source_count} sources"
    )
    first_header = f"{_TITLE}\n{meta}"
    body_budget = MAX_MESSAGE_CHARS - len(first_header) - _HEADER_ALLOWANCE

    pages: list[list[str]] = [[]]
    used = 0
    for indicator in report.indicators:
        block = _indicator_block(indicator, body_budget)
        extra = len(block) + (len(_BLOCK_SEP) if pages[-1] else 0)
        if pages[-1] and used + extra > body_budget:
            pages.append([block])
            used = len(block)
        else:
            pages[-1].append(block)
            used += extra

    total = len(pages)
    messages = []
    for page, blocks in enumerate(pages, 1):
        header = first_header if page == 1 else f"{_TITLE} ({page}/{total})"
        messages.append(f"{header}\n\n{_BLOCK_SEP.join(blocks)}")
    return messages


def _skip(emit: Emit, reason: str) -> bool:
    logger.info("Telegram daily report skipped: %s", reason)
    emit(_STAGE, f"Telegram report skipped: {reason}", status="skip", reason=reason)
    return False


def _is_stale(report: CouncilReport) -> bool:
    """True when the snapshot predates today's run.

    `crawl.run_council_safe` swallows council failures, so on a night the council falls over
    the "latest" snapshot is still yesterday's. Without this check the report would go out
    looking like fresh analysis of stale data.
    """
    max_age = settings.telegram_report_max_age_hours
    if max_age <= 0:
        return False
    return _as_utc(report.generated_at) < datetime.now(timezone.utc) - timedelta(hours=max_age)


def send_daily_indicator_report(
    report: CouncilReport | None = None, emit: Emit = noop_emit
) -> bool:
    """Push the latest macro indicators to the Telegram channel. Returns whether it sent.

    Never raises: every failure is logged and reported as an event, because the caller is an
    ingestion pipeline whose own work is already done and must not be undone by a chat outage.
    """
    from ..council import latest_council

    try:
        if not settings.telegram_daily_report_enabled:
            return _skip(emit, "TELEGRAM_DAILY_REPORT_ENABLED is off")
        if not (settings.telegram_bot_token or "").strip():
            return _skip(emit, "TELEGRAM_BOT_TOKEN not set")
        if not (settings.telegram_chat_id or "").strip():
            return _skip(emit, "TELEGRAM_CHAT_ID not set")

        if report is None:
            report = latest_council()
        if report is None:
            return _skip(emit, "no council snapshot to report on")
        if not report.indicators:
            return _skip(emit, "the latest snapshot has no macro indicators")
        if _is_stale(report):
            return _skip(
                emit,
                f"the latest snapshot is older than "
                f"{settings.telegram_report_max_age_hours}h ({report.generated_at:%Y-%m-%d %H:%M} UTC)",
            )

        messages = format_indicator_report(report)
        emit(_STAGE, f"Sending {len(report.indicators)} macro indicators to Telegram",
             status="start", indicators=len(report.indicators), messages=len(messages))
        for message in messages:
            send_message(message)
    except TelegramUnavailable as exc:
        return _skip(emit, str(exc))
    except TelegramError as exc:
        logger.warning("Telegram daily report failed: %s", exc)
        emit(_STAGE, f"Telegram report failed: {exc}", status="error", reason=str(exc))
        return False
    except Exception as exc:  # noqa: BLE001 - a chat outage must not fail the crawl
        logger.warning("Telegram daily report failed: %s", exc)
        emit(_STAGE, f"Telegram report failed: {exc}", status="error", reason=str(exc))
        return False

    logger.info("Telegram daily report sent (%d message(s))", len(messages))
    emit(_STAGE, f"Telegram report sent ({len(messages)} message(s))",
         status="ok", messages=len(messages))
    return True
