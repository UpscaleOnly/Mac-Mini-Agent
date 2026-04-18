"""
main.py — OpenClaw FastAPI entry point

Request flow (ADR-027):
  Any Channel (Telegram, CLI, web, internal)
    → POST /agent (channel-agnostic)
    → Session Loader / Creator (ADR-035 trust tier)
    → Interceptor (ADR-027 + ADR-035 budget)
    → Persona Router
    → LLM Execution (Ollama / OpenRouter)
    → agent_actions write (ALWAYS, no exceptions)
    → JSON response returned to caller

Channel adapters:
  - Telegram bot (telegram_bot.py) — polls Telegram, POSTs to /agent, sends reply
  - /webhook/{bot_token} — receives Telegram webhooks, POSTs internally to pipeline
  - Future: CLI, web UI, internal scheduler

Startup sequence:
  1. Init PostgreSQL pool and bootstrap schema
  2. Detect crashed sessions (ADR-035 §7.4)
  3. Start heartbeat background task (asyncio — continuous)
  4. Start APScheduler (timed jobs: keep-warm, weekly digest ADR-031)
"""
import asyncio
import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from app.config import get_settings
from app.db import init_pool, close_pool
from app.session_loader import (
    load_or_create_session, detect_crashed_sessions, write_heartbeat,
)
from app.interceptor import intercept, post_call_budget_update
from app.persona_router import resolve_persona
from app.llm import execute
from app.audit import write_action
from app.models import AgentRequest, AgentActionRecord, Persona, Channel
from app.scheduling.scheduler import start_scheduler, shutdown_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

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
    version="0.4.0",
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
    return {"status": "ok", "version": "0.4.0"}


# ---------------------------------------------------------------------------
# Core agent endpoint — channel-agnostic
# ---------------------------------------------------------------------------

@app.post("/agent")
async def agent_endpoint(body: AgentInput):
    """
    Core agent pipeline. All channels route through here.

    Flow:
      1. Verify operator identity
      2. Resolve persona
      3. Load or create session
      4. Interceptor pre-call checks
      5. LLM execution
      6. Post-call budget update
      7. Write audit record
      8. Return response as JSON
    """
    settings = get_settings()

    # 1. Verify operator identity
    if body.user_id and body.user_id != str(settings.telegram_operator_id):
        log.warning("Rejected request from non-operator user %s", body.user_id)
        return JSONResponse(
            status_code=403,
            content={"error": "unauthorized", "detail": "Operator ID mismatch"},
        )

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
    settings = get_settings()
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

    result = await agent_endpoint(input_body)

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
