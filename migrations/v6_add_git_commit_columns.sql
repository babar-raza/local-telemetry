-- Migration: v6_add_git_commit_columns
-- Description: Add missing git commit tracking columns to agent_runs table
-- These columns were defined in schema v6 but may be missing in existing databases
--
-- Columns added:
--   git_commit_source TEXT - How commit was created ('manual', 'llm', 'ci')
--   git_commit_author TEXT - Git author string (e.g., "Name <email>")
--   git_commit_timestamp TEXT - ISO8601 timestamp of when commit was made
--
-- Note: git_commit_hash already exists from v4 migration
--
-- Usage:
--   sqlite3 telemetry.db < migrations/v6_add_git_commit_columns.sql
--
-- Rollback:
--   SQLite does not support DROP COLUMN easily.
--   Restore from pre-migration backup (created by migrate_v6_fix_columns.py)

-- Add git_commit_source column (if not exists)
-- Note: SQLite will error if column already exists, so use ALTER TABLE with caution
-- This file is for documentation; use migrate_v6_fix_columns.py for safe migration
ALTER TABLE agent_runs ADD COLUMN git_commit_source TEXT;

-- Add git_commit_author column (if not exists)
ALTER TABLE agent_runs ADD COLUMN git_commit_author TEXT;

-- Add git_commit_timestamp column (if not exists)
ALTER TABLE agent_runs ADD COLUMN git_commit_timestamp TEXT;

-- Record migration version
INSERT OR IGNORE INTO schema_migrations (version, description, applied_at)
VALUES (6, 'Add git commit tracking columns (source, author, timestamp)', datetime('now'));
