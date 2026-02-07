# Backup and Restore Guide

## Docker Backup (Recommended)

### Quick Backup
```bash
docker compose cp local-telemetry-api:/data/telemetry.sqlite ./backup_$(date +%Y%m%d).sqlite
```

### Scripted Backup (Windows)
```powershell
.\scripts\backup_docker_telemetry.ps1
```

### Restore
```bash
docker compose stop
docker compose cp ./backup_file.sqlite local-telemetry-api:/data/telemetry.sqlite
docker compose start
```

### Restore (Windows script)
```powershell
.\scripts\restore_docker_backup.ps1
```

## Automated Backup Schedule

Use `scripts/setup_docker_backup_task.ps1` to create a Windows Task Scheduler task for daily backups.

## Validate Backup Integrity

```bash
sqlite3 backup_file.sqlite "PRAGMA integrity_check;"
```

Expected output: `ok`

## Retention Policy

The platform includes automated retention to manage database growth:

```bash
# Run inside Docker container
docker compose exec local-telemetry-api python scripts/db_retention_policy_batched.py --days 30

# Or via Windows scheduled task
.\scripts\docker_retention_cleanup.ps1
```

Default: 30-day retention. Set `TELEMETRY_DRY_RUN_CLEANUP=0` to enable actual deletion (default is dry-run mode).

Automate with: `scripts/setup_docker_retention_task.ps1`

## Recovery from NDJSON (Corruption)

When SQLite is corrupted and no backup is viable, rebuild from NDJSON files in `{metrics_dir}/raw/`.

1. **Check integrity (no changes):**
   ```bash
   docker compose exec local-telemetry-api sqlite3 /data/telemetry.sqlite "PRAGMA integrity_check;"
   ```

2. **If corrupted, stop the service:**
   ```bash
   docker compose stop
   ```

3. **Restore from latest backup** (preferred). If no backup exists, the NDJSON files in `raw/` contain all events and can be replayed to rebuild the database.

4. **Post-recovery:** Verify schema version matches current:
   ```sql
   SELECT MAX(version) FROM schema_migrations;
   ```
   If it shows an older version, run `python scripts/setup_database.py` to align.

NDJSON files are the append-only source of truth -- keep `{metrics_dir}/raw` intact for replay capability.

## Notes
- Backups rely on correct `TELEMETRY_DB_PATH`; see `../reference/config.md`.
