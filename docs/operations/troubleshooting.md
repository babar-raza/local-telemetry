# Troubleshooting Guide

## Installation Issues

### "No module named 'telemetry'"

**Cause:** Package not installed.
**Fix:** `pip install -e .` from project root.

### "Directory does not exist"

**Cause:** Storage not initialized.
**Fix:** Set `TELEMETRY_DB_PATH` or `TELEMETRY_BASE_DIR` environment variable, or use Docker (auto-creates `/data`).

## Runtime Issues

### "Database is locked"

**Cause:** Concurrent write contention or multiple API workers.
**Fix:**
1. Ensure `TELEMETRY_API_WORKERS=1` (must be 1).
2. Should resolve automatically via retry logic (3 retries with exponential backoff).
3. If persistent, check for hanging processes: `tasklist | findstr python` (Windows) or `ps aux | grep python` (Linux).
4. Kill stalled processes and retry.

### "Permission denied" when writing

**Cause:** No write permissions to storage directory.
**Fix:** Check folder permissions. In Docker, ensure volume is writable by the `telemetry` user (UID 1000).

### Telemetry not appearing

**Checklist:**
1. Is the API running? `curl http://localhost:8765/health`
2. Can you import telemetry? `python -c "import telemetry; print('OK')"`
3. Is `TELEMETRY_API_URL` set correctly?
4. Check API logs: `docker compose logs local-telemetry-api`

## Client Configuration Issues

### 404 Errors in API Logs

**Cause:** Google Sheets client is enabled but `GOOGLE_SHEETS_API_URL` points to localhost instead of a real Google Sheets endpoint.
**Fix:** Set `GOOGLE_SHEETS_API_ENABLED=false` or provide a valid Google Sheets URL. Restart service.

### API Retry Logic

- **4xx errors:** Client errors, NOT retried.
- **5xx errors:** Server errors, ARE retried (3 attempts, delays 1s/2s/4s).
- **Connection/timeout errors:** ARE retried.

## Database Issues

### Expected Production PRAGMA Values

| Setting | Value | Purpose |
|---------|-------|---------|
| `busy_timeout` | 30000 ms | Wait for locks |
| `journal_mode` | DELETE | Docker-compatible |
| `synchronous` | FULL | Crash-safe writes |

PRAGMAs are **per-connection**. Raw `sqlite3.connect()` uses SQLite defaults. When using external tools (sqlite3 CLI, DB Browser), set PRAGMAs manually:
```sql
PRAGMA busy_timeout=30000;
PRAGMA journal_mode=DELETE;
PRAGMA synchronous=FULL;
```

### Wrong data in database

Query recent runs via API:
```bash
curl "http://localhost:8765/api/v1/runs?limit=10"
```

Or via Docker:
```bash
docker compose exec local-telemetry-api sqlite3 /data/telemetry.sqlite \
  "SELECT event_id, status, agent_name FROM agent_runs ORDER BY created_at DESC LIMIT 10;"
```

### Database too large

Check size:
```bash
docker compose exec local-telemetry-api ls -lh /data/telemetry.sqlite
```

Run retention cleanup:
```bash
docker compose exec local-telemetry-api python scripts/db_retention_policy_batched.py --days 30
```

### Database corruption recovery

1. Stop all access.
2. Restore from backup: see [backup-and-restore guide](../guides/backup-and-restore.md).
3. Verify integrity: `sqlite3 <db> "PRAGMA integrity_check;"`

## Performance Issues

### Slow queries

Check indexes exist:
```bash
docker compose exec local-telemetry-api sqlite3 /data/telemetry.sqlite \
  "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_runs_%' ORDER BY name;"
```

If missing, apply migrations in `migrations/` directory. Run `ANALYZE agent_runs;` to update query planner statistics.

### Slow writes

Check:
- Disk speed (SSD recommended)
- Antivirus interference (exclude DB path)
- `TELEMETRY_DB_SYNCHRONOUS=FULL` is correct but slower than NORMAL (by design)

## Getting Help

1. Check API health: `curl http://localhost:8765/health`
2. Check API metrics: `curl http://localhost:8765/metrics`
3. Check Docker logs: `docker compose logs -f local-telemetry-api`
4. Report issue with output from above.
