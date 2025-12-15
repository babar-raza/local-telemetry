# CLI Reference

Canonical commands and flags (source: `scripts/`).

## Setup
- `python scripts/setup_storage.py`
  - Creates base dirs `{base}/raw, db, reports, exports, config, logs` (prefers D:\ then C:\ on Windows).
- `python scripts/setup_database.py`
  - Creates/verify schema at `{base}/db/telemetry.sqlite`; exports `config/schema.sql`.

## Health & Validation
- `python scripts/validate_installation.py`
  - Checks Python deps, storage dirs, DB presence, config sanity, and test presence.
- `python scripts/monitor_telemetry_health.py`
  - Checks storage existence, DB integrity/tables, disk space, write permissions, recent activity (last hour), DB size.

## Backup & Recovery
- `python scripts/backup_database.py [--keep N]`
  - Hot backup via SQLite backup API; verifies integrity; rotates to keep N (default 7) under `{metrics_dir}/backups`.
- `python scripts/backup_telemetry_db.py [--restore PATH] [--keep-days N]`
  - Create backup with integrity check; retention by days (default 7); optional interactive restore from `--restore`.
- `python scripts/recover_database.py [--check-only] [--force]`
  - If corrupted, backs up corrupted DB, recreates schema (v2), and replays NDJSON from `{metrics_dir}/raw`. `--check-only` skips recovery; `--force` recovers even if healthy.

## Extraction & Deliverables
- `python scripts/extract_files_from_agent_output.py --log-file PATH [--output-dir DIR] [--dry-run] [--overwrite] [--report PATH] [--format text|json]`
  - Parses agent output for file blocks; validates extensions/length/confidence; writes files or reports.
- `python scripts/auto_extract_agent_outputs.py (--agent-id ID | --log-file PATH) [--task-spec PATH] [--output-dir DIR] [--dry-run] [--overwrite] [--report PATH]`
  - Wraps extraction with task-spec validation of expected deliverables; prints report and optional file.
- `python scripts/quality_gate.py --task-spec PATH [--agent-id ID] [--config PATH] [--output PATH] [--format text|json|yaml] [--dry-run]`
  - Validates deliverables and acceptance checks from task spec using `config/quality_gate_config.yaml` by default.
- `python scripts/verify_analysis.py DOCUMENT [--config PATH] [--output PATH] [--format text|json|yaml] [--dry-run] [--verify]`
  - Extracts claims from DOCUMENT using `config/verification_checklist.yaml`, verifies filesystem/line-count claims, and reports pass rate.

## Telemetry Operations
- `python scripts/monitor_telemetry_health.py` — see Health section above.
- `python scripts/measure_performance.py`
  - Benchmarks write/query latency and DB size using real TelemetryClient (note: script currently calls `RunContext.update_metrics`; adjust to `set_metrics` if needed).

## Testing
- `python scripts/run_tests.py [--unit | --integration | --smoke] [--verbose|-v] [--coverage]`
  - Wraps pytest with path setup; integration expects real storage at `{base}`.

## Paths & Environment
- Commands rely on `AGENT_METRICS_DIR`/`TELEMETRY_BASE_DIR`/`TELEMETRY_DB_PATH` for storage selection (see `reference/config.md`).
- Backup/recovery scripts write to `{metrics_dir}/backups`; recovery reads `{metrics_dir}/raw/*.ndjson`.
