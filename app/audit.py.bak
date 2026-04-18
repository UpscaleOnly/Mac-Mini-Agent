"""
audit.py — agent_actions audit record writer (ADR-029, ADR-035 §4.4)

Every request writes exactly one row to agent_actions.
No exceptions — errors are recorded with error column populated.
This is the NIST AU-2 / AU-3 compliance mechanism.
"""
import logging
from app.db import get_pool
from app.models import AgentActionRecord

log = logging.getLogger(__name__)


async def write_action(record: AgentActionRecord) -> None:
    """
    Insert a single row into agent_actions.
    Called after every LLM dispatch or error, unconditionally.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO agent_actions (
                action_id, session_id, persona, trust_tier, action_type,
                tool_name, operator_telegram_id, raw_input, routing,
                model_used, input_tokens, output_tokens, cost_usd,
                response_text, validation_verdict, irreversibility_score,
                approval_status, error, created_at
            ) VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9,
                $10, $11, $12, $13,
                $14, $15, $16,
                $17, $18, $19
            )
        """,
            record.action_id,
            record.session_id,
            record.persona,
            record.trust_tier,
            record.action_type,
            record.tool_name,
            record.operator_telegram_id,
            record.raw_input,
            record.routing,
            record.model_used,
            record.input_tokens,
            record.output_tokens,
            record.cost_usd,
            record.response_text,
            record.validation_verdict,
            record.irreversibility_score,
            record.approval_status,
            record.error,
            record.created_at,
        )

    log.debug("Audit record written: action=%s session=%s persona=%s cost=$%.6f",
              record.action_id, record.session_id, record.persona, record.cost_usd)
