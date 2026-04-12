# OpenClaw FastAPI Skeleton — Option B (ADR-035 Core)

## What's Included

Four tables and the full interceptor pipeline:

| Table | ADR-035 Section | Purpose |
|-------|----------------|---------|
| `sessions` | §6.4 | Session tracking with trust tier, tier reason, elevation flag |
| `session_budget` | §4.3 | Per-session token budget with ceiling enforcement |
| `tool_registry` | §5.3 | Metadata-first tool definitions — data-layer security boundary |
| `session_state` | §7.3 | Crash recovery with 30-second heartbeat |
| `agent_actions` | §4.4, §9 | Partitioned audit table with input/output token split |

## Files

| File | Purpose |
|------|---------|
| `schema.sql` | All table definitions, indexes, initial partitions |
| `app/config.py` | Settings from environment variables |
| `app/models.py` | Pydantic models and enums matching ADR-035 |
| `app/db.py` | PostgreSQL pool, bootstrap from schema.sql |
| `app/session_loader.py` | Session create/load, trust tier assignment, crash detection |
| `app/interceptor.py` | Circuit breaker, tool registry, token budget enforcement |
| `app/audit.py` | agent_actions write (unconditional) |
| `app/llm.py` | Ollama / OpenRouter execution routing |
| `app/persona_router.py` | Persona resolution from bot token or command |
| `app/main.py` | FastAPI app with webhook endpoint and heartbeat loop |

## Request Pipeline

```
Telegram Webhook
  → Session Loader / Creator (trust tier + budget + state)
  → Interceptor pre-call checks:
      1. Circuit breaker (10 calls / 60s)
      2. Tool registry load (cached per session)
      3. Token budget estimate vs ceiling
      4. Cost escalation threshold check
  → LLM Execution (Ollama local, OpenRouter cloud)
  → Post-call budget update (atomic)
  → agent_actions write (ALWAYS)
  → Response → Telegram
```

## session_id Format

UUID throughout, per ADR-035. All foreign keys reference `sessions.session_id`.

## Partitioning

`agent_actions` is partitioned by month on `created_at`. Three initial partitions
are created (April–June 2026). Monthly partition creation and 90-day retention
(DROP TABLE) are handled by a cron job under the dev account.

## Phase 1.5 — Deferred Tables

Two tables are deferred: `workflow_runs` and `workflow_steps` (ADR-035 §8).

### What they do

Track multi-step automated pipelines with step-level granularity:
per-workflow token budgets, step sequencing with dependencies, crash
resume at step level, step-completion Telegram notifications, and
workflow success rate metrics for the ADR-033 dashboard.

### When to add them

Add `workflow_runs` and `workflow_steps` when ANY of these conditions is met:

1. The first multi-step automated pipeline is ready for production
   (e.g., `federal_policy_brief` nightly ingest: scrape → dedupe → chunk →
   embed → generate PDF → send email — 7 dependent steps).

2. Any Automate persona job has more than 3 sequential dependent steps
   where a failure at step N requires knowing which prior steps completed.

3. You need crash-resume at step granularity — meaning a crashed job should
   skip already-completed steps and resume from the exact point of failure,
   not restart from the beginning.

4. You want per-workflow cost attribution — tracking total token spend
   across multiple sessions for a single logical job.

### What to do when ready

1. Schema definitions are in ADR-035 Sections 8.2 and 8.3.
2. Add the FK from `session_state.workflow_id` to `workflow_runs.workflow_id`.
3. Add workflow Telegram notifications (§8.4): start, step completion,
   workflow completion, workflow failure with resume instructions.
4. Add dashboard metrics from ADR-033 §10: workflow success rate,
   active workflow step progress.

Until then, `session_state.completed_steps` (JSONB array) tracks step
progress for simple sequences adequately.

## Not Yet Wired (Phase 1 implementation tasks)

These components exist in the code as stubs or TODOs:

- Telegram approval gating (ADR-028) — the `interceptor.py` detects when
  approval is needed but doesn't yet send the Y/N Telegram prompt
- Output validation pipeline (ADR-022) — `validation_verdict` column exists
  but no validation logic runs yet
- YAML network policy enforcement (ADR-030) — `permitted_network_destinations`
  is stored in tool_registry but not enforced at dispatch
- Tool registry population — `tool_registry` table is empty; rows must be
  INSERTed for each tool before it can be dispatched (ADR-035 §5.5)
