#!/usr/bin/env python3
"""test_db_maintenance.py -- agent_actions partition maintenance (ADR-047 F10).

No database, model or network: plan() is pure and run_maintenance() is driven
by a fake connection. Run inside the container:
    docker exec openclaw_fastapi python test_db_maintenance.py
Exits non-zero if any check fails.

The behaviour being guarded: F7 (no partition after July 2026 took /agent
down for two months) and F10 (90-day retention never enforced).
"""
import asyncio
from datetime import datetime, timezone

from app import maintenance as mt

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def utc(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=timezone.utc)


def monthly(y1, m1, y2, m2):
    """(name, bound) pairs as pg_get_expr prints them, month y1-m1 .. y2-m2."""
    out = []
    y, m = y1, m1
    while (y, m) <= (y2, m2):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append((f"agent_actions_{y}_{m:02d}",
                    f"FOR VALUES FROM ('{y}-{m:02d}-01 00:00:00+00') "
                    f"TO ('{ny}-{nm:02d}-01 00:00:00+00')"))
        y, m = ny, nm
    return out


LIVE = monthly(2026, 4, 2027, 12) + [("agent_actions_default", "DEFAULT")]

# ── plan(): today's live state ──────────────────────────────────────────
create, drop, skipped = mt.plan(utc(2026, 9, 30, 11), LIVE)
check("live 2026-09-30: nothing to create (partitions run to Dec 2027)", create == [])
check("live 2026-09-30: drops April, May, June 2026",
      drop == ["agent_actions_2026_04", "agent_actions_2026_05", "agent_actions_2026_06"])
check("live 2026-09-30: July kept (its last day is inside 90 days)",
      "agent_actions_2026_07" not in drop)
check("DEFAULT partition never dropped or skipped-reported",
      "agent_actions_default" not in drop and not skipped)

# ── plan(): the 90-day boundary is inclusive of whole months only ────────
_, drop, _ = mt.plan(utc(2026, 9, 29, 0), LIVE)          # cutoff = 2026-07-01 00:00
check("boundary: June (ends exactly at cutoff) dropped", "agent_actions_2026_06" in drop)
_, drop, _ = mt.plan(utc(2026, 9, 28, 23), LIVE)         # cutoff just before Jul 1
check("boundary: June kept one hour earlier", "agent_actions_2026_06" not in drop)

# ── plan(): creation, including across a year end ───────────────────────
create, _, _ = mt.plan(utc(2027, 11, 15), LIVE)
check("2027-11-15: creates Jan and Feb 2028",
      [str(m) for m in create] == ["2028-01-01", "2028-02-01"])
create, _, _ = mt.plan(utc(2026, 9, 30), monthly(2026, 4, 2026, 9))
check("gap ahead: creates the current month + 3 that are missing",
      [str(m) for m in create] == ["2026-10-01", "2026-11-01", "2026-12-01"])
create, _, _ = mt.plan(utc(2026, 12, 31, 23), [])
check("empty table on Dec 31: Dec 2026 .. Mar 2027",
      [str(m) for m in create] == ["2026-12-01", "2027-01-01", "2027-02-01", "2027-03-01"])

# ── plan(): anything unexpected is left alone ───────────────────────────
odd = LIVE + [("agent_actions_archive", "FOR VALUES FROM ('2020-01-01 00:00:00+00') TO ('2020-02-01 00:00:00+00')"),
              ("agent_actions_2020_01", "garbage")]
_, drop, skipped = mt.plan(utc(2026, 9, 30), odd)
check("non-monthly name never dropped", "agent_actions_archive" not in drop)
check("unreadable bounds never dropped", "agent_actions_2020_01" not in drop)
check("both reported as skipped", len(skipped) == 2)

check("add_months across year end", str(mt.add_months(mt.date(2027, 11, 1), 3)) == "2028-02-01")


# ── run_maintenance() with a fake connection ────────────────────────────
class FakeTx:
    def __init__(self, conn): self.conn = conn
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False


class FakeConn:
    def __init__(self, partitions, rows_in=None, stranded=0, fail_on=None):
        self.partitions = partitions
        self.rows_in = rows_in or {}
        self.stranded = stranded
        self.fail_on = fail_on
        self.executed = []

    def transaction(self): return FakeTx(self)

    async def fetch(self, sql, *args):
        return [{"name": n, "bound": b} for n, b in self.partitions]

    async def fetchval(self, sql, *args):
        if "agent_actions_default" in sql:
            return self.stranded
        name = sql.split('"')[1]
        return self.rows_in.get(name, 0)

    async def execute(self, sql, *args):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("canceling statement due to lock timeout")
        self.executed.append(sql)


def run(conn, now):
    return asyncio.run(mt.run_maintenance(conn, now=now))


conn = FakeConn(LIVE, rows_in={"agent_actions_2026_04": 22, "agent_actions_2026_05": 4})
s = run(conn, utc(2026, 9, 30, 11))
check("run: drops three, counts 26 rows", s["rows_dropped"] == 26 and len(s["dropped"]) == 3)
check("run: every statement set lock_timeout first",
      sum("lock_timeout" in q for q in conn.executed) == 3)
check("run: no errors", s["errors"] == [])
check("describe(): one line with counts",
      mt.describe(s) == "created=none dropped=agent_actions_2026_04(22),agent_actions_2026_05(4),"
                        "agent_actions_2026_06(0) rows_dropped=26")

conn = FakeConn(monthly(2026, 9, 2026, 11), stranded=5)
s = run(conn, utc(2026, 9, 30))
check("run: DEFAULT holds rows -> create skipped, error recorded",
      s["created"] == [] and len(s["errors"]) == 1 and "must be moved" in s["errors"][0])
check("run: no CREATE issued when rows are stranded",
      not any("CREATE TABLE" in q for q in conn.executed))

conn = FakeConn(monthly(2026, 9, 2026, 11))
s = run(conn, utc(2026, 9, 30))
check("run: creates the missing month", s["created"] == ["agent_actions_2026_12"])
check("run: CREATE uses explicit UTC bounds",
      any("FROM ('2026-12-01T00:00:00+00:00') TO ('2027-01-01T00:00:00+00:00')" in q
          for q in conn.executed))

conn = FakeConn(LIVE, fail_on='DROP TABLE "agent_actions_2026_05"')
s = run(conn, utc(2026, 9, 30, 11))
check("run: one lock timeout does not stop the others",
      len(s["dropped"]) == 2 and len(s["errors"]) == 1 and "lock timeout" in s["errors"][0])

print()
if FAILS:
    raise SystemExit(f"{len(FAILS)} FAILED")
print("all db-maintenance tests passed")
