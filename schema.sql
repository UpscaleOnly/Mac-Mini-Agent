-- ============================================================================
-- OpenClaw Agent Server — Complete PostgreSQL Schema
-- ============================================================================
-- ADR-029: agent_actions (partitioned, with input_tokens/output_tokens per ADR-035)
-- ADR-035: sessions, session_budget, tool_registry, session_state
-- ADR-037: session_transcripts, agent_heartbeat, service_health, knowledge_updates
-- ADR-034: hardware_metrics + hardware_alerts view
-- ADR-038: security_events
--
-- Phase 1.5 (deferred): workflow_runs, workflow_steps, ssh_forwarder
--
-- Run as: psql -U openclaw -d openclaw -f schema.sql
-- Account: dev
-- Date: April 12, 2026
-- Updated: April 13, 2026 — channel-agnostic sessions (Entry #002)
-- Updated: April 18, 2026 — sessions table aligned with running DB (Entry #003)
-- Updated: April 19, 2026 — schema_version seeding replaced with single authoritative stamp
-- ============================================================================

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================================
-- 1. SESSIONS (ADR-035 §6.4)
-- Core session tracking with trust tier assignment
-- ============================================================================
CREATE TABLE IF NOT EXISTS sessions (
    session_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona                 TEXT NOT NULL,                           -- prototype / automate / research
    channel                 TEXT NOT NULL DEFAULT 'telegram',        -- telegram / cli / web / internal
    channel_id              TEXT NOT NULL,                           -- Channel-specific conversation ID
    operator_id             BIGINT NOT NULL,                        -- Telegram operator ID for verification
    initiated_by            TEXT NOT NULL DEFAULT 'operator',        -- operator / automate_scheduler / system
    trust_tier              INTEGER NOT NULL DEFAULT 2,              -- ADR-035 §6: 1=read-only, 2=low-risk, 3=operator-approved, 4=manual-gate
    trust_tier_reason       TEXT,                                    -- Plain-language reason for tier assignment
    tier_elevation_requested BOOLEAN NOT NULL DEFAULT FALSE,         -- Pending operator Telegram approval
    model_tier              INTEGER NOT NULL DEFAULT 2,              -- ADR-021: 1=7B, 2=14B, 3=32B, 4=Opus
    status                  TEXT NOT NULL DEFAULT 'active',          -- active / completed / failed / timeout
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at                TIMESTAMPTZ,
    last_active_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT sessions_persona_check CHECK (
        persona = ANY (ARRAY['prototype', 'automate', 'research'])
    ),
    CONSTRAINT sessions_channel_check CHECK (
        channel = ANY (ARRAY['telegram', 'cli', 'web', 'internal'])
    ),
    CONSTRAINT sessions_trust_tier_check CHECK (
        trust_tier >= 1 AND trust_tier <= 4
    )
);

CREATE INDEX IF NOT EXISTS idx_sessions_persona ON sessions(persona);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_channel_id ON sessions(channel_id);

-- ============================================================================
-- 2. SESSION_BUDGET (ADR-035 §4.3)
-- Per-session token budget tracking with ceiling enforcement
-- ============================================================================
CREATE TABLE IF NOT EXISTS session_budget (
    session_id              UUID PRIMARY KEY REFERENCES sessions(session_id),
    persona                 TEXT NOT NULL,
    budget_ceiling_tokens   INTEGER NOT NULL DEFAULT 50000,          -- Hard ceiling. Operator sets at session creation.
    input_tokens_consumed   INTEGER NOT NULL DEFAULT 0,              -- Running total of prompt/context tokens
    output_tokens_consumed  INTEGER NOT NULL DEFAULT 0,              -- Running total of completion tokens
    total_tokens_consumed   INTEGER GENERATED ALWAYS AS
                            (input_tokens_consumed + output_tokens_consumed) STORED,
    cost_usd                NUMERIC(10,6) NOT NULL DEFAULT 0,        -- Running dollar cost
    escalation_triggered    BOOLEAN NOT NULL DEFAULT FALSE,          -- Set true when cost_usd crosses $1.00
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- 3. TOOL_REGISTRY (ADR-035 §5.3)
-- Metadata-first tool definitions — data-layer security boundary
-- ============================================================================
CREATE TABLE IF NOT EXISTS tool_registry (
    tool_name                   TEXT PRIMARY KEY,
    description                 TEXT NOT NULL,
    permitted_personas          TEXT[] NOT NULL,                      -- ARRAY['prototype','research']
    risk_level                  TEXT NOT NULL,                        -- low / medium / high / critical
    irreversibility_score       INTEGER NOT NULL,                     -- 0-100, maps to ADR-018
    min_trust_tier              INTEGER NOT NULL DEFAULT 1,           -- Minimum session trust tier required
    requires_approval           BOOLEAN NOT NULL DEFAULT FALSE,       -- Every invocation needs Telegram Y/N
    permitted_network_destinations TEXT[],                            -- Subset of ADR-030 persona network policy
    max_calls_per_session       INTEGER,                              -- NULL = unlimited within budget
    input_schema                JSONB,                                -- Expected input parameter shape
    output_schema               JSONB,                                -- Expected return shape (ADR-022)
    phase_available             TEXT NOT NULL DEFAULT 'phase1',       -- phase1 / phase1.5 / phase2
    enabled                     BOOLEAN NOT NULL DEFAULT FALSE,       -- Master switch. FALSE = invisible to agent.
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_reviewed_at            TIMESTAMPTZ                           -- ADR-031: >90 days stale = review trigger
);

CREATE INDEX IF NOT EXISTS idx_tool_registry_enabled ON tool_registry(enabled) WHERE enabled = TRUE;

-- ============================================================================
-- 4. SESSION_STATE (ADR-035 §7.3)
-- Crash recovery with 30-second heartbeat
-- ============================================================================
CREATE TABLE IF NOT EXISTS session_state (
    session_id              UUID PRIMARY KEY REFERENCES sessions(session_id),
    persona                 TEXT NOT NULL,
    workflow_id             UUID,                                    -- NULL for interactive sessions
    trust_tier              INTEGER NOT NULL,                        -- Mirrors sessions.trust_tier
    current_step            TEXT,                                    -- Step currently executing. NULL if between steps.
    completed_steps         JSONB NOT NULL DEFAULT '[]'::jsonb,      -- Ordered array of completed step names
    pending_steps           JSONB NOT NULL DEFAULT '[]'::jsonb,      -- Ordered array of remaining step names
    inputs                  JSONB,                                   -- Session input parameters for exact replay
    partial_outputs         JSONB NOT NULL DEFAULT '{}'::jsonb,      -- Intermediate outputs keyed by step name
    status                  TEXT NOT NULL DEFAULT 'active',          -- active / completed / crashed / recovered / cancelled
    failure_reason          TEXT,                                    -- Populated on crash or cancellation
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_heartbeat          TIMESTAMPTZ NOT NULL DEFAULT NOW(),      -- Updated every 30 seconds by runtime
    completed_at            TIMESTAMPTZ                              -- Populated on terminal status
);

CREATE INDEX IF NOT EXISTS idx_session_state_status ON session_state(status) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_session_state_heartbeat ON session_state(last_heartbeat) WHERE status = 'active';

-- ============================================================================
-- 5. AGENT_ACTIONS (ADR-029 + ADR-035 §4.4, §9)
-- Partitioned audit table with input/output token split
-- 21 original columns + 2 new (input_tokens, output_tokens)
-- Partitioned by month on created_at
-- NOTE: PRIMARY KEY includes created_at — required by PostgreSQL for
--       partitioned tables. action_id UUID remains unique in practice.
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_actions (
    action_id               UUID DEFAULT gen_random_uuid(),
    session_id              UUID,                                    -- References sessions(session_id)
    persona                 TEXT NOT NULL,                           -- prototype / automate / research
    action_type             TEXT NOT NULL,                           -- tool_call / llm_request / approval_request / trust_tier_elevation_request
    tool_name               TEXT,                                    -- Tool invoked (NULL for direct LLM calls)
    model_tier              INTEGER,                                 -- ADR-021 tier used for this action
    model_name              TEXT,                                    -- e.g. 'mistral-nemo-14b', 'claude-sonnet'
    routing_decision        TEXT,                                    -- local / cloud / escalated
    input_tokens            INTEGER,                                 -- ADR-035: tokens in prompt + context
    output_tokens           INTEGER,                                 -- ADR-035: tokens in model completion
    cost_usd                NUMERIC(10,6) DEFAULT 0,                 -- Per-action cost
    irreversibility_score   INTEGER,                                 -- ADR-018 score for this action
    approval_required       BOOLEAN DEFAULT FALSE,                   -- Did this action require Telegram approval?
    approval_response       TEXT,                                    -- approved / denied / timeout / auto_no
    validation_verdict      TEXT,                                    -- pass / fail / skip
    prompt_injection_flag   BOOLEAN DEFAULT FALSE,                   -- ADR-022 injection detection
    gpu_memory_pressure     TEXT,                                    -- nominal / warning / critical
    m1_thermal_state        TEXT,                                    -- nominal / fair / serious / critical
    circuit_breaker_hit     BOOLEAN DEFAULT FALSE,                   -- ADR-027 circuit breaker triggered
    error_message           TEXT,                                    -- Error details if action failed
    context_trimmed         BOOLEAN DEFAULT FALSE,                   -- ADR-027 context trim applied
    replay_buffer_flag      BOOLEAN DEFAULT FALSE,                   -- Written to replay buffer
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at             TIMESTAMPTZ,                             -- When action completed/resolved
    PRIMARY KEY (action_id, created_at)
) PARTITION BY RANGE (created_at);

-- Initial partitions: April 2026 through July 2026 (4 months)
CREATE TABLE IF NOT EXISTS agent_actions_2026_04 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_05 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_06 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_07 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

-- Indexes on partitioned table (created on each partition automatically)
CREATE INDEX IF NOT EXISTS idx_agent_actions_session ON agent_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_persona ON agent_actions(persona);
CREATE INDEX IF NOT EXISTS idx_agent_actions_created ON agent_actions(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_actions_action_type ON agent_actions(action_type);

-- ============================================================================
-- 6. SESSION_TRANSCRIPTS (ADR-037 §5.1)
-- Full session capture for knowledge extraction
-- ============================================================================
CREATE TABLE IF NOT EXISTS session_transcripts (
    id                      SERIAL PRIMARY KEY,
    session_id              UUID UNIQUE NOT NULL,
    agent_id                VARCHAR NOT NULL,                        -- prototype / automate / research
    user_id                 VARCHAR,
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    user_input              TEXT,
    agent_reasoning         TEXT,
    final_output            TEXT,
    tokens_used             INTEGER,
    duration_seconds        INTEGER,
    status                  VARCHAR(20),                             -- completed / failed / timeout
    markdown_file_path      VARCHAR,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcripts_agent_ts ON session_transcripts(agent_id, timestamp);

-- ============================================================================
-- 7. AGENT_HEARTBEAT (ADR-037 §5.2)
-- Heartbeat during long-running tasks
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_heartbeat (
    id                      SERIAL PRIMARY KEY,
    agent_id                VARCHAR NOT NULL,
    job_id                  VARCHAR,
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    status                  VARCHAR(20),                             -- running / paused / completed / failed
    progress                TEXT,                                    -- e.g. 'Page 847 of 1000'
    checkpoint              INTEGER,                                 -- Numerical progress marker
    message                 TEXT,
    next_run_scheduled      TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_agent_ts ON agent_heartbeat(agent_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_heartbeat_job ON agent_heartbeat(job_id);

-- ============================================================================
-- 8. SERVICE_HEALTH (ADR-037 §5.3)
-- Infrastructure health checks
-- ============================================================================
CREATE TABLE IF NOT EXISTS service_health (
    id                      SERIAL PRIMARY KEY,
    service_name            VARCHAR NOT NULL,                        -- postgresql / ollama / chromadb / telegram
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    is_healthy              BOOLEAN,
    response_time_ms        INTEGER,
    error_message           TEXT,
    action_taken            VARCHAR(50),                             -- none / restart / alert
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_health_name_ts ON service_health(service_name, timestamp);

-- ============================================================================
-- 9. KNOWLEDGE_UPDATES (ADR-037 §5.4)
-- Knowledge extraction log
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge_updates (
    id                      SERIAL PRIMARY KEY,
    agent_id                VARCHAR NOT NULL,
    session_id              UUID,
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    update_type             VARCHAR(20),                             -- decision / code / fact / insight
    content                 TEXT,
    markdown_file_updated   VARCHAR,                                 -- DECISIONS.md / CODE_REFERENCE.md / etc.
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_agent_ts ON knowledge_updates(agent_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_updates(update_type);

-- ============================================================================
-- 10. HARDWARE_METRICS (ADR-034)
-- Hardware telemetry from hw_collector.py
-- ============================================================================
CREATE TABLE IF NOT EXISTS hardware_metrics (
    id                      SERIAL PRIMARY KEY,
    timestamp               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cpu_percent_percore     JSONB,                                   -- Per-core utilization array
    cpu_percent_total       REAL,
    gpu_percent_total       REAL,
    gpu_freq_mhz           INTEGER,
    ane_power_mw            REAL,
    cpu_temp_c              REAL,
    gpu_temp_c              REAL,
    fan_rpm                 INTEGER,
    system_power_w          REAL,
    mem_total_gb            REAL,
    mem_used_gb             REAL,
    mem_free_gb             REAL,
    mem_swap_used_gb        REAL,
    thermal_pressure        TEXT,                                    -- nominal / fair / serious / critical
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hw_metrics_ts ON hardware_metrics(timestamp);

-- Hardware alerts view (ADR-034, feeds Phase 2 compliance_monitor)
CREATE OR REPLACE VIEW hardware_alerts AS
SELECT *
FROM hardware_metrics
WHERE thermal_pressure IN ('serious', 'critical')
   OR mem_swap_used_gb > 0
   OR mem_used_gb > (mem_total_gb * 0.93)
   OR cpu_temp_c > 95
   OR gpu_temp_c > 95
ORDER BY timestamp DESC;

-- ============================================================================
-- 11. SECURITY_EVENTS (ADR-038)
-- Application-layer threat detection and SSH authentication events
-- Sources: interceptor pattern scanner (Phase 1), SSH log forwarder (Phase 1.5)
-- ============================================================================
CREATE TABLE IF NOT EXISTS security_events (
    event_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type        TEXT NOT NULL,                   -- injection / suspicious_input / persona_override /
                                                       -- encoding_attack / shell_injection / abnormal_length /
                                                       -- brute_force / unauthorized_user /
                                                       -- ssh_failure / ssh_success / ssh_key_rejected
    severity          TEXT NOT NULL DEFAULT 'medium',  -- low / medium / high / critical
    source            TEXT NOT NULL DEFAULT 'interceptor', -- interceptor / ssh_forwarder
    persona           TEXT,                            -- NULL for SSH events
    session_id        UUID REFERENCES sessions(session_id) ON DELETE SET NULL,
    channel           TEXT,                            -- NULL for SSH events
    channel_id        TEXT,                            -- NULL for SSH events
    user_id           TEXT,                            -- NULL for SSH events
    input_snippet     TEXT,                            -- First 200 chars of triggering input. NULL for SSH.
    pattern_matched   TEXT,                            -- Specific pattern or rule that matched
    action_taken      TEXT NOT NULL DEFAULT 'flagged', -- flagged / blocked
    alert_sent        BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE if real-time Telegram alert was sent
    raw_detail        JSONB,                           -- Additional context. SSH: host, port, source IP.
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT security_events_severity_check CHECK (
        severity = ANY (ARRAY['low', 'medium', 'high', 'critical'])
    ),
    CONSTRAINT security_events_source_check CHECK (
        source = ANY (ARRAY['interceptor', 'ssh_forwarder'])
    ),
    CONSTRAINT security_events_action_check CHECK (
        action_taken = ANY (ARRAY['flagged', 'blocked'])
    )
);

CREATE INDEX IF NOT EXISTS idx_security_events_type
    ON security_events(event_type);

CREATE INDEX IF NOT EXISTS idx_security_events_created
    ON security_events(created_at);

CREATE INDEX IF NOT EXISTS idx_security_events_severity
    ON security_events(severity) WHERE severity IN ('high', 'critical');

CREATE INDEX IF NOT EXISTS idx_security_events_session
    ON security_events(session_id) WHERE session_id IS NOT NULL;

-- ============================================================================
-- SCHEMA VERSION TRACKING
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version         INTEGER PRIMARY KEY,
    description     TEXT NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Single authoritative version stamp for fresh installs.
-- schema.sql only runs on an empty database — this table was just created
-- above and is guaranteed empty. No conflict handling needed.
-- MUST match REQUIRED_SCHEMA_VERSION in app/db.py.
INSERT INTO schema_version (version, description) VALUES
    (4, 'Baseline schema — April 19, 2026. Includes ADR-029, ADR-034, ADR-035, ADR-037, ADR-038.');

-- ============================================================================
-- DONE
-- Tables created: 11 + 1 view + 1 version tracker
--   ADR-035: sessions, session_budget, tool_registry, session_state
--   ADR-029/035: agent_actions (partitioned, 4 initial monthly partitions)
--   ADR-037: session_transcripts, agent_heartbeat, service_health, knowledge_updates
--   ADR-034: hardware_metrics + hardware_alerts view
--   ADR-038: security_events
--   Meta: schema_version
--
-- Phase 1.5 deferred: workflow_runs, workflow_steps (ADR-035 §8)
-- Phase 1.5 deferred: ssh_forwarder — writes to security_events from Mac host
-- ============================================================================
