"""
scheduling/jobs.py — Scheduled job definitions for OpenClaw

Each function is a self-contained job. Jobs are registered in scheduler module.

Jobs defined here:
  keep_warm_job     — HTTP GET /health every 5 minutes (cold-start prevention)
  weekly_digest_job — Sunday 07:00 EST digest via full agent pipeline (ADR-031)

Design rules:
  - Jobs must be async.
  - Jobs must not raise unhandled exceptions (catch and log everything).
  - Jobs that go through the agent pipeline use initiated_by="automate_scheduler"
    AND send the X-Internal-Auth header so they pass identity verification
    (Session 19 — body.user_id is no longer trusted as a bypass signal).
  - Jobs must not carry state between runs — fetch what they need each execution.
"""
import logging
import os
import httpx

log = logging.getLogger(__name__)

# Internal base URL — container-local, no external network hop
_BASE_URL = "http://localhost:8080"

# Internal API token — must match INTERNAL_API_TOKEN read by main module.
# Read at call time (not module load) so .env updates take effect on next run.


def _internal_headers() -> dict:
    """Build headers with internal auth token for system-initiated requests."""
    token = os.environ.get("INTERNAL_API_TOKEN", "").strip()
    if not token:
        log.warning(
            "INTERNAL_API_TOKEN not set — system jobs will be rejected with 403."
        )
        return {}
    return {"X-Internal-Auth": token}


# ---------------------------------------------------------------------------
# Keep-warm job
# ---------------------------------------------------------------------------

async def keep_warm_job() -> None:
    """
    Ping GET /health every 5 minutes to prevent ASGI cold-start penalty.

    Uses a real HTTP request (not a direct function call) so the full
    ASGI worker stack is exercised — connection pool, middleware, routing.
    Logs a warning if the ping fails; never raises.

    /health does not require authentication — no internal token needed.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{_BASE_URL}/health")
            if resp.status_code == 200:
                log.debug("Keep-warm ping OK — %s", resp.json())
            else:
                log.warning(
                    "Keep-warm ping returned unexpected status %d", resp.status_code
                )
    except Exception as e:
        log.warning("Keep-warm ping failed: %s", e)


# ---------------------------------------------------------------------------
# Weekly digest job (ADR-031)
# ---------------------------------------------------------------------------

async def weekly_digest_job() -> None:
    """
    Sunday 07:00 EST — automated weekly digest via full agent pipeline.

    Routes through POST /agent with initiated_by='automate_scheduler' so
    the call is logged to agent_actions and subject to normal interceptor
    budget checks (ADR-035). The automate persona handles digest generation.

    Identity: passes X-Internal-Auth header. body.user_id is unset and is
    NOT consulted on the system-token path (Session 19 ADR-038 §6 closure).

    Settings loaded fresh each run — no stale config risk.
    Errors are caught and logged; digest failure never crashes the scheduler.
    """
    from app.config import get_settings

    settings = get_settings()

    # Operator chat ID is the delivery target
    channel_id = str(settings.telegram_operator_id)
    if not channel_id:
        log.error("weekly_digest_job: telegram_operator_id not configured — skipping.")
        return

    headers = _internal_headers()
    if not headers:
        log.error(
            "weekly_digest_job: INTERNAL_API_TOKEN not configured — skipping. "
            "The digest cannot run without internal auth."
        )
        return

    payload = {
        "persona": "automate",
        "text": (
            "Generate the weekly OpenClaw digest. "
            "Summarize system activity, session counts, budget consumption, "
            "and any anomalies from the past 7 days. "
            "Keep it concise — operator review format."
        ),
        "channel": "telegram",
        "channel_id": channel_id,
        "user_id": "",          # Not consulted on internal-token path
        "initiated_by": "automate_scheduler",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{_BASE_URL}/agent",
                json=payload,
                headers=headers,
            )
            if resp.status_code == 200:
                log.info(
                    "weekly_digest_job: digest dispatched successfully — session %s",
                    resp.json().get("session_id", "unknown"),
                )
            else:
                log.error(
                    "weekly_digest_job: /agent returned %d — %s",
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception as e:
        log.error("weekly_digest_job: unhandled exception — %s", e)
