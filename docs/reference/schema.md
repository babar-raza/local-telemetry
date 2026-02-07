# Schema Reference

Canonical schema: `src/telemetry/schema.py`. Current version: v7.

## Tables
- `agent_runs` -- Main run tracking table (~45 columns).
- `run_events` -- Event log table (defined; client writes events to NDJSON only).
- `commits` -- Commit metadata keyed by `commit_hash`.
- `schema_migrations` -- Applied versions with timestamps.

## Indexes (agent_runs)
- `idx_runs_event_id` -- Idempotency lookups (v6)
- `idx_runs_agent` -- Filter by agent_name
- `idx_runs_status` -- Filter by status
- `idx_runs_start` -- Sort by start_time
- `idx_runs_created_desc` -- Sort by created_at DESC
- `idx_runs_agent_status_created` -- Multi-filter: agent + status + time
- `idx_runs_agent_created` -- Multi-filter: agent + time range
- `idx_runs_api_posted` -- API posting status
- `idx_runs_insight` -- Link to insights
- `idx_runs_job_type` -- Job type filter (v7)

## Indexes (other tables)
- `idx_events_run` -- Event lookups by run_id (run_events)
- `idx_commits_run` -- Commit lookups by run_id (commits)

## Key Field Constraints

### `event_id`
- `TEXT NOT NULL UNIQUE` -- UUID v4 (36 chars). Provides idempotency for at-least-once delivery.

### `run_id`
- `TEXT NOT NULL` -- No database-level length limit.
- Application-level: max 255 chars, no path separators (`/`, `\`), no null bytes. Validated by `TelemetryClient._validate_custom_run_id()`.
- Auto-generated format: `{YYYYMMDD}T{HHMMSS}Z-{agent_name}-{uuid8}` (e.g., `20251231T153045Z-seo-analyzer-a1b2c3d4`).

### `status`
- `TEXT NOT NULL DEFAULT 'running'`
- `CHECK (status IN ('running', 'success', 'failure', 'partial', 'timeout', 'cancelled'))`

### Numeric Fields
```sql
CHECK (items_discovered >= 0)
CHECK (items_succeeded >= 0)
CHECK (items_failed >= 0)
CHECK (items_skipped >= 0)
CHECK (duration_ms >= 0)
CHECK (api_retry_count >= 0)
```

### Foreign Keys
- `run_events.run_id` references `agent_runs.run_id`.

## Production PRAGMA Settings
- `journal_mode=DELETE` (Docker-compatible)
- `synchronous=FULL` (corruption prevention)
- `busy_timeout=30000` (lock contention)

See `architecture/decisions.md` (ADR-001) for the rationale behind DELETE over WAL.

## Migrations
Schema migrations are in `migrations/`:
- `003_add_created_at_index.sql`
- `004_add_composite_indexes.sql`
- `v5_add_website_fields.sql`
- `v6_add_git_commit_columns.sql`
- `v7_add_job_type_index.sql`

SQL export for current schema: `schema/telemetry_v7.sql`
