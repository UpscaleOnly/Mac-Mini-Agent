"""test_agent_lock.py -- /agent inference lock (ADR-047 §6).

Fake pool and fake Ollama call; no database, model or network. Run inside
the container:
    docker exec openclaw_fastapi python test_agent_lock.py
"""
import asyncio
from app import llm

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


class FakeConn:
    def __init__(self, free_after):
        self.tries, self.free_after, self.unlocked = 0, free_after, False

    async def fetchval(self, sql, key):
        assert "pg_try_advisory_lock" in sql and key == 470047
        self.tries += 1
        return self.tries > self.free_after

    async def execute(self, sql, key):
        assert "pg_advisory_unlock" in sql
        self.unlocked = True


class FakePool:
    def __init__(self, conn):
        self.conn, self.released = conn, False

    async def acquire(self):
        return self.conn

    async def release(self, conn):
        self.released = True


calls = []


async def fake_ollama(req):
    calls.append(req)
    return {"response_text": "hi", "input_tokens": 1, "output_tokens": 1,
            "model_used": "m", "error": None}


def run(conn=None, pool_error=False):
    calls.clear()
    pool = FakePool(conn)

    async def get_pool():
        if pool_error:
            raise RuntimeError("pool down")
        return pool

    llm.get_pool, llm.call_ollama = get_pool, fake_ollama
    return asyncio.run(llm.call_ollama_locked("REQ")), pool


llm.LOCK_POLL_SECONDS = 0
c = FakeConn(free_after=0)
res, pool = run(c)
check("free lock: Ollama called once", res["error"] is None and len(calls) == 1)
check("free lock: unlocked and connection released", c.unlocked and pool.released)

c = FakeConn(free_after=2)
res, pool = run(c)
check("busy then free: waits, then calls", res["error"] is None and c.tries == 3)

llm.LOCK_WAIT_SECONDS = 0
c = FakeConn(free_after=10**6)
res, pool = run(c)
check("never free: busy error, Ollama NOT called",
      "busy" in (res["error"] or "") and calls == [])
check("never free: connection still released", pool.released and not c.unlocked)

res, pool = run(pool_error=True)
check("database down: proceeds unlocked (AU-5 posture)",
      res["error"] is None and len(calls) == 1)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    raise SystemExit(1)
print("all agent-lock tests passed")
