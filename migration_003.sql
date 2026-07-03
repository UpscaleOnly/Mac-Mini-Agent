-- migration_003.sql — ADR-038 Security Event Detection and Alerting
-- Adds security_events table and supporting indexes.
-- Run once against the live database:
--   docker exec -i openclaw_postgres psql -U openclaw -d openclaw < migration_003.sql
-- schema.sql is the single source of truth — this migration and schema.sql
-- must remain in sync.

CREATE TABLE IF NOT EXISTS security_events (
    event_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type        TEXT NOT NULL,
    severity          TEXT NOT NULL DEFAULT 'medium',
    source            TEXT NOT NULL DEFAULT 'interceptor',
    persona           TEXT,
    session_id        UUID REFERENCES sessions(session_id) ON DELETE SET NULL,
    channel           TEXT,
    channel_id        TEXT,
    user_id           TEXT,
    input_snippet     TEXT,
    pattern_matched   TEXT,
    action_taken      TEXT NOT NULL DEFAULT 'flagged',
    alert_sent        BOOLEAN NOT NULL DEFAULT FALSE,
    raw_detail        JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_security_events_type
    ON security_events(event_type);

CREATE INDEX IF NOT EXISTS idx_security_events_created
    ON security_events(created_at);

CREATE INDEX IF NOT EXISTS idx_security_events_severity
    ON security_events(severity) WHERE severity IN ('high', 'critical');
