# OpenClaw Change Management Log

ADR-031 — Change Management and Security Review Triggers

Formal log structure TBD in ADR-031 dedicated session. Entries below capture changes until then.

---

## Entry #001 — April 12–13, 2026

**Operator:** Sheldon Wheeler

**Category:** Infrastructure — Phase 1 database schema and tool registry deployment

### Changes Made

1. **Phase 1 database schema deployed** — schema.sql executed against openclaw_postgres. 10 tables + 1 view + 1 version tracker created. Tables: sessions, session_budget, tool_registry, session_state, agent_actions (partitioned with April–June 2026 monthly partitions), session_transcripts, agent_heartbeat, service_health, knowledge_updates, hardware_metrics. Views: hardware_alerts. Meta: schema_version.

2. **Python code aligned to schema** — Four files updated: models.py (Pydantic models match all table columns), audit.py (24-column INSERT matches agent_actions), session_loader.py (INSERT matches sessions table), main.py (startup crash detection, heartbeat task, health endpoint). Version bumped to 0.3.0.

3. **Docker build optimized** — .dockerignore created excluding ollama/, postgres/, chromadb/ volume data from build context. Build dropped from 21.5GB/415s to 81KB/12s. asyncpg added to requirements.txt.

4. **Tool registry populated** — 13 tools inserted via tool_registry_seed.sql (11 Phase 1 + 2 Phase 1.5), all enabled = FALSE. No new egress destinations activated. One tool (web_search_local) declares api.search.brave.com as a future permitted destination. One tool (shell_exec) has requires_approval = TRUE and risk_level = high.

### Files Changed

| File | Action |
|------|--------|
| ~/openclaw/schema.sql | Created (corrected, matches running database) |
| ~/openclaw/tool_registry_seed.sql | Created (13 tool INSERT statements) |
| ~/openclaw/.dockerignore | Created |
| ~/openclaw/requirements.txt | Modified (asyncpg added) |
| ~/openclaw/app/models.py | Modified (v0.3.0) |
| ~/openclaw/app/audit.py | Modified (24-column INSERT) |
| ~/openclaw/app/session_loader.py | Modified (matches sessions table) |
| ~/openclaw/app/main.py | Modified (v0.3.0) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-029 | agent_actions table created with partitioning and input/output token columns |
| ADR-034 | hardware_metrics table and hardware_alerts view created |
| ADR-035 | sessions, session_budget, tool_registry, session_state tables created. Tool registry populated (Step 9). Implementation Steps 1–9 complete. |
| ADR-037 | session_transcripts, agent_heartbeat, service_health, knowledge_updates tables created |

### NIST Controls Touched

AU-2, AU-3, AU-9, AC-3, AC-6, CM-7(1), IR-4, IR-8, SC-5, SI-4, SI-12

### Risk Assessment

No new egress destinations activated. No tools enabled. No agent behavior changed. All changes are infrastructure preparation — the system is not yet dispatching tool calls. Clean startup confirmed with FastAPI 0.3.0 returning 200 on health endpoint.

### ADR-035 Implementation Sequence Status After This Entry

| Step | Action | Status |
|------|--------|--------|
| 1–6 | Database tables created | DONE |
| 7 | Python code aligned to schema | DONE |
| 8 | Startup crash detection | DONE |
| 9 | Tool registry populated | DONE |
| 10 | ADR-031 change log entry | DONE (this entry) |

---

## Entry #002 — April 13, 2026

**Operator:** Sheldon Wheeler

**Category:** Infrastructure — Channel-agnostic pipeline refactor and Telegram UX improvement

**Commits:** `e4ee032`, `fe3bb69`

### Changes Made

1. **Channel-agnostic `/agent` endpoint** — The `/agent` POST endpoint now accepts `{persona, text, channel, channel_id, user_id}` as the single pipeline entry point. Telegram bot refactored into a thin adapter that translates Telegram messages into this generic format. This decouples the pipeline from Telegram so future channels (webhook, CLI, web UI) use the same path.

2. **`sessions` table updated** — Replaced `chat_id` (bigint, Telegram-specific) with `channel` (text, default 'telegram') and `channel_id` (text). Matches the channel-agnostic design.

