"""
config.py — Application settings from environment variables.

All sensitive values loaded from .env file via Docker Compose env_file directive.
Never committed to Git (.gitignore enforced).
"""
from functools import lru_cache
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # PostgreSQL
    postgres_host: str = "openclaw_postgres"
    postgres_port: int = 5432
    postgres_db: str = "openclaw"
    postgres_user: str = "openclaw"
    postgres_password: str = "changeme"

    # Ollama
    ollama_host: str = "openclaw_ollama"
    ollama_port: int = 11434
    ollama_default_model: str = "gemma4:e4b"

    # OpenRouter (cloud escalation — Phase 1 Sonnet only)
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-sonnet-4-20250514"

    # Telegram
    telegram_bot_token: str = ""
    telegram_operator_id: int = 0

    # Budget defaults (ADR-035 §4, ADR-028)
    default_budget_ceiling_tokens: int = 50000
    cost_escalation_threshold_usd: float = 1.00

    # Quiet hours (ADR-028) — 24h format
    quiet_hours_start: int = 19  # 7 PM
    quiet_hours_end: int = 7     # 7 AM

    # Circuit breaker (ADR-027)
    circuit_breaker_max_calls: int = 10
    circuit_breaker_window_seconds: int = 60

    # Session heartbeat (ADR-035 §7)
    heartbeat_interval_seconds: int = 30
    heartbeat_stale_threshold_seconds: int = 90

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
