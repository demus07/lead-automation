"""Environment-based configuration.

Only infrastructure secrets live in the environment. Business configuration (agency profile, LLM
provider choice, search providers, thresholds) lives in the `settings` table so it can be edited from
the dashboard; secret values there are encrypted with ``ENCRYPTION_KEY``.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from typing import Annotated

from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Agency Growth Engine"
    environment: str = Field("development", description="development | test | production")
    debug: bool = False

    database_url: str = "postgresql+psycopg://agency:agency@localhost:5432/agency"
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = Field("dev-insecure-change-me", min_length=16)
    encryption_key: str = ""  # Fernet key (urlsafe base64, 32 bytes). Generated in dev if blank.
    access_token_minutes: int = 60 * 12
    cookie_secure: bool = False
    cookie_domain: str | None = None
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    rate_limit_per_minute: int = 240
    login_rate_limit_per_minute: int = 10

    # URLs used to build OAuth redirect URIs
    public_api_url: str = "http://localhost:8000"
    public_app_url: str = "http://localhost:3000"

    # OAuth client credentials (optional; integrations show "not configured" without them)
    google_client_id: str = ""
    google_client_secret: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_tenant: str = "common"

    # Bootstrap admin (created on first start if no users exist)
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    # Crawler identity
    crawler_user_agent: str = "AgencyGrowthEngineBot/1.0 (+contact: set CRAWLER_CONTACT)"
    crawler_contact: str = ""
    playwright_enabled: bool = False

    celery_eager: bool = False

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            if v.strip().startswith("["):
                import json

                return json.loads(v)
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def user_agent(self) -> str:
        if self.crawler_contact:
            return f"AgencyGrowthEngineBot/1.0 (+{self.crawler_contact})"
        return self.crawler_user_agent


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production:
        if s.secret_key.startswith("dev-") or not s.encryption_key:
            raise RuntimeError("SECRET_KEY and ENCRYPTION_KEY must be set in production")
    return s
