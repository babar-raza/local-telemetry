-- Telemetry DB Audit Queries
-- Safe read-only queries for database analysis

-- Get database file size (run externally)
-- dir data\telemetry.sqlite

-- List all tables and their row counts
SELECT 'agent_runs' as table_name, COUNT(*) as row_count FROM agent_runs
UNION ALL
SELECT 'run_events', COUNT(*) FROM run_events
UNION ALL
SELECT 'commits', COUNT(*) FROM commits
UNION ALL
SELECT 'schema_migrations', COUNT(*) FROM schema_migrations;

-- Get table schemas
SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';

-- Top agents by run count
SELECT agent_name, COUNT(*) as run_count
FROM agent_runs
GROUP BY agent_name
ORDER BY run_count DESC;

-- Status distribution
SELECT status, COUNT(*) as count
FROM agent_runs
GROUP BY status;

-- Daily volume
SELECT DATE(start_time) as day, COUNT(*) as run_count
FROM agent_runs
WHERE start_time IS NOT NULL
GROUP BY DATE(start_time)
ORDER BY day DESC;

-- Event types (if any)
SELECT event_type, COUNT(*) as count
FROM run_events
GROUP BY event_type
ORDER BY count DESC;

-- Largest payloads (if any)
SELECT LENGTH(details) as size, event_type
FROM run_events
WHERE details IS NOT NULL
ORDER BY size DESC
LIMIT 10;

-- Index analysis
SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';

-- Database page usage
PRAGMA page_size;
PRAGMA page_count;
PRAGMA freelist_count;