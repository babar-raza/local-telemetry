# Monitoring & Health (Operators)

## Routine Checks
- **Installation validation** (Day 1 sanity):
  ```bash
  python scripts/validate_installation.py
  ```
  - Verifies Python deps, storage dirs, DB presence, config sanity, and test suite presence.
- **Ongoing health**:
  ```bash
  python scripts/monitor_telemetry_health.py
  ```
  - Checks: storage dirs exist, DB integrity/tables, disk space, write permissions, recent activity (last hour), DB size threshold.

## What to watch
- Disk space: warns if <5GB, fails if <1GB.
- DB integrity: should report `ok`; otherwise run recovery (`guides/recovery-from-ndjson.md`) or restore backup.
- Recent activity: zero runs in last hour may indicate upstream agent issues.
- API posting: watch `api_posted`/`api_retry_count` via DB query if remote posting enabled.

## Alerts & Logs
- Health script prints to stdout; redirect to logs for scheduled runs.
- For monitoring storage size and backup freshness, check `{metrics_dir}/backups` timestamps.

## Links
- Configuration: `reference/config.md`
- CLI details: `reference/cli.md`
- File contracts: `reference/file-contracts.md`
