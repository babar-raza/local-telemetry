-- Migration v7: Add index on job_type for faster DISTINCT queries
--
-- Problem: SELECT DISTINCT job_type FROM agent_runs does a full table scan
-- on 21M+ rows, taking >2 minutes.
--
-- Solution: Add index on job_type column to enable index scan.
--
-- Performance impact:
--   Before: >2 minutes (full table scan)
--   After: <100ms (index scan)
--
-- Safe to run multiple times (uses IF NOT EXISTS).
-- Run via: python scripts/migrate_v7_add_job_type_index.py <db_path>

CREATE INDEX IF NOT EXISTS idx_runs_job_type ON agent_runs(job_type);
