# Operator Quickstart

Set up telemetry storage and database on a fresh machine.

## Steps
1. **Install dependencies**
   ```bash
   pip install -e .
   ```
2. **Create storage layout**
   ```bash
   python scripts/setup_storage.py
   ```
   - Selects base dir (prefers `D:/agent-metrics`, fallback `C:/agent-metrics` or auto-detect per `reference/config.md`).
3. **Create database schema**
   ```bash
   python scripts/setup_database.py
   ```
   - Creates `db/telemetry.sqlite`, verifies schema, exports `config/schema.sql`.
4. **Validate installation**
   ```bash
   python scripts/validate_installation.py
   ```
   - Confirms Python deps, directories, DB presence, config, and tests existence.
5. **Schedule backups (recommended)**
   ```bash
   python scripts/backup_database.py --keep 7
   ```
   - Use OS scheduler (Task Scheduler/cron) daily.

## Verify
- Check `raw/` and `db/` exist under the chosen base.
- Run `python scripts/monitor_telemetry_health.py` to ensure all checks pass.

## Next
- Instrument agents: `guides/instrumentation.md`
- Operational runbooks: `operations/runbook.md`
- Backup/restore details: `guides/backup-and-restore.md`
