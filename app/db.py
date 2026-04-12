"""
db.py — PostgreSQL connection pool (asyncpg)

Provides:
  - init_pool()  : creates the connection pool on startup
  - get_pool()   : returns the shared pool
  - close_pool() : called on shutdown
  - bootstrap()  : runs schema.sql if tables don't exist

Schema follows ADR-035 Option B:
  sessions, session_budget, tool_registry, session_state, agent_actions (partitioned)

Deferred to Phase 1.5: workflow_runs, workflow_steps
"""
import asyncpg
import logging
import os
from app.config import get_settings

log = logging.getLogger(__name__)
_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call init_pool() on startup.")
    return _pool


async def init_pool() -> None:
    global _pool
    settings = get_settings()
    log.info("Connecting to PostgreSQL at %s:%s/%s",
             settings.postgres_host, settings.postgres_port, settings.postgres_db)
    _pool = await asyncpg.create_pool(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        min_size=2,
        max_size=10,
    )
    log.info("PostgreSQL pool ready.")
    await bootstrap()


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        log.info("PostgreSQL pool closed.")


async def bootstrap() -> None:
    """
    Runs schema.sql against the database.
    Uses IF NOT EXISTS throughout — safe to run on every startup.
    """
    schema_path = os.path.join(os.path.dirname(__file__), "..", "schema.sql")
    schema_path = os.path.abspath(schema_path)

    if not os.path.exists(schema_path):
        log.error("schema.sql not found at %s — cannot bootstrap.", schema_path)
        raise FileNotFoundError(f"schema.sql not found at {schema_path}")

    with open(schema_path, "r") as f:
        schema_sql = f.read()

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)

    log.info("Database schema verified / created from schema.sql.")
