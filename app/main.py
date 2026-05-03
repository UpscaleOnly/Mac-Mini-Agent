"""
main.py — OpenClaw FastAPI entry point

Request flow (ADR-027):
  Any Channel (Telegram, CLI, web, internal)
    → POST /agent (channel-agnostic)
    → Identity verification (operator user_id OR internal token)
    → Session Loader / Creator (ADR-035 trust tier)
    → Interceptor (ADR-027 + ADR-035 budget)
    → Persona Router
    → LLM Execution (Ollama / OpenRouter)
    → agent_actions write (ALWAYS, no exceptions)
    → JSON response returned to caller

Channel adapters:
  - Telegram bot (telegram_bot module) — polls Telegram, POSTs to /agent, sends reply
  - /webhook/{bot_token} — receives Telegram webhooks, POSTs internally to pipeline
  - Future: CLI, web UI, internal scheduler

Identity verification (Session 19 update — closes ADR-038 §6 gap):
  Two trust paths, evaluated in order:
    1. INTERNAL TOKEN PATH — if X-Internal-Auth header is present and matches
       INTERNAL_API_TOKEN, the request is trusted as system-initiated. The body's
       user_id field is IGNORED in this path (per Session 19 decision: body fields
       cannot be used as trust signals).
    2. OPERATOR USER_ID PATH — if no internal token, body.user_id MUST equal the
       configured operator ID. Anything else (including empty string) is rejected
       and logged as a security event.

  Unauthorized rejections write a security_events row and fire a real-time
  Telegram alert per ADR-038 §6. Two lightweight rate counters track probing:
    - Global counter: > 10 unauthorized requests in 60 min → escalation alert
    - Per-IP counter: > 5 from same source IP in 60 min → escalation alert

Startup sequence:
  1. Init PostgreSQL pool and bootstrap schema
  2. Detect crashed sessions (ADR-035 §7.4)
  3. Start heartbeat background task (asyncio — continuous)
  4. Start APScheduler (timed jobs: keep-warm, weekly digest ADR-031)
"""
import asyncio
import os
import time
import uuid
import logging
from collections import deque
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import get_settings
from app.db import init_pool, close_pool
from app.session_loader import (
    load_or_create_session, detect_crashed_sessions, write_heartbeat,
)
from app.interceptor import intercept, post_call_budget_update
from app.persona_router import resolve_persona
from app.llm import execute
from app.audit import write_action
from app.security import write_security_event, send_security_alert, mark_alert_sent
from app.models import AgentRequest, AgentActionRecord, Persona, Channel
from app.scheduling.scheduler import start_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal authentication token (Session 19 — ADR-038 §6 closure)
# ---------------------------------------------------------------------------
# Read once at module load. System-initiated callers (jobs.py weekly digest,
# future scheduled tasks) send this in the X-Internal-Auth header to bypass
# the operator user_id check. The token never leaves the Docker network.
#
# If unset, internal-token auth is disabled and only operator user_id works.
# That breaks scheduled jobs — set INTERNAL_API_TOKEN in .env before deploy.
INTERNAL_API_TOKEN: str = os.environ.get("INTERNAL_API_TOKEN", "").strip()

# ---------------------------------------------------------------------------
# Unauthorized rate counters (in-memory, per-process)
# ---------------------------------------------------------------------------
# Two counters track unauthorized request bursts:
#   _unauth_global    — all unauthorized requests, regardless of source
#   _unauth_by_ip     — per source IP (best effort; rotated/spoofed IPs evade)
#
# Both windows are 60 minutes. Threshold-crossing fires ONE additional
# escalation alert; individual events still write security_events rows.
_UNAUTH_WINDOW_SECONDS: int = 3600
_UNAUTH_GLOBAL_THRESHOLD: int = 10
_UNAUTH_PER_IP_THRESHOLD: int = 5

_unauth_global: deque[float] = deque()
_unauth_by_ip: dict[str, deque[float]] = {}

# Track which thresholds we've already alerted on within the current window
# to prevent alert spam (one escalation alert per threshold crossing).
_unauth_global_alert_sent_until: float = 0.0
_unauth_ip_alert_sent_until: dict[str, float] = {}


