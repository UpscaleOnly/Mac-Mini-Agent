"""
db.py — PostgreSQL connection pool and bootstrap

Bootstrap strategy (revised Session 12):

  On every startup, exactly one of two paths runs:

  PATH A — Empty database (fresh install, local rebuild, Mac Studio setup day):
    - No OpenClaw tables exist in the database
    - Run schema.sql in full: creates all tables, indexes, partitions
    - schema_version is seeded to REQUIRED_SCHEMA_VERSION by schema.sql itself
    - Log: "Fresh database detected — schema.sql applied."

  PATH B — Existing database (normal container restart, crash recovery):
    - OpenClaw tables already exist
    - schema.sql is NOT run — migrations are the only thing that modifies
      an existing database
    - Read MAX(version) from schema_version
    - If version == REQUIRED_SCHEMA_VERSION: proceed normally
    - If version < REQUIRED_SCHEMA_VERSION: log CRITICAL with exact migration
      command to run, then raise RuntimeError (container exits — no silent limp)

  This eliminates the two-actor ambiguity:
    - schema.sql   → bootstrap artifact only (fresh installs)
    - migrations   → the ONLY thing that modifies an existing database
    - schema_version → single source of truth for live database state

  REQUIRED_SCHEMA_VERSION must be incremented here whenever a new
  migration file is added.
"""

import logging
import os
import pathlib

import asyncpg

from app.config import get_settings

log = logging.getLogger(__name__)

# ── Schema version gate ───────────────────────────────────────────────────────
# Increment this when you add a new migration file.
# Current migrations: 001 (initial), 002 (sessions align), 003 (security_events)
# schema.sql seeds versions 1–4; REQUIRED is 4.
REQUIRED_SCHEMA_VERSION: int = 4

# Path to schema.sql — used only for PATH A (fresh installs)
_SCHEMA_SQL_PATH = pathlib.Path(__file__).parent.parent / "schema.sql"

# Module-level pool — accessed via get_pool()
_pool: asyncpg.Pool | None = None


# ── Pool access ───────────────────────────────────────────────────────────────

async def get_pool() -> asyncpg.Pool:
    """Return the active connection pool. Raises if not yet initialised."""
    if _pool is None:
        raise RuntimeError(
            "Database pool is not initialised. "
            "Call init_pool() during application startup."
        )
    return _pool


# ── Startup ───────────────────────────────────────────────────────────────────

async def init_pool() -> None:
    """
    Create the asyncpg connection pool and run the bootstrap check.

    Called once from main.py lifespan startup. Safe to call only once —
    raises if the pool is already initialised.
    """
    global _pool

    if _pool is not None:
        raise RuntimeError("init_pool() called twice — pool already exists.")

    settings = get_settings()

    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}"
    )
    log.info(
        "Connecting to PostgreSQL at %s:%d/%s",
        settings.postgres_host, settings.postgres_port, settings.postgres_db,
    )

    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=30,
    )

    await _bootstrap()


async def _bootstrap() -> None:
    """
    Conditional bootstrap: PATH A (fresh) or PATH B (existing).

    Detection method: check for ANY user table in the public schema via
    pg_catalog.pg_tables. This is future-proof — it does not depend on a
    specific table name and correctly identifies a fresh database regardless
    of what schema.sql creates or renames in the future.
    """
    pool = await get_pool()

    async with pool.acquire() as conn:

        # ── Detect fresh vs existing ──────────────────────────────────────────
        # Any table present in public → existing database → PATH B.
        # No tables at all → fresh database → PATH A.
        table_exists = await conn.fetchval("""
            SELECT EXISTS (
                SELECT 1
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
            )
        """)

        if not table_exists:
            # ── PATH A: Fresh database ────────────────────────────────────────
            log.info(
                "Fresh database detected — no OpenClaw tables found. "
                "Running schema.sql to bootstrap."
            )
            await _apply_schema_sql(conn)
            log.info(
                "schema.sql applied successfully. "
                "Database is at schema version %d.",
                REQUIRED_SCHEMA_VERSION,
            )

        else:
            # ── PATH B: Existing database ─────────────────────────────────────
            log.info(
                "Existing database detected — schema.sql will NOT be run. "
                "Checking schema_version."
            )
            await _check_schema_version(conn)


