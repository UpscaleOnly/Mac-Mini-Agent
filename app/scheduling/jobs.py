"""
scheduling/jobs.py — Scheduled job definitions for OpenClaw

Each function is a self-contained job. Jobs are registered in scheduler.py.

Jobs defined here:
  keep_warm_job              — HTTP GET /health every 5 minutes (cold-start prevention)
  weekly_digest_job          — Sunday 07:00 EST digest via full agent pipeline (ADR-031)
  scrape_dispatcher_job      — Per-project scraper fan-out (ADR-039 H4)

Design rules:
  - Jobs must be async.
  - Jobs must not raise unhandled exceptions (catch and log everything).
  - Jobs that go through the agent pipeline use initiated_by="automate_scheduler".
  - Jobs must not carry state between runs — fetch what they need each execution.

Scraper dispatch (ADR-039 H4):
  scrape_dispatcher_job(project) is the single entry point for all scraping.
  It filters SCRAPERS by project, runs each one in a worker thread via
  asyncio.to_thread(), and bounds concurrency with a semaphore.
  See app/scheduling/scrapers/__init__.py for the registry.
"""
import asyncio
import logging
import httpx

log = logging.getLogger(__name__)

# Internal base URL — container-local, no external network hop
_BASE_URL = "http://localhost:8080"

# Scraper dispatcher concurrency cap.
# Each project's scrapers run with at most this many in parallel.
# Mac Air M1 + sync psycopg2 + sync httpx — 3 is comfortable. Dial up after Mac Studio.
DISPATCH_CONCURRENCY = 3


# ---------------------------------------------------------------------------
# Keep-warm job
# ---------------------------------------------------------------------------

async def keep_warm_job() -> None:
    """
    Ping GET /health every 5 minutes to prevent ASGI cold-start penalty.

    Uses a real HTTP request (not a direct function call) so the full
    ASGI worker stack is exercised — connection pool, middleware, routing.
    Logs a warning if the ping fails; never raises.
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
        "user_id": "",          # System-initiated — no operator user_id check
        "initiated_by": "automate_scheduler",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{_BASE_URL}/agent", json=payload)
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


# ---------------------------------------------------------------------------
# Scraper dispatcher (ADR-039 H4)
# ---------------------------------------------------------------------------

async def scrape_dispatcher_job(project: str) -> None:
    """
    Per-project scraper fan-out. Runs all scrapers tagged with `project`
    using a bounded asyncio.gather() — concurrency capped by DISPATCH_CONCURRENCY.

    Each scraper's run() is sync (BaseScraper uses psycopg2 + sync httpx),
    so each is wrapped in asyncio.to_thread() and the semaphore bounds
    how many threads are active at once.

    Scrapers run independently — one failure does not affect the others.
    The dispatcher itself never raises; per-scraper outcomes are logged.

    Called from scheduler.py via functools.partial(project=...).
    """
    # Late import — avoids circular import at module load and lets the
    # registry be modified without restarting just to update jobs.py.
    from app.scheduling.scrapers import scrapers_for_project

    scraper_classes = scrapers_for_project(project)
    if not scraper_classes:
        log.warning(
            "scrape_dispatcher_job: no scrapers registered for project=%s — skipping",
            project,
        )
        return

    log.info(
        "scrape_dispatcher_job: project=%s scrapers=%d concurrency=%d",
        project, len(scraper_classes), DISPATCH_CONCURRENCY,
    )

    semaphore = asyncio.Semaphore(DISPATCH_CONCURRENCY)

    async def _run_one(scraper_cls):
        async with semaphore:
            try:
                # Instantiate fresh each run — no state carry-over
                instance = scraper_cls()
                # BaseScraper.run() never raises — but we catch anyway as belt-and-suspenders
                summary = await asyncio.to_thread(instance.run)
                return scraper_cls.__name__, summary
            except Exception as e:
                log.error(
                    "scrape_dispatcher_job: %s crashed outside run() — %s: %s",
                    scraper_cls.__name__, type(e).__name__, e,
                )
                return scraper_cls.__name__, {"status": "crashed", "error": str(e)}

    results = await asyncio.gather(
        *(_run_one(cls) for cls in scraper_classes),
        return_exceptions=False,
    )

    # Summarize for the log line
    success_count = sum(1 for _, s in results if s.get("status") == "success")
    partial_count = sum(1 for _, s in results if s.get("status") == "partial")
    failed_count = sum(1 for _, s in results if s.get("status") in ("failed", "crashed"))
    total_inserted = sum(s.get("docs_inserted", 0) for _, s in results)

    log.info(
        "scrape_dispatcher_job: project=%s complete — "
        "success=%d partial=%d failed=%d total_inserted=%d",
        project, success_count, partial_count, failed_count, total_inserted,
    )
