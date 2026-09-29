"""
audit.py — agent_actions audit record writer (ADR-029, ADR-035 §4.4)

Every request writes exactly one row to agent_actions.
No exceptions — errors are recorded with error_message column populated.
This is the NIST AU-2 / AU-3 compliance mechanism.

Column list matches agent_actions table in schema.sql exactly.
Python attribute names use llm_ prefix (llm_model_tier, llm_model_name)
to avoid Pydantic v2 model_ namespace collision, but the SQL INSERT
maps them to the original database columns (model_tier, model_name).

AU-5 — response to audit logging failure (operator decision, September 29,
2026, Entry #046). An audit-write failure must NOT fail the request, and must
not require the operator to review each failure by hand. So:
  - write_action() never raises.
  - A failed insert is appended to a JSONL spool on the host
    (./spool, mounted at /app/spool) and logged once at ERROR.
  - The next successful write replays the spool automatically. Inserts use
    ON CONFLICT DO NOTHING on the (action_id, created_at) primary key, so a
    record can never be written twice.
  - Only if the spool itself cannot be written is a record lost; that is
    logged at CRITICAL.
Background: F7 (ADR-046 §13) — from August 1 to September 29, 2026 a missing
partition made every insert fail, and because this function raised, every
/agent request failed with it.
"""
import asyncio
import logging
import os
from pathlib import Path

from app.db import get_pool
from app.models import AgentActionRecord

log = logging.getLogger(__name__)

SPOOL_PATH = Path(os.environ.get("AUDIT_SPOOL_PATH", "/app/spool/audit_spool.jsonl"))
_spool_lock = asyncio.Lock()

_INSERT_SQL = """
    INSERT INTO agent_actions (
        action_id, session_id, persona, action_type,
        tool_name, model_tier, model_name, routing_decision,
        input_tokens, output_tokens, cost_usd,
        irreversibility_score, approval_required, approval_response,
        validation_verdict, prompt_injection_flag,
        gpu_memory_pressure, m1_thermal_state,
        circuit_breaker_hit, error_message,
        context_trimmed, replay_buffer_flag,
        created_at, resolved_at
    ) VALUES (
        $1,  $2,  $3,  $4,
        $5,  $6,  $7,  $8,
        $9,  $10, $11,
        $12, $13, $14,
        $15, $16,
        $17, $18,
        $19, $20,
        $21, $22,
        $23, $24
    )
    ON CONFLICT (action_id, created_at) DO NOTHING
"""


async def _insert(conn, record: AgentActionRecord) -> None:
    await conn.execute(
        _INSERT_SQL,
        record.action_id,
        record.session_id,
        record.persona,
        record.action_type,
        record.tool_name,
        record.llm_model_tier,
        record.llm_model_name,
        record.routing_decision,
        record.input_tokens,
        record.output_tokens,
        record.cost_usd,
        record.irreversibility_score,
        record.approval_required,
        record.approval_response,
        record.validation_verdict,
        record.prompt_injection_flag,
        record.gpu_memory_pressure,
        record.m1_thermal_state,
        record.circuit_breaker_hit,
        record.error_message,
        record.context_trimmed,
        record.replay_buffer_flag,
        record.created_at,
        record.resolved_at,
    )


async def write_action(record: AgentActionRecord) -> None:
    """
    Insert a single row into agent_actions.
    Called after every LLM dispatch or error, unconditionally. Never raises.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await _insert(conn, record)
    except Exception as e:
        log.error(
            "AUDIT WRITE FAILED — record spooled for automatic replay (AU-5): "
            "%s: %s | action=%s", type(e).__name__, e, record.action_id,
        )
        await _spool(record)
        return

    log.debug("Audit record written: action=%s session=%s persona=%s cost=$%.6f",
              record.action_id, record.session_id, record.persona, record.cost_usd)

    if _spool_pending():
        await _replay_spool()


def _spool_pending() -> bool:
    try:
        return SPOOL_PATH.exists() and SPOOL_PATH.stat().st_size > 0
    except OSError:
        return False


async def _spool(record: AgentActionRecord) -> None:
    async with _spool_lock:
        try:
            SPOOL_PATH.parent.mkdir(parents=True, exist_ok=True)
            with SPOOL_PATH.open("a", encoding="utf-8") as f:
                f.write(record.model_dump_json() + "\n")
        except Exception as e:
            log.critical(
                "AUDIT RECORD LOST — database write and spool both failed: "
                "%s: %s | action=%s", type(e).__name__, e, record.action_id,
            )


async def _replay_spool() -> None:
    """Re-insert spooled records; keep any that still fail. Never raises."""
    async with _spool_lock:
        try:
            lines = [l for l in SPOOL_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception as e:
            log.error("Audit spool unreadable — %s: %s", type(e).__name__, e)
            return

        remaining: list[str] = []
        replayed = 0
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                for i, line in enumerate(lines):
                    try:
                        await _insert(conn, AgentActionRecord.model_validate_json(line))
                        replayed += 1
                    except Exception as e:
                        log.error("Audit spool replay stopped — %s: %s", type(e).__name__, e)
                        remaining = lines[i:]
                        break
        except Exception as e:
            log.error("Audit spool replay could not connect — %s: %s", type(e).__name__, e)
            return

        try:
            tmp = SPOOL_PATH.with_suffix(".tmp")
            tmp.write_text("".join(l + "\n" for l in remaining), encoding="utf-8")
            os.replace(tmp, SPOOL_PATH)
        except Exception as e:
            log.error("Audit spool rewrite failed — %s: %s (records may replay again; "
                      "ON CONFLICT makes that harmless)", type(e).__name__, e)
        log.warning("Audit spool replayed: %d written, %d still pending", replayed, len(remaining))
