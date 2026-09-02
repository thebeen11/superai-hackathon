"""Application configuration, loaded from environment / .env.

Env files are layered: an optional shared `.env` base, then a per-environment file chosen
by `APP_ENV` (`local` by default → `.env.local`; set `APP_ENV=prod` → `.env.prod`). The
later file wins, and OS environment variables outrank both — so on Cloud Run (where
`APP_ENV=prod` is set and no `.env.prod` is shipped) the platform-injected env/secrets are
used directly. Missing env files are skipped silently.
"""
from __future__ import annotations

import os

from pydantic_settings import BaseSettings, SettingsConfigDict

_APP_ENV = os.getenv("APP_ENV", "local")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", f".env.{_APP_ENV}"),  # base, then per-env overlay; last wins
        extra="ignore",
    )

    # Which environment this process loaded config for (exposed for /health, logs).
    app_env: str = _APP_ENV

    # --- Discovery source APIs ---
    exa_api_key: str | None = None
    youtube_api_key: str | None = None
    discovery_max_results_per_source: int = 5

    # --- Supadata (YouTube channel subscriptions: metadata + transcripts) ---
    # Used only by the channel-subscription source; the query-driven `/discover`
    # YouTube branch still uses YOUTUBE_API_KEY + youtube-transcript-api.
    # Billing is per credit (1 transcript = 1 credit, 1 metadata lookup = 1 credit) and
    # the free tier is 100 credits/month at 1 req/s — hence the conservative defaults.
    supadata_api_key: str | None = None
    supadata_base_url: str = "https://api.supadata.ai/v1"
    youtube_channel_backfill: int = 5           # videos pulled when a channel is added
    youtube_poll_limit: int = 10                # newest videos inspected per poll
    youtube_transcript_chunk_size: int = 1000   # chars per evidence-sized chunk
    youtube_poll_enabled: bool = True
    youtube_poll_interval_minutes: int = 1440   # 24h

    # --- Gemini on Vertex AI (reasoning) ---
    # Auth is via Application Default Credentials (ADC) — no API keys. On Cloud Run the
    # service account is used automatically; locally run `gcloud auth application-default
    # login`. If `gcp_project` is unset, google-auth resolves it from ADC.
    gcp_project: str | None = None
    # Gemini 3.x is served on the `global` endpoint, not the regional ones — asking
    # us-central1 for gemini-3.1-pro-preview / gemini-3.6-flash returns 404.
    vertex_location: str = "global"
    gemini_model: str = "gemini-3.1-pro-preview"
    gemini_max_retries: int = 3
    # Tier 4 (Freddy) debates Bull vs Bear. Originally two *different* model families to
    # curb collusion (PROJECT_GUIDANCE §11); on Gemini-only these are the same family
    # (3.1 Pro vs 3.6 Flash), so the anti-collusion guardrail is weaker — intentional
    # tradeoff.
    gemini_bull_model: str = "gemini-3.1-pro-preview"
    gemini_bear_model: str = "gemini-3.6-flash"
    # Alternating Bull/Bear turns in the chamber; each round costs one Gemini call.
    debate_rounds: int = 6

    # --- Daily crawl (day-to-day ingestion) ---
    # `POST /crawl/daily` always works; the in-process timer only runs when enabled.
    # On Cloud Run (scale-to-zero) leave it off and trigger the endpoint from Cloud
    # Scheduler instead (see deploy.sh).
    daily_crawl_query: str = (
        "stock market investing news: AI, semiconductors, energy, and the economy"
    )
    daily_crawl_max_results: int = 20
    daily_crawl_enabled: bool = False
    daily_crawl_hour_utc: int = 1  # timer fires at HH:00 UTC, crawling yesterday

    # --- Telegram daily report (macro indicators) ---
    # Sent at the end of the daily crawl, once the council has written a fresh snapshot —
    # in prod the existing Cloud Scheduler `daily-crawl` job is therefore the trigger, and
    # there is no separate schedule for the report. The bot must be an ADMIN of the target
    # channel; TELEGRAM_CHAT_ID is either "@channelname" or the numeric -100... id. With
    # either value unset the send is skipped with a recorded reason, the same posture as a
    # missing discovery key.
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None
    telegram_api_base_url: str = "https://api.telegram.org"
    telegram_daily_report_enabled: bool = True
    # A failed council leaves *yesterday's* snapshot as the latest one; don't re-send it as
    # if it were today's analysis. 0 disables the check.
    telegram_report_max_age_hours: int = 24

    # --- Macro Analyst second pass (bear-signpost gap backfill) ---
    # Pass 1 grades the fixed checklist against whatever `[MACRO]` material the crawl
    # happened to bring in, so rows nothing spoke to come back unevidenced. Pass 2 searches
    # the web for those rows specifically and re-grades only them (app/council/macro.py).
    # The fetched documents are run-scoped: grounded, cited, recorded in the snapshot's
    # source manifest — never written to `cleaned_items`. With no EXA_API_KEY the pass
    # degrades to a recorded skip, the same posture as a missing discovery key.
    macro_backfill_enabled: bool = True
    macro_backfill_max_gaps: int = 6          # bounds Exa spend when pass 1 grades nothing
    macro_backfill_results_per_gap: int = 2
    macro_backfill_max_items: int = 12
    macro_backfill_lookback_days: int = 45    # a signpost is a statement about *now*

    # --- Database (RDS Postgres) ---
    database_url: str | None = None

    # --- Agent identity layers (Agent Console) ---
    # When on, every system prompt is composed as SOUL + RULES + MENTAL MODELS +
    # PERSONALITY + the task's own instructions (see app/prompts/identity.py).
    # Set AGENT_IDENTITY_LAYERS=false to fall back to the bare task prompts.
    agent_identity_layers: bool = True


settings = Settings()