async def _apply_schema_sql(conn: asyncpg.Connection) -> None:
    """
    Read schema.sql from disk and execute it against the database.
    Called only for PATH A (fresh installs).
    """
    if not _SCHEMA_SQL_PATH.exists():
        raise RuntimeError(
            f"schema.sql not found at {_SCHEMA_SQL_PATH}. "
            "Cannot bootstrap a fresh database."
        )

    schema_sql = _SCHEMA_SQL_PATH.read_text(encoding="utf-8")

    try:
        await conn.execute(schema_sql)
    except Exception as exc:
        raise RuntimeError(
            f"schema.sql execution failed during fresh bootstrap: {exc}"
        ) from exc


async def _check_schema_version(conn: asyncpg.Connection) -> None:
    """
    Read schema_version from the live database and compare against
    REQUIRED_SCHEMA_VERSION. Raises RuntimeError if the database is behind.
    Called only for PATH B (existing databases).
    """
    # schema_version table itself might be missing on very old installs
    version_table_exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT 1
            FROM pg_tables
            WHERE schemaname = 'public'
              AND tablename  = 'schema_version'
        )
    """)

    if not version_table_exists:
        raise RuntimeError(
            "SCHEMA VERSION CHECK FAILED: schema_version table does not exist. "
            "The database predates the version tracking system. "
            "Manual intervention required — check migration history and "
            "apply migrations in order before restarting."
        )

    live_version = await conn.fetchval(
        "SELECT MAX(version) FROM schema_version"
    )

    if live_version is None:
        raise RuntimeError(
            "SCHEMA VERSION CHECK FAILED: schema_version table exists but "
            "contains no rows. Database state is indeterminate. "
            "Manual intervention required."
        )

    if live_version < REQUIRED_SCHEMA_VERSION:
        raise RuntimeError(
            f"SCHEMA VERSION MISMATCH — startup aborted.\n"
            f"  Live database version : {live_version}\n"
            f"  Required version      : {REQUIRED_SCHEMA_VERSION}\n"
            f"  Gap                   : {REQUIRED_SCHEMA_VERSION - live_version} migration(s) behind\n"
            f"\n"
            f"  Apply the missing migration(s) and restart the container:\n"
            f"\n"
            f"  docker cp ~/openclaw/migration_00N.sql openclaw_postgres:/tmp/\n"
            f"  docker exec -i openclaw_postgres psql -U openclaw -d openclaw "
            f"-f /tmp/migration_00N.sql\n"
            f"\n"
            f"  Then restart: docker restart openclaw_fastapi\n"
            f"\n"
            f"  DO NOT modify schema.sql to fix this — use a migration file."
        )

    if live_version > REQUIRED_SCHEMA_VERSION:
        # Database is ahead of the code — warn but do not block.
        # This can happen if a migration was applied but REQUIRED_SCHEMA_VERSION
        # was not incremented in this file. Treat as a developer oversight.
        log.warning(
            "Schema version WARNING: live database (%d) is ahead of "
            "REQUIRED_SCHEMA_VERSION (%d) in db.py. "
            "Increment REQUIRED_SCHEMA_VERSION in db.py to suppress this warning.",
            live_version,
            REQUIRED_SCHEMA_VERSION,
        )
        return

    log.info(
        "Schema version OK — live database is at version %d (required %d).",
        live_version,
        REQUIRED_SCHEMA_VERSION,
    )


# ── Shutdown ──────────────────────────────────────────────────────────────────

async def close_pool() -> None:
    """Close the connection pool gracefully. Called from main.py lifespan shutdown."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        log.info("PostgreSQL connection pool closed.")
