"""
maintenance.py — nightly agent_actions partition maintenance (ADR-047 §5/§11 step 6, F10)

agent_actions is range-partitioned by month on created_at (ADR-035 §9) with
90-day retention (ADR-029). ADR-035 §9 assigned both jobs — creating next
months' partitions and dropping expired ones — to a "nightly maintenance job"
that was never built. F7 (no partition after July 2026, every /agent request
failing from Aug 1 to Sep 29) and F10 (April–May rows retained past 90 days)
were both that missing job.

Each run:
  1. Ensures a monthly partition exists for the current month and MONTHS_AHEAD
     months after it. Before creating one, checks agent_actions_default for
     rows in that month: PostgreSQL refuses the create if any exist, so the
     month is skipped and one ERROR is logged (the rows must be moved first).
  2. Drops every monthly partition whose whole month is older than
     RETENTION_DAYS. Retention is therefore at least 90 days and at most about
     121 (monthly granularity). The DEFAULT partition is never touched.
Bounds are read from the catalog, not inferred from table names. Every
statement runs under a short lock_timeout, so a clash with the 04:00 pg_dump
fails fast instead of queueing /agent writes behind it. Every step is
idempotent: a failed night is retried by the next one, no manual review.

plan() is pure (no database) so the decisions can be unit-tested;
run_maintenance() applies them. The job wrapper lives in scheduling/jobs.py.
"""
import logging
import re
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)

PARENT = "agent_actions"
DEFAULT_PARTITION = "agent_actions_default"
MONTHS_AHEAD = 3
RETENTION_DAYS = 90
LOCK_TIMEOUT = "5s"

_MONTHLY_NAME = re.compile(r"^agent_actions_(\d{4})_(\d{2})$")
_BOUNDS = re.compile(r"FROM \('([^']+)'\) TO \('([^']+)'\)")


def month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def partition_name(m: date) -> str:
    return f"{PARENT}_{m:%Y_%m}"


def _utc_midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def parse_bounds(expr: str):
    """'FOR VALUES FROM ('2026-04-01 00:00:00+00') TO (...)' -> (lower, upper), or None."""
    m = _BOUNDS.search(expr or "")
    if not m:
        return None
    try:
        lo, hi = (datetime.fromisoformat(s.replace(" ", "T")) for s in m.groups())
    except ValueError:
        return None
    if lo.tzinfo is None or hi.tzinfo is None:
        return None
    return lo, hi


def plan(now: datetime, partitions):
    """
    Decide what to create and drop.

    now        -- timezone-aware current time
    partitions -- iterable of (name, bound_expr) for every child of agent_actions

    Returns (to_create, to_drop, skipped):
      to_create -- month-start dates needing a partition, oldest first
      to_drop   -- partition names wholly older than RETENTION_DAYS, oldest first
      skipped   -- (name, reason) for children left alone
    """
    today = now.astimezone(timezone.utc).date()
    cutoff = now - timedelta(days=RETENTION_DAYS)

    monthly = {}          # lower bound (UTC date) -> (name, lower, upper)
    skipped = []
    for name, expr in partitions:
        if name == DEFAULT_PARTITION:
            continue
        if not _MONTHLY_NAME.match(name):
            skipped.append((name, "not a monthly partition name"))
            continue
        bounds = parse_bounds(expr)
        if bounds is None:
            skipped.append((name, f"unreadable bounds: {expr}"))
            continue
        lo, hi = bounds
        monthly[lo.astimezone(timezone.utc).date()] = (name, lo, hi)

    first = month_start(today)
    wanted = [add_months(first, i) for i in range(MONTHS_AHEAD + 1)]
    to_create = [m for m in wanted if m not in monthly]

    to_drop = [name for _, (name, lo, hi) in sorted(monthly.items()) if hi <= cutoff]
    return to_create, to_drop, skipped


async def run_maintenance(conn, now: datetime = None) -> dict:
    """
    Apply plan() on an asyncpg connection. Never raises for a single failed
    step: each create/drop is its own transaction, and failures are collected
    in summary['errors'] for the job to log and audit.
    """
    now = now or datetime.now(timezone.utc)
    summary = {"created": [], "dropped": [], "rows_dropped": 0,
               "skipped": [], "errors": []}

    rows = await conn.fetch(
        """
        SELECT c.relname AS name, pg_get_expr(c.relpartbound, c.oid) AS bound
        FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
        WHERE i.inhparent = $1::regclass
        """,
        PARENT,
    )
    to_create, to_drop, skipped = plan(now, [(r["name"], r["bound"]) for r in rows])
    summary["skipped"] = [f"{n} ({why})" for n, why in skipped]

    for m in to_create:
        name = partition_name(m)
        lo, hi = _utc_midnight(m), _utc_midnight(add_months(m, 1))
        try:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
                stranded = await conn.fetchval(
                    f"SELECT count(*) FROM {DEFAULT_PARTITION} "
                    "WHERE created_at >= $1 AND created_at < $2", lo, hi)
                if stranded:
                    summary["errors"].append(
                        f"{name} not created: {stranded} row(s) for that month are in "
                        f"{DEFAULT_PARTITION} and must be moved out first")
                    continue
                await conn.execute(
                    f'CREATE TABLE IF NOT EXISTS "{name}" PARTITION OF {PARENT} '
                    f"FOR VALUES FROM ('{lo.isoformat()}') TO ('{hi.isoformat()}')")
            summary["created"].append(name)
        except Exception as e:
            summary["errors"].append(f"{name} create failed: {type(e).__name__}: {e}")

    for name in to_drop:
        if not _MONTHLY_NAME.match(name):      # belt and braces: never drop anything else
            continue
        try:
            async with conn.transaction():
                await conn.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
                n = await conn.fetchval(f'SELECT count(*) FROM "{name}"')
                await conn.execute(f'DROP TABLE "{name}"')
            summary["dropped"].append(f"{name}({n})")
            summary["rows_dropped"] += n
        except Exception as e:
            summary["errors"].append(f"{name} drop failed: {type(e).__name__}: {e}")

    return summary


def describe(summary: dict) -> str:
    """One-line summary for the log and the audit record."""
    parts = [
        "created=" + (",".join(summary["created"]) or "none"),
        "dropped=" + (",".join(summary["dropped"]) or "none"),
        f"rows_dropped={summary['rows_dropped']}",
    ]
    if summary["skipped"]:
        parts.append("skipped=" + ";".join(summary["skipped"]))
    if summary["errors"]:
        parts.append(f"errors={len(summary['errors'])}")
    return " ".join(parts)
