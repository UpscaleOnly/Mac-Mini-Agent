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



---

## Entry #010 — May 15, 2026

**Operator:** Sheldon Wheeler

**Category:** Governance — ADR-039 amendment (A6 DECIDED, §7.5 added)

**Commits:** (pending end-of-session push)

### Changes Made

1. **ADR-039 §5.6 added — Sub-decision A6 (Project knowledge refresh cadence) DECIDED.** New Category A sub-decision capturing the project-knowledge-staleness pattern surfaced as Open Item 3 in Entry #009 and previously flagged in the Session 19 review (HIGH-2). Four options considered. **Option 4 selected:** weekly Sunday refresh as the primary required cadence (slotting into the existing ADR-031 Sunday rhythm), with end-of-session refresh as an opportunistic step for files modified that session. Sub-decision §5.6.1 through §5.6.5 record options, status, remediation tasks, canonical-file-set placeholder, and closure conditions. Provisional canonical file set defined in §5.6.3 pending population of §5.6.4 in a future session.

2. **ADR-039 §7.5 added — Threshold escalation alerts not persisted as `security_events` rows.** New Category C entry capturing Open Item 4 from Entry #009 as a scope clarification to ADR-038, not a remediation item. Documents that per-IP and global threshold escalation alerts intentionally do not write their own `security_events` rows; the underlying per-request rows are the audit record. Notes the design consequence (escalation-frequency cannot be answered from the database alone) and the documentation-only corrective action (ADR-038 §6 to be updated in a future session to reference §7.5).

3. **Items 1 and 2 from Entry #009 Open Items held — not migrated to ADR-039 §6.** Per-IP rate counter wrong-IP value (Low) and router bot "unknown persona" reply (Low) explicitly held this session. They remain in Entry #009's Open Items table for future attention.

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/ADR_039.docx` | Modified (§5.6 inserted between §5.5 and §6; §7.5 inserted between §7.4 and §8). Paragraph count 234 → 259. Validation PASSED. |
| `~/openclaw/changelog.md` | Updated (Entry #010 added) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-039 | Two amendments. A6 sub-decision DECIDED at architectural level; remediation tasks open. §7.5 documents threshold-escalation design choice. |
| ADR-031 | Three downstream obligations created by A6, each requiring a future changelog entry to close: (a) ADR-031 amendment to add the weekly Sunday refresh as a named change-management rule; (b) ADR-031 amendment to add canonical-file-set maintenance as a change trigger; (c) canonical file set populated in ADR-039 §5.6.4 and session-closing ritual updated. |
| ADR-038 | One downstream obligation: ADR-038 §6 to be amended to reference ADR-039 §7.5. |

### NIST Controls Touched

CM-1, CM-3, CM-4, CM-9, SA-11

### Risk Assessment

No code changes. No schema changes. No egress changes. No tools enabled. Behavior of the running system unchanged. Changes are documentation-only — a governance amendment recording a decision and a scope clarification. ADR-039 itself remains OPEN; A6 is the sixth sub-decision and joins A1 and C2 as closed at the sub-decision level, with three Category A sub-decisions (A2, A3, A4, A5) and several remediation items still open.

### Open Items Surfaced This Session

| Item | Severity | Notes |
|------|----------|-------|
| ADR-039 §7.3 May 15, 2026 federal_policy_brief shipping deadline has arrived without delivery | Medium | First PDF not delivered. Three open items from `Federal_Policy_Brief_Project_Spec.docx` §10 still block (email infra, sender domain, PDF library — though PDF library was decided as ReportLab+Platypus in May 7 chat without changelog capture). §7.3 in ADR-039 needs re-baselining or formal acknowledgment of the slip. |
| PDF library decision (ReportLab + Platypus) made May 7 but never recorded in changelog | Low | Decision is on record in chat history only; not in `changelog.md` and not in `Federal_Policy_Brief_Project_Spec.docx` §10 Open Item #3. Should be captured in a future changelog entry. |
| Carried forward from Entry #009: per-IP rate counter wrong-IP value | Low | Held this session. |
| Carried forward from Entry #009: router bot "unknown persona" reply | Low | Held this session. |
| Carried forward from Entry #009: project knowledge staleness pattern | Medium | A6 architecturally addresses this; remediation tasks remain open (canonical file set definition, ADR-031 amendment, session-closing ritual update). |

### Verification

ADR-039.docx new version (21,572 bytes, 259 paragraphs) confirmed saved to `~/openclaw/` and uploaded to claude.ai project knowledge. OneDrive backup updated.
---

## Entry #011 — May 17, 2026

**Operator:** Sheldon Wheeler

**Category:** Feature — first scraper for federal_policy_brief project (ADR-039 H4 closure)

**Commits:** `3711a53`

### Changes Made

1. **BaseScraper abstract class created** — `app/scheduling/scrapers/base.py`. Provides retry-with-backoff (5 attempts × 120s sleep, retry only on TimeoutException/ConnectError/ReadError/5xx/429), Keychain-aware DB connection via `app.config.get_settings()` (no env-var fallback per A1 closure), run-record audit via the new scraper_runs table, dedup via `ON CONFLICT (source_domain, content_hash) DO NOTHING`. Subclasses implement `fetch()` and `parse()` only — everything else is inherited. `ScrapedRow` dataclass added as the contract between `parse()` and the base insert helper.

2. **scraper_runs table created via migration_005.sql** — Audit trail for every scraper execution. Columns: scraper_name, project, source_domain, started_at, ended_at, status (CHECK: running/success/partial/failed), docs_fetched, docs_inserted, docs_skipped, retries_used, error_message, created_at. Indexes on (scraper_name, started_at DESC), (project, started_at DESC), and status. Status determination: failed if fetch() raised AND zero docs returned; partial if fetch() raised but some docs came back; success otherwise. Migration named 005 because Entry #009 (May 3, ADR-038 §6 closure) had used the 004 slot.

3. **scraped_content schema extended** — Added `project VARCHAR(64) NOT NULL` and `scraper_run_id INTEGER` FK. Table had 18 pre-existing rows from an undocumented April 26 run of the old standalone scraper; backfilled to `project='federal_policy_brief'`, `scraper_run_id=NULL`. FK uses `ON DELETE SET NULL` so future scraper_runs retention pruning will not destroy content rows. New indexes on both columns.

4. **FederalRegisterScraper subclass shipped** — First concrete BaseScraper at `app/scheduling/scrapers/federal_register.py`. Targets 6 HHS-adjacent agencies (HHS, CMS, USDA, ACF, IRS, SSA) via REST API only — no HTML parsing. Per-agency error isolation: one agency's retry exhaustion does not abort the run, just logs and continues. `parse()` skips docs with no `html_url` (unlinkable rows are worse than missing rows) and parses `publication_date` to a real date object with NULL fallback on malformed input. Replaces the old standalone `federal_register_scraper.py` which is deleted in this entry.

5. **scrape_dispatcher_job added to jobs.py** — Bounded `asyncio.gather()` with concurrency cap of 3 (`DISPATCH_CONCURRENCY` module constant). Reads scrapers from `SCRAPERS` registry in `app/scheduling/scrapers/__init__.py`, filters by `project` parameter, runs each via `asyncio.to_thread()` to parallelize sync scraper code across threads while the asyncio loop bounds concurrency. Per-scraper failures isolated via try/except in `_run_one`. Scales to N scrapers per project without changes to this code; adding a scraper is one import + one line in the registry.

6. **federal_policy_scrape cron registered** — Daily 01:00 ET. Uses `functools.partial(scrape_dispatcher_job, project="federal_policy_brief")` to pre-bind the project parameter. Misfire grace 600 seconds. Same pattern will apply to future per-project crons (medical_brief, durham_politics — both Research persona).

7. **schema.sql brought current** — `scraped_content` and `scraper_runs` definitions added for fresh installs. `security_events_source_check` CHECK constraint widened to include `'main_identity_check'` (catching up the May 3 Entry #009 change that never made it back to schema.sql in project knowledge — see Open Items below). Version stamp bumped to 6 with corrected description.

8. **REQUIRED_SCHEMA_VERSION bumped 5 → 6** — One-line edit in `app/db.py`. Bumped after migration applied, per the ordering rule (raising the required version before applying the migration crashes startup hard; raising it after just logs a warning if anything).

9. **Old standalone scraper deleted** — `app/scheduling/federal_register_scraper.py` removed. Stale nano artifact `app/scheduling/jobs.py.save` also deleted. Stray empty `~/openclaw/main` file (May 15 typo) removed before git commit.

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/migration_005.sql` | Created and applied to live DB |
| `~/openclaw/schema.sql` | Modified (scraped_content + scraper_runs added, security_events CHECK widened, version → 6) |
| `~/openclaw/app/db.py` | Modified (REQUIRED_SCHEMA_VERSION 5 → 6) |
| `~/openclaw/app/scheduling/scrapers/__init__.py` | Created (SCRAPERS registry + scrapers_for_project helper) |
| `~/openclaw/app/scheduling/scrapers/base.py` | Created (BaseScraper ABC + ScrapedRow dataclass + retry logic) |
| `~/openclaw/app/scheduling/scrapers/federal_register.py` | Created (first concrete subclass) |
| `~/openclaw/app/scheduling/jobs.py` | Modified (scrape_dispatcher_job added with bounded asyncio.gather) |
| `~/openclaw/app/scheduling/scheduler.py` | Modified (federal_policy_scrape cron registered at 01:00 ET) |
| `~/openclaw/app/scheduling/federal_register_scraper.py` | Deleted (replaced by scrapers/federal_register.py) |
| `~/openclaw/app/scheduling/jobs.py.save` | Deleted (stale nano artifact) |
| `~/openclaw/main` | Deleted (stray empty file from May 15) |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-039 | H4 sub-decision CLOSED — first scraper shipped two days past the §7.3 May 15 target. Inverts the governance-to-feature ratio flagged by the adversarial review (38 ADRs, 0 features → first feature shipped). Many §7 items still open. |
| ADR-029 | scraper_runs is the audit table for scrapers, analogous to agent_actions for the agent pipeline. Scrapers operate below the agent pipeline; no /agent hop, no LLM tokens, no interceptor. Separate audit trail by design. |
| ADR-030 | Reaffirmed: scrapers fetch from pinned source-domain URLs only. No Brave Search, no discovery. BaseScraper class documentation makes this explicit constraint visible. |
| ADR-031 | Migration applied via the documented workflow: backup → apply → verify → rebuild → commit. STOP POINTS observed at each verification stage. |
| ADR-035 | Schema version model from Entry #006 followed end-to-end: migration to live DB, schema.sql updated for fresh installs, REQUIRED_SCHEMA_VERSION kept in lockstep with live state. |
| ADR-038 §6 | schema.sql caught up to live state — `main_identity_check` value now present in `security_events_source_check` CHECK constraint. Closes a project-knowledge drift gap not addressed in Entry #009. |

