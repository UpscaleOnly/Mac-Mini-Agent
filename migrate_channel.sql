-- ============================================================================
-- Migration: Make sessions table channel-agnostic
-- ============================================================================
-- Changes:
--   1. Add 'channel' column (telegram, cli, web, internal)
--   2. Rename chat_id → channel_id, change type bigint → text
--   3. Update initiated_by default from 'operator_telegram' to 'operator'
--   4. Rebuild index on new column name
--
-- Date: April 13, 2026
-- Reason: Decouple core agent pipeline from Telegram-specific data types.
--         Enables CLI, web, and internal channels to use the same session
--         table without Telegram-shaped payloads.
-- ============================================================================

BEGIN;

-- 1. Add channel column with default for existing rows
ALTER TABLE sessions ADD COLUMN channel TEXT NOT NULL DEFAULT 'telegram';

-- 2. Rename chat_id → channel_id and change type to text
ALTER TABLE sessions RENAME COLUMN chat_id TO channel_id;
ALTER TABLE sessions ALTER COLUMN channel_id TYPE TEXT USING channel_id::TEXT;

-- 3. Update initiated_by default
ALTER TABLE sessions ALTER COLUMN initiated_by SET DEFAULT 'operator';

-- 4. Drop old index, create new one
DROP INDEX IF EXISTS idx_sessions_chat_id;
CREATE INDEX idx_sessions_channel_id ON sessions(channel_id);

-- 5. Add check constraint for channel values
ALTER TABLE sessions ADD CONSTRAINT sessions_channel_check
    CHECK (channel = ANY (ARRAY['telegram', 'cli', 'web', 'internal']));

COMMIT;
