"""
config.py — Application settings loader.

Non-secret configuration loaded from .env via Docker Compose env_file directive.
Secrets (tokens, passwords, API keys) loaded from macOS Keychain at startup.
Keychain entries use account=openclaw, service=SECRET_NAME.

ADR-039 A1: Keychain migration — plaintext credentials removed from .env.
Never commit secrets to Git (.gitignore enforced).
"""
import subprocess
import logging
from functools import lru_cache
from pydantic_settings import BaseSettings

log = logging.getLogger(__name__)


def _keychain_get(service: str, fallback: str = "") -> str:
    """
    Read a secret from macOS Keychain.
    Returns fallback if the entry is missing or the command fails.
    Inside Docker, Keychain is unavailable — fallback to environment variable.
    """
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", "openclaw", "-s", service, "-w"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            value = result.stdout.strip()
            if value and value != "empty":
                return value
    except (FileNotFoundError, subprocess.TimeoutExpired):
        # security command not available (Linux/Docker) — fall through to fallback
        pass
    except Exception as e:
        log.warning("Keychain lookup failed for %s: %s", service, e)

    return fallback


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


class SecretsOverlay:
    """
    Wraps Settings and overlays Keychain values on top of environment values
    for the six secret fields. All other settings pass through unchanged.

    Keychain is queried once at instantiation. The result is cached via
    get_settings() / lru_cache so Keychain is read exactly once per process.
    """

    def __init__(self, base: Settings):
        self._base = base

        # Overlay secrets from Keychain (falls back to .env value if Keychain unavailable)
        self.postgres_password = _keychain_get(
            "POSTGRES_PASSWORD", base.postgres_password
        )
        self.telegram_bot_token = _keychain_get(
            "TELEGRAM_TOKEN_ROUTER", base.telegram_bot_token
        )
        self.openrouter_api_key = _keychain_get(
            "OPENROUTER_API_KEY", base.openrouter_api_key
        )

        # Per-persona tokens available for the router bot and telegram_bot.py
        self.telegram_token_prototype = _keychain_get("TELEGRAM_TOKEN_PROTOTYPE")
        self.telegram_token_automate = _keychain_get("TELEGRAM_TOKEN_AUTOMATE")
        self.telegram_token_research = _keychain_get("TELEGRAM_TOKEN_RESEARCH")
        self.telegram_token_router = _keychain_get(
            "TELEGRAM_TOKEN_ROUTER", base.telegram_bot_token
        )

    def __getattr__(self, name: str):
        """Pass through any attribute not explicitly overlaid to the base Settings."""
        return getattr(self._base, name)


@lru_cache()
def get_settings() -> SecretsOverlay:
    base = Settings()
    overlay = SecretsOverlay(base)
    log.info("Settings loaded. Keychain overlay applied.")
    return overlay
