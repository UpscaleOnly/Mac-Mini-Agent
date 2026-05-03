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

## Entry #005 — April 19, 2026

**Operator:** Sheldon Wheeler

**Category:** Verification and Housekeeping — ADR-038 Phase 1 close-out, gitignore cleanup

### Changes Made

1. **ADR-038 Phase 1 Step 5 verified — end-to-end security detection confirmed** — Test message containing "ignore previous instructions" sent via Telegram on April 18, 2026. Confirmed: `security_events` row written with `event_type = injection`, `severity = high`, `action_taken = flagged`, `alert_sent = TRUE`. Real-time Telegram alert received on router bot. ADR-038 Phase 1 implementation sequence Steps 1–5 complete. Step 6 (this changelog entry) completes Phase 1.

2. **`.gitignore` updated** — Added entries to exclude `.bak`, `*.bak`, `.save`, and `docker-compose.yml.bak`. Prevents backup artifacts from entering version control on future commits.

3. **Cleanup commit staged** — Git commit to follow covering `.gitignore` addition and any stale backup files removed from tracked paths.

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/.gitignore` | Modified (backup file exclusions added) |
| `~/openclaw/changelog.md` | Updated (Entry #005 added) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-038 | Phase 1 implementation sequence complete. Steps 1–6 all done. Steps 7–8 (SSH forwarder) deferred to Phase 1.5 / Mac Studio setup day. |
| ADR-031 | This entry fulfills ADR-038 Step 6 — changelog entry confirming security framework close-out. |

### NIST Controls Touched

AU-2, AU-3, CM-3, IR-4, SI-4

### Risk Assessment

No code changes. Verification only. `.gitignore` change is administrative — no behavior impact. ADR-038 Phase 1 is now fully closed.

---

## Entry #006 — April 19, 2026

**Operator:** Sheldon Wheeler

**Category:** Infrastructure — Bootstrap safety, schema authority model, version gate

**Commits:** (pending end-of-session rebuild)

### Changes Made

1. **Bootstrap authority model redesigned** — Eliminated the two-actor ambiguity where both `schema.sql` and migrations could modify the database. Production rule adopted: migrations are the only thing permitted to modify an existing database. `schema.sql` is now a bootstrap-only artifact used exclusively for fresh installs, local rebuilds, and Mac Studio setup day.

2. **`app/db.py` rewritten** — Conditional bootstrap logic implemented. On every startup, `db.py` detects whether the database is fresh or existing by querying `pg_catalog.pg_tables WHERE schemaname = 'public'` for any user table. Two paths:
   - **PATH A (no tables):** Fresh database — run `schema.sql` in full, stamp version.
   - **PATH B (tables exist):** Existing database — `schema.sql` is NOT run. Read `MAX(version)` from `schema_version`, compare against `REQUIRED_SCHEMA_VERSION = 4`. Behind → CRITICAL log + `RuntimeError` (container exits, no silent limp). Equal → proceed. Ahead → warning only (dev discipline issue, not a runtime failure).
   - Version gate error message includes the exact `docker cp` + `docker exec psql` commands needed to apply missing migrations.

3. **`schema.sql` version stamp simplified** — Replaced four `ON CONFLICT DO NOTHING` INSERT statements with a single unconditional `INSERT INTO schema_version VALUES (4, ...)`. No conflict handling is needed — `schema.sql` only runs on an empty database where the table was just created. Comment cross-references `REQUIRED_SCHEMA_VERSION` in `db.py` as the single number to keep in sync when adding migrations.

4. **Docker image rebuild model documented** — Confirmed that `docker restart` does not pick up code changes (no bind mount — code is baked into the image). Established operational rule: edit freely during a session, run `docker compose build openclaw_fastapi` + `docker compose up -d openclaw_fastapi` once at end of session. This is the session-closing ritual alongside GitHub push.

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/app/db.py` | Replaced (conditional bootstrap, version gate) |
| `~/openclaw/schema.sql` | Modified (version stamp simplified to single INSERT) |
| `~/openclaw/changelog.md` | Updated (Entry #006 added) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-035 | `db.py` bootstrap behavior formally defined. `schema_version` is now enforced at startup. |
| ADR-031 | This entry fulfills the changelog requirement for the bootstrap redesign. |

### NIST Controls Touched

CM-3, CM-6, SI-2, SI-7(1)

### Risk Assessment

No schema changes. No migrations applied. No egress changes. No tools enabled. Behavior change is startup-only: existing database now skips `schema.sql` and enforces version gate instead of silently proceeding. On the current MacBook Air with schema version 4 matching `REQUIRED_SCHEMA_VERSION = 4`, startup proceeds identically to before. Verification pending end-of-session rebuild — expected log output: `Existing database detected — schema.sql will NOT be run.` followed by `Schema version OK — live database is at version 4 (required 4).`

### Docker Operational Rule (permanent)

`docker restart` restarts the process only. Code changes require a full image rebuild:

```
cd ~/openclaw && docker compose build openclaw_fastapi
docker compose up -d openclaw_fastapi
```

Run once at the end of each session, not after every edit. This is the session-closing ritual alongside `git push`.

---



---

## Entry #007 — April 24, 2026

**Operator:** Sheldon Wheeler

**Category:** Security — Backup integrity verification (ADR-039 C2)

### Changes Made

1. **Backup restore test completed** — Verified openclaw_manual_20260419_171305.sql (55KB, April 19) restores cleanly. All 17 tables confirmed present including partitions. Test database dropped clean.

2. **ADR-019 backup integrity confirmed** — Restore test satisfies ADR-039 remediation item C2.

### Files Changed

None. Verification task only.

### ADR-039 Status

C2 — CLOSED.

---

## Entry #008 — April 24, 2026

**Operator:** Sheldon Wheeler

**Category:** Security — Secrets management migration (ADR-039 A1)

### Changes Made

1. **Telegram bot tokens rotated** — All four tokens replaced via BotFather. Old tokens revoked. New tokens active.

2. **Keychain migration complete** — Six secrets stored in macOS Keychain under account=openclaw.

3. **config.py replaced** — New version includes _keychain_get() helper and SecretsOverlay class.

4. **.env scrubbed** — All token and password values removed. Empty placeholders remain.

5. **Stack rebuilt and verified** — Startup log confirms: Settings loaded. Keychain overlay applied.

### Files Changed

- config.py — replaced with Keychain-aware version
- .env — secrets scrubbed

### ADR-039 Status

A1 — CLOSED.

---

## Entry #009 — May 3, 2026

**Operator:** Sheldon Wheeler

**Category:** Security Framework — ADR-038 §6 closure (unauthorized_user) and audit data integrity

**Commits:** (pending end-of-session push)

### Changes Made

1. **ADR-038 §6 unauthorized_user — verified end-to-end after two corrective fixes.** The
   Session 19 deployment (commit `dfd103e`) returned HTTP 403 and fired the Telegram
   alert correctly, but had two latent bugs that surfaced during Step 6–9 verification:

   - **Constraint bug.** `_verify_identity()` writes `source='main_identity_check'`, but
     `security_events_source_check` allowed only `('interceptor', 'ssh_forwarder')`.
     Every unauthorized request was failing its `INSERT` silently while still returning
     403 and firing the alert. No audit row was being written.
   - **alert_sent bug.** Rows were being written with `alert_sent=FALSE` and never
     updated after Telegram confirmed delivery. The `f` was hardcoded by ordering: insert
     happens before alert send. Every successful alert was being recorded as failed in
     the audit trail.

   Both fixes deployed and verified in this session. Step 6–9 now produce all expected
   signals: HTTP 403, Telegram alert, `security_events` row with `source='main_identity_check'`
   and `action_taken='blocked'`, and `alert_sent=TRUE` after Telegram confirms delivery.
   Burst test (11 unauthorized requests) confirmed both per-IP (≥5 in 60min) and global
   (≥10 in 60min) escalation alerts fire as designed.

2. **Migration 004 — `security_events.source` CHECK constraint widened.** Added
   `'main_identity_check'` to the whitelist alongside the existing `'interceptor'` and
   `'ssh_forwarder'` values. Migration applied via standard `docker cp` + `docker exec
   psql -f` pattern (matches Migration 002 / 003 deployment). Schema version bumped 4 → 5.

3. **`schema.sql` updated to v5.** Bootstrap-correct constraint for fresh databases (Mac
   Studio setup day): inline CHECK in the `security_events` table definition includes
   the new value. Single authoritative `INSERT INTO schema_version` row updated to v5.
   Header comment line added documenting the May 3 change.

4. **`app/db.py` — `REQUIRED_SCHEMA_VERSION` bumped 4 → 5.** Comment block updated to
   list four migrations (001 initial, 002 sessions align, 003 security_events, 004
   source CHECK widened).

5. **`app/main.py` — `mark_alert_sent(event_id)` call added.** Reuses the existing
   `mark_alert_sent` helper from `security.py` (already used by `scan_security()`).
   Placed inside the per-event try block, immediately after `send_security_alert(...)`,
   so a Telegram-send exception correctly leaves `alert_sent=FALSE`. Threshold
   escalation alerts (per-IP and global) intentionally do not call `mark_alert_sent` —
   they don't write their own `security_events` rows; they're notification-only by
   design.

6. **`.gitignore` rule corrected for session-suffixed backups.** Existing `.bak` and
   `*.bak` patterns from Entry #005 did not match the `.bak.session20` and `.bak.s19`
   forms used in this and prior sessions. Five backup files were appearing as untracked
   in `git status`. Added `*.bak.*` and `*.bak.session*` patterns. Verified via
   `git status` that all five backups are now correctly filtered.

### Apply Sequence (recorded for next time we add a CHECK constraint)

Database migration first (so live DB is at v5 before new code runs version gate):
1. `docker cp migration_004.sql openclaw_postgres:/tmp/migration_004.sql`
2. `docker exec openclaw_postgres psql -U openclaw -d openclaw -f /tmp/migration_004.sql`
3. Verify: `SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = 'security_events_source_check';`
4. Verify: `SELECT MAX(version) FROM schema_version;` → 5

Code swap second:
5. Replace `~/openclaw/schema.sql` and `~/openclaw/app/db.py`
6. `docker compose build fastapi && docker compose up -d fastapi`
7. Verify startup log: `Schema version OK — live database is at version 5 (required 5).`

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/migration_004.sql` | Created (CHECK constraint widened, schema_version → 5) |
| `~/openclaw/schema.sql` | Modified (v5 — inline CHECK + version stamp updated) |
| `~/openclaw/app/db.py` | Modified (REQUIRED_SCHEMA_VERSION → 5, comment block) |
| `~/openclaw/app/main.py` | Modified (mark_alert_sent import + call) |
| `~/openclaw/.gitignore` | Modified (`.bak.*` and `.bak.session*` patterns added) |
| `~/openclaw/changelog.md` | Updated (Entry #009 added) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-038 | §6 unauthorized_user verified operational end-to-end. CRIT-3 (Session 19 review) closed for real. Audit-quality bug (alert_sent column) also closed. |
| ADR-031 | §6.3 real-time unauthorized user alert verified firing. Schema authority model (Entry #006) followed: migration applied to live DB; `schema.sql` updated for fresh installs. |
| ADR-039 | No direct closure. Session 19 review item Section 6 / "ADR-038 §6 implementation gap" → resolved. |

### NIST Controls Touched

AC-3, AC-6, AU-2, AU-3, AU-9, CM-3, IR-4, SI-4

### Risk Assessment

No new egress destinations. No tools enabled. No cost or budget changes. Schema change
is constraint-only — no data column added, no data modified, no row count change.
Behavior changes: (a) unauthorized requests now write a `security_events` row that was
previously failing silently; (b) `alert_sent` column now accurately reflects Telegram
delivery state. Both are corrections of audit-data quality bugs, not new behavior in
the request-handling path. End-to-end verified via 4 curl tests + 11-request burst —
all signals (HTTP, Telegram, database) consistent.

### Open Items Surfaced This Session

Logged for future attention. Not blocking close-out.

| Item | Severity | Notes |
|------|----------|-------|
| Per-IP rate counter keyed to incorrect IP value | Low | Threshold WARNING log shows `ip=149.154.166.110` (Telegram server) for curls run from localhost. Counter still trips correctly; only the recorded IP is wrong. Likely `_record_unauthorized()` reads a header instead of the immediate peer. |
| Router bot "unknown persona" reply on `/prototype hello` | Low | Pre-existing routing issue separate from today's work. Bot did successfully forward a different message later in the session, so not totally broken. |
| Project knowledge staleness | Medium | This session: `main.py` in project knowledge was 228 lines behind disk; `migration_003.sql` was in project knowledge but missing on disk. Session 19 review (HIGH-2) flagged the same pattern for `CURRENT_STATE.md` and `CODE_REFERENCE.md`. No documented refresh cadence in ADR-031. Phase 1.5 housekeeping. |
| Threshold escalation alerts do not write `security_events` rows | Design | Intentional today (escalation is notification-only) but worth a brief ADR note documenting the decision. Future audit queries for "how often did a threshold escalation fire" cannot be answered from the database. |

### Session 20 Test Coverage

| Test | Status |
|------|--------|
| Step 6 — Unauthorized request → 403 + alert + audit row + `alert_sent=t` | Closed |
| Step 7 — Internal token request → 200, no security event | Closed |
| Step 8 — Operator request → 200, no security event | Closed |
| Step 9 — Burst of 11 → all 403, both threshold escalations fired | Closed |

