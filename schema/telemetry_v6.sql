-- Telemetry Platform Database Schema
-- Version: 7
-- Generated: Auto-generated from schema.py
-- v7: Added idx_runs_job_type index for faster DISTINCT queries

-- Enable DELETE mode for Docker volume compatibility
PRAGMA journal_mode=DELETE;
PRAGMA synchronous=FULL;

-- Tables

-- Table: agent_runs
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    schema_version INTEGER DEFAULT 7,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    start_time TEXT NOT NULL,
    end_time TEXT,
    agent_name TEXT NOT NULL,
    agent_owner TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    product TEXT,
    product_family TEXT,
    platform TEXT,
    subdomain TEXT,
    website TEXT,
    website_section TEXT,
    item_name TEXT,
    items_discovered INTEGER DEFAULT 0,
    items_succeeded INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    items_skipped INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    input_summary TEXT,
    output_summary TEXT,
    source_ref TEXT,
    target_ref TEXT,
    error_summary TEXT,
    error_details TEXT,
    git_repo TEXT,
    git_branch TEXT,
    git_commit_hash TEXT,
    git_run_tag TEXT,
    git_commit_source TEXT,
    git_commit_author TEXT,
    git_commit_timestamp TEXT,
    host TEXT,
    environment TEXT,
    trigger_type TEXT,
    metrics_json TEXT,
    context_json TEXT,
    api_posted INTEGER DEFAULT 0,
    api_posted_at TEXT,
    api_retry_count INTEGER DEFAULT 0,
    insight_id TEXT,
    parent_run_id TEXT,
    CHECK (items_discovered >= 0),
    CHECK (items_succeeded >= 0),
    CHECK (items_failed >= 0),
    CHECK (items_skipped >= 0),
    CHECK (duration_ms >= 0),
    CHECK (api_retry_count >= 0),
    CHECK (status IN ('running', 'success', 'failure', 'partial', 'timeout', 'cancelled'))
);

-- Table: run_events
CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload_json TEXT
);

-- Table: commits
CREATE TABLE IF NOT EXISTS commits (
    commit_hash TEXT PRIMARY KEY,
    run_id TEXT REFERENCES agent_runs(run_id),
    agent_name TEXT,
    repo TEXT,
    branch TEXT,
    commit_date TEXT,
    author TEXT,
    message TEXT,
    files_changed INTEGER,
    insertions INTEGER,
    deletions INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Table: schema_migrations
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now')),
    description TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_runs_event_id ON agent_runs(event_id);
CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name);
CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_start ON agent_runs(start_time);
CREATE INDEX IF NOT EXISTS idx_runs_created_desc ON agent_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_agent_status_created ON agent_runs(agent_name, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_agent_created ON agent_runs(agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_job_type ON agent_runs(job_type);
CREATE INDEX IF NOT EXISTS idx_runs_parent_run ON agent_runs(parent_run_id);
CREATE INDEX IF NOT EXISTS idx_runs_api_posted ON agent_runs(api_posted);
CREATE INDEX IF NOT EXISTS idx_runs_insight ON agent_runs(insight_id);
CREATE INDEX IF NOT EXISTS idx_runs_commit ON agent_runs(git_commit_hash);
CREATE INDEX IF NOT EXISTS idx_runs_website ON agent_runs(website);
CREATE INDEX IF NOT EXISTS idx_runs_website_section ON agent_runs(website, website_section);
CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id);
CREATE INDEX IF NOT EXISTS idx_commits_run ON commits(run_id);

-- Record schema version
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES (7, 'Schema v7: Added idx_runs_job_type index for faster DISTINCT queries');
