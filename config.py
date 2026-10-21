"""
config.py - Application Configuration
======================================
Uses Pydantic Settings for type-safe configuration from environment variables.
Powered by Groq.
"""

import logging
import sys

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _setup_logging(level: str) -> logging.Logger:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Groq
    # -------------------------------------------------------------------------
    groq_api_key: str = Field(
        default="",
        description="Groq API key. Set via GROQ_API_KEY env var.",
    )
    groq_model: str = Field(
        default="openai/gpt-oss-120b",
        description="Groq-hosted model name.",
    )
    groq_max_tokens: int = Field(
        default=4096,
        ge=256,
        le=32768,
        description="Maximum output tokens per response.",
    )

    # -------------------------------------------------------------------------
    # Optional Supabase authentication and history
    # -------------------------------------------------------------------------
    supabase_url: str = Field(
        default="",
        description="Supabase project URL used for optional user accounts and history.",
    )
    supabase_anon_key: str = Field(
        default="",
        description="Supabase anon/publishable key; never use a service-role key here.",
    )
    app_api_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Internal FastAPI service URL used by the Streamlit frontend.",
    )
    app_api_key: str = Field(
        default="",
        description="Shared secret protecting internal FastAPI endpoints.",
    )

    # -------------------------------------------------------------------------
    # File Upload Limits
    # -------------------------------------------------------------------------
    max_upload_size_mb: float = Field(default=50.0, gt=0, le=500)
    max_rows: int = Field(default=500_000, gt=0)
    max_columns: int = Field(default=200, gt=0)

    # -------------------------------------------------------------------------
    # Agent Behavior
    # -------------------------------------------------------------------------
    max_tool_calls: int = Field(default=10, ge=1, le=20)
    api_timeout_seconds: int = Field(default=60, ge=5, le=300)
    max_result_rows: int = Field(default=1000, ge=1)
    max_chart_categories: int = Field(default=50, ge=2)

    # -------------------------------------------------------------------------
    # Application
    # -------------------------------------------------------------------------
    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")

    @field_validator("app_env")
    @classmethod
    def _validate_app_env(cls, v: str) -> str:
        allowed = {"development", "production"}
        if v.lower() not in allowed:
            raise ValueError(f"app_env must be one of {allowed}")
        return v.lower()

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    # -------------------------------------------------------------------------
    # Derived helpers
    # -------------------------------------------------------------------------
    @property
    def max_upload_size_bytes(self) -> int:
        return int(self.max_upload_size_mb * 1024 * 1024)

    @property
    def has_groq_key(self) -> bool:
        return bool(self.groq_api_key and self.groq_api_key.strip())

    @property
    def has_supabase_config(self) -> bool:
        return bool(
            self.supabase_url.strip()
            and self.supabase_anon_key.strip()
        )

    def validate_ai_configuration(self) -> None:
        if not self.has_groq_key:
            raise RuntimeError(
                "Groq API key is not configured. "
                "Please set GROQ_API_KEY in your .env file. "
                "Get an API key at: https://console.groq.com/keys"
            )

    def safe_summary(self) -> dict:
        return {
            "model": self.groq_model,
            "max_tokens": self.groq_max_tokens,
            "max_upload_size_mb": self.max_upload_size_mb,
            "max_rows": self.max_rows,
            "max_columns": self.max_columns,
            "max_tool_calls": self.max_tool_calls,
            "environment": self.app_env,
            "api_key_configured": self.has_groq_key,
            "accounts_configured": self.has_supabase_config,
            "backend_configured": bool(self.app_api_key.strip()),
        }


def get_settings() -> Settings:
    """Return fresh application settings — reads .env on every call."""
    s = Settings()
    _setup_logging(s.log_level)
    return s


settings: Settings = get_settings()
