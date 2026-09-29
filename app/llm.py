"""
llm.py — LLM execution router (ADR-003, ADR-021)

Routes requests to Ollama (local) or the cloud tiers. Tier labels per
ADR-047 §8: Tier 1 local, reserved (unassigned); Tier 2 local, the single
deployed model; Tier 3 Claude API standard; Tier 4 Claude API top.
The cloud path (Tiers 3/4) is DISABLED by ADR-047 §7 until a concrete need
arises; when rebuilt it targets the Anthropic API directly, not OpenRouter.

Returns response text and token counts for audit and budget tracking.
"""
import asyncio
import httpx
import logging
import time
from app.config import get_settings
from app.db import get_pool
from app.models import AgentRequest, Routing

log = logging.getLogger(__name__)

# ADR-047 §6 -- one inference job at a time, host-wide. Same key as
# generate_brief_review.py, which runs on the host; PostgreSQL is the one
# place both can see.
INFERENCE_LOCK_KEY = 470047
LOCK_WAIT_SECONDS = 60
LOCK_POLL_SECONDS = 5


def determine_routing(req: AgentRequest) -> Routing:
    """
    Determine model routing based on persona and request characteristics.
    Phase 1: all requests route to local Tier 2 (default Ollama model).
    Cloud escalation path exists but is not triggered automatically yet.
    """
    # Phase 1: local inference for everything
    # Cloud escalation requires explicit operator approval (ADR-028)
    return Routing.LOCAL_TIER2


async def call_ollama(req: AgentRequest) -> dict:
    """
    Call local Ollama instance for inference.
    Returns dict with response_text, input_tokens, output_tokens, model_used.
    """
    settings = get_settings()
    url = f"http://{settings.ollama_host}:{settings.ollama_port}/api/generate"

    payload = {
        "model": settings.ollama_default_model,
        "prompt": req.raw_text,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return {
            "response_text": data.get("response", ""),
            "input_tokens": data.get("prompt_eval_count", 0),
            "output_tokens": data.get("eval_count", 0),
            "model_used": settings.ollama_default_model,
            "error": None,
        }

    except httpx.HTTPStatusError as e:
        log.error("Ollama HTTP error: %s", e)
        return {
            "response_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model_used": settings.ollama_default_model,
            "error": f"Ollama HTTP {e.response.status_code}: {e.response.text[:200]}",
        }
    except Exception as e:
        log.error("Ollama connection error: %s", e)
        return {
            "response_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model_used": settings.ollama_default_model,
            "error": f"Ollama error: {str(e)[:200]}",
        }


async def call_ollama_locked(req: AgentRequest) -> dict:
    """call_ollama() under the host-wide inference lock (ADR-047 §6).

    Waits up to LOCK_WAIT_SECONDS for another job (e.g. the brief generator)
    to finish, then returns a 'busy' error rather than loading a second
    model into shared memory. If the lock itself cannot be reached (database
    down), the call proceeds unlocked -- like AU-5, a failure of the
    bookkeeping must not fail the request -- and one warning is logged.
    """
    try:
        pool = await get_pool()
        conn = await pool.acquire()
    except Exception as e:
        log.warning("Inference lock unavailable (%s) -- calling Ollama unlocked", e)
        return await call_ollama(req)

    try:
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while not await conn.fetchval("SELECT pg_try_advisory_lock($1)", INFERENCE_LOCK_KEY):
            if time.monotonic() >= deadline:
                settings = get_settings()
                return {
                    "response_text": "",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "model_used": settings.ollama_default_model,
                    "error": "local model busy with another job (ADR-047 §6) -- try again shortly",
                }
            await asyncio.sleep(LOCK_POLL_SECONDS)
        try:
            return await call_ollama(req)
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", INFERENCE_LOCK_KEY)
    finally:
        await pool.release(conn)


async def call_openrouter(req: AgentRequest) -> dict:
    """
    Cloud Tier 3 inference -- DISABLED (ADR-047 §7).

    The OpenRouter implementation below never worked: it posted the auth
    headers as the request body (json=headers, finding F11, Entry #048), and
    its model setting is read from an env name .env does not set (F12). It is
    retained, unreachable, for reference until the path is rebuilt against the
    Anthropic API. This early return makes no network call.
    """
    settings = get_settings()
    return {
        "response_text": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "model_used": "cloud_disabled",
        "error": "cloud path disabled (ADR-047 §7)",
    }

    if not settings.openrouter_api_key:
        return {
            "response_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model_used": settings.openrouter_model,
            "error": "OpenRouter API key not configured",
        }

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": [{"role": "user", "content": req.raw_text}],
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=headers, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data.get("choices", [{}])[0]
        usage = data.get("usage", {})

        return {
            "response_text": choice.get("message", {}).get("content", ""),
            "input_tokens": usage.get("prompt_tokens", 0),
            "output_tokens": usage.get("completion_tokens", 0),
            "model_used": settings.openrouter_model,
            "error": None,
        }

    except Exception as e:
        log.error("OpenRouter error: %s", e)
        return {
            "response_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model_used": settings.openrouter_model,
            "error": f"OpenRouter error: {str(e)[:200]}",
        }


async def execute(req: AgentRequest) -> AgentRequest:
    """
    Main execution entry point.
    Determines routing, calls the appropriate backend, and populates
    the request object with response data for audit writing.
    """
    routing = determine_routing(req)
    req.routing = routing

    if routing in (Routing.LOCAL_TIER1, Routing.LOCAL_TIER2):
        result = await call_ollama_locked(req)
    elif routing == Routing.CLOUD_TIER3:
        result = await call_openrouter(req)
    elif routing == Routing.CLOUD_TIER4:
        # Hard block in Phase 1 (ADR-021)
        result = {
            "response_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model_used": "opus_blocked",
            "error": "Tier 4 (Opus) hard-blocked in Phase 1",
        }
    else:
        result = {
            "response_text": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "model_used": "unknown",
            "error": f"Unknown routing: {routing}",
        }

    # Populate request with results
    req.llm_model_used = result["model_used"]
    req.input_tokens = result["input_tokens"]
    req.output_tokens = result["output_tokens"]
    req.response_text = result["response_text"]
    req.error = result["error"]

    # Compute cost (local = $0, cloud = per-token pricing)
    if routing in (Routing.LOCAL_TIER1, Routing.LOCAL_TIER2):
        req.cost_usd = 0.0
    elif routing == Routing.CLOUD_TIER3:
        # Sonnet pricing: $3/M input, $15/M output (approximate)
        req.cost_usd = (req.input_tokens * 3.0 / 1_000_000 +
                        req.output_tokens * 15.0 / 1_000_000)

    return req
