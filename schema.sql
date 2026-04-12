-- ============================================================================
-- OpenClaw Schema Patch — Fix agent_actions partition key + create remaining tables
-- Run after initial schema.sql partial success
-- ============================================================================

-- ============================================================================
-- 5. AGENT_ACTIONS (ADR-029 + ADR-035 §4.4, §9)
-- Fixed: PRIMARY KEY includes created_at for partitioning compatibility
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_actions (
    action_id               UUID DEFAULT gen_random_uuid(),
    session_id              UUID,
    persona                 TEXT NOT NULL,
    action_type             TEXT NOT NULL,
    tool_name               TEXT,
    model_tier              INTEGER,
    model_name              TEXT,
    routing_decision        TEXT,
    input_tokens            INTEGER,
    output_tokens           INTEGER,
    cost_usd                NUMERIC(10,6) DEFAULT 0,
    irreversibility_score   INTEGER,
    approval_required       BOOLEAN DEFAULT FALSE,
    approval_response       TEXT,
    validation_verdict      TEXT,
    prompt_injection_flag   BOOLEAN DEFAULT FALSE,
    gpu_memory_pressure     TEXT,
    m1_thermal_state        TEXT,
    circuit_breaker_hit     BOOLEAN DEFAULT FALSE,
    error_message           TEXT,
    context_trimmed         BOOLEAN DEFAULT FALSE,
    replay_buffer_flag      BOOLEAN DEFAULT FALSE,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at             TIMESTAMPTZ,
    PRIMARY KEY (action_id, created_at)
) PARTITION BY RANGE (created_at);

-- Initial partitions: April 2026 through July 2026
CREATE TABLE IF NOT EXISTS agent_actions_2026_04 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_05 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_06 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE IF NOT EXISTS agent_actions_2026_07 PARTITION OF agent_actions
    FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE INDEX IF NOT EXISTS idx_agent_actions_session ON agent_actions(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_actions_persona ON agent_actions(persona);
CREATE INDEX IF NOT EXISTS idx_agent_actions_created ON agent_actions(created_at);
CREATE INDEX IF NOT EXISTS idx_agent_actions_action_type ON agent_actions(action_type);

-- ============================================================================
-- 6. SESSION_TRANSCRIPTS (ADR-037 §5.1)
-- ============================================================================
CREATE TABLE IF NOT EXISTS session_transcripts (
    id                      SERIAL PRIMARY KEY,
    session_id              UUID UNIQUE NOT NULL,
    agent_id                VARCHAR NOT NULL,
    user_id                 VARCHAR,
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    user_input              TEXT,
    agent_reasoning         TEXT,
    final_output            TEXT,
    tokens_used             INTEGER,
    duration_seconds        INTEGER,
    status                  VARCHAR(20),
    markdown_file_path      VARCHAR,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transcripts_agent_ts ON session_transcripts(agent_id, timestamp);

-- ============================================================================
-- 7. AGENT_HEARTBEAT (ADR-037 §5.2)
-- ============================================================================
CREATE TABLE IF NOT EXISTS agent_heartbeat (
    id                      SERIAL PRIMARY KEY,
    agent_id                VARCHAR NOT NULL,
    job_id                  VARCHAR,
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    status                  VARCHAR(20),
    progress                TEXT,
    checkpoint              INTEGER,
    message                 TEXT,
    next_run_scheduled      TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_heartbeat_agent_ts ON agent_heartbeat(agent_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_heartbeat_job ON agent_heartbeat(job_id);

-- ============================================================================
-- 8. SERVICE_HEALTH (ADR-037 §5.3)
-- ============================================================================
CREATE TABLE IF NOT EXISTS service_health (
    id                      SERIAL PRIMARY KEY,
    service_name            VARCHAR NOT NULL,
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    is_healthy              BOOLEAN,
    response_time_ms        INTEGER,
    error_message           TEXT,
    action_taken            VARCHAR(50),
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_service_health_name_ts ON service_health(service_name, timestamp);

-- ============================================================================
-- 9. KNOWLEDGE_UPDATES (ADR-037 §5.4)
-- ============================================================================
CREATE TABLE IF NOT EXISTS knowledge_updates (
    id                      SERIAL PRIMARY KEY,
    agent_id                VARCHAR NOT NULL,
    session_id              UUID,
    timestamp               TIMESTAMPTZ DEFAULT NOW(),
    update_type             VARCHAR(20),
    content                 TEXT,
    markdown_file_updated   VARCHAR,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_knowledge_agent_ts ON knowledge_updates(agent_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_knowledge_type ON knowledge_updates(update_type);

-- ============================================================================
-- 10. HARDWARE_METRICS (ADR-034)
-- ============================================================================
CREATE TABLE IF NOT EXISTS hardware_metrics (
    id                      SERIAL PRIMARY KEY,
    timestamp               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cpu_percent_percore     JSONB,
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
    thermal_pressure        TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hw_metrics_ts ON hardware_metrics(timestamp);

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
-- SCHEMA VERSION
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_version (
    version         INTEGER PRIMARY KEY,
    description     TEXT NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_version (version, description) VALUES
    (1, 'Phase 1 initial schema: ADR-029 + ADR-034 + ADR-035 + ADR-037. April 12, 2026.')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- DONE — Patch complete
-- ============================================================================
