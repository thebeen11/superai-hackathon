"""Application configuration, loaded from environment / .env."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Discovery source APIs ---
    exa_api_key: str | None = None
    youtube_api_key: str | None = None
    discovery_max_results_per_source: int = 5

    # --- Bedrock (reasoning) ---
    aws_region: str = "us-west-2"
    # Reasoning model. The workshop account allows Amazon Nova and Claude Opus.
    # Default: Claude Opus 4.6 via the us-west-2 cross-region inference profile.
    bedrock_model_id: str = "us.anthropic.claude-opus-4-6-v1"
    bedrock_max_retries: int = 3

    # --- Database (RDS Postgres) ---
    database_url: str | None = None


settings = Settings()
