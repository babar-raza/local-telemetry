# Telemetry Platform Runbook

**System:** Local Telemetry Platform
**Owner:** Local Telemetry Team
**Last Updated:** 2025-12-11

---

## System Overview

**Purpose:** Track agent runs, metrics, and performance
**Storage:** `D:\agent-metrics` (local Windows storage)
**Database:** SQLite at `D:\agent-metrics\db\telemetry.sqlite`
**Environment:** Windows, Python 3.9-3.13

---

## Health Checks

### Daily Health Check (5 minutes)

```bash
# Run automated health check
python scripts/monitor_telemetry_health.py

# Expected: Exit code 0, all checks OK
```

**If failures detected:** See Recovery Procedures

### Manual Health Verification

```bash
# 1. Check storage exists
dir D:\agent-metrics

# 2. Check database accessible
sqlite3 D:\agent-metrics\db\telemetry.sqlite "SELECT COUNT(*) FROM agent_runs;"

# 3. Check recent activity
python -c "import sqlite3; from datetime import datetime, timedelta, timezone; conn = sqlite3.connect('D:\\agent-metrics\\db\\telemetry.sqlite'); cursor = conn.cursor(); cursor.execute('SELECT COUNT(*) FROM agent_runs WHERE start_time >= ?', ((datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),)); print(f'Runs last 24h: {cursor.fetchone()[0]}'); conn.close()"

# 4. Check disk space
python -c "import shutil; total, used, free = shutil.disk_usage('D:\\agent-metrics'); print(f'Free: {free/(1024**3):.1f} GB')"
```

---

## Common Operations

### Query Recent Runs

```bash
sqlite3 D:\agent-metrics\db\telemetry.sqlite "SELECT run_id, agent_name, job_type, status, start_time FROM agent_runs ORDER BY start_time DESC LIMIT 20;"
```

### Query by Agent

```bash
sqlite3 D:\agent-metrics\db\telemetry.sqlite "SELECT COUNT(*), SUM(items_discovered), SUM(items_succeeded) FROM agent_runs WHERE agent_name = 'seo-intelligence';"
```

### Query Workflow Chain

```bash
sqlite3 D:\agent-metrics\db\telemetry.sqlite "SELECT run_id, job_type, status FROM agent_runs WHERE insight_id = '[insight_id]' ORDER BY start_time;"
```

### Create Backup

```bash
python scripts/backup_telemetry_db.py
```

**Backups stored:** `D:\agent-metrics\backups\`
**Retention:** 7 days

### View NDJSON Logs

```bash
type D:\agent-metrics\raw\events_20251211.ndjson | more
```

---

## Recovery Procedures

### Database Locked

**Symptoms:** "database is locked" errors
**Cause:** Concurrent write contention

**Recovery:**
1. Wait 30 seconds (auto-retry should resolve)
2. If persists, check for hanging processes:
   ```bash
   tasklist | findstr python
   ```
3. Kill any stalled Python processes
4. Retry operation

### Database Corrupted

**Symptoms:** "disk I/O error", "database disk image is malformed"

**Recovery:**
1. Stop all agents writing telemetry
2. Run integrity check:
   ```bash
   sqlite3 D:\agent-metrics\db\telemetry.sqlite "PRAGMA integrity_check;"
   ```
3. If not "ok", restore from backup:
   ```bash
   python scripts/backup_telemetry_db.py --restore D:\agent-metrics\backups\telemetry_backup_[latest].sqlite
   ```
4. Restart agents

### Disk Full

**Symptoms:** "No space left on device"

**Recovery:**
1. Check disk space:
   ```bash
   python -c "import shutil; total, used, free = shutil.disk_usage('D:\\'); print(f'Free: {free/(1024**3):.1f} GB')"
   ```
2. If < 1GB, archive old NDJSON files:
   ```bash
   cd D:\agent-metrics\raw
   # Compress files older than 30 days
   # Move to archive location
   ```
3. Consider moving metrics to larger disk

### No Recent Activity

**Symptoms:** Health check shows 0 runs in last hour

**Investigation:**
1. Check if agents are running
2. Check if telemetry integration working:
   ```python
   from telemetry import TelemetryClient
   client = TelemetryClient.from_env()
   with client.track_run("test", "healthcheck") as ctx:
       ctx.update_metrics(items_discovered=1)
   # Should complete without error
   ```
3. Check environment variable set:
   ```bash
   echo %AGENT_METRICS_DIR%
   ```

---

## Maintenance Tasks

### Weekly

- [ ] Run health check
- [ ] Review backup retention
- [ ] Check disk space trend

### Monthly

- [ ] Review database size growth
- [ ] Archive old NDJSON files (> 90 days)
- [ ] Update documentation if needed

### Quarterly

- [ ] Review query performance
- [ ] Consider adding indexes if queries slow
- [ ] Update retention policies if needed

---

## Performance Baselines

**Write Latency:** p95 < 50ms
**Query Latency:** Simple queries < 100ms
**Throughput:** > 20 writes/second
**Database Size:** ~100 bytes/run

**If metrics degrade:**
1. Run performance test: `python scripts/measure_performance.py`
2. Check for database fragmentation
3. Consider running VACUUM
4. Check disk I/O performance

---

## Escalation

### Level 1: Automated Monitoring
- Health check script failures → Alert

### Level 2: Manual Investigation
- Follow recovery procedures
- Check logs

### Level 3: Development Team
- If recovery procedures fail
- If data corruption
- If performance degradation

**Contact:** Development Team

---

## Emergency Procedures

### Complete System Failure

1. **Assess:** What's broken?
   - Storage inaccessible?
   - Database corrupted?
   - Disk full?

2. **Stabilize:** Stop agents from writing

3. **Restore:**
   - Restore database from latest backup
   - Verify integrity
   - Re-initialize if needed

4. **Verify:**
   ```bash
   python scripts/validate_installation.py
   ```

5. **Resume:** Restart agents

### Data Loss Recovery

**If backup exists:**
```bash
python scripts/backup_telemetry_db.py --restore [backup-file]
```

**If no backup:**
- NDJSON files contain all raw data
- Can rebuild database from NDJSON (script needed)
- Contact development team

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-11 | Initial runbook | Telemetry Team |
