"""test_inference_guards.py -- generator v9 inference guards (ADR-047 §4-§6, §8).

No database, Ollama or network needed -- it imports the generator's pure
functions and drives the memory gate with fake snapshots. Run on the host:
    python3 test_inference_guards.py
Run after any edit to the guard functions.
"""
import generate_brief_review as g

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


# ---- truncation guard ----
check("normal call is not truncated",
      g.truncation_reason("SNAP", {"prompt_eval_count": 3000, "eval_count": 500,
                                   "done_reason": "stop"}) is None)
check("prompt+output at the margin is truncated",
      g.truncation_reason("SNAP", {"prompt_eval_count": 7700, "eval_count": 236,
                                   "done_reason": "stop"}) is not None)
check("just under the margin is not truncated",
      g.truncation_reason("SNAP", {"prompt_eval_count": 7700, "eval_count": 235,
                                   "done_reason": "stop"}) is None)
check("done_reason 'length' is truncated even when small",
      g.truncation_reason("SNAP", {"prompt_eval_count": 100, "eval_count": 50,
                                   "done_reason": "length"}) is not None)
check("missing token counts do not crash or flag",
      g.truncation_reason("SNAP", {}) is None)
r = g.truncation_reason("CMS", {"prompt_eval_count": 8100, "eval_count": 90})
check("truncation warning names the section and starts TRUNCATION",
      r.startswith("TRUNCATION -- CMS:"))

# ---- parsers (strings as measured on the host, Sep 29) ----
check("free % parsed",
      g.parse_free_pct("System-wide memory free percentage: 59%") == 59)
check("free % absent -> None", g.parse_free_pct("garbage") is None)
check("swap used parsed",
      g.parse_swap_used_mb("total = 4096.00M  used = 1558.12M  free = 946.94M  (encrypted)") == 1558.12)
check("swap absent -> None", g.parse_swap_used_mb("") is None)

# ---- pre-flight gate ----
ok = {"level": 1, "free_pct": 59, "swap_mb": 1500.0}
check("gate passes at level 1, 59% free", g.gate_ok(ok))
check("gate fails at 39% free", not g.gate_ok({**ok, "free_pct": 39}))
check("gate fails at pressure level 2", not g.gate_ok({**ok, "level": 2}))
check("gate fails when unreadable", not g.gate_ok({"level": None, "free_pct": None, "swap_mb": None}))

seq = iter([{**ok, "free_pct": 20}, {**ok, "free_pct": 45}])
slept = []
snap = g.preflight_gate(snapshot=lambda: next(seq), sleep=slept.append, wait=120, poll=60)
check("gate waits once, then passes", snap["free_pct"] == 45 and slept == [60])

try:
    g.preflight_gate(snapshot=lambda: {**ok, "level": 4}, sleep=lambda s: None,
                     wait=120, poll=60)
    check("gate exits 3 when never met", False)
except SystemExit as e:
    check("gate exits 3 when never met", e.code == 3)

# ---- memory state (ADR-047 §8) ----
check("GREEN when nothing changed",
      g.memory_state(ok, ok)[0] == "GREEN")
check("YELLOW when swap grows > 1 GB",
      g.memory_state(ok, {**ok, "swap_mb": 2600.0})[0] == "YELLOW")
check("YELLOW when free < 25%",
      g.memory_state(ok, {**ok, "free_pct": 20})[0] == "YELLOW")
check("YELLOW at pressure level 2 (warn) -- the Sep 29 live-run case",
      g.memory_state(ok, {**ok, "level": 2, "free_pct": 35, "swap_mb": 2408.0})[0] == "YELLOW")
check("RED at critical pressure",
      g.memory_state(ok, {**ok, "level": 4})[0] == "RED")
check("unreadable snapshot does not crash",
      g.memory_state({"level": None, "free_pct": None, "swap_mb": None},
                     {"level": None, "free_pct": None, "swap_mb": None})[0] == "GREEN")

# ---- the two lock holders must agree on the key ----
llm_src = open("app/llm.py", encoding="utf-8").read()
check("generator and app/llm.py share lock key 470047",
      g.INFERENCE_LOCK_KEY == 470047 and "INFERENCE_LOCK_KEY = 470047" in llm_src)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    raise SystemExit(1)
print("all inference-guard tests passed")
