"""
persona_router.py — Persona identification from Telegram context (ADR-017)

Each Telegram bot maps to one persona:
  - Prototype bot → prototype persona
  - Automate bot  → automate persona
  - Research bot  → research persona

In Phase 1, all three bots route through a single FastAPI instance.
The bot token in the webhook URL identifies which persona is active.

For now, a single bot handles all personas with a /persona command
or chat-based routing. This will be split to per-persona bots
when the three Telegram bots are created on setup day.
"""
import logging
from app.models import Persona
from app.config import get_settings

log = logging.getLogger(__name__)

# Maps Telegram bot tokens to persona. Populated on startup.
_token_persona_map: dict[str, Persona] = {}


def configure_persona_routing(token_map: dict[str, Persona]) -> None:
    """
    Called on startup with a mapping of bot tokens to personas.
    In single-bot Phase 1, this maps the single token to a default persona.
    """
    global _token_persona_map
    _token_persona_map = token_map
    log.info("Persona routing configured: %d bot(s)", len(token_map))


def resolve_persona(
    bot_token: str | None = None,
    command_text: str | None = None,
) -> Persona:
    """
    Determine the active persona for an incoming request.

    Priority:
      1. Bot token mapping (per-persona bots)
      2. Explicit /persona command in message text
      3. Default to prototype
    """
    # 1. Token-based routing (multi-bot setup)
    if bot_token and bot_token in _token_persona_map:
        return _token_persona_map[bot_token]

    # 2. Command-based routing (single-bot Phase 1)
    if command_text:
        lower = command_text.strip().lower()
        if lower.startswith("/prototype"):
            return Persona.PROTOTYPE
        elif lower.startswith("/automate"):
            return Persona.AUTOMATE
        elif lower.startswith("/research"):
            return Persona.RESEARCH

    # 3. Default
    return Persona.PROTOTYPE
