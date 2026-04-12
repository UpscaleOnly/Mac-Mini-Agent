"""
interceptor.py — Middleware interceptor (ADR-027) with token budget enforcement (ADR-035 §4.5)

Three-stage pipeline:
  1. Pre-call checks: circuit breaker, tool registry validation, token budget estimate
  2. LLM dispatch: route to Ollama or OpenRouter
  3. Post-call writes: agent_actions record, session_budget update, cost threshold check

The interceptor is the single enforcement point for:
  - Circuit breaker (10 calls / 60 seconds, ADR-027)
  - Tool registry persona + trust tier validation (ADR-035 §5)
  - Token budget ceiling (ADR-035 §4)
  - Cost escalation threshold ($1.00, ADR-028)
"""
import time
import uuid
import logging
from collections import deque
from datetime import datetime
from typing import Optional

from app.config import get_settings
from app.db import get_pool
from app.models import (
    AgentRequest, AgentActionRecord, Persona, TrustTier,
    Routing, ToolRegistryEntry, SessionBudgetStatus,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process circuit breaker (ADR-027)
# ---------------------------------------------------------------------------
_call_timestamps: deque[float] = deque()


def _circuit_breaker_check() -> bool:
    """
    Returns True if the call is allowed, False if circuit breaker tripped.
    Tracks call timestamps in a sliding window.
    """
    settings = get_settings()
    now = time.time()
    window_start = now - settings.circuit_breaker_window_seconds

    # Purge expired timestamps
    while _call_timestamps and _call_timestamps[0] < window_start:
        _call_timestamps.popleft()

    if len(_call_timestamps) >= settings.circuit_breaker_max_calls:
        log.warning("Circuit breaker tripped: %d calls in %d seconds",
                    len(_call_timestamps), settings.circuit_breaker_window_seconds)
        return False

    _call_timestamps.append(now)
    return True


# ---------------------------------------------------------------------------
# Tool registry query (ADR-035 §5.4)
# ---------------------------------------------------------------------------
_tool_cache: dict[str, list[ToolRegistryEntry]] = {}
_tool_cache_session: Optional[uuid.UUID] = None


async def load_tool_registry(persona: Persona, session_id: uuid.UUID) -> list[ToolRegistryEntry]:
    """
    Load enabled tools for this persona from tool_registry.
    Cached per session — registry is read once at session startup (ADR-035 §5.4).
    """
    global _tool_cache, _tool_cache_session

    cache_key = persona.value
    if _tool_cache_session == session_id and cache_key in _tool_cache:
        return _tool_cache[cache_key]

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT tool_name, description, permitted_personas, risk_level,
                   irreversibility_score, min_trust_tier, requires_approval,
                   permitted_network_destinations, max_calls_per_session,
                   input_schema, output_schema, phase_available, enabled
            FROM tool_registry
            WHERE enabled = TRUE
              AND phase_available = 'phase1'
              AND $1 = ANY(permitted_personas)
        """, persona.value)

    tools = []
    for row in rows:
        tools.append(ToolRegistryEntry(
            tool_name=row["tool_name"],
            description=row["description"],
            permitted_personas=row["permitted_personas"],
            risk_level=row["risk_level"],
            irreversibility_score=row["irreversibility_score"],
            min_trust_tier=row["min_trust_tier"],
            requires_approval=row["requires_approval"],
            permitted_network_destinations=row["permitted_network_destinations"],
            max_calls_per_session=row["max_calls_per_session"],
            input_schema=row["input_schema"],
            output_schema=row["output_schema"],
            phase_available=row["phase_available"],
            enabled=row["enabled"],
        ))

    _tool_cache_session = session_id
    _tool_cache[cache_key] = tools
    log.info("Loaded %d tools for persona %s", len(tools), persona.value)
    return tools


def check_tool_permission(
    tool_name: str,
    trust_tier: int,
    tools: list[ToolRegistryEntry],
) -> tuple[bool, str]:
    """
    Validate that a tool call is permitted for the current session trust tier.
    Returns (allowed, reason).
    """
    tool = next((t for t in tools if t.tool_name == tool_name), None)
    if tool is None:
        return False, f"Tool '{tool_name}' not found in registry for this persona"

    if trust_tier < tool.min_trust_tier:
        return False, (f"Session trust tier {trust_tier} below tool minimum "
                       f"{tool.min_trust_tier} for '{tool_name}'")

    return True, "permitted"


# ---------------------------------------------------------------------------
# Token budget checks (ADR-035 §4.5)
# ---------------------------------------------------------------------------

async def get_budget_status(session_id: uuid.UUID) -> SessionBudgetStatus:
    """Fetch current session budget from session_budget table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT session_id, input_tokens_consumed, output_tokens_consumed,
                   total_tokens_consumed, budget_ceiling_tokens, cost_usd,
                   escalation_triggered
            FROM session_budget
            WHERE session_id = $1
        """, session_id)

    if row is None:
        log.error("No session_budget row for session %s", session_id)
        return SessionBudgetStatus(session_id=session_id)

    total = row["total_tokens_consumed"]
    ceiling = row["budget_ceiling_tokens"]
    pct = (total / ceiling * 100) if ceiling > 0 else 0.0

    return SessionBudgetStatus(
        session_id=row["session_id"],
        input_tokens_consumed=row["input_tokens_consumed"],
        output_tokens_consumed=row["output_tokens_consumed"],
        total_tokens_consumed=total,
        budget_ceiling_tokens=ceiling,
        cost_usd=float(row["cost_usd"]),
        escalation_triggered=row["escalation_triggered"],
        pct_consumed=pct,
    )


async def pre_call_budget_check(
    session_id: uuid.UUID,
    estimated_input_tokens: int,
) -> tuple[bool, str, SessionBudgetStatus]:
    """
    ADR-035 §4.5 — Pre-call estimate.
    Returns (proceed, reason, budget_status).
    If estimated total would push within 10% of ceiling, returns proceed=False.
    """
    budget = await get_budget_status(session_id)

    projected = budget.total_tokens_consumed + estimated_input_tokens
    if projected >= budget.budget_ceiling_tokens:
        return (False,
                f"Budget ceiling would be exceeded: {projected} >= {budget.budget_ceiling_tokens}",
                budget)

    if projected >= (budget.budget_ceiling_tokens * 0.9):
        return (False,
                f"Within 10% of budget ceiling: {projected} / {budget.budget_ceiling_tokens} "
                f"— requires operator confirmation",
                budget)

    return (True, "within budget", budget)


async def post_call_budget_update(
    session_id: uuid.UUID,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> SessionBudgetStatus:
    """
    ADR-035 §4.5 — Post-call write.
    Updates session_budget running totals atomically.
    Returns updated budget status.
    """
    settings = get_settings()
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE session_budget
            SET input_tokens_consumed = input_tokens_consumed + $2,
                output_tokens_consumed = output_tokens_consumed + $3,
                cost_usd = cost_usd + $4,
                last_updated = NOW()
            WHERE session_id = $1
        """, session_id, input_tokens, output_tokens, cost_usd)

    # Re-read for threshold check
    budget = await get_budget_status(session_id)

    # Cost threshold check (ADR-028)
    if budget.cost_usd >= settings.cost_escalation_threshold_usd and not budget.escalation_triggered:
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE session_budget
                SET escalation_triggered = TRUE, last_updated = NOW()
                WHERE session_id = $1
            """, session_id)
        budget.escalation_triggered = True
        log.warning("Cost threshold $%.2f crossed for session %s — escalation triggered",
                    settings.cost_escalation_threshold_usd, session_id)
        # TODO: Send Telegram alert here (ADR-028 approval gate)

    return budget


# ---------------------------------------------------------------------------
# Main interceptor entry point
# ---------------------------------------------------------------------------

async def intercept(req: AgentRequest) -> dict:
    """
    Main interceptor pipeline. Called before LLM dispatch.

    Returns a dict with:
      - proceed: bool — whether to continue to LLM dispatch
      - reason: str — explanation if blocked
      - budget: SessionBudgetStatus — current budget state
      - tools: list[ToolRegistryEntry] — available tools for this session

    If proceed is False, the caller should return an error to the user
    and still write an agent_actions record with the error.
    """
    result = {
        "proceed": True,
        "reason": "ok",
        "budget": None,
        "tools": [],
    }

    # 1. Circuit breaker
    if not _circuit_breaker_check():
        result["proceed"] = False
        result["reason"] = "Circuit breaker tripped — too many calls in window"
        return result

    # 2. Load tool registry for this persona
    tools = await load_tool_registry(req.persona, req.session_id)
    result["tools"] = tools

    # 3. Pre-call budget check
    # Estimate input tokens from raw_text length (rough: 1 token ≈ 4 chars)
    estimated_input = max(len(req.raw_text) // 4, 100)
    proceed, reason, budget = await pre_call_budget_check(
        req.session_id, estimated_input
    )
    result["budget"] = budget

    if not proceed:
        result["proceed"] = False
        result["reason"] = reason
        return result

    # 4. Check for pending cost escalation
    if budget.escalation_triggered:
        result["proceed"] = False
        result["reason"] = (f"Cost escalation triggered (${budget.cost_usd:.4f} >= "
                           f"${get_settings().cost_escalation_threshold_usd:.2f}) "
                           f"— awaiting operator approval")
        return result

    return result