def _record_unauthorized(client_ip: str) -> tuple[bool, bool]:
    """
    Append timestamps to global and per-IP counters, prune expired entries,
    and return (global_threshold_hit, per_ip_threshold_hit) flags.

    Each flag is True only at the moment of crossing — repeat hits within
    the same window do not re-fire until the window rolls over.
    """
    global _unauth_global_alert_sent_until
    now = time.time()
    cutoff = now - _UNAUTH_WINDOW_SECONDS

    # Global counter
    while _unauth_global and _unauth_global[0] < cutoff:
        _unauth_global.popleft()
    _unauth_global.append(now)
    global_count = len(_unauth_global)

    global_hit = False
    if global_count >= _UNAUTH_GLOBAL_THRESHOLD and now >= _unauth_global_alert_sent_until:
        global_hit = True
        _unauth_global_alert_sent_until = now + _UNAUTH_WINDOW_SECONDS

    # Per-IP counter
    per_ip_hit = False
    if client_ip:
        ip_deque = _unauth_by_ip.setdefault(client_ip, deque())
        while ip_deque and ip_deque[0] < cutoff:
            ip_deque.popleft()
        ip_deque.append(now)
        ip_count = len(ip_deque)

        ip_alert_until = _unauth_ip_alert_sent_until.get(client_ip, 0.0)
        if ip_count >= _UNAUTH_PER_IP_THRESHOLD and now >= ip_alert_until:
            per_ip_hit = True
            _unauth_ip_alert_sent_until[client_ip] = now + _UNAUTH_WINDOW_SECONDS

    return (global_hit, per_ip_hit)


# Active sessions for heartbeat tracking
_active_sessions: set[uuid.UUID] = set()
_heartbeat_task: asyncio.Task | None = None


