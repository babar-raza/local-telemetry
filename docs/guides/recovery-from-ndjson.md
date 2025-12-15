# Recovery from NDJSON (Operators)

Use when SQLite DB is corrupted. Source of truth: `scripts/recover_database.py`.

## Prerequisites
- NDJSON files present in `{metrics_dir}/raw/*.ndjson`.
- Back up current DB first (script does this automatically).

## Steps
1. **Health check only (no changes)**
   ```bash
   python scripts/recover_database.py --check-only
   ```
   - Runs `PRAGMA quick_check` and reports status.
2. **Recover (forced if needed)**
   ```bash
   python scripts/recover_database.py --force
   ```
   - Backs up corrupted DB to `telemetry.corrupted.{timestamp}.sqlite`.
   - Recreates schema (script uses schema v2) and replays NDJSON events into new DB.

## Post-recovery validation
- Verify schema version matches expected (library expects v3):
  ```bash
  sqlite3 {metrics_dir}/db/telemetry.sqlite "SELECT MAX(version) FROM schema_migrations;"
  ```
- Run health check:
  ```bash
  python scripts/monitor_telemetry_health.py
  ```
- If schema shows version 2, re-run `scripts/setup_database.py` to align with v3, then reconcile data as needed.

## Notes
- NDJSON is the append-only source; events are not stored in DB by design.
- Keep `{metrics_dir}/raw` intact to allow replay.
- For standard backup/restore (when DB is healthy), use `guides/backup-and-restore.md`.
