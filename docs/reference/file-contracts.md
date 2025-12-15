# File & Data Contracts

Canonical storage layout and schemas (source: `src/telemetry/local.py`, `src/telemetry/schema.py`, `scripts/backup_*.py`, `scripts/setup_storage.py`).

## Directory Layout (created by `scripts/setup_storage.py`)
```
{base}/
  raw/       # NDJSON event logs
  db/        # SQLite database (telemetry.sqlite)
  reports/   # Generated reports
  exports/   # CSV exports
  config/    # Config files (schema.sql, YAML configs)
  logs/      # System logs
  backups/   # Created by backup scripts
```
`{base}` defaults to auto-detected path (see `reference/config.md`).

## NDJSON Events (`src/telemetry/local.py`)
- File naming: `events_YYYYMMDD.ndjson` in `{base}/raw/`.
- Each line is JSON object with `record_type`:
  - `run` → RunRecord payload (fields match SQLite agent_runs table)
  - `event` → RunEvent payload (`run_id`, `event_type`, `timestamp`, optional `payload_json`)
- Writes are append-only with file locking and fsync per entry.

## SQLite Schema (v3) (`src/telemetry/schema.py`)
- Database: `{base}/db/telemetry.sqlite`
- Tables:
  - `agent_runs` (PRIMARY KEY run_id):
    - Core: `schema_version`, `agent_name`, `agent_owner`, `job_type`, `trigger_type`, `start_time`, `end_time`, `status`
    - Metrics: `items_discovered`, `items_succeeded`, `items_failed`, `duration_ms`, `metrics_json`
    - Summaries: `input_summary`, `output_summary`, `error_summary`
    - Business: `insight_id`, `product`, `platform`, `product_family`, `subdomain`
    - Git: `git_repo`, `git_branch`, `git_run_tag`
    - Host/API: `host`, `api_posted`, `api_posted_at`, `api_retry_count`
    - Timestamps: `created_at`, `updated_at`
  - `run_events`: `id`, `run_id`, `event_type`, `timestamp`, `payload_json` (not written by client; events are NDJSON-only by design)
  - `commits`: commit metadata keyed by `commit_hash`
  - `schema_migrations`: applied schema versions
- Indexes: `idx_runs_agent`, `idx_runs_status`, `idx_runs_start`, `idx_runs_api_posted`, `idx_runs_insight`, `idx_events_run`, `idx_commits_run`.
- WAL mode enabled on creation; busy_timeout=5000 and synchronous=NORMAL set by `DatabaseWriter`.

## API Posting Markers
- `api_posted` (0/1), `api_posted_at`, `api_retry_count` updated after API attempts (`TelemetryClient.end_run` + `DatabaseWriter` helpers).

## Backups (`scripts/backup_database.py`, `scripts/backup_telemetry_db.py`)
- Output directory: `{metrics_dir}/backups/`
- Filenames:
  - `telemetry.backup.{YYYYMMDD}.sqlite` (or `telemetry.backup.{YYYYMMDD_HHMMSS}.sqlite` if collision)
  - `telemetry_backup_{YYYYMMDD_HHMMSS}.sqlite`
- Integrity check: SQLite `PRAGMA quick_check`/`integrity_check` run pre/post backup.

## Recovery (`scripts/recover_database.py`)
- Reads NDJSON from `{metrics_dir}/raw/*.ndjson`.
- Rebuilds database schema (v2 in script) and replays runs; backs up corrupted DB to `telemetry.corrupted.{timestamp}.sqlite` before writing.

## Reports/Outputs
- `config/schema.sql` exported by `scripts/setup_database.py`.
- Quality gate / verification reports: user-specified paths via `--output`; not fixed contract beyond CLI options.
