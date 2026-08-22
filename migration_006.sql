-- ============================================================================
-- Migration 006 — brief_runs table (send-to-inbox audit trail)
-- ============================================================================
-- Date: August 22, 2026
-- Changelog: Entry #022 (pending)
-- ADR: ADR-039 H4 remediation — send-to-inbox delivery mechanism
--
-- generate_brief_review.py v5 adds a --send flag that emails the generated
-- brief via authenticated SMTP (self-send to the operator's own iCloud
-- inbox — see ADR-039 H4 sub-decision, August 22, 2026: no ESP or purchased
-- sender domain needed while the only recipient is the operator).
--
-- This migration adds one table: brief_runs. One row is written per --send
-- invocation (never for review-only runs, which remain side-effect-free).
-- It records what was sent, whether verification was clean, and whether the
-- SMTP send itself succeeded — the audit trail that lets HARD_FAIL_ON_UNVERIFIED
-- eventually flip to True with confidence.
--
-- Pre-migration state: schema_version = 6
-- Post-migration state: schema_version = 7
--
-- Run as: psql -U openclaw -d openclaw -f migration_006.sql
-- ============================================================================

-- ── Step 1: Create brief_runs table ──────────────────────────────────

CREATE TABLE IF NOT EXISTS brief_runs (
    id                      SERIAL PRIMARY KEY,
    project                 VARCHAR(64) NOT NULL,
    run_timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    date_range_start        DATE NOT NULL,
    date_range_end          DATE NOT NULL,
    doc_count               INTEGER NOT NULL DEFAULT 0,
    claim_warning_count     INTEGER NOT NULL DEFAULT 0,
    verification_status     VARCHAR(20) NOT NULL,
    send_status             VARCHAR(20) NOT NULL,
    recipient               VARCHAR(255),
    error_message           TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT brief_runs_verification_status_check
        CHECK (verification_status IN ('clean', 'warnings')),
    CONSTRAINT brief_runs_send_status_check
        CHECK (send_status IN ('sent', 'failed', 'skipped_unverified'))
);

CREATE INDEX IF NOT EXISTS idx_brief_runs_project_timestamp
    ON brief_runs(project, run_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_brief_runs_send_status
    ON brief_runs(send_status);

COMMENT ON TABLE brief_runs IS
    'One row per generate_brief_review.py --send invocation. Review-only runs '
    '(no --send) never write here. Populated by record_brief_run() in '
    'generate_brief_review.py.';

-- ── Step 2: Record migration ─────────────────────────────────────────

INSERT INTO schema_version (version, description) VALUES
    (7, 'Migration 006: brief_runs table created. ADR-039 H4 send-to-inbox audit trail. August 22, 2026.')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- VERIFICATION QUERIES (run manually after migration)
-- ============================================================================
-- 1. Confirm new table exists:
--      \dt brief_runs
--
-- 2. Confirm schema version:
--      SELECT version, description FROM schema_version ORDER BY version DESC LIMIT 1;
--      (expect version = 7)
--
-- 3. Confirm zero impact on existing data:
--      SELECT count(*) FROM scraped_content;
--      SELECT count(*) FROM scraper_runs;
--      (expect unchanged from pre-migration counts)
-- ============================================================================
