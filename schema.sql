-- =============================================================================
-- OpenClaw Schema — Option B (ADR-035 Core)
-- =============================================================================
-- Tables: sessions, session_budget, tool_registry, session_state, agent_actions
-- Deferred to Phase 1.5: workflow_runs, workflow_steps
--   Trigger: when first multi-step automated pipeline (e.g. federal_policy_brief
--   nightly ingest) is ready for production. Those tables track step-level
--   progress, crash resume points, and per-workflow token budgets.
--
-- session_id is UUID throughout. All foreign keys reference sessions.session_id.
-- agent_actions is partitioned by month on created_at (ADR-035 Section 9).
-- Run under dev account against openclaw database.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- 1. sessions — core session tracking with trust tier (ADR-016, ADR-035 §6)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sessions (
    session_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona                 TEXT NOT NULL CHECK (persona IN ('prototype', 'automate', 'research')),
    trust_tier              INTEGER NOT NULL DEFAULT 2 CHECK (trust_tier BETWEEN 1 AND 4),
    trust_tier_reason       TEXT,
    tier_elevation_requested BOOLEAN NOT NULL DEFAULT FALSE,
    operator_id             BIGINT NOT NULL,
    chat_id                 BIGINT NOT NULL,
    initiated_by            TEXT NOT NULL DEFAULT 'operator_telegram',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_active_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_chat_id ON sessions (chat_id);
CREATE INDEX IF NOT EXISTS idx_sessions_persona ON sessions (persona);

-- ---------------------------------------------------------------------------
-- 2. session_budget — per-session token budget tracking (ADR-035 §4)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_budget (
    session_id              UUID PRIMARY KEY REFERENCES sessions(session_id),
    persona                 TEXT NOT NULL CHECK (persona IN ('prototype', 'automate', 'research')),
    budget_ceiling_tokens   INTEGER NOT NULL DEFAULT 50000,
    input_tokens_consumed   INTEGER NOT NULL DEFAULT 0,
    output_tokens_consumed  INTEGER NOT NULL DEFAULT 0,
    total_tokens_consumed   INTEGER GENERATED ALWAYS AS (input_tokens_consumed + output_tokens_consumed) STORED,
    cost_usd                NUMERIC(10,6) NOT NULL DEFAULT 0,
    escalation_triggered    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- 3. tool_registry — metadata-first tool definitions (ADR-035 §5)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tool_registry (
    tool_name                   TEXT PRIMARY KEY,
    description                 TEXT NOT NULL,
    permitted_personas          TEXT[] NOT NULL,
    risk_level                  TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    irreversibility_score       INTEGER NOT NULL CHECK (irreversibility_score BETWEEN 0 AND 100),
    min_trust_tier              INTEGER NOT NULL DEFAULT 1 CHECK (min_trust_tier BETWEEN 1 AND 4),
    requires_approval           BOOLEAN NOT NULL DEFAULT FALSE,
    permitted_network_destinations TEXT[],
    max_calls_per_session       INTEGER,
    input_schema                JSONB,
    output_schema               JSONB,
    phase_available             TEXT NOT NULL DEFAULT 'phase1',
    enabled                     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_reviewed_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_tool_registry_enabled ON tool_registry (enabled) WHERE enabled = TRUE;

-- ---------------------------------------------------------------------------
-- 4. session_state — crash recovery with heartbeat (ADR-035 §7)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_state (
    session_id              UUID PRIMARY KEY REFERENCES sessions(session_id),
    persona                 TEXT NOT NULL CHECK (persona IN ('prototype', 'automate', 'research')),
    workflow_id             UUID,
    trust_tier              INTEGER NOT NULL,
    current_step            TEXT,
    completed_steps         JSONB NOT NULL DEFAULT '[]',
    pending_steps           JSONB NOT NULL DEFAULT '[]',
    inputs                  JSONB,
    partial_outputs         JSONB NOT NULL DEFAULT '{}',
    status                  TEXT NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'completed', 'crashed', 'recovered', 'cancelled')),
    failure_reason          TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at            TIMESTAMPTZ
);

-- Note: workflow_id FK to workflow_runs deferred to Phase 1.5.
-- When workflow_runs table is created, add:
--   ALTER TABLE session_state
--     ADD CONSTRAINT fk_session_state_workflow
--     FOREIGN KEY (workflow_id) REFERENCES workflow_runs(workflow_id);

CREATE INDEX IF NOT EXISTS idx_session_state_status ON session_state (status) WHERE status = 'active';

-- ---------------------------------------------------------------------------
-- 5. agent_actions — partitioned audit table (ADR-029, amended by ADR-035 §4,§9)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS agent_actions (
    action_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id              UUID NOT NULL,
    persona                 TEXT NOT NULL CHECK (persona IN ('prototype', 'automate', 'research')),
    trust_tier              INTEGER NOT NULL,
    action_type             TEXT NOT NULL DEFAULT 'tool_call',
    tool_name               TEXT,
    operator_telegram_id    BIGINT NOT NULL,
    raw_input               TEXT NOT NULL,
    routing                 TEXT NOT NULL,
    model_used              TEXT NOT NULL,
    input_tokens            INTEGER NOT NULL DEFAULT 0,
    output_tokens           INTEGER NOT NULL DEFAULT 0,
    cost_usd                NUMERIC(10,6) NOT NULL DEFAULT 0,
    response_text           TEXT NOT NULL DEFAULT '',
    validation_verdict      TEXT,
    irreversibility_score   INTEGER,
    approval_status         TEXT,
    error                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
) PARTITION BY RANGE (created_at);

-- Initial partitions — extend monthly via maintenance job
CREATE TABLE IF NOT EXISTS agent_actions_2026_04 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_05 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_06 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');

CREATE INDEX IF NOT EXISTS idx_agent_actions_session ON agent_actions (session_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_created ON agent_actions (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_actions_persona ON agent_actions (persona);

-- =============================================================================
-- PHASE 1.5 — Deferred Tables (workflow_runs, workflow_steps)
-- =============================================================================
-- Add these tables when the first multi-step automated pipeline is ready:
--   - federal_policy_brief nightly ingest (scrape → dedupe → chunk → embed → generate → send)
--   - Any Automate persona job with >3 sequential dependent steps
--   - Any job requiring crash-resume at step granularity
--
-- Until then, session_state.completed_steps JSONB tracks step progress
-- for simple sequences. The workflow tables add:
--   - Per-workflow token budgets spanning multiple sessions
--   - Step-level Telegram notifications
--   - Formal step sequencing with dependency tracking
--   - Workflow-level success rate metrics (ADR-033 dashboard)
--
-- Schema definitions are in ADR-035 Sections 8.2 and 8.3.
-- When ready, also add FK from session_state.workflow_id → workflow_runs.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Monthly partition maintenance (run via cron under dev account)
-- ---------------------------------------------------------------------------
-- To create next month's partition:
--   CREATE TABLE agent_actions_YYYY_MM PARTITION OF agent_actions
--     FOR VALUES FROM ('YYYY-MM-01') TO ('YYYY-{MM+1}-01');
--
-- To enforce 90-day retention (ADR-029):
--   DROP TABLE IF EXISTS agent_actions_<month_91_days_ago>;
--
-- The nightly pg_dump (ADR-019) includes all partitions automatically.
-- =============================================================================
