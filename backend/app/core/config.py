from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        populate_by_name=True,
    )

    bot_token: str | None = Field(default=None, alias="BOT_TOKEN")
    webapp_url: HttpUrl | None = Field(default=None, alias="WEBAPP_URL")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/soznai.db",
        alias="DATABASE_URL",
    )
    log_file: Path = Field(default=Path("logs/soznai.log"))
    request_timeout_seconds: float = Field(default=10.0)
    retry_attempts: int = Field(default=3)
    webhook_secret_token: str | None = Field(default=None, alias="WEBHOOK_SECRET")
    admin_api_token: str | None = Field(default=None, alias="ADMIN_TOKEN")

    # AI routing and OpenAI integration
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model_primary: str = Field(default="gpt-4-mini", alias="OPENAI_MODEL_PRIMARY")
    openai_model_deep: str = Field(default="gpt-4-turbo", alias="OPENAI_MODEL_DEEP")
    openai_daily_limit_usd: float = Field(default=0.50, alias="OPENAI_DAILY_LIMIT_USD")
    openai_soft_limit_usd: float = Field(default=0.35, alias="OPENAI_SOFT_LIMIT_USD")
    openai_enable_batch: bool = Field(default=False, alias="OPENAI_ENABLE_BATCH")
    ai_router_mode: str = Field(default="auto", alias="AI_ROUTER_MODE")
    ai_cache_ttl_sec: int = Field(default=86400, alias="AI_CACHE_TTL_SEC")
    ai_max_tokens_quick: int = Field(default=120, alias="AI_MAX_TOKENS_QUICK")
    ai_max_tokens_deep: int = Field(default=400, alias="AI_MAX_TOKENS_DEEP")

    # Insight engine configuration
    insights_ai_enabled: bool = Field(default=False, alias="INSIGHTS_AI_ENABLED")
    insights_debounce_seconds: int = Field(default=300, alias="INSIGHTS_DEBOUNCE_SEC")
    insights_weeks_default: int = Field(default=4, alias="INSIGHTS_WEEKS_DEFAULT")

    version: str = Field(default_factory=lambda: Settings._load_version())

    @staticmethod
    def _load_version() -> str:
        version_env = os.getenv("VERSION")
        if version_env:
            return version_env
        version_file = Path("VERSION")
        if version_file.exists():
            return version_file.read_text(encoding="utf-8").strip()
        return "0.0.0"

    @field_validator("log_file", mode="before")
    @classmethod
    def _validate_log_file(cls, value: Path | str) -> Path:
        path = Path(value)
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @field_validator("ai_router_mode", mode="before")
    @classmethod
    def _validate_ai_mode(cls, value: str | None) -> str:
        allowed = {"auto", "mini_only", "local_only", "turbo_only"}
        if not value:
            return "auto"
        normalized = str(value).lower()
        if normalized not in allowed:
            return "auto"
        return normalized

    @field_validator("ai_cache_ttl_sec", mode="before")
    @classmethod
    def _validate_ai_ttl(cls, value: int | str | None) -> int:
        if value is None:
            return 86400
        ttl = int(value)
        return max(ttl, 60)

    @field_validator("insights_debounce_seconds", mode="before")
    @classmethod
    def _validate_insights_debounce(cls, value: int | str | None) -> int:
        if value is None:
            return 300
        debounce = int(value)
        return max(debounce, 60)

    @field_validator("database_url", mode="before")
    @classmethod
    def _validate_database_url(cls, value: str | None) -> str:
        if not value:
            value = "sqlite:///./data/soznai.db"

        normalized = str(value)
        if normalized.startswith("postgres://"):
            normalized = normalized.replace("postgres://", "postgresql://", 1)
        if normalized.startswith("postgresql://") and "+asyncpg" not in normalized:
            normalized = normalized.replace("postgresql://", "postgresql+asyncpg://", 1)
        if normalized.startswith("sqlite://") and "+aiosqlite" not in normalized:
            normalized = normalized.replace("sqlite://", "sqlite+aiosqlite://", 1)

        if normalized.startswith("sqlite+aiosqlite:///"):
            db_path = normalized.split("///", maxsplit=1)[-1]
            if db_path:
                db_file = Path(db_path)
                db_file.parent.mkdir(parents=True, exist_ok=True)

        return normalized


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor."""

    return Settings()
