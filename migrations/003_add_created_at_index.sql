-- Migration 003: Add index on created_at for query performance
-- Date: 2025-12-24
-- Issue: GET /api/v1/runs uses ORDER BY created_at DESC without index

CREATE INDEX IF NOT EXISTS idx_runs_created_desc ON agent_runs(created_at DESC);

-- Verify index was created
SELECT name, sql FROM sqlite_master
WHERE type='index' AND tbl_name='agent_runs' AND name='idx_runs_created_desc';
