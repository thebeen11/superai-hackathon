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
    # AWS credentials. Loaded from .env / environment. If left unset, boto3 falls back
    # to its default credential chain (~/.aws, instance role, sourced env vars).
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None  # required for temporary STS credentials
    # Reasoning model. The workshop account allows Amazon Nova and Claude Opus.
    # Default: Claude Opus 4.6 via the us-west-2 cross-region inference profile.
    bedrock_model_id: str = "us.anthropic.claude-opus-4-6-v1"
    bedrock_max_retries: int = 3
    # Tier 4 (Freddy) debates with two *different* model families to curb collusion
    # (PROJECT_GUIDANCE §11). The workshop account only permits Claude Opus and Amazon
    # Nova, so Bull = Claude Opus, Bear = Amazon Nova Pro — still two distinct families.
    bedrock_bull_model_id: str = "us.anthropic.claude-opus-4-6-v1"
    bedrock_bear_model_id: str = "us.amazon.nova-pro-v1:0"

    # --- Database (RDS Postgres) ---
    database_url: str | None = None


settings = Settings()
