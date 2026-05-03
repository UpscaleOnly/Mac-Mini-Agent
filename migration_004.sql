-- ============================================================================
-- Migration 004 — Widen security_events.source CHECK constraint
-- ============================================================================
-- Date: May 3, 2026
-- Changelog: Entry #00X (Session 20)
--
-- ADR-038 §6 specifies that unauthorized_user events are detected and written
-- to security_events from main.py's identity check. The closure code in
-- main.py (commit dfd103e) writes source='main_identity_check', but the
-- existing CHECK constraint allows only ('interceptor', 'ssh_forwarder').
-- INSERTs from main.py were rejected; the row never landed even though the
-- 403 response and Telegram alert fired correctly.
--
-- This migration drops and recreates the CHECK constraint with the new
-- source value added. No data changes; constraint widening only.
--
-- Schema version: 4 → 5
--
-- Run as:
--   docker cp migration_004.sql openclaw_postgres:/tmp/migration_004.sql
--   docker exec openclaw_postgres psql -U openclaw -d openclaw \
--     -f /tmp/migration_004.sql
-- ============================================================================

BEGIN;

-- ── Step 1: Drop the existing CHECK constraint ──────────────────────

ALTER TABLE security_events
    DROP CONSTRAINT IF EXISTS security_events_source_check;

-- ── Step 2: Recreate with widened whitelist ─────────────────────────

ALTER TABLE security_events
    ADD CONSTRAINT security_events_source_check CHECK (
        source = ANY (ARRAY[
            'interceptor',
            'ssh_forwarder',
            'main_identity_check'
        ])
    );

-- ── Step 3: Record migration ────────────────────────────────────────

INSERT INTO schema_version (version, description) VALUES
    (5, 'Migration 004: security_events.source CHECK widened to include main_identity_check. ADR-038 §6 closure. May 3, 2026.')
ON CONFLICT (version) DO NOTHING;

COMMIT;

-- ============================================================================
-- VERIFICATION QUERIES (run manually after migration)
-- ============================================================================
-- Check constraint definition:
--   SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
--    WHERE conname = 'security_events_source_check';
--   (expect: source = ANY (ARRAY['interceptor'::text, 'ssh_forwarder'::text,
--                                'main_identity_check'::text]))
--
-- Check schema version:
--   SELECT MAX(version) FROM schema_version;
--   (expect 5)
--
-- Check version 5 row was inserted:
--   SELECT version, description FROM schema_version ORDER BY version DESC LIMIT 1;
--
-- After this migration, the test from Step 6 of unauth_application_steps.md
-- should produce a security_events row with source='main_identity_check'.
-- ============================================================================
