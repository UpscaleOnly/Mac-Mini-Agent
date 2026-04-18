"""
scheduling/scheduler.py — APScheduler singleton for OpenClaw

Owns the AsyncIOScheduler instance and exposes start/shutdown helpers
called from main.py lifespan. Job definitions live in jobs.py.

Design notes:
  - Heartbeat loop stays in main.py (continuous asyncio task — not a job).
  - This module owns all discrete timed jobs (cron, interval, one-shot).
  - Add new jobs here by importing from jobs.py and calling scheduler.add_job().
  - timezone is always America/New_York; never use UTC for operator-facing schedules.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import pytz

log = logging.getLogger(__name__)

# Module-level singleton — imported by main.py lifespan
scheduler = AsyncIOScheduler(timezone=pytz.timezone("America/New_York"))


def register_jobs() -> None:
    """
    Register all scheduled jobs.
    Called once during lifespan startup, before scheduler.start().
    Import job functions here to keep job definitions co-located in jobs.py.
    """
    from app.scheduling.jobs import keep_warm_job, weekly_digest_job

    # Keep-warm: ping /health every 5 minutes to prevent cold-start penalty
    scheduler.add_job(
        keep_warm_job,
        trigger=IntervalTrigger(minutes=5),
        id="keep_warm",
        name="Keep-Warm Health Ping",
        replace_existing=True,
        misfire_grace_time=30,
    )
    log.info("Scheduled job registered: keep_warm (every 5 minutes)")

    # Weekly digest: Sunday 07:00 EST — ADR-031
    scheduler.add_job(
        weekly_digest_job,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=7,
            minute=0,
            timezone=pytz.timezone("America/New_York"),
        ),
        id="weekly_digest",
        name="Weekly Digest (ADR-031)",
        replace_existing=True,
        misfire_grace_time=300,  # 5-minute grace — digest can fire late
    )
    log.info("Scheduled job registered: weekly_digest (Sunday 07:00 EST)")


def start_scheduler() -> None:
    """Register jobs and start the scheduler. Called from lifespan startup."""
    register_jobs()
    scheduler.start()
    log.info("APScheduler started. Active jobs: %d", len(scheduler.get_jobs()))


def shutdown_scheduler() -> None:
    """Graceful shutdown. Called from lifespan teardown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("APScheduler shutdown complete.")
