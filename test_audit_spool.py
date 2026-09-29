#!/usr/bin/env python3
"""
AU-5 audit spool tests for app/audit.py (Entry #046).

Run inside the container (needs the app's dependencies):
    docker exec openclaw_fastapi python test_audit_spool.py
No database is touched -- get_pool is replaced by fakes. The spool is a
temporary file. Exits non-zero on the first failure.

The behaviour being guarded: from Aug 1 to Sep 29, 2026 a failed audit
insert raised, and took every /agent request down with it (ADR-046 F7).
"""
import asyncio
import os
import tempfile
import uuid
from pathlib import Path

import app.audit as audit
from app.models import AgentActionRecord


def check(name, got, want):
    if got != want:
        raise SystemExit(f"FAIL {name}\n  got:  {got!r}\n  want: {want!r}")
    print(f"ok   {name}")


def rec():
    return AgentActionRecord(action_id=uuid.uuid4(), session_id=uuid.uuid4(), persona="prototype")


class FakeConn:
    def __init__(self, store, fail=False):
        self.store, self.fail = store, fail

    async def execute(self, sql, *args):
        if self.fail:
            raise RuntimeError('no partition of relation "agent_actions" found for row')
        assert "ON CONFLICT (action_id, created_at) DO NOTHING" in sql
        self.store.setdefault((args[0], args[22]), args)


class FakePool:
    def __init__(self, store, fail=False):
        self.conn = FakeConn(store, fail)

    def acquire(self):
        pool = self

        class _Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


def use_pool(store, fail=False):
    async def get_pool():
        return FakePool(store, fail)
    audit.get_pool = get_pool


def spool_lines():
    p = audit.SPOOL_PATH
    return [l for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


async def main():
    audit.SPOOL_PATH = Path(tempfile.mkdtemp()) / "audit_spool.jsonl"
    store = {}

    # ---- failure: never raises, spools ----
    use_pool(store, fail=True)
    r1, r2 = rec(), rec()
    await audit.write_action(r1)          # would have raised before AU-5
    await audit.write_action(r2)
    check("failed writes do not raise", True, True)
    check("failed writes are spooled", len(spool_lines()), 2)
    check("nothing reached the database", len(store), 0)

    # ---- pool itself unavailable: still no raise ----
    async def broken_pool():
        raise ConnectionRefusedError("postgres down")
    audit.get_pool = broken_pool
    await audit.write_action(rec())
    check("connection failure spooled too", len(spool_lines()), 3)

    # ---- recovery: next success replays automatically ----
    use_pool(store, fail=False)
    r4 = rec()
    await audit.write_action(r4)
    check("replay: all four records now in the database", len(store), 4)
    check("replay: spool emptied", spool_lines(), [])
    check("replayed record keeps its original action_id",
          (r1.action_id in {k[0] for k in store}), True)

    # ---- duplicates are impossible ----
    audit.SPOOL_PATH.write_text(r1.model_dump_json() + "\n")
    await audit.write_action(rec())
    check("re-spooled duplicate does not double-write", len(store), 5)

    # ---- spool unwritable: logged CRITICAL, still no raise ----
    audit.SPOOL_PATH = Path("/proc/nonexistent/audit_spool.jsonl")
    use_pool(store, fail=True)
    await audit.write_action(rec())
    check("spool failure does not raise", True, True)


asyncio.run(main())
print("\nall audit-spool tests passed")