3. **Option B persona switching** — `/prototype Hello` now switches persona and sends "Hello" as a message in one step. `/prototype` alone still just switches persona. Works for all three personas.

4. **Timeout increases** — Ollama timeout raised from 120s to 300s in `llm.py`. Telegram bot timeout raised from 180s to 360s in `telegram_bot.py`. Root cause: bot timeout was expiring before Ollama finished generating on the 16GB Air.

### Files Changed

| File | Action |
|------|--------|
| ~/openclaw/app/main.py | Modified (channel-agnostic /agent endpoint) |
| ~/openclaw/app/telegram_bot.py | Modified (thin adapter, Option B, 360s timeout) |
| ~/openclaw/app/llm.py | Modified (300s Ollama timeout) |
| ~/openclaw/app/session_loader.py | Modified (channel/channel_id fields) |
| ~/openclaw/app/models.py | Modified (channel-agnostic request model) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-035 | sessions table schema updated (channel_id column type change) |

### NIST Controls Touched

AU-2, AU-3, AC-3, CM-3

### Risk Assessment

No new egress destinations. No tools enabled. Pipeline behavior unchanged — same interceptor → Ollama → audit → budget path. The refactor changes how messages enter the pipeline, not what the pipeline does. Full end-to-end verification completed: Telegram → router bot → `/agent` → session → interceptor → Ollama → audit → budget → response.

---

## Entry #003 — April 18, 2026

**Operator:** Sheldon Wheeler

**Category:** Code Quality — Pydantic namespace fix, sessions table migration, schema single source of truth

**Commits:** (Session 12 work — no new commit yet)

### Changes Made

1. **Pydantic `model_` namespace warnings resolved** — Three field names collided with Pydantic v2's reserved `model_` namespace. Renamed across four Python files: `model_used` → `llm_model_used`, `model_name` → `llm_model_name`, `model_tier` → `llm_model_tier`. Database column names unchanged — `audit.py` INSERT maps the new Python attribute names back to the original SQL column names. FastAPI startup is now warning-free.

2. **Sessions table forward migration applied** — The running `sessions` table was missing four columns present in `schema.sql`: `status`, `started_at`, `ended_at`, `model_tier`. `migration_002.sql` written and applied via `docker cp` + `docker exec psql -f`. Two existing rows preserved; `started_at` backfilled from `created_at`; schema version bumped to 3.

3. **`schema.sql` updated to true single source of truth (v3)** — Reconciled all columns present in the running database with the canonical schema. CHECK constraints added. `schema_version` table seeded with all three migration records.

4. **End-to-end re-verified** — Clean FastAPI startup confirmed (no Pydantic warnings, no schema errors). Telegram round-trip confirmed with `/prototype hello`.

### Files Changed

