"""test_workload_config.py -- chat workload settings (ADR-047 §14).

No database, model or network. Run inside the container:
    docker exec openclaw_fastapi python test_workload_config.py
"""
from app import llm
from app.config import get_settings

FAILS = []


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


s = get_settings()
check("chat model is gemma4:e4b", s.ollama_default_model == "gemma4:e4b")
check("chat thinking is off by default", s.ollama_chat_think is False)
check("plain message: default kept, text unchanged",
      llm.split_think("What is due this week?", False) == (False, "What is due this week?"))
check("'think:' prefix turns thinking on and is removed",
      llm.split_think("think: compare these two rules", False) == (True, "compare these two rules"))
check("prefix is case-insensitive and tolerates leading space",
      llm.split_think("  THINK:why?", False) == (True, "why?"))
check("'think' mid-sentence is not a prefix",
      llm.split_think("I think: maybe", False) == (False, "I think: maybe"))
check("'/think' is not the prefix (Telegram drops slash-commands anyway)",
      llm.split_think("/think x", False)[0] is False)

print()
if FAILS:
    print(f"{len(FAILS)} FAILED")
    raise SystemExit(1)
print("all workload-config tests passed")
