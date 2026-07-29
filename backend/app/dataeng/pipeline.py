"""Data Engineering pipeline (Req 7, 8-15).

Per item, in order: redact -> resolve entities -> label -> theme -> guardrail -> persist.
Items are processed independently: one item failing never halts the batch; failures are
surfaced in the DataEngReport.
"""
from __future__ import annotations

import logging

from ..db.repository import upsert_cleaned_item
from ..events import Emit, call_maybe_emit, noop_emit
from ..models import (
    CleanedItem,
    DataEngReport,
    DiscoveryResult,
    ProcessingFailure,
    SourceItem,
)
from . import entities, labels, redact, themes
from .guardrail import enforce

logger = logging.getLogger(__name__)


def _build_cleaned_item(item: SourceItem, emit: Emit = noop_emit) -> CleanedItem | None:
    """Run all skills for one item. Returns None if the item is all noise (Req 8.4)."""
    emit("dataeng.item", f"Redacting: {item.url}", status="progress", source_url=item.url)
    redaction = redact.redact(item)
    if redaction.is_all_noise:
        logger.info("Dropping all-noise item %s", item.url)
        return None

    emit("dataeng.item", "Resolving entities", status="progress", source_url=item.url)
    resolved = entities.resolve_entities(redaction.clean_text)
    emit("dataeng.item", "Assigning stream/industry labels", status="progress", source_url=item.url)
    label = labels.assign_labels(redaction.clean_text)
    emit("dataeng.item", "Tagging market themes", status="progress", source_url=item.url)
    item_themes = themes.assign_themes(redaction.clean_text)

    cleaned = CleanedItem(
        source_url=item.url,
        source_type=item.source_type,
        title=item.title,
        clean_text=redaction.clean_text,
        stream=label.stream,
        industry=label.industry,
        entities=resolved,
        themes=item_themes,
        segments=redaction.segments,
        author=item.author,
        published_at=item.published_at,
        retrieved_at=item.retrieved_at,
    )
    return enforce(cleaned, item)  # no-orphan-data guardrail (Req 13)


def process_discovery_result(result: DiscoveryResult, emit: Emit = noop_emit) -> DataEngReport:
    """Clean, label, and persist every item in a DiscoveryResult (Req 7)."""
    report = DataEngReport()

    total = len(result.items)
    emit("dataeng", f"Processing {total} items", status="start", total=total)
    if not result.items:
        emit("dataeng", "No items to process", status="ok", persisted=0, failed=0)
        return report  # empty input → processed count 0 (Req 7.4)

    for index, item in enumerate(result.items, start=1):
        emit("dataeng.item", f"[{index}/{total}] {item.title}", status="start",
             index=index, total=total, source_url=item.url)
        try:
            cleaned = call_maybe_emit(_build_cleaned_item, item, emit=emit)
            if cleaned is None:
                emit("dataeng.item", f"Dropped (all noise): {item.url}",
                     status="skip", source_url=item.url)
                report.failures.append(
                    ProcessingFailure(source_url=item.url, reason="all-noise; nothing to persist")
                )
                report.failed += 1
                continue
            upsert_cleaned_item(cleaned)
            emit("dataeng.item", f"Persisted: {item.url}", status="ok",
                 source_url=item.url, stream=cleaned.stream.value, industry=cleaned.industry)
            report.persisted += 1
        except Exception as exc:  # noqa: BLE001 - isolate per-item failures (Req 7.2/7.3)
            logger.warning("Item %s failed: %s", item.url, exc)
            emit("dataeng.item", f"Failed: {item.url} ({exc})", status="error",
                 source_url=item.url, reason=str(exc))
            report.failures.append(ProcessingFailure(source_url=item.url, reason=str(exc)))
            report.failed += 1

    logger.info("Data engineering: %d persisted, %d failed", report.persisted, report.failed)
    emit("dataeng", f"Done: {report.persisted} persisted, {report.failed} failed",
         status="ok", persisted=report.persisted, failed=report.failed)
    return report
