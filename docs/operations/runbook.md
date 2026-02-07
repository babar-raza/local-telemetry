# Telemetry Platform Runbook

**System:** Local Telemetry Platform v3.0.0
**Deployment:** Docker (`docker-compose.yml`)
**Database:** SQLite at `/data/telemetry.sqlite` (inside container)

---

## Health Checks

### Quick Health Check

```bash
curl http://localhost:8765/health
# Expected: {"status": "ok", "version": "3.0.0", ...}

curl http://localhost:8765/metrics
# Shows total runs, agent counts, recent activity
```

### Docker Health

```bash
docker compose ps
# Should show "Up (healthy)"

docker compose logs --tail=20 local-telemetry-api
# Check for errors
```

### Manual Verification

```bash
# Check recent activity
curl "http://localhost:8765/api/v1/runs?limit=5"

# Check metadata (agents and job types)
curl http://localhost:8765/api/v1/metadata
```

---

## Common Operations

### Query Runs via API

```bash
# Recent runs
curl "http://localhost:8765/api/v1/runs?limit=20"

# Filter by agent
curl "http://localhost:8765/api/v1/runs?agent_name=my-agent&limit=10"

# Filter by status
curl "http://localhost:8765/api/v1/runs?status=failure&limit=10"
```

### Query via SQLite

```bash
docker compose exec local-telemetry-api sqlite3 /data/telemetry.sqlite \
  "SELECT event_id, agent_name, status, created_at FROM agent_runs ORDER BY created_at DESC LIMIT 20;"
```

### Create Backup

```bash
docker compose cp local-telemetry-api:/data/telemetry.sqlite ./backup_$(date +%Y%m%d).sqlite
```

See `../guides/backup-and-restore.md` for full backup/restore procedures.

---

## Recovery Procedures

### Database Locked

**Symptoms:** "database is locked" errors
**Cause:** Concurrent write contention or multiple workers.

**Recovery:**
1. Verify `TELEMETRY_API_WORKERS=1` in docker-compose.yml.
2. Wait 30 seconds (auto-retry should resolve).
3. If persistent: `docker compose restart`
4. Check no other processes accessing the DB directly.

### Database Corrupted

**Symptoms:** "disk I/O error", "database disk image is malformed"

**Recovery:**
1. Stop service: `docker compose stop`
2. Check integrity: `sqlite3 backup.sqlite "PRAGMA integrity_check;"`
3. Restore from backup: see `../guides/backup-and-restore.md`
4. Restart: `docker compose start`

### Disk Full

**Symptoms:** "No space left on device"

**Recovery:**
1. Check Docker volume usage: `docker system df`
2. Run retention cleanup: `docker compose exec local-telemetry-api python scripts/db_retention_policy_batched.py --days 30`
3. Prune Docker: `docker system prune`
4. Consider increasing disk allocation.

### No Recent Activity

**Investigation:**
1. Check API health: `curl http://localhost:8765/health`
2. Check if agents are posting: `docker compose logs --tail=50 local-telemetry-api`
3. Verify agents have correct `TELEMETRY_API_URL`.

---

## Maintenance Tasks

### Weekly
- Check API health endpoint
- Review Docker logs for errors
- Verify backup schedule is running

### Monthly
- Review database size growth
- Run retention cleanup if not automated
- Check disk space trend

### Quarterly
- Review query performance (check `curl http://localhost:8765/metrics`)
- Update retention policies if needed
- Consider running `VACUUM` on large databases

---

## Alerting Thresholds

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| Health endpoint | 200 OK | N/A | Non-200 or timeout |
| Recent 24h runs | > 0 | 0 for > 2h | 0 for > 6h |
| DB size | < 500MB | 500MB-1GB | > 1GB |
| Error rate | < 5% | 5-15% | > 15% |

**Alert response:**
- **Warning:** Investigate within 2 hours. Check logs and agent health.
- **Critical:** Respond within 15 minutes. Check service health, restart if needed.

---

## Performance Baselines

| Metric | Target |
|--------|--------|
| Write latency (p95) | < 50ms |
| Query latency (simple) | < 100ms |
| Throughput | > 20 writes/second |
| Database size per run | ~100 bytes |

If metrics degrade, check disk I/O performance and consider running `VACUUM`.

---

## Escalation

1. **Self-service:** Follow recovery procedures above.
2. **If recovery fails:** Check `troubleshooting.md`.
3. **Data corruption:** Restore from backup, report to development team.

---

## Change Log

| Date | Change |
|------|--------|
| 2026-02-07 | Updated for v3.0.0, Docker-first operations |
| 2025-12-11 | Initial runbook |
