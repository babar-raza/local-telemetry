# Schema Reference

Canonical schema: `src/telemetry/schema.py`.

- **Version:** 3 (records in `schema_migrations` table).
- **Tables:**
  - `agent_runs` — see `reference/file-contracts.md` for column list.
  - `run_events` — event log table (defined; client writes events to NDJSON only).
  - `commits` — commit metadata keyed by `commit_hash`.
  - `schema_migrations` — applied versions with timestamps.
- **Indexes:**
  - **agent_runs table:**
    - `idx_runs_event_id` — Idempotency lookups (v6)
    - `idx_runs_agent` — Filter by agent_name
    - `idx_runs_status` — Filter by status
    - `idx_runs_start` — Sort by start_time
    - `idx_runs_created_desc` — Sort by created_at DESC (v2.1.0)
    - `idx_runs_agent_status_created` — Multi-filter queries: agent + status + time (v2.1.0)
    - `idx_runs_agent_created` — Multi-filter queries: agent + time range (v2.1.0)
    - `idx_runs_api_posted` — API posting status
    - `idx_runs_insight` — Link to insights
  - **run_events table:** `idx_events_run` — Event lookups by run_id
  - **commits table:** `idx_commits_run` — Commit lookups by run_id
- **Pragmas on creation:** WAL mode, `busy_timeout=5000`, `synchronous=NORMAL`, `wal_autocheckpoint=1000`.
- **SQL export:** `config/schema.sql` produced by `scripts/setup_database.py`.

For storage layout and NDJSON contracts, see `reference/file-contracts.md`.
