"""
models.py — Pydantic models and enums for OpenClaw runtime.

All models align to ADR-035 schema definitions.
session_id is UUID throughout.
"""
from __future__ import annotations
import uuid
from datetime import datetime
from enum import Enum, IntEnum
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Persona(str, Enum):
    PROTOTYPE = "prototype"
    AUTOMATE = "automate"
    RESEARCH = "research"


class TrustTier(IntEnum):
    """ADR-035 §6 — Session trust tiers."""
    READ_ONLY = 1           # Read operations only
    LOW_RISK_WRITE = 2      # Low-risk writes (irreversibility ≤ 9)
    OPERATOR_APPROVED = 3   # Moderate writes, shell permitted with approval
    MANUAL_GATE = 4         # All actions require explicit confirmation


class Routing(str, Enum):
    LOCAL_TIER1 = "local_tier1"     # 7B
    LOCAL_TIER2 = "local_tier2"     # 14B / 32B
    CLOUD_TIER3 = "cloud_tier3"     # Sonnet via OpenRouter
    CLOUD_TIER4 = "cloud_tier4"     # Opus — hard blocked Phase 1


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CRASHED = "crashed"
    RECOVERED = "recovered"
    CANCELLED = "cancelled"


class ActionType(str, Enum):
    TOOL_CALL = "tool_call"
    LLM_RESPONSE = "llm_response"
    TRUST_TIER_ELEVATION_REQUEST = "trust_tier_elevation_request"
    SYSTEM_EVENT = "system_event"


class Channel(str, Enum):
    """Supported input channels."""
    TELEGRAM = "telegram"
    CLI = "cli"
    WEB = "web"
    INTERNAL = "internal"       # system-initiated (nightly jobs, health checks)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class AgentRequest(BaseModel):
    """
    Inbound request from any channel.
    Channel-agnostic — Telegram, CLI, web, or internal trigger.
    """
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    session_id: uuid.UUID
    persona: Persona
    trust_tier: TrustTier
    channel: Channel
    channel_id: str                 # Telegram chat_id, CLI session, web session token
    raw_text: str
    initiated_by: str = "operator"
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Populated after LLM execution
    routing: Optional[Routing] = None
    model_used: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    response_text: str = ""
    error: Optional[str] = None


class AgentActionRecord(BaseModel):
    """
    Row written to agent_actions on every request (ADR-029, ADR-035 §4.4).
    Field names match agent_actions table columns exactly.
    """
    action_id: uuid.UUID
    session_id: uuid.UUID
    persona: str
    action_type: str = "llm_response"
    tool_name: Optional[str] = None
    model_tier: Optional[int] = None
    model_name: Optional[str] = None
    routing_decision: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    irreversibility_score: Optional[int] = None
    approval_required: bool = False
    approval_response: Optional[str] = None
    validation_verdict: Optional[str] = None
    prompt_injection_flag: bool = False
    gpu_memory_pressure: Optional[str] = None
    m1_thermal_state: Optional[str] = None
    circuit_breaker_hit: bool = False
    error_message: Optional[str] = None
    context_trimmed: bool = False
    replay_buffer_flag: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None

    @classmethod
    def from_request(cls, req: AgentRequest) -> AgentActionRecord:
        """Build an audit record from a completed AgentRequest."""
        # Map routing enum to model tier integer
        tier_map = {
            Routing.LOCAL_TIER1: 1,
            Routing.LOCAL_TIER2: 2,
            Routing.CLOUD_TIER3: 3,
            Routing.CLOUD_TIER4: 4,
        }
        model_tier = tier_map.get(req.routing) if req.routing else None

        return cls(
            action_id=req.request_id,
            session_id=req.session_id,
            persona=req.persona.value,
            action_type="llm_response",
            model_tier=model_tier,
            model_name=req.model_used or "unknown",
            routing_decision=req.routing.value if req.routing else "unknown",
            input_tokens=req.input_tokens,
            output_tokens=req.output_tokens,
            cost_usd=req.cost_usd,
            error_message=req.error,
            created_at=req.created_at,
            resolved_at=datetime.utcnow(),
        )


class ToolRegistryEntry(BaseModel):
    """Runtime representation of a tool_registry row (ADR-035 §5)."""
    tool_name: str
    description: str
    permitted_personas: list[str]
    risk_level: str
    irreversibility_score: int
    min_trust_tier: int = 1
    requires_approval: bool = False
    permitted_network_destinations: Optional[list[str]] = None
    max_calls_per_session: Optional[int] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    phase_available: str = "phase1"
    enabled: bool = True


class SessionBudgetStatus(BaseModel):
    """Current budget state for display and threshold checks."""
    session_id: uuid.UUID
    input_tokens_consumed: int = 0
    output_tokens_consumed: int = 0
    total_tokens_consumed: int = 0
    budget_ceiling_tokens: int = 50000
    cost_usd: float = 0.0
    escalation_triggered: bool = False
    pct_consumed: float = 0.0

    @property
    def near_ceiling(self) -> bool:
        """True if within 10% of budget ceiling (ADR-035 §4.5)."""
        return self.total_tokens_consumed >= (self.budget_ceiling_tokens * 0.9)
