"""Application configuration.

All settings come from environment variables prefixed with ``TESSERA_`` (or a
``.env`` file). Secrets are never hard-coded for production; the development
defaults below are rejected when ``TESSERA_ENV=production``.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]  # gotham_like/
DATA_DIR = ROOT_DIR / "data"

_DEV_SECRET = "dev-only-insecure-secret-change-me-0123456789abcdef"
# Fernet key (urlsafe base64 of 32 bytes). Development only.
_DEV_ENC_KEY = "ZGV2LW9ubHktZW5jcnlwdGlvbi1rZXktMzJieXRlcyE="


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TESSERA_", env_file=".env", extra="ignore")

    env: str = "development"
    app_name: str = "Tessera Investigative Workbench"
    version: str = "0.1.0"

    database_url: str = "postgresql+psycopg://tessera:tessera@localhost:5432/tessera"
    redis_url: str | None = "redis://localhost:6379/0"

    secret_key: str = _DEV_SECRET
    encryption_key: str = _DEV_ENC_KEY
    access_token_minutes: int = 60
    session_idle_minutes: int = 120

    rate_limit_per_minute: int = 600
    login_rate_limit_per_minute: int = 20

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    ontology_path: Path = DATA_DIR / "schemas" / "ontology.json"
    rules_path: Path = DATA_DIR / "schemas" / "rules.json"
    synthetic_dir: Path = DATA_DIR / "synthetic"

    # Guard rails for graph operations (never ship the full graph to a client)
    graph_max_nodes: int = 2000
    graph_max_depth: int = 5
    graph_max_fanout: int = 200
    path_max_results: int = 50

    retention_days_audit: int = 2555  # ~7 years
    retention_days_raw_records: int = 1825

    log_level: str = "INFO"
    log_json: bool = True

    @model_validator(mode="after")
    def _reject_dev_secrets_in_prod(self) -> "Settings":
        if self.env == "production":
            if self.secret_key == _DEV_SECRET or self.encryption_key == _DEV_ENC_KEY:
                raise ValueError("Development secrets must not be used in production")
            if len(self.secret_key) < 32:
                raise ValueError("TESSERA_SECRET_KEY must be at least 32 characters")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