### NIST Controls Touched

AU-2 (audit events — scraper_runs is the audit record for scraping operations), AU-3 (content of audit records — full run summary captured including counts and error_message), AU-12 (audit generation — every scraper execution generates exactly one scraper_runs row), CM-3 (configuration change control — migration applied via ADR-031 workflow with STOP POINTS), SA-11 (developer testing — manual dry-run verified end-to-end before scheduled fire), SI-12 (information management — `ON CONFLICT DO NOTHING` dedup prevents corruption from re-runs).

### Risk Assessment

No egress changes — `federalregister.gov` was already on the Automate persona network whitelist per project spec. No new tools enabled — scrapers operate below the agent pipeline and do not appear in `tool_registry`. No cost or budget changes — zero LLM tokens consumed. Schema changes are additive — new table, new nullable column then `SET NOT NULL` after backfill of (effectively) an empty table, new FK with `ON DELETE SET NULL`. Behavior change: a daily cron now fires at 01:00 ET — verified to complete in 7 seconds on dry-run, comfortable within the 04:00 ET pg_dump window. End-to-end verified via manual run (98 fetched, 70 inserted, 28 skipped, status=success) and dedup verified via second consecutive run (98 fetched, 0 inserted, 98 skipped, status=success). Rollback path documented in deployment plan Phase 2.3 (drop FK, drop columns, drop scraper_runs, delete version 6 row).

### Verification

