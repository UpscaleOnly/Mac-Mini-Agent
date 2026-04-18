"""
llm.py — LLM execution router (ADR-003, ADR-021)

Routes requests to Ollama (local Tier 1/2) or OpenRouter (cloud Tier 3).
Tier 4 (Opus) is hard-blocked in Phase 1.

Returns response text and token counts for audit and budget tracking.
"""
import httpx
import logging
from app.config import get_settings
from app.models import AgentRequest, Routing

log = logging.getLogger(__name__)


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


async def call_openrouter(req: AgentRequest) -> dict:
    """
    Call OpenRouter for cloud Tier 3 inference.
    Phase 1: Sonnet only. Opus hard-blocked.
    """
    settings = get_settings()

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
        result = await call_ollama(req)
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
