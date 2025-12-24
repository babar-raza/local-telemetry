-- Migration 004: Add composite indexes for multi-filter query optimization
-- Date: 2025-12-24
-- Issue: GET /api/v1/runs with multiple filters performs poorly

-- Index for: agent_name + status + time filtering (stale run detection)
CREATE INDEX IF NOT EXISTS idx_runs_agent_status_created
ON agent_runs(agent_name, status, created_at DESC);

-- Index for: agent_name + time range filtering (analytics)
CREATE INDEX IF NOT EXISTS idx_runs_agent_created
ON agent_runs(agent_name, created_at DESC);

-- Verify indexes were created
SELECT name, sql FROM sqlite_master
WHERE type='index' AND tbl_name='agent_runs'
AND name IN ('idx_runs_agent_status_created', 'idx_runs_agent_created');
