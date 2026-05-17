-- ============================================================================
-- Migration 005 — Scraper audit infrastructure
-- ============================================================================
-- Date: May 17, 2026
-- Changelog: Entry #011 (pending)
-- ADR: ADR-039 H4 remediation — first scraper for federal_policy_brief
--
-- NOTE: Renumbered from 004 to 005 mid-session. Migration 004 (May 3, 2026)
-- already exists in live DB — it widened the security_events.source CHECK
-- constraint to include 'main_identity_check' for ADR-038 §6 closure
-- (Entry #009). That migration was applied to the live database but no
-- corresponding .sql file is in project knowledge — a gap to address in
-- a separate session.
--
-- Three changes:
--   1. Add `project` column to scraped_content for multi-project tagging
--      (federal_policy_brief, medical_brief, durham_politics, etc.)
--   2. Add `scraper_run_id` FK column to scraped_content for run-level audit
--   3. Create scraper_runs table — one row per scraper execution
--
-- The scraped_content table is currently empty (verified via \dt on May 17),
-- so column additions are zero-cost. After this migration, every inserted
-- scraped_content row carries (project, scraper_run_id) for full traceability.
--
-- Pre-migration state: schema_version = 5
-- Post-migration state: schema_version = 6
--
-- Run as: psql -U openclaw -d openclaw -f migration_005.sql
-- ============================================================================

-- ── Step 1: Create scraper_runs table ────────────────────────────────

CREATE TABLE IF NOT EXISTS scraper_runs (
    id              SERIAL PRIMARY KEY,
    scraper_name    VARCHAR(64) NOT NULL,
    project         VARCHAR(64) NOT NULL,
    source_domain   VARCHAR(255) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ,
    status          VARCHAR(20) NOT NULL DEFAULT 'running',
    docs_fetched    INTEGER NOT NULL DEFAULT 0,
    docs_inserted   INTEGER NOT NULL DEFAULT 0,
    docs_skipped    INTEGER NOT NULL DEFAULT 0,
    retries_used    INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT scraper_runs_status_check
        CHECK (status IN ('running', 'success', 'partial', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_name_started
    ON scraper_runs(scraper_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_project_started
    ON scraper_runs(project, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_scraper_runs_status
    ON scraper_runs(status);

COMMENT ON TABLE scraper_runs IS
    'One row per scraper execution. Audit trail for Automate persona scraping. '
    'Populated by BaseScraper.run() in app/scheduling/scrapers/base.py.';

-- ── Step 2: Add project column to scraped_content ────────────────────

ALTER TABLE scraped_content
    ADD COLUMN IF NOT EXISTS project VARCHAR(64);

-- Backfill any existing rows (table is empty as of May 17, 2026, but safe to run)
UPDATE scraped_content
    SET project = 'federal_policy_brief'
    WHERE project IS NULL;

ALTER TABLE scraped_content
    ALTER COLUMN project SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_scraped_content_project
    ON scraped_content(project);

-- ── Step 3: Add scraper_run_id FK column to scraped_content ──────────

ALTER TABLE scraped_content
    ADD COLUMN IF NOT EXISTS scraper_run_id INTEGER
    REFERENCES scraper_runs(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_scraped_content_run
    ON scraped_content(scraper_run_id);

-- ── Step 4: Record migration ─────────────────────────────────────────

INSERT INTO schema_version (version, description) VALUES
    (6, 'Migration 005: scraper_runs table created; scraped_content gained project and scraper_run_id columns. ADR-039 H4. May 17, 2026.')
ON CONFLICT (version) DO NOTHING;

-- ============================================================================
-- VERIFICATION QUERIES (run manually after migration)
-- ============================================================================
-- 1. Confirm new table exists:
--      \dt scraper_runs
--
-- 2. Confirm scraped_content has new columns:
--      \d scraped_content
--      (expect: project NOT NULL, scraper_run_id integer)
--
-- 3. Confirm indexes:
--      SELECT indexname FROM pg_indexes
--      WHERE tablename IN ('scraper_runs', 'scraped_content')
--      ORDER BY tablename, indexname;
--
-- 4. Confirm schema version:
--      SELECT version, description FROM schema_version ORDER BY version DESC LIMIT 1;
--      (expect version = 6)
--
-- 5. Confirm zero impact on existing data:
--      SELECT count(*) FROM scraped_content;
--      (expect 0 — table was empty before migration)
-- ============================================================================
