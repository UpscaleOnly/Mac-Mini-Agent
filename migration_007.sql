-- ============================================================================
-- Migration 007 — agent_actions partitions (ADR-046 F7 remediation)
-- ============================================================================
-- Date: September 29, 2026
-- Changelog: Entry #045
-- ADR: ADR-046 Finding F7 (HIGH); ADR-029 / ADR-035 §4.4 (audit record on
--      every request)
--
-- agent_actions is range-partitioned on created_at. schema.sql created
-- partitions for April–July 2026 only, with no DEFAULT partition and no job
-- that creates new ones. From 2026-08-01 every INSERT failed with
-- "no partition of relation agent_actions found for row" — and because
-- app/audit.py write_action() is unguarded and /agent returns only after it,
-- every /agent request failed after its LLM call.
--
-- This migration:
--   1. Adds monthly partitions for August 2026 through December 2027.
--   2. Adds a DEFAULT partition so a missing month can never again break
--      audit writes. Rows landing there are a signal that monthly
--      partitions have run out — see the verification query below.
--
-- Caveat for whoever adds 2028 partitions: PostgreSQL refuses to attach a
-- new range partition if the DEFAULT partition already holds rows in that
-- range. Check agent_actions_default first; move any such rows out before
-- creating the partition.
--
-- Run in a single transaction:
--   docker exec -i openclaw_postgres psql -U openclaw -d openclaw -1 -v ON_ERROR_STOP=1 < migration_007.sql
--
-- Pre-migration state:  schema_version = 7
-- Post-migration state: schema_version = 8
-- ============================================================================

-- ── Step 1: Monthly partitions, 2026-08 through 2027-12 ──────────────────

DO $$
DECLARE
    m DATE := DATE '2026-08-01';
BEGIN
    WHILE m < DATE '2028-01-01' LOOP
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF agent_actions '
            'FOR VALUES FROM (%L) TO (%L)',
            'agent_actions_' || to_char(m, 'YYYY_MM'),
            m, (m + INTERVAL '1 month')::date
        );
        m := (m + INTERVAL '1 month')::date;
    END LOOP;
END $$;

-- ── Step 2: DEFAULT partition — the safety net ───────────────────────────

CREATE TABLE IF NOT EXISTS agent_actions_default PARTITION OF agent_actions DEFAULT;

COMMENT ON TABLE agent_actions_default IS
    'Safety net (migration 007, ADR-046 F7). Any row here means a monthly '
    'partition is missing. Must be empty of a range before that range''s '
    'monthly partition can be created.';

-- ── Step 3: Record migration ─────────────────────────────────────────────

INSERT INTO schema_version (version, description) VALUES
    (8, 'Migration 007: agent_actions partitions 2026-08..2027-12 plus DEFAULT partition. ADR-046 F7. September 29, 2026.');

-- ============================================================================
-- Verification (run after applying)
--
-- 1. An insert dated now succeeds (rolled back — writes nothing):
--      BEGIN;
--      INSERT INTO agent_actions (action_id, persona, action_type, created_at)
--        SELECT gen_random_uuid(), persona, action_type, now() FROM agent_actions LIMIT 1;
--      ROLLBACK;
--
-- 2. Partition count and version:
--      SELECT count(*) FROM pg_inherits WHERE inhparent = 'agent_actions'::regclass;
--      (expect 22 = 4 original + 17 monthly + 1 default)
--      SELECT max(version) FROM schema_version;   (expect 8)
--
-- 3. Ongoing health check — should always be 0:
--      SELECT count(*) FROM agent_actions_default;
-- ============================================================================
