"""Telegram Bot API transport — sends a message to one chat/channel.

Pure transport: this module knows nothing about the council, `CouncilReport`, or what a
macro indicator is. Formatting lives in `daily_report.py`, the same split
`discovery/supadata.py` keeps between HTTP and domain mapping.

Operator setup, because every failure mode here is a setup mistake:

  1. Create a bot with @BotFather; it hands you `TELEGRAM_BOT_TOKEN`.
  2. Add that bot to the target channel **as an administrator with "Post Messages"**.
     A bot that is merely a member cannot post — Telegram answers 403.
  3. `TELEGRAM_CHAT_ID` is either the public `@channelusername` or the numeric id of a
     private channel (the `-100…` form).

Docs: https://core.telegram.org/bots/api#sendmessage
"""
from __future__ import annotations

import logging
import time

from ..config import settings

logger = logging.getLogger(__name__)

_TIMEOUT_S = 30.0

# Telegram's hard cap on a single sendMessage `text`.
MAX_MESSAGE_CHARS = 4096

# 429 is a *rate* limit, not a permanent refusal — Telegram tells us how long to wait in
# `parameters.retry_after`, so back off and retry rather than dropping the report.
_RATE_LIMIT_RETRIES = 3
_RATE_LIMIT_BACKOFF_S = 1.5


class TelegramError(Exception):
    """A Telegram response we cannot use. `code` is Telegram's own `description`."""

    def __init__(self, message: str, *, code: str = "", status: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class TelegramUnavailable(Exception):
    """Credentials are missing or rejected — the whole channel is unusable.

    Same role `SourceUnavailable` plays for a discovery source: not a transient failure of
    one message, but a configuration problem that every send will hit.
    """


def _require_credentials() -> tuple[str, str]:
    """The bot token and chat id, or `TelegramUnavailable` naming which one is missing.

    An empty string counts as unset: Cloud Run mounts a Secret Manager value verbatim, so
    an unfilled secret arrives as `""` rather than as an absent variable.
    """
    token = (settings.telegram_bot_token or "").strip()
    chat_id = (settings.telegram_chat_id or "").strip()
    if not token:
        raise TelegramUnavailable("TELEGRAM_BOT_TOKEN not set")
    if not chat_id:
        raise TelegramUnavailable("TELEGRAM_CHAT_ID not set")
    return token, chat_id


def _retry_after(body: dict, headers) -> float | None:
    """Seconds Telegram asked us to wait, from the JSON body or the header, if either says."""
    params = body.get("parameters")
    if isinstance(params, dict):
        value = params.get("retry_after")
        if isinstance(value, (int, float)):
            return float(value)
    header = headers.get("Retry-After") if headers else None
    if header and str(header).replace(".", "", 1).isdigit():
        return float(header)
    return None


def send_message(text: str) -> None:
    """Post one message to the configured chat, retrying rate-limit rejections.

    Raises `TelegramUnavailable` when the credentials themselves are unusable (so the caller
    can skip the whole notification with a recorded reason) and `TelegramError` for anything
    else, including a rate limit that survives every retry.
    """
    import httpx

    token, chat_id = _require_credentials()
    url = f"{settings.telegram_api_base_url.rstrip('/')}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    for attempt in range(_RATE_LIMIT_RETRIES + 1):
        try:
            response = httpx.request("POST", url, json=payload, timeout=_TIMEOUT_S)
        except httpx.HTTPError as exc:
            raise TelegramError(f"Telegram request failed: {exc}") from exc

        if response.status_code < 400:
            return

        # Telegram's error envelope: {ok: false, error_code, description, parameters}
        try:
            body = response.json()
        except ValueError:
            body = {}
        description = str(body.get("description") or response.text or f"HTTP {response.status_code}")

        if response.status_code == 429:
            if attempt < _RATE_LIMIT_RETRIES:
                delay = _retry_after(body, response.headers) or _RATE_LIMIT_BACKOFF_S * (2**attempt)
                logger.debug("Telegram rate-limited; retrying in %.1fs", delay)
                time.sleep(delay)
                continue
            raise TelegramError(description, code="rate-limited", status=429)

        if response.status_code in (401, 403, 404):
            # 401 = bad token, 404 = no bot with that id, 403 = the bot is not an admin of
            # the channel (or was removed). All three are setup problems, not bad messages.
            raise TelegramUnavailable(f"Telegram unavailable ({response.status_code}): {description}")

        raise TelegramError(description, code=str(body.get("error_code") or ""),
                            status=response.status_code)

    raise TelegramError("Telegram sendMessage exhausted its retries")
