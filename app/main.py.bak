"""
main.py — OpenClaw FastAPI entry point

Request flow (ADR-027):
  Telegram Webhook
    → Session Loader / Creator (ADR-035 trust tier)
    → Interceptor (ADR-027 + ADR-035 budget)
    → Persona Router
    → LLM Execution (Ollama / OpenRouter)
    → agent_actions write (ALWAYS, no exceptions)
    → Response → Telegram

Startup sequence:
  1. Init PostgreSQL pool and bootstrap schema
  2. Detect crashed sessions (ADR-035 §7.4)
  3. Start heartbeat background task
"""
import asyncio
import uuid
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_pool, close_pool
from app.session_loader import (
    load_or_create_session, detect_crashed_sessions, write_heartbeat,
)
from app.interceptor import intercept, post_call_budget_update
from app.persona_router import resolve_persona
from app.llm import execute
from app.audit import write_action
from app.models import AgentRequest, AgentActionRecord, Persona

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
        # TODO: Send Telegram alerts for crashed sessions
        log.warning("Total crashed sessions detected on startup: %d", len(crashed))
    else:
        log.info("No crashed sessions detected on startup.")

    # Start heartbeat background task
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    log.info("Heartbeat background task started.")

    yield

    # Shutdown
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
    version="0.2.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health check (ADR-037, hw_collector)
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.2.0"}


# ---------------------------------------------------------------------------
# Telegram webhook endpoint
# ---------------------------------------------------------------------------

@app.post("/webhook/{bot_token}")
async def telegram_webhook(bot_token: str, request: Request):
    """
    Telegram webhook receiver.
    Processes incoming messages through the full interceptor pipeline.
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

    # Verify operator identity
    if user_id != settings.telegram_operator_id:
        log.warning("Rejected message from non-operator user %d", user_id)
        return JSONResponse({"ok": True})

    # --- PIPELINE START ---

    # 1. Resolve persona
    persona = resolve_persona(bot_token=bot_token, command_text=text)

    # 2. Load or create session
    session = await load_or_create_session(
        chat_id=chat_id,
        operator_id=user_id,
        persona=persona,
        initiated_by="operator_telegram",
    )
    session_id = session["session_id"]
    _active_sessions.add(session_id)

    # 3. Build request object
    req = AgentRequest(
        session_id=session_id,
        persona=persona,
        trust_tier=session["trust_tier"],
        operator_telegram_id=user_id,
        chat_id=chat_id,
        raw_text=text,
    )

    # 4. Interceptor pre-call checks
    gate = await intercept(req)

    if not gate["proceed"]:
        # Blocked by interceptor — record the block and respond
        req.error = gate["reason"]
        req.routing = None
        req.model_used = "blocked"
        record = AgentActionRecord.from_request(req)
        record.action_type = "system_event"
        await write_action(record)

        await _send_telegram(
            bot_token,
            chat_id,
            f"Request blocked: {gate['reason']}",
        )
        return JSONResponse({"ok": True})

    # 5. LLM execution
    req = await execute(req)

    # 6. Post-call budget update (ADR-035 §4.5)
    budget = await post_call_budget_update(
        session_id=session_id,
        input_tokens=req.input_tokens,
        output_tokens=req.output_tokens,
        cost_usd=req.cost_usd,
    )

    # 7. Write audit record (ALWAYS — ADR-029)
    record = AgentActionRecord.from_request(req)
    await write_action(record)

    # 8. Send response to Telegram
    response_text = req.response_text or req.error or "No response generated."
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
