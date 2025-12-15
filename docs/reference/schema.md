# Schema Reference

Canonical schema: `src/telemetry/schema.py`.

- **Version:** 3 (records in `schema_migrations` table).
- **Tables:**
  - `agent_runs` — see `reference/file-contracts.md` for column list.
  - `run_events` — event log table (defined; client writes events to NDJSON only).
  - `commits` — commit metadata keyed by `commit_hash`.
  - `schema_migrations` — applied versions with timestamps.
- **Indexes:** `idx_runs_agent`, `idx_runs_status`, `idx_runs_start`, `idx_runs_api_posted`, `idx_runs_insight`, `idx_events_run`, `idx_commits_run`.
- **Pragmas on creation:** WAL mode, `busy_timeout=5000`, `synchronous=NORMAL`, `wal_autocheckpoint=1000`.
- **SQL export:** `config/schema.sql` produced by `scripts/setup_database.py`.

For storage layout and NDJSON contracts, see `reference/file-contracts.md`.
