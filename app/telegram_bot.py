"""
OpenClaw Router Bot — Telegram channel adapter.

Thin adapter: receives Telegram messages, POSTs to the /agent endpoint,
and sends the response back to Telegram. All pipeline logic (session
management, interceptor, audit, LLM execution) lives in FastAPI.

Supports persona switching via /prototype, /automate, /research commands.
"""

import os
import asyncio
import logging
import httpx
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("openclaw.router")

# ── Config ──────────────────────────────────────────────────────────
OPERATOR_ID = int(os.environ.get("OPERATOR_TELEGRAM_ID", "0"))
ROUTER_TOKEN = os.environ.get("TELEGRAM_TOKEN_ROUTER", "")

# FastAPI agent endpoint — internal Docker network
AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8080/agent")

PERSONAS = ["prototype", "automate", "research"]

# Track which persona the operator is talking to
active_persona = {"current": "prototype"}


# ── Agent call ──────────────────────────────────────────────────────
async def call_agent(text: str, persona: str, chat_id: int, user_id: int) -> str:
    """
    POST to the FastAPI /agent endpoint and return the response text.
    All pipeline logic (session, interceptor, audit, LLM) runs in FastAPI.
    """
    payload = {
        "persona": persona,
        "text": text,
        "channel": "telegram",
        "channel_id": str(chat_id),
        "user_id": str(user_id),
        "initiated_by": "operator",
    }
    try:
        async with httpx.AsyncClient(timeout=360.0) as client:
            resp = await client.post(AGENT_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "No response from agent.")
    except httpx.TimeoutException:
        logger.error("Agent request timed out")
        return "Sorry, the agent took too long to respond. Try again."
    except Exception as e:
        logger.error(f"Agent call error: {e}")
        return f"Error reaching the agent: {e}"


# ── Command handlers ───────────────────────────────────────────────
async def start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user.id != OPERATOR_ID:
        return
    await update.message.reply_text(
        "OpenClaw Router online.\n\n"
        "Switch personas with:\n"
        "/prototype — SaaS prototyping\n"
        "/automate — automation tasks\n"
        "/research — research and reference\n"
        "/status — show current persona\n\n"
        f"Active persona: {active_persona['current']}"
    )


async def switch_persona(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user.id != OPERATOR_ID:
        return
    # Extract command and optional message: "/prototype Hello" -> persona=prototype, msg=Hello
    parts = update.message.text.strip().split(None, 1)
    persona = parts[0].strip("/").lower()
    trailing_text = parts[1] if len(parts) > 1 else None

    if persona not in PERSONAS:
        await update.message.reply_text(f"Unknown persona: {persona}")
        return

    active_persona["current"] = persona
    logger.info(f"Persona switched to: {persona}")

    if trailing_text:
        await update.message.reply_text(f"Switched to {persona}. Processing message...")
        await update.message.chat.send_action("typing")
        chat_id = update.message.chat.id
        user_id = update.effective_user.id
        reply = await call_agent(trailing_text, persona, chat_id, user_id)
        if len(reply) > 4000:
            for i in range(0, len(reply), 4000):
                await update.message.reply_text(reply[i : i + 4000])
        else:
            await update.message.reply_text(reply)
    else:
        await update.message.reply_text(f"Switched to {persona} persona.")


async def status_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user.id != OPERATOR_ID:
        return
    await update.message.reply_text(
        f"Active persona: {active_persona['current']}\n"
        f"Pipeline: FastAPI /agent"
    )


# ── Message handler ────────────────────────────────────────────────
async def handle_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_user.id != OPERATOR_ID:
        logger.warning(
            f"Rejected message from user {update.effective_user.id}"
        )
        return

    user_text = update.message.text
    persona = active_persona["current"]
    chat_id = update.message.chat.id
    user_id = update.effective_user.id
    logger.info(f"[{persona}] Received: {user_text[:80]}")

    await update.message.chat.send_action("typing")

    reply = await call_agent(user_text, persona, chat_id, user_id)

    if len(reply) > 4000:
        for i in range(0, len(reply), 4000):
            await update.message.reply_text(reply[i : i + 4000])
    else:
        await update.message.reply_text(reply)

    logger.info(f"[{persona}] Replied: {reply[:80]}")


# ── Main ────────────────────────────────────────────────────────────
async def run_router():
    """Start the single router bot in polling mode."""
    if not ROUTER_TOKEN:
        logger.error("TELEGRAM_TOKEN_ROUTER not set. Exiting.")
        return

    app = ApplicationBuilder().token(ROUTER_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    for persona in PERSONAS:
        app.add_handler(CommandHandler(persona, switch_persona))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info("Starting OpenClaw Router bot in polling mode...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Router bot running. Press Ctrl+C to stop.")

    try:
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down router bot...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(run_router())
