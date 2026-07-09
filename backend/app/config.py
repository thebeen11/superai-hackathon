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

    # --- Gemini on Vertex AI (reasoning) ---
    # Auth is via Application Default Credentials (ADC) — no API keys. On Cloud Run the
    # service account is used automatically; locally run `gcloud auth application-default
    # login`. If `gcp_project` is unset, google-auth resolves it from ADC.
    gcp_project: str | None = None
    vertex_location: str = "us-central1"
    gemini_model: str = "gemini-2.5-pro"
    gemini_max_retries: int = 3
    # Tier 4 (Freddy) debates Bull vs Bear. Originally two *different* model families to
    # curb collusion (PROJECT_GUIDANCE §11); on Gemini-only these are the same family
    # (pro vs flash), so the anti-collusion guardrail is weaker — intentional tradeoff.
    gemini_bull_model: str = "gemini-2.5-pro"
    gemini_bear_model: str = "gemini-2.5-flash"

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

    # --- Database (RDS Postgres) ---
    database_url: str | None = None


settings = Settings()