async def _heartbeat_loop():
    """Background task: write heartbeat for all active sessions every 30s."""
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.heartbeat_interval_seconds)
        for sid in list(_active_sessions):
            try:
                await write_heartbeat(sid)
            except Exception as e:
                log.error("Heartbeat write failed for %s: %s", sid, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global _heartbeat_task

    # Startup
    await init_pool()
    log.info("PostgreSQL pool initialised.")

    # Internal token presence check (warn-only — not fatal)
    if not INTERNAL_API_TOKEN:
        log.warning(
            "INTERNAL_API_TOKEN is not set. Scheduled jobs (weekly digest) "
            "will be rejected with 403. Set INTERNAL_API_TOKEN in .env."
        )
    else:
        log.info("INTERNAL_API_TOKEN configured (length %d).", len(INTERNAL_API_TOKEN))

    # Crash detection (ADR-035 §7.4)
    crashed = await detect_crashed_sessions()
    if crashed:
        for c in crashed:
            log.warning(
                "CRASHED SESSION: %s (%s) — step: %s, completed: %d, last heartbeat: %s",
                c["session_id"], c["persona"], c["current_step"],
                c["completed_steps_count"], c["last_heartbeat"],
            )
        log.warning("Total crashed sessions detected on startup: %d", len(crashed))
    else:
        log.info("No crashed sessions detected on startup.")

    # Start heartbeat background task (continuous asyncio — not a scheduled job)
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    log.info("Heartbeat background task started.")

    # Start APScheduler — keep-warm and weekly digest (ADR-031)
    start_scheduler()

    yield

    # Shutdown
    shutdown_scheduler()
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
    await close_pool()
    log.info("Shutdown complete.")


app = FastAPI(
    title="OpenClaw Agent Server",
    version="0.4.1",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Inbound request model for /agent endpoint
# ---------------------------------------------------------------------------

class AgentInput(BaseModel):
    """
    Channel-agnostic inbound request.
    Any channel adapter POSTs this to /agent.
    """
    persona: str                        # prototype, automate, research
    text: str                           # user message
    channel: str = "telegram"           # telegram, cli, web, internal
    channel_id: str = ""                # Telegram chat ID, CLI session, etc.
    user_id: str = ""                   # operator identity for verification
    initiated_by: str = "operator"      # operator, automate_scheduler, system


# ---------------------------------------------------------------------------
# Health check (ADR-037, hw_collector)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.4.1"}


# ---------------------------------------------------------------------------
# Identity verification helper (Session 19 — ADR-038 §6 closure)
# ---------------------------------------------------------------------------

async def _verify_identity(
    body: AgentInput,
    request: Request,
) -> Optional[JSONResponse]:
    """
    Verify request identity. Returns None if authorized, else a 403 JSONResponse.

    Two trust paths:
      1. X-Internal-Auth header matches INTERNAL_API_TOKEN — system-initiated,
         body.user_id is ignored.
      2. body.user_id matches configured operator ID — operator-initiated.

    Anything else is unauthorized: writes security_events row, fires Telegram
    alert, increments rate counters. Threshold-crossing fires escalation alert.
    """
    settings = get_settings()
    operator_id = str(settings.telegram_operator_id)

    # Path 1: Internal token (system-initiated jobs)
    auth_header = request.headers.get("X-Internal-Auth", "")
    if INTERNAL_API_TOKEN and auth_header and auth_header == INTERNAL_API_TOKEN:
        # Trusted system call. user_id is not consulted.
        return None

    # Path 2: Operator user_id check
    # Empty string is no longer a valid trust signal (Session 19 decision).
    if body.user_id and body.user_id == operator_id:
        return None

    # ── Unauthorized ──────────────────────────────────────────────────────
    client_ip = request.client.host if request.client else "unknown"
    user_id_value = body.user_id or "(empty)"

    log.warning(
        "Unauthorized /agent request — user_id=%s client_ip=%s persona=%s",
        user_id_value, client_ip, body.persona,
    )

    # Write the unauthorized_user security event (ADR-038 §6, severity=critical)
    pattern_value = f"user_id={user_id_value}"
    event_id = await write_security_event(
        event_type="unauthorized_user",
        severity="critical",
        source="main_identity_check",
        persona=body.persona,
        session_id=None,                # no session yet — pre-pipeline check
        channel=body.channel,
        channel_id=body.channel_id or None,
        user_id=user_id_value,
        input_text=body.text,
        pattern_matched=pattern_value,
        action_taken="blocked",
        alert_sent=False,
        raw_detail={"client_ip": client_ip, "initiated_by": body.initiated_by},
    )

    # Fire real-time Telegram alert (quiet hours overridden for critical)
    try:
        await send_security_alert(
            event_type="unauthorized_user",
            severity="critical",
            persona=body.persona,
            session_id=None,
            channel=body.channel,
            user_id=user_id_value,
            pattern_matched=pattern_value,
            input_text=body.text,
            action_taken="blocked",
        )
        # Mark the row alert_sent=TRUE only after Telegram confirmed delivery
        await mark_alert_sent(event_id)
    except Exception as e:
        log.error("Unauthorized alert send failed: %s", e)

    # Update rate counters and fire escalation alerts on threshold crossing
    global_hit, per_ip_hit = _record_unauthorized(client_ip)

    if global_hit:
        log.warning(
            "Unauthorized GLOBAL threshold crossed: >= %d events in %ds",
            _UNAUTH_GLOBAL_THRESHOLD, _UNAUTH_WINDOW_SECONDS,
        )
        try:
            await send_security_alert(
                event_type="unauthorized_user",
                severity="critical",
                persona="(system)",
                session_id=None,
                channel="(global)",
                user_id="(threshold)",
                pattern_matched=(
                    f">={_UNAUTH_GLOBAL_THRESHOLD}_unauth_in_"
                    f"{_UNAUTH_WINDOW_SECONDS}s"
                ),
                input_text=None,
                action_taken="threshold_global",
            )
        except Exception as e:
            log.error("Global threshold alert failed: %s", e)

    if per_ip_hit:
        log.warning(
            "Unauthorized PER-IP threshold crossed: ip=%s >= %d events in %ds",
            client_ip, _UNAUTH_PER_IP_THRESHOLD, _UNAUTH_WINDOW_SECONDS,
        )
        try:
            await send_security_alert(
                event_type="unauthorized_user",
                severity="critical",
                persona="(system)",
                session_id=None,
                channel="(per_ip)",
                user_id=client_ip,
                pattern_matched=(
                    f">={_UNAUTH_PER_IP_THRESHOLD}_unauth_from_{client_ip}_in_"
                    f"{_UNAUTH_WINDOW_SECONDS}s"
                ),
                input_text=None,
                action_taken="threshold_per_ip",
            )
        except Exception as e:
            log.error("Per-IP threshold alert failed: %s", e)

    return JSONResponse(
        status_code=403,
        content={"error": "unauthorized", "detail": "Identity verification failed"},
    )


# ---------------------------------------------------------------------------
# Core agent endpoint — channel-agnostic
# ---------------------------------------------------------------------------

@app.post("/agent")
async def agent_endpoint(body: AgentInput, request: Request):
    """
    Core agent pipeline. All channels route through here.

    Flow:
      1. Verify identity (operator user_id OR internal token)
      2. Resolve persona
      3. Resolve channel
      4. Load or create session
      5. Interceptor pre-call checks
      6. LLM execution
      7. Post-call budget update
      8. Write audit record
      9. Return response as JSON
    """
    # 1. Identity verification (Session 19 — closes ADR-038 §6 gap)
    unauth_response = await _verify_identity(body, request)
    if unauth_response is not None:
        return unauth_response

    # 2. Resolve persona
    try:
        persona = Persona(body.persona.lower())
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_persona",
                     "detail": f"Unknown persona: {body.persona}"},
        )

    # 3. Resolve channel
    try:
        channel = Channel(body.channel.lower())
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_channel",
                     "detail": f"Unknown channel: {body.channel}"},
        )

    # 4. Load or create session
    session = await load_or_create_session(
        channel=channel.value,
        channel_id=body.channel_id,
        persona=persona,
        initiated_by=body.initiated_by,
    )
    session_id = session["session_id"]
    _active_sessions.add(session_id)

    # 5. Build internal request object
    req = AgentRequest(
        session_id=session_id,
        persona=persona,
        trust_tier=session["trust_tier"],
        channel=channel,
        channel_id=body.channel_id,
        raw_text=body.text,
        initiated_by=body.initiated_by,
    )

    # 6. Interceptor pre-call checks
    gate = await intercept(req)

    if not gate["proceed"]:
        # Blocked by interceptor — record the block and respond
        req.error = gate["reason"]
        req.routing = None
        req.llm_model_used = "blocked"
        record = AgentActionRecord.from_request(req)
        record.action_type = "system_event"
        record.error_message = gate["reason"]
        await write_action(record)

        return JSONResponse(content={
            "response": f"Request blocked: {gate['reason']}",
            "session_id": str(session_id),
            "blocked": True,
        })

    # 7. LLM execution
    req = await execute(req)

    # 8. Post-call budget update (ADR-035 §4.5)
    budget = await post_call_budget_update(
        session_id=session_id,
        input_tokens=req.input_tokens,
        output_tokens=req.output_tokens,
        cost_usd=req.cost_usd,
    )

    # 9. Write audit record (ALWAYS — ADR-029)
    record = AgentActionRecord.from_request(req)
    await write_action(record)

    # 10. Return response
    response_text = req.response_text or req.error or "No response generated."

    return JSONResponse(content={
        "response": response_text,
        "session_id": str(session_id),
        "persona": persona.value,
        "model": req.llm_model_used,
        "input_tokens": req.input_tokens,
        "output_tokens": req.output_tokens,
        "cost_usd": req.cost_usd,
        "blocked": False,
    })


