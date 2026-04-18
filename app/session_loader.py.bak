"""
session_loader.py — Session create / load with trust tier assignment (ADR-035 §6)

Creates session + session_budget + session_state rows atomically.
Trust tier assigned at creation based on persona and initiation context.
Trust tier reason recorded for audit (ADR-035 §6.4).
"""
import uuid
import logging
from datetime import datetime
from app.db import get_pool
from app.config import get_settings
from app.models import Persona, TrustTier

log = logging.getLogger(__name__)


def _determine_trust_tier(persona: Persona, initiated_by: str) -> tuple[TrustTier, str]:
    """
    ADR-035 §6.3 — Trust tier assigned at session creation.
    Returns (tier, reason) tuple. Reason is logged for audit.
    """
    if initiated_by == "operator_telegram":
        if persona == Persona.PROTOTYPE:
            return (TrustTier.OPERATOR_APPROVED,
                    "Interactive Prototype session via operator Telegram")
        elif persona == Persona.AUTOMATE:
            return (TrustTier.LOW_RISK_WRITE,
                    "Automate persona — low-risk write default")
        elif persona == Persona.RESEARCH:
            return (TrustTier.LOW_RISK_WRITE,
                    "Research persona — low-risk write default")

    if initiated_by == "automate_scheduler":
        return (TrustTier.LOW_RISK_WRITE,
                "Scheduled Automate job — low-risk write")

    if initiated_by == "system":
        return (TrustTier.READ_ONLY,
                "System-initiated session — read-only default")

    # Unrecognised initiation path — safe default
    return (TrustTier.READ_ONLY,
            f"Unknown initiated_by '{initiated_by}' — defaulting to read-only")


async def load_or_create_session(
    chat_id: int,
    operator_id: int,
    persona: Persona,
    initiated_by: str = "operator_telegram",
) -> dict:
    """
    Returns a session dict with session_id, trust_tier, trust_tier_reason.

    If a session already exists for this chat_id + persona combo and is active,
    returns the existing session and updates last_active_at.

    If no active session exists, creates session + session_budget + session_state
    rows atomically in a transaction.
    """
    pool = await get_pool()
    settings = get_settings()

    async with pool.acquire() as conn:
        # Check for existing active session for this chat
        row = await conn.fetchrow("""
            SELECT s.session_id, s.trust_tier, s.trust_tier_reason
            FROM sessions s
            JOIN session_state ss ON s.session_id = ss.session_id
            WHERE s.chat_id = $1
              AND s.persona = $2
              AND ss.status = 'active'
            ORDER BY s.created_at DESC
            LIMIT 1
        """, chat_id, persona.value)

        if row:
            # Update last_active_at on the existing session
            await conn.execute("""
                UPDATE sessions SET last_active_at = NOW()
                WHERE session_id = $1
            """, row["session_id"])
            log.info("Resumed session %s for chat %s / %s",
                     row["session_id"], chat_id, persona.value)
            return {
                "session_id": row["session_id"],
                "trust_tier": row["trust_tier"],
                "trust_tier_reason": row["trust_tier_reason"],
                "is_new": False,
            }

        # Create new session atomically
        trust_tier, reason = _determine_trust_tier(persona, initiated_by)
        session_id = uuid.uuid4()

        async with conn.transaction():
            # 1. sessions row
            await conn.execute("""
                INSERT INTO sessions
                    (session_id, persona, trust_tier, trust_tier_reason,
                     operator_id, chat_id, initiated_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, session_id, persona.value, int(trust_tier), reason,
                operator_id, chat_id, initiated_by)

            # 2. session_budget row (ADR-035 §4)
            await conn.execute("""
                INSERT INTO session_budget
                    (session_id, persona, budget_ceiling_tokens)
                VALUES ($1, $2, $3)
            """, session_id, persona.value,
                settings.default_budget_ceiling_tokens)

            # 3. session_state row (ADR-035 §7)
            await conn.execute("""
                INSERT INTO session_state
                    (session_id, persona, trust_tier, status)
                VALUES ($1, $2, $3, 'active')
            """, session_id, persona.value, int(trust_tier))

        log.info("Created session %s for chat %s / %s — tier %d (%s)",
                 session_id, chat_id, persona.value, trust_tier, reason)

        return {
            "session_id": session_id,
            "trust_tier": int(trust_tier),
            "trust_tier_reason": reason,
            "is_new": True,
        }


async def complete_session(session_id: uuid.UUID) -> None:
    """Mark a session as completed in session_state."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE session_state
            SET status = 'completed', completed_at = NOW()
            WHERE session_id = $1 AND status = 'active'
        """, session_id)
        log.info("Session %s marked completed.", session_id)


async def detect_crashed_sessions() -> list[dict]:
    """
    ADR-035 §7.4 — Startup crash detection.
    Finds active sessions with stale heartbeats and marks them crashed.
    Returns list of crashed session dicts for Telegram alerting.
    """
    settings = get_settings()
    pool = await get_pool()
    crashed = []

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT session_id, persona, current_step, completed_steps,
                   last_heartbeat, created_at
            FROM session_state
            WHERE status = 'active'
              AND last_heartbeat < NOW() - INTERVAL '1 second' * $1
        """, settings.heartbeat_stale_threshold_seconds)

        for row in rows:
            await conn.execute("""
                UPDATE session_state
                SET status = 'crashed',
                    failure_reason = 'Process restart detected — heartbeat stale'
                WHERE session_id = $1
            """, row["session_id"])

            crashed.append({
                "session_id": row["session_id"],
                "persona": row["persona"],
                "current_step": row["current_step"],
                "completed_steps_count": len(row["completed_steps"]) if row["completed_steps"] else 0,
                "last_heartbeat": row["last_heartbeat"],
                "created_at": row["created_at"],
            })
            log.warning("Crashed session detected: %s (%s) — last heartbeat %s",
                        row["session_id"], row["persona"], row["last_heartbeat"])

    return crashed


async def write_heartbeat(session_id: uuid.UUID) -> None:
    """Update heartbeat timestamp for an active session (ADR-035 §7)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE session_state
            SET last_heartbeat = NOW()
            WHERE session_id = $1 AND status = 'active'
        """, session_id)
