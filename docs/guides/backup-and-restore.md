# Backup and Restore Guide (Operators)

## Prerequisites
- Storage configured (`AGENT_METRICS_DIR` / `TELEMETRY_BASE_DIR` / `TELEMETRY_DB_PATH`).
- SQLite available on PATH.

## Backup (daily/automated)
1. Run hot backup:
   ```bash
   python scripts/backup_database.py --keep 7
   ```
   - Uses SQLite backup API; verifies integrity before/after.
   - Backups saved to `{metrics_dir}/backups/telemetry.backup.{date}.sqlite`.
2. Optional alternative with retention by days:
   ```bash
   python scripts/backup_telemetry_db.py --keep-days 7
   ```
   - Creates `telemetry_backup_{timestamp}.sqlite`; verifies integrity.

## Restore (from backup_telemetry_db)
1. Run interactive restore:
   ```bash
   python scripts/backup_telemetry_db.py --restore path/to/telemetry_backup_YYYYMMDD_HHMMSS.sqlite
   ```
   - Creates safety backup of current DB before overwrite.
   - Verifies restored DB with `PRAGMA integrity_check`.

## Rotate/clean
- `backup_database.py --keep N` deletes older backups beyond N.
- `backup_telemetry_db.py --keep-days N` removes backups older than N days (keeps most recent).

## Validate
- Check backup integrity manually:
  ```bash
  sqlite3 {metrics_dir}/backups/telemetry.backup.20251215.sqlite "PRAGMA integrity_check;"
  ```
- Confirm recent backup timestamps in `{metrics_dir}/backups`.

## Notes
- Backups rely on correct `metrics_dir`; see `reference/config.md`.
- Recovery from NDJSON (for corruption) uses `scripts/recover_database.py` — see `guides/recovery-from-ndjson.md`.
- File naming and layout: see `reference/file-contracts.md`.
