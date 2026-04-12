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