- Manual backup taken pre-deployment: 82,706 bytes, May 17, 2026, in Mac-Mini-Backups iCloud folder ✓
- Migration applied: schema_version moved 5 → 6 ✓
- `scraped_content` shape verified via `\d`: 13 columns, new project (NOT NULL) + scraper_run_id (FK) ✓
- `scraper_runs` shape verified via `\d`: 13 columns, 4 indexes, status CHECK constraint with 4 valid values ✓
- FastAPI clean startup post-rebuild: `Schema version OK — live database is at version 6 (required 6)` ✓
- 3 jobs registered: `APScheduler started. Active jobs: 3` — federal_policy_scrape visible in the registration log ✓
- Manual dry-run #1: scraper_runs row id=1, status=success, 98/70/28, 7-second duration ✓
- Manual dry-run #2 (dedup check): scraper_runs row id=2, status=success, 98/0/98, 7-second duration ✓
- Spot-check of 5 newest rows: real Federal Register data, correct content_type mapping, correct date parsing, correct agency names ✓
- Git commit `3711a53` pushed to GitHub (`9dfd2d1..3711a53` on main) ✓
- Scheduled run for 01:00 ET on May 18, 2026 — **pending verification next session** ✗

### Open Items Surfaced This Session

| Item | Severity | Notes |
|------|----------|-------|
| Backup gap discovered | High | Only one backup in `Mac-Mini-Backups/` pre-session, dated April 19 — 28 days old. IR Runbook SEV-2 threshold is 48h. No Telegram failure-alert was received during the 28-day gap, implying the failure-alert path itself is also broken. Manual backup taken this session as a baseline. Root-cause investigation deferred as a separate session ("Option B" in this session's exchange). |
| A6 remediation overdue | High | ADR-039 §5.6 (project-knowledge refresh cadence, decided Session 21) hit live during this session. schema.sql was stale by 14 days, missing the May 3 ADR-038 §6 change. Caused mid-session rework: renumbering migration 004 → 005, retargeting schema versions 4→5 → 5→6, db.py bump 5 → 6 instead of 4 → 5. A6 implementation now overdue, not just open. |
| Missing migration_004.sql source file | Medium | Entry #009 (May 3) applied a migration widening `security_events_source_check` to include `'main_identity_check'`. The migration was applied to live DB and the description recorded in `schema_version`, but no `.sql` file exists in project knowledge or the git repo. Should be reconstructed from live DB state in a follow-up session and committed to the repo for a complete migration history on disk. |
| 18 pre-existing rows in scraped_content | Low | Pre-existing rows from an undocumented manual run of the old standalone scraper on April 26 at 14:01 UTC, all from federalregister.gov. Backfilled by migration_005 to `project='federal_policy_brief'`, `scraper_run_id=NULL` (predate scraper_runs existence). Dedup will prevent reinsertion. No changelog record of the original run. Documented here for historical completeness. |
| 15 remaining federal_policy_brief scrapers | Medium | H4 only ships `federal_register`. Still needed: cms, hhs.gov (separate from FR agency filter), usda.gov, acf.hhs.gov, ssa.gov, congress.gov, kff.org, cbpp.org, clasp.org, nashp.org, ncsl.org, nga.org, aphsa.org, macpac.gov, plus any others identified during build. Each is one subclass file + one registry line. Pattern is now proven. |
| `retries_used` counter always records 0 | Low | The counter is declared in `BaseScraper.run()` but the HTTP helper does not thread the count back to it. Counter is cosmetic in the audit table — retry behavior itself works correctly. Threading the count from `_http_get_with_retry` back to `run()` is a follow-up; not blocking. |
| Phase 4 (db.py constant bump) executed out of order | Resolved | The constant was bumped to 6 before the migration was applied, briefly creating a window where FastAPI would have crashed on restart. No restart occurred during the window. Migration was then applied to bring the DB into sync. Document this as a known pre-flight check for future migrations: always confirm the deployment plan order before running any commands. |
| ADR-039 §7.3 May 15 ship target | Medium | First scraper shipped May 17, two days past the §7.3 target. PDF delivery for federal_policy_brief still blocked on: email infrastructure (open), sender domain (open), PDF library decision (decided May 7 as ReportLab + Platypus, but still uncaptured in changelog — needs a separate entry). |
| Backup file artifacts | Low | `app/scheduling/jobs.py.bak.s19`, `app/scheduling/jobs.py.bak.s22`, `app/scheduling/scheduler.py.bak.s22`, `schema.sql.bak.s22` all present on disk and gitignored. Delete in next session after 24-hour stability confirmed. |

### What's Next

| Action | When |
|--------|------|
| Verify 01:00 ET scheduled run fired successfully | Next session, May 18 morning |
| Delete backup file artifacts (`.bak.s22` files) | Next session, after Phase 9 verification |
| Investigate backup-cron / failure-alert gap (Option B from this session) | Separate session, this week |
| Implement A6 (project-knowledge refresh cadence) | Overdue, next priority session |
| Reconstruct missing `migration_004.sql` source file from live DB | Follow-up session |
| Begin `federal_policy_brief` PDF library work (ReportLab + Platypus) | After H4 stability confirmed |
| Add scraper #2 (CMS) following the BaseScraper template | Once federal_register has 7 days of clean scheduled runs |
---

## Entry #012 — May 17, 2026

**Operator:** Sheldon Wheeler

**Category:** Governance — A6 remediation closure (ADR-039 §5.6.4 populated; ADR-031 amended)

**Commits:** (pending end-of-session push)

### Changes Made

1. **ADR-031 amended — §3.7 added (canonical file set maintenance as change trigger).** New seventh subsection under Section 3 "Change Trigger Categories". Triggers: adding a new project that introduces files matching the §5.6.4 canonical file set patterns; adding a new module under app/ or app/scheduling/scrapers/; removing a file currently named in the canonical set; renaming a canonical file; any change to §5.6.4 itself. Required ADR review: ADR-039 (§5.6.4 is the authoritative list) and ADR-037 (per-project markdown naming pattern). Closes the second of three downstream obligations created by Entry #010.

2. **ADR-031 amended — §5 Scheduled Reviews gains weekly Sunday project-knowledge refresh row.** New row between the existing Sunday 08:00 digest row and the Monthly row. Cadence: weekly, Sunday operator session. Action: re-upload every file named in ADR-039 §5.6.4 to the Claude.ai project, verify byte sizes and counts match local disk, log completion in changelog.md as part of the Sunday session entry. End-of-session refresh during the week is encouraged but not load-bearing. Mechanism: manual operator action; optional `refresh_pk.sh` helper deferred per §5.6.3. NIST: CM-3, CM-4, CM-9, SA-11. Closes the first of three downstream obligations.

3. **ADR-031 amended — §4 ADR Impact Map gains Canonical File Set Maintenance row.** Required ADR review: ADR-039 §5.6.4 and ADR-037. Approval: operator self-approval; log entry same day; §5.6.4 list updated in the same commit.

4. **ADR-031 amended — §7 Retention Policy gains scraper_runs row.** 180 days, manual prune via scheduled task (Phase 1.5). Closes a small drift item from Entry #011 — the new table introduced in migration_005 had no retention entry in ADR-031.

5. **ADR-031 amended — §9 NIST 800-53 Alignment updated.** CM-3 mechanism cites §3.7. CM-9 mechanism cites §5 project-knowledge refresh cadence. SA-11 IMPROVED with mechanism citing reduced stale-artifact risk during adversarial review. §10 ADR Cross-Reference gains ADR-039 row; ADR-037 row updated to reference per-project markdown pattern. §12 Future Considerations gains `refresh_pk.sh` helper as Phase 1.5 item.

6. **ADR-039 §5.6.4 populated — canonical file set defined.** Replaces the May 15 placeholder with an explicit list grouped into seven categories: app/ Python modules (10 files), app/scheduling/ Python modules (3 files), app/scheduling/scrapers/ Python modules (3 files plus directory pattern for future scrapers), SQL (schema.sql, current latest migration, tool_registry_seed.sql), infrastructure (docker-compose.yml, .env.example, requirements.txt, .gitignore, .dockerignore), operations (changelog.md), and per-project markdown (4 files for federal_policy_brief plus a noted pattern for future projects). Out-of-scope section explicitly excludes ADR documents (refresh on amendment only), historical project-status docs, compliance docs, PDF references, backup files, and session-review markdown. Baseline total approximately 30 active canonical files. Closes the third of three downstream obligations.

7. **ADR-039 §5.6.3 remediation tasks marked DONE.** Four of five tasks now closed (canonical file set defined, ADR-031 §5 amended, ADR-031 §3.7 amended, session-closing ritual updated). `refresh_pk.sh` helper remains explicitly OPEN and Phase 1.5.

8. **ADR-039 §5.6.5 closure updated.** A6 is now closed in full at the architectural and remediation level except for the optional `refresh_pk.sh` task.

9. **ADR-039 §10 closure-status footer added.** Records that as of May 17, 2026 Critical band A1 is DECIDED; High band A2/A3/A5 OPEN, H2/H4 closed; Medium band A4 OPEN, A6 DECIDED; Section 6 C2/M2/H4 closed, H5/L1 open.

10. **ADR-039 §7.3 status note added.** Records that the H4 forcing-function deadline (May 15) slipped by two days per Entry #011, and that PDF delivery to inbox remains blocked on email infrastructure, sender domain, and the not-yet-changelog-captured May 7 ReportLab + Platypus decision.

11. **Session-closing ritual updated — operator memory edit.** Memory entry now includes opportunistic end-of-session project-knowledge refresh for files modified that session, with the load-bearing rule being the Sunday weekly refresh.

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/ADR_031.docx` | Modified (§3.7 added; §4, §5, §7, §9, §10, §12 amended; status, ADR References, NIST controls, scope wording updated). Paragraph count 234 → 417. Validation PASSED. Bytes: 21,408. |
| `~/openclaw/ADR_039.docx` | Modified (§5.6.4 populated; §5.6.5 closure updated; §6 H4 row marked closed; §7.3 status note added; §10 closure-status footer added; §11 cross-reference updated). Paragraph count 259 → 306. Validation PASSED. Bytes: 24,255. |
| `~/openclaw/changelog.md` | Updated (Entry #012 added — this entry) |
| (operator memory) | Edited via `memory_user_edits` to add opportunistic end-of-session project-knowledge refresh as a session-closing ritual step. Not a file change, recorded here for completeness. |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-039 | §5.6.4 canonical file set populated. §5.6.5 closure updated. §5.6.3 four of five remediation tasks closed. §6 H4 row marked closed. §7.3 deadline-slip note added. §10 closure-status footer added. §11 cross-reference updated. A6 sub-decision now closed except for the explicitly optional `refresh_pk.sh` Phase 1.5 task. |
| ADR-031 | Five amendments: §3.7 added; §4 impact map row added; §5 scheduled reviews row added; §7 retention table row added; §9 NIST mechanisms updated. §10 cross-reference adds ADR-039 row and updates ADR-037 row. §12 future considerations adds `refresh_pk.sh`. All three downstream obligations from Entry #010 are closed in this entry. |
| ADR-037 | No edits to ADR-037 itself this entry. Cross-references in ADR-031 §10 and ADR-039 §11 updated to reflect that the per-project canonical markdown naming pattern (*_CURRENT_STATE / *_DECISIONS / *_CODE_REFERENCE / *_KNOWLEDGE) originates in ADR-037 and is now load-bearing for ADR-039 §5.6.4 and ADR-031 §3.7. |
| ADR-038 | No change this entry. Downstream obligation from Entry #010 (ADR-038 §6 to reference ADR-039 §7.5) remains open. |

### NIST Controls Touched

CM-1, CM-3, CM-3(2), CM-4, CM-9, SA-11

### Risk Assessment

No code changes. No schema changes. No egress changes. No tools enabled. No cost or budget changes. Behavior of the running system unchanged. Changes are documentation-only — three governance amendments executed in one session to close the three downstream obligations created by Entry #010. Validation PASSED on both `.docx` files. No `docker compose build` required; session-closing ritual is `cp` files into `~/openclaw/`, append this entry to `changelog.md`, re-upload both `.docx` files to project knowledge (itself an A6-compliant act), and `git add -A && git commit && git push`.

### A6 Closure Note

A6 sub-decision was DECIDED on May 15, 2026 per Entry #010. The three downstream obligations from that entry are closed in this entry:

| Obligation | Status | Implementation |
|------------|--------|----------------|
| (a) ADR-031 amendment — weekly Sunday refresh as a named change-management rule | CLOSED | ADR-031 §5 new row added; §4 impact map and §9 NIST CM-9 mechanism aligned |
| (b) ADR-031 amendment — canonical-file-set maintenance as a change trigger | CLOSED | ADR-031 §3.7 added; §4 impact map row added; §9 NIST CM-3 mechanism aligned |
| (c) Canonical file set populated in ADR-039 §5.6.4 and session-closing ritual updated | CLOSED | ADR-039 §5.6.4 populated with seven categories and ~30 baseline files; operator memory updated |

The optional `refresh_pk.sh` helper from §5.6.3 remains explicitly OPEN as a Phase 1.5 item.

The fact that the A6 remediation was overdue per Entry #011 Open Items — and would have prevented the mid-session migration renumber rework if it had been closed earlier — is acknowledged. This entry was the forcing function that re-aligned the working assumption (operator memory believed C2 / A1 were still pending) against actual changelog state.

### Open Items Surfaced This Session

| Item | Severity | Notes |
|------|----------|-------|
| `refresh_pk.sh` helper script | Low | Optional per ADR-039 §5.6.3. Tracked as Phase 1.5 item in ADR-031 §12. |
| ADR-038 §6 amendment to reference ADR-039 §7.5 | Low | Downstream obligation from Entry #010 unchanged; not closed this session. |
| Operator memory drift discovered | Medium | Operator memory was tracking deferred-low-risk items (C2, A1, `.env` scrub, changelog entries, git commit) that had actually been closed in Entries #007 and #008 (April 24, 2026). Memory edit this session to remove the stale deferred-items list. Not a code or governance gap; a recurring operator-memory hygiene issue. Consider whether memory itself becomes a canonical-set entry or whether A6 Sunday refresh implicitly covers it through changelog state. |
| Carried forward from Entry #011: 01:00 ET scheduled scraper run verification (Phase 9) | High | Pending May 18 morning. |
| Carried forward from Entry #011: backup-cron / failure-alert investigation (Option B) | High | Pending this week. |
| Carried forward from Entry #011: missing migration_004.sql reconstruction | Medium | Pending. |
| Carried forward from Entry #011: 15 remaining federal_policy_brief scrapers | Medium | Pending. |
| Carried forward from Entry #011: backup file artifacts (`.bak.s22`) | Low | Hold until 24h after Phase 9 verification. |
| Carried forward from Entry #010: ADR-039 §7.3 federal_policy_brief PDF delivery target re-baselining | Medium | §7.3 status note added this entry; formal re-baseline still pending. |
| Carried forward from Entry #010: PDF library decision (ReportLab + Platypus) May 7 not in changelog | Low | Should be captured in a future changelog entry. |
| Carried forward from Entry #009 / earlier: per-IP rate counter wrong-IP value, router bot "unknown persona" reply | Low | Unchanged. |

### Verification

- ADR_031.docx new version: 21,408 bytes, 417 paragraphs, validation PASSED ✓
- ADR_039.docx new version: 24,255 bytes, 306 paragraphs, validation PASSED ✓
- Entry #012 (this entry) added to changelog.md ✓
- Operator memory edit applied via memory_user_edits ✓
- Three documents re-uploaded to claude.ai project knowledge (ADR-031, ADR-039, changelog.md) — pending operator action this session close
- Git commit pending session close

### What's Next

Same as Entry #011 §What's Next, unchanged except this entry closes the three A6 obligations:

| Action | When |
|--------|------|
| Verify 01:00 ET scheduled run fired successfully | Next session, May 18 morning |
| Investigate backup-cron / failure-alert gap (Option B) | Separate session, this week |
| Delete backup file artifacts (`.bak.s22` files) | Next session, after Phase 9 verification |
| Reconstruct missing `migration_004.sql` source file from live DB | Follow-up session |
| Amend ADR-038 §6 to reference ADR-039 §7.5 | Follow-up session |
| Capture ReportLab + Platypus PDF library decision in changelog | Follow-up session |
| Begin `federal_policy_brief` PDF library work | After H4 stability confirmed |
| Add scraper #2 (CMS) following the BaseScraper template | Once federal_register has 7 days of clean scheduled runs |
| Optional: implement `refresh_pk.sh` helper (ADR-039 §5.6.3) | Phase 1.5 |
---

## Entry #013 — May 17, 2026

**Operator:** Sheldon Wheeler

**Category:** Infrastructure — Interim backup automation (Option B closure)

**Commits:** (pending end-of-session push)

### Changes Made

1. **Root cause of 28-day backup gap identified.** Per Entry #011 Open Items, only one backup file existed in `Mac-Mini-Backups/` pre-Session 22 (April 19, 28 days old). Investigation this session via `crontab -l`, `launchctl list | grep -i openclaw`, and `ls /Users` confirmed: no cron job, no launchd agent, no `dev` user account exist on the MacBook Air. The Session 7 ADR-019 design ties backup automation to the `dev` account under the ADR-020 five-account split, scheduled for Mac Studio setup day. The five-account split has not been built on the interim MacBook Air. Therefore no scheduling mechanism was ever deployed — the gap is "automation never installed on interim hardware," not "automation broken." Failure-alert silence is consistent with this: nothing was scheduled that could fail. The original Entry #011 framing ("backup-cron / failure-alert investigation") is updated by this entry.

2. **Interim backup automation installed under `sheldonwheeler` user via launchd.** New shell script at `~/openclaw/scripts/backup.sh`. Scheduled at 04:00 local time daily via a launchd user agent at `~/Library/LaunchAgents/com.openclaw.backup.plist`. Performs `docker exec openclaw_postgres pg_dump -U openclaw -d openclaw -Z 9` writing a gzip-compressed dump to `~/Documents/Mac-Mini-Backups-Interim/dumps/openclaw_YYYYMMDD_HHMMSS.sql.gz` (iCloud-synced via Desktop & Documents Folders sync). Logs to `~/Documents/Mac-Mini-Backups-Interim/logs/backup_YYYYMMDD.log`. Applies 30-day retention to dump files (per ADR-031 §7) and 90-day retention to log files (per ADR-019). Sends Telegram alert via curl to bot API on any failure stage (pg_dump_failed, pg_dump_empty, postgres_down, directory_unreachable). Reads the **router bot token from macOS Keychain** (service=`TELEGRAM_TOKEN_ROUTER`, account=`openclaw`, per A1 closure / Entry #008). Reads the **operator chat ID from `.env`** (variable `OPERATOR_TELEGRAM_ID`) since the chat ID is not in Keychain — only the six rotated secrets are. This matches the existing convention in `telegram_bot.py` which also reads `OPERATOR_TELEGRAM_ID` from environment. Folder-size alert at 5 GB threshold per ADR-019, one-time-per-crossing via marker file.

3. **launchd chosen over cron after cron path failed.** Initial install attempt was `crontab -` (single-line install). macOS prompted with "Terminal would like to administer your computer" — a broad system-level admin grant prompt not appropriate for installing a per-user cron. Declined. `crontab -` then failed with `Operation not permitted` (TCC sandbox restriction on legacy cron subsystem). Pivoted to `launchctl load -w` of a user agent plist, which is the modern macOS-preferred scheduling mechanism. No admin prompt; the load command succeeds silently for user agents.

4. **TCC permission grant required for launchd-spawned bash.** Initial launchd-fired run failed with `Operation not permitted` writing to iCloud paths. Confirmed via dump output that scripts spawned by launchd run in a restricted TCC sandbox that does not permit writes to `~/Library/Mobile Documents/` (iCloud Drive raw path) or `~/Documents/` (Desktop & Documents Folders sync target). Resolved by granting **Full Disk Access to `/bin/bash`** via System Settings → Privacy & Security → Full Disk Access → `+` → `/bin/bash`. After grant, launchd-fired runs succeed with no permission errors. The grant scopes Full Disk Access to any bash-interpreted script, which is a wide grant; acceptable on a single-user developer machine where the operator is the only entity running bash scripts. To be revisited on Mac Studio setup day under the `dev` account model.

5. **Backup destination path changed from raw iCloud to Documents-synced iCloud.** Original script wrote to `~/Library/Mobile Documents/com~apple~CloudDocs/Mac-Mini-Backups/interim-macbook-air/`. Mid-session, after the first TCC failure on that raw path, the script was modified to write to `~/Documents/Mac-Mini-Backups-Interim/dumps/` instead. Both paths sync to the same iCloud account; the Documents-synced path is the cleaner pattern for non-iCloud-native processes. The change was made before FDA was granted, and the same TCC error then recurred on the new path — confirming the issue was permission scope, not path. FDA on bash then unblocked both paths; the Documents path was retained as the simpler convention.

6. **Subfolder separation in iCloud.** New top-level iCloud folder `Mac-Mini-Backups-Interim/` containing `dumps/` and `logs/`. The two pre-existing manual backups (April 19, May 17) remain at the top level of the original `Mac-Mini-Backups/` folder as historical artifacts. Mac Studio setup day will use the original folder for the canonical `dev`-owned launchd output, keeping the production location pristine.

7. **`pmset repeat wakeorpoweron`** scheduled for 03:55 daily, 5-minute buffer before launchd fires at 04:00. The MacBook Air must be plugged into AC overnight for the wake schedule to fire (battery-only wake is not honored by `pmset`).

8. **Manual fire-test executed (B28).** Before relying on the schedule, script was run once by hand with `bash ~/openclaw/scripts/backup.sh` to verify: postgres container detected; `pg_dump` produces a non-empty `.sql.gz` file; log line written; folder size sum computes correctly. Result: clean three-line log, dump landed at 34,433 bytes.

9. **Telegram alert path tested via deliberate failure injection (B11–B13).** Before relying on the alert, postgres container was stopped (`docker stop openclaw_postgres`), backup script run, alert received on operator phone within seconds. Container restarted, script re-run successfully. First end-to-end verification of the backup-alert path on this hardware.

10. **Second alert delivery confirmed via launchd-fired run with TCC failure (B23).** During FDA troubleshooting, an unscheduled launchd-fired run failed on TCC. Script alert path fired correctly through the failure mode (`ALERT_SENT: pg_dump_failed` log line, Telegram message received). This is the second independent confirmation that the alert path is robust, and the only one that exercised the launchd-spawned alert path specifically.

11. **launchd-fired run verified successful post-FDA (B41–B47).** After granting FDA to bash, launchd-fired job produces a fresh dump at `~/Documents/Mac-Mini-Backups-Interim/dumps/openclaw_YYYYMMDD_HHMMSS.sql.gz`, log line at `~/Documents/Mac-Mini-Backups-Interim/logs/backup_YYYYMMDD.log`, no alert (successful run). Verified at 22:00 UTC, 34,433 bytes.

12. **ADR-019 interim deviation documented.** ADR-019 §1 specifies 4 AM cron under `dev` account writing via dev write-only ACL. On the MacBook Air interim there is no `dev` account; the launchd user agent runs under `sheldonwheeler` with Full Disk Access to `/bin/bash`. This is a known deviation explicitly bounded to interim hardware and explicitly reverted on Mac Studio setup day. Recorded in this changelog entry; permanent ADR-019 changes are not warranted since the deviation is interim-only and time-bounded.

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/scripts/backup.sh` | Created — nightly backup script with Telegram failure alert and 30-day retention. Writes to `~/Documents/Mac-Mini-Backups-Interim/dumps/` and `~/Documents/Mac-Mini-Backups-Interim/logs/`. |
| `~/Library/LaunchAgents/com.openclaw.backup.plist` | Created — launchd user agent. Label `com.openclaw.backup`, fires daily at 04:00 local. Loaded with `launchctl load -w`. |
| `~/Documents/Mac-Mini-Backups-Interim/dumps/` | Created — folder for nightly compressed dumps. iCloud-synced via Desktop & Documents Folders. |
| `~/Documents/Mac-Mini-Backups-Interim/logs/` | Created — folder for daily log files. Same sync. |
| (pmset schedule) | Modified — added daily wake at 03:55 via `sudo pmset repeat wakeorpoweron MTWRFSU 03:55:00`. Verified via `pmset -g sched`. |
| (TCC database) | Modified — granted Full Disk Access to `/bin/bash` via System Settings GUI. |
| `~/openclaw/changelog.md` | Updated — this entry |

Note: `backup.sh` is tracked in git under `~/openclaw/scripts/`. The launchd plist lives in `~/Library/LaunchAgents/`, outside the repo, so it is also not tracked by git. The plist file content is recorded in operator notes (pmset_reference.txt, this entry) for reproducibility.

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-019 | Interim deviation acknowledged for MacBook Air. Schedule 04:00 matches §1. Failure-alert via Telegram matches §1. 5GB folder-size alert matches §1. Deviations: (a) scheduling via launchd, not cron, due to cron TCC issues on modern macOS; (b) runs as `sheldonwheeler`, not `dev`, due to ADR-020 five-account split not being built on interim hardware; (c) destination is `~/Documents/Mac-Mini-Backups-Interim/` not `Mac-Mini-Backups/`, due to TCC restrictions on the original path for launchd-spawned processes. All three deviations revert on Mac Studio setup day. |
| ADR-020 | Five-account split (admin / dev / openclaw / sheldon / spousal) is not built on interim hardware. Documented here as the reason for the ADR-019 deviation. ADR-020 not amended; remains the canonical Mac Studio plan. |
| ADR-031 | §7 retention table: 30-day rolling window for nightly backups is enforced by `find -mtime +30 -delete` in backup.sh. 90-day log retention enforced similarly. |
| ADR-039 | A4 (backup destination diversity) remains OPEN. Adding Backblaze B2 stays deferred to Mac Studio setup day per §5.4.2. This entry does not close A4. |
| ADR-039 | A1 closure (Entry #008) — `backup.sh` reads bot token from Keychain via `security find-generic-password -a openclaw -s TELEGRAM_TOKEN_ROUTER -w`. No secrets in script or in launchd plist. |
| IR Runbook | Scenario 2 (Backup Failure) Containment Step 2 (`cat /tmp/pg_backup.log`) is now obsolete — the log lives in `~/Documents/Mac-Mini-Backups-Interim/logs/backup_YYYYMMDD.log` during interim operation. IR Runbook to be amended in a follow-up session to reflect the interim log path and to add a note about the Mac Studio cutover path. |

### NIST Controls Touched

CP-9 (System Backup) — IMPROVED: scheduled backups now exist on interim hardware; no longer dependent on manual operator action.
CP-10 (System Recovery and Reconstitution) — IMPROVED: restore window is no longer 28 days; aligns with IR Runbook SEV-2 48-hour threshold.
IR-4 (Incident Handling) — IMPROVED: failure path now triggers an alert; alert path tested end-to-end this session (twice — manual stop test, and natural launchd-fired TCC failure).
SI-4 (System Monitoring) — IMPROVED: backup success and folder size are monitored daily.
AU-2 / AU-3 (Audit events): each run produces an audit log line in the daily log file.

### Risk Assessment

No egress changes — `api.telegram.org` was already permitted for the existing router bot. No tools enabled. No schema changes. No code-path changes inside the FastAPI container. The new shell script runs outside the container as a host-level launchd job; it does not touch the application code or alter the request pipeline. The only behavioral change visible from outside this script: a new `.sql.gz` file appears in iCloud each morning and a daily log line is written. Failure-mode behavior: a Telegram alert fires within seconds of the failure stage.

Two interim deviations from canonical design constitute real reductions in principle-of-least-privilege posture, both acknowledged for interim duration:
- Running under `sheldonwheeler` instead of `dev`: the script and its launchd-spawned bash have full FS access; ADR-020 canonical model would have dev with write-only ACL only.
- Full Disk Access on `/bin/bash`: any bash-interpreted script on this machine now has elevated file access. On a single-user developer machine this is acceptable; in a multi-user or production environment it would not be.

Both deviations revert on Mac Studio setup day under the dev account + launchd-or-cron-with-dedicated-grant model.

### Verification

- Script syntax check: `bash -n ~/openclaw/scripts/backup.sh` → no errors ✓
- Manual fire-test #1: `bash ~/openclaw/scripts/backup.sh` → exit 0, 34,430-byte dump at 17:35:50 ✓
- Telegram failure-injection test: stopped postgres, ran script manually → Telegram alert "postgres_down" received on operator phone within seconds ✓
- Restored postgres, manual fire-test #2 → exit 0, 34,435-byte dump at 17:12:54 ✓
- launchctl load: `launchctl load -w ~/Library/LaunchAgents/com.openclaw.backup.plist` → silent success ✓
- launchctl list: `launchctl list | grep openclaw` → `- 0 com.openclaw.backup` registered ✓
- First launchd-fired run pre-FDA: failed with TCC "Operation not permitted" → Telegram alert "pg_dump_failed" received → confirmed alert path works in launchd context too ✓
- Full Disk Access granted to `/bin/bash` via System Settings → confirmed in privacy panel ✓
- Second launchd-fired run post-FDA: clean three-line log, 34,433-byte dump at 18:00:39 ✓
- pmset schedule registered: `pmset -g sched` → `wakepoweron at 3:55AM every day` ✓
- File count in `~/Documents/Mac-Mini-Backups-Interim/dumps/`: 2 files at session close, both ~34KB ✓

### Open Items Surfaced This Session

| Item | Severity | Notes |
|------|----------|-------|
| First fully autonomous scheduled run verification | High | Tomorrow morning, May 18, 04:00 ET. Verify a new `.sql.gz` lands in `~/Documents/Mac-Mini-Backups-Interim/dumps/`. Adjacent in time to 01:00 ET federal_register scheduled run from Entry #011. Both verified in one Monday-morning session. |
| IR Runbook Scenario 2 path update | Medium | Log path during interim operation is `~/Documents/Mac-Mini-Backups-Interim/logs/backup_YYYYMMDD.log`, not `/tmp/pg_backup.log`. Runbook to be amended in a follow-up session. |
| `.env` has two operator-id variables with same value | Low | Both `OPERATOR_TELEGRAM_ID` and `TELEGRAM_OPERATOR_ID` exist in `.env` with identical values. Pick one canonical name (likely `OPERATOR_TELEGRAM_ID` since `telegram_bot.py` reads that one). Remove the other in a future session. |
| MacBook on battery overnight | Medium | If the Air ever runs on battery overnight, the 03:55 wake will not fire and the 04:00 launchd will be skipped. Telegram alert path will be silent because the script never ran. Operational practice: leave on AC overnight. Possible future enhancement: a separate "no backup landed in the last 30 hours" check (Phase 1.5 or Mac Studio day). |
| Backblaze B2 second destination (A4) | Medium | Unchanged — still open, still deferred to Mac Studio setup day. Today's work does not address destination diversity. |
| Encrypted backup before iCloud write | Medium | A1 remediation task (encrypt pg_dump output before iCloud) remains OPEN per ADR-039 §5.1.3. Deferred to Mac Studio setup day. |
| Full Disk Access scope review | Low | Current grant is broad (`/bin/bash` gets FDA). Mac Studio setup day reverts to a narrower grant model under the dev account. Track for that day's setup checklist. |
| Carried forward from Entry #012: all items unchanged | various | A6 closure complete; all prior open items still open. |

### What's Next

| Action | When |
|--------|------|
| Verify 01:00 ET federal_register scheduled run fired successfully | Tomorrow morning, May 18 |
| Verify 04:00 ET launchd-fired backup run fired successfully | Tomorrow morning, May 18 |
| Spot-check `~/Documents/Mac-Mini-Backups-Interim/dumps/` for the new dump file | Tomorrow morning |
| Spot-check `~/Documents/Mac-Mini-Backups-Interim/logs/backup_20260518.log` | Tomorrow morning |
| Delete `.bak.s22` backup file artifacts (Entry #011) | After Phase 9 verification |
| IR Runbook Scenario 2 amendment for interim log path | Follow-up session |
| Reconstruct missing migration_004.sql source file | Follow-up session |
| Amend ADR-038 §6 to reference ADR-039 §7.5 | Follow-up session |
| Capture ReportLab + Platypus PDF library decision | Follow-up session |
| Begin federal_policy_brief PDF library work | After H4 stability confirmed |
| Add scraper #2 (CMS) | Once federal_register has 7 days of clean scheduled runs |
| Mac Studio setup day: revert ADR-019 to canonical `dev` cron/launchd, remove interim subfolders, migrate any retained dumps to top-level Mac-Mini-Backups, narrow FDA grant scope | Mac Studio setup day |
---

## Entry #014 — May 17, 2026

**Operator:** Sheldon Wheeler

**Category:** Operational — Anthropic memory defect support ticket filed; follow-up decisions registered

**Commits:** (pending end-of-session push)

### Changes Made

1. **Anthropic support ticket filed for memory persistence defect.** Conversation ID `215474340039847` opened via Fin (Anthropic's frontline triage bot). Ticket documents that `memory_user_edits` tool reports successful in-session writes but writes do not propagate to fresh sessions on this account. Pattern has been observed for approximately 2 months, dating to mid-March 2026. Tonight's evidence: in one conversation Claude added memory entry #11 (OpenClaw no-shell-execution architectural rule) and edited entry #7 (session-closing ritual), tool calls reported success, then a fresh session opened immediately afterward returned a memory snapshot reflecting approximately mid-April 2026 state — neither change present. Ticket includes billing-impact section requesting credit for plan-overage charges attributable to context-rebuilding work caused by the defect, dating from mid-March 2026 through resolution.

2. **Reddit corroboration noted.** Multiple users reporting the same defect publicly. Reddit threads confirm this is not account-specific and not user error. Worth attaching as supplementary evidence if Anthropic support pushes back. Recommended action: if Fin (the support bot) attempts to close the ticket with FAQ-style suggestions, request human escalation explicitly using the phrase "please escalate this conversation to a human support agent."

3. **ADR-041 created as placeholder for third-party memory injection evaluation.** Status OPEN. Evaluates whether to install Claude-mem, Ember, or another MCP-based memory server as a replacement for Anthropic's broken memory feature. Decision deferred pending support response; backstop deadline 14 days from ticket filing (May 31, 2026) or earlier if Anthropic responds with a clear fix-or-no-fix outcome. See ADR_041.docx for evaluation criteria.

4. **OpenAI migration consideration logged as a single bullet in ADR-041 open items.** Not pursued as a separate analysis at this time per operator direction; placeholder only.

### Files Changed

| File | Action |
|------|--------|
| `~/openclaw/ADR_041.docx` | Created — third-party memory injection evaluation, Status OPEN |
| `~/openclaw/changelog.md` | Updated — this entry |

### ADRs Affected

| ADR | Relationship |
|-----|-------------|
| ADR-041 | Created. New OPEN sub-decision A6 follow-up, addresses the same defect that A6 was a partial governance-layer workaround for. |
| ADR-039 §5.6 (A6) | Tonight's events validate the original A6 finding. A6 is the governance-layer workaround for exactly this defect; if ADR-041 results in a technical replacement, A6 may be revisited (still load-bearing? superseded? both?). |

### NIST Controls Touched

None directly. Support-ticket filing and ADR placeholder do not change system posture. CM-3 (Configuration Change Control) noted because ADR-041 will trigger a configuration change if a memory tool is installed.

### Risk Assessment

No code changes. No schema changes. No egress changes (Anthropic support is an existing trust relationship). The new ADR is documentation only. Risk associated with potentially installing third-party memory tools (Claude-mem, Ember) is deferred to ADR-041's evaluation and explicitly listed there as a criterion (security posture review required before any install).

### Open Items Surfaced This Session

| Item | Severity | Notes |
|------|----------|-------|
| Anthropic support response on conversation 215474340039847 | High | Track response time. If Fin closes with FAQ, escalate to human. If no response in 7 days, follow up. If billing credit denied, document for the record. |
| Reddit thread links to attach to ticket | Low | Save URLs of representative Reddit threads about the same memory defect. Attach to support ticket as supplementary evidence in next exchange. |
| ADR-041 evaluation when triggered | Medium | Decision deadline: Anthropic response OR 14 days, whichever first. |
| Carried forward from Entry #013 | various | All items unchanged. |

### What's Next

| Action | When |
|--------|------|
| Verify 01:00 ET federal_register scheduled run | Tomorrow morning |
| Verify 04:00 ET launchd-fired backup run | Tomorrow morning |
| Watch for Anthropic email response on ticket 215474340039847 | Daily check next 7 days |
| Save Reddit thread URLs for ticket evidence | Next session |
| Begin ADR-041 evaluation if Anthropic response is "no fix" or no response by May 31 | Per ADR-041 |
| All Entry #013 next-steps unchanged | per Entry #013 |