# ---------------------------------------------------------------------------
# Telegram webhook adapter (converts Telegram payload → /agent format)
# ---------------------------------------------------------------------------

@app.post("/webhook/{bot_token}")
async def telegram_webhook(bot_token: str, request: Request):
    """
    Telegram webhook receiver.
    Thin adapter: extracts message data, calls the core agent pipeline,
    and sends the response back to Telegram.
    """
    body = await request.json()

    # Extract message data from Telegram update
    message = body.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id", 0)
    user_id = message.get("from", {}).get("id", 0)

    if not text or not chat_id:
        return JSONResponse({"ok": True})  # Ignore non-text updates

    # Resolve persona from bot token or command
    persona = resolve_persona(bot_token=bot_token, command_text=text)

    # Build the channel-agnostic payload and call the core pipeline directly
    # (internal function call, not HTTP — avoids network round-trip)
    input_body = AgentInput(
        persona=persona.value,
        text=text,
        channel="telegram",
        channel_id=str(chat_id),
        user_id=str(user_id),
        initiated_by="operator",
    )

    result = await agent_endpoint(input_body, request)

    # Extract response from JSONResponse
    import json
    result_data = json.loads(result.body.decode())
    response_text = result_data.get("response", "No response generated.")

    # Send response back to Telegram
    await _send_telegram(bot_token, chat_id, response_text)

    return JSONResponse({"ok": True})


# ---------------------------------------------------------------------------
# Telegram send helper
# ---------------------------------------------------------------------------

async def _send_telegram(bot_token: str, chat_id: int, text: str) -> None:
    """Send a message back to Telegram. Truncates to 4096 chars (Telegram limit)."""
    import httpx

    if len(text) > 4096:
        text = text[:4093] + "..."

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                log.error("Telegram send failed: %s", resp.text[:200])
    except Exception as e:
        log.error("Telegram send error: %s", e)
