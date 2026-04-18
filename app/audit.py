"""
audit.py — agent_actions audit record writer (ADR-029, ADR-035 §4.4)

Every request writes exactly one row to agent_actions.
No exceptions — errors are recorded with error_message column populated.
This is the NIST AU-2 / AU-3 compliance mechanism.

Column list matches agent_actions table in schema.sql exactly.
Python attribute names use llm_ prefix (llm_model_tier, llm_model_name)
to avoid Pydantic v2 model_ namespace collision, but the SQL INSERT
maps them to the original database columns (model_tier, model_name).
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
        """,
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

    log.debug("Audit record written: action=%s session=%s persona=%s cost=$%.6f",
              record.action_id, record.session_id, record.persona, record.cost_usd)
