-- TELEMETRY DATABASE SCHEMA v6
-- Supports: SQLite (DELETE mode) and PostgreSQL
-- Key addition: event_id for idempotency
-- Migration from v5: Adds event_id UNIQUE constraint for at-least-once delivery

-- ============================================================
-- MAIN TELEMETRY TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS agent_runs (
    -- Primary key
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- SQLite
    -- id SERIAL PRIMARY KEY,  -- PostgreSQL (uncomment for PG)

    -- Idempotency & Traceability
    event_id TEXT NOT NULL UNIQUE,  -- UUID v4, prevents duplicates
    run_id TEXT NOT NULL,            -- Application-level run identifier

    -- Timestamps
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,

    -- Agent Identity
    agent_name TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',  -- running, success, failure, partial, timeout, cancelled

    -- Product/Domain Context
    product TEXT,
    product_family TEXT,
    platform TEXT,
    subdomain TEXT,

    -- Website Context (for SEO agents)
    website TEXT,
    website_section TEXT,
    item_name TEXT,

    -- Volume Metrics
    items_discovered INTEGER DEFAULT 0,
    items_succeeded INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    items_skipped INTEGER DEFAULT 0,

    -- Performance Metrics
    duration_ms INTEGER DEFAULT 0,

    -- Input/Output References
    input_summary TEXT,
    output_summary TEXT,
    source_ref TEXT,
    target_ref TEXT,

    -- Error Details
    error_summary TEXT,
    error_details TEXT,

    -- Git Context
    git_repo TEXT,
    git_branch TEXT,
    git_commit_hash TEXT,
    git_run_tag TEXT,

    -- Environment
    host TEXT,
    environment TEXT,
    trigger_type TEXT,

    -- Extended Metadata (JSON)
    metrics_json TEXT,  -- JSON string in SQLite, JSONB in PostgreSQL
    context_json TEXT,  -- Additional context

    -- API Sync Tracking
    api_posted BOOLEAN DEFAULT 0,
    api_posted_at TIMESTAMP,
    api_retry_count INTEGER DEFAULT 0,

    -- Insight Linking (SEO Intelligence)
    insight_id TEXT,
    parent_run_id TEXT,

    -- Constraints
    CHECK (items_discovered >= 0),
    CHECK (items_succeeded >= 0),
    CHECK (items_failed >= 0),
    CHECK (items_skipped >= 0),
    CHECK (duration_ms >= 0),
    CHECK (api_retry_count >= 0),
    CHECK (status IN ('running', 'success', 'failure', 'partial', 'timeout', 'cancelled'))
);

-- ============================================================
-- INDEXES (DELETE mode compatible, PostgreSQL compatible)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_runs_event_id ON agent_runs(event_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_start ON agent_runs(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_runs_insight ON agent_runs(insight_id) WHERE insight_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_commit ON agent_runs(git_commit_hash) WHERE git_commit_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_api_posted ON agent_runs(api_posted, api_posted_at);
CREATE INDEX IF NOT EXISTS idx_runs_website ON agent_runs(website) WHERE website IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_runs_website_section ON agent_runs(website_section) WHERE website_section IS NOT NULL;

-- ============================================================
-- RELATED TABLES (from existing schema)
-- ============================================================

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    message TEXT,
    details TEXT,
    FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id);

CREATE TABLE IF NOT EXISTS commits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    commit_hash TEXT NOT NULL UNIQUE,
    repo TEXT NOT NULL,
    branch TEXT,
    author TEXT,
    message TEXT,
    timestamp TIMESTAMP,
    metadata TEXT
);

CREATE INDEX IF NOT EXISTS idx_commits_hash ON commits(commit_hash);

-- ============================================================
-- SCHEMA MIGRATIONS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

-- Record schema version
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (6, 'Schema v6: Added event_id with UNIQUE constraint for idempotency');
