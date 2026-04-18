-- ============================================================================
-- Migration 002 — Align sessions table with schema.sql
-- ============================================================================
-- Date: April 18, 2026
-- Changelog: Entry #003
--
-- The running sessions table was created from an earlier schema version.
-- schema.sql was updated separately. This migration brings the running
-- table in line with the canonical schema.sql definition.
--
-- Adds: status, started_at, ended_at, model_tier
-- Keeps: operator_id, initiated_by, last_active_at (used by running code)
-- Backfills: status = 'active' for all existing rows
-- Creates: idx_sessions_status, idx_sessions_started (from schema.sql)
--
-- Run as: psql -U openclaw -d openclaw -f migration_002.sql
-- ============================================================================

-- ── Step 1: Add missing columns ──────────────────────────────────────

ALTER TABLE sessions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS model_tier INTEGER NOT NULL DEFAULT 2;

-- ── Step 2: Backfill started_at from created_at ─────────────────────

UPDATE sessions
SET started_at = created_at
WHERE started_at IS NULL;

-- ── Step 3: Add NOT NULL constraint to started_at after backfill ─────

ALTER TABLE sessions ALTER COLUMN started_at SET NOT NULL;
ALTER TABLE sessions ALTER COLUMN started_at SET DEFAULT NOW();

-- ── Step 4: Create indexes from schema.sql ──────────────────────────

CREATE INDEX IF NOT EXISTS idx_sessions_status
    ON sessions(status) WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_sessions_started
    ON sessions(started_at);

-- ── Step 5: Record migration ────────────────────────────────────────

INSERT INTO schema_version (version, description) VALUES
    (3, 'Migration 002: sessions table aligned — added status, started_at, ended_at, model_tier. April 18, 2026.')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- VERIFICATION QUERIES (run manually after migration)
-- ============================================================================
-- Check columns exist:
--   \d sessions
--
-- Check backfill:
--   SELECT count(*) FROM sessions WHERE started_at IS NULL;
--   (expect 0)
--
-- Check index:
--   SELECT indexname FROM pg_indexes WHERE tablename = 'sessions';
--   (expect idx_sessions_status and idx_sessions_started)
--
-- Check row count unchanged:
--   SELECT count(*) FROM sessions;
-- ============================================================================