| File | Action |
|------|--------|
| ~/openclaw/changelog.md | Updated (Entry #003 added) |
| ~/openclaw/schema.sql | Replaced (v3 — true single source of truth) |
| ~/openclaw/migration_002.sql | Created (forward migration for sessions table) |
| ~/openclaw/app/models.py | Replaced (llm_ prefix rename) |
| ~/openclaw/app/main.py | Replaced (llm_model_used references updated) |
| ~/openclaw/app/llm.py | Replaced (llm_model_used reference updated) |
| ~/openclaw/app/audit.py | Replaced (llm_model_tier, llm_model_name references updated) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-035 | sessions table now fully aligned to canonical schema. |
| ADR-029 | audit.py INSERT mapping verified correct after field rename. |

### NIST Controls Touched

AU-2, AU-3, CM-3

### Risk Assessment

No new egress destinations. No tools enabled. No agent behavior changed. Changes are cosmetic (Pydantic warning elimination) and corrective (schema alignment). Running database now matches `schema.sql` exactly.

### Docker Operational Note

`docker exec -f /dev/stdin` piping is unreliable for SQL files. Confirmed working method: `docker cp file.sql container:/tmp/file.sql` followed by `docker exec container psql -U openclaw -d openclaw -f /tmp/file.sql`.

---

## Entry #004 — April 18, 2026

**Operator:** Sheldon Wheeler

**Category:** Security Framework + Performance — ADR-031, ADR-038, security event detection, Ollama native GPU migration

### Changes Made

1. **ADR-031 written (Change Management and Security Review Triggers)** — First complete formal recording of ADR-031. Defines 6 named change trigger categories, ADR impact map, 4 scheduled review cadences, weekly automated Telegram digest (14 metrics across activity, cost, performance, and security), retention policy as single source of truth. Closes CM-1, CM-3, CM-4, CM-9, AU-6(1) NIST gaps.

2. **ADR-038 written (Security Event Detection and Alerting)** — New ADR defining the security event framework. Application-layer pattern scanner (Phase 1) and SSH log forwarder (Phase 1.5) defined. `security_events` PostgreSQL table schema, 7 detection event types, real-time Telegram alert thresholds (high/critical override quiet hours), accepted gap documentation.

3. **`security_events` table created** — `migration_003.sql` written and applied. Table created with 4 indexes and 3 CHECK constraints. Schema version bumped to 4. `schema.sql` updated to include `security_events` as table 11.

4. **`app/security.py` written** — Pattern scanner implementing all 6 detection checks: prompt injection (8 patterns), persona override (7 patterns), shell injection (9 patterns — blocks request), encoding attack (base64 + hex), abnormal input length, brute force (5+ blocked requests from same channel_id in 60 minutes). Flag-and-continue by default; shell injection blocks. `write_ssh_event()` stubbed for Phase 1.5 SSH forwarder.

5. **`app/interceptor.py` updated** — `scan_security()` wired in as step 2 of the interceptor pipeline, between circuit breaker and tool registry load. Import added. Block path handled.

6. **Ollama moved from Docker container to native macOS** — Diagnosed `100% CPU` execution in Docker container (Docker Desktop VM has no access to Apple Silicon GPU). Installed Ollama natively, pulled Gemma 4 E4B, stopped Ollama container, updated `.env` `OLLAMA_HOST=host.docker.internal`, removed Ollama service from `docker-compose.yml`, removed `depends_on: ollama` from FastAPI service. Result: `100% GPU` confirmed via `ollama ps`. Response time improved from 2-3 minutes to 30-45 seconds.

### Files Changed

| File | Action |
|------|--------|
| ~/openclaw/ADR_031.docx | Created (Change Management framework — first complete recording) |
| ~/openclaw/ADR_038.docx | Created (Security Event Detection and Alerting) |
| ~/openclaw/migration_003.sql | Created (security_events table) |
| ~/openclaw/schema.sql | Replaced (v4 — security_events added as table 11) |
| ~/openclaw/app/security.py | Created (pattern scanner, ADR-038 Phase 1) |
| ~/openclaw/app/interceptor.py | Modified (scan_security() wired in as step 2) |
| ~/openclaw/docker-compose.yml | Modified (Ollama service removed, depends_on cleaned) |
| ~/openclaw/.env | Modified (OLLAMA_HOST=host.docker.internal) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-031 | Formally written this session. Single source of truth for change management. |
| ADR-038 | New ADR. Security event framework adopted. Phase 1 implementation complete (minus weekly digest task). |
| ADR-027 | Interceptor updated — security scan added as step 2. |
| ADR-035 | security_events table added to schema alongside existing ADR-035 tables. |
| ADR-005 | OLLAMA_HOST changed from container hostname to host.docker.internal. |

### NIST Controls Touched

AC-3, AU-2, AU-3, AU-6(1), CM-1, CM-3, CM-4, CM-7(1), CM-9, IR-4, IR-5, SI-3, SI-4, SI-4(2), SI-4(5)

### Risk Assessment

Ollama move: no data loss, no schema change, no egress change. Native Ollama serves the same model via same port — only the network path changed (container → host). Security scanner: flag-and-continue on all event types except shell_injection (blocked). No legitimate operator inputs contain shell metacharacters. End-to-end verified: `/prototype hello` and `/prototype what is your function` both responded correctly via native GPU Ollama. Response time 30-45 seconds confirmed on MacBook Air M1.

### Performance Note

Ollama in Docker Desktop ran `100% CPU` due to Linux VM having no Apple Silicon GPU access. Native Ollama runs `100% GPU`. Response time improvement: 2-3 minutes → 30-45 seconds (4-6x). Mac Studio M1 Max (32GB unified memory, Phase 1.5) expected to reduce further to 5-15 seconds.

---
