# Troubleshooting Guide

## Installation Issues

### "No module named 'telemetry'"

**Cause:** Package not installed
**Fix:** `pip install -e .` from project root

### "Directory does not exist"

**Cause:** Storage not initialized
**Fix:** `python scripts/setup_storage.py`

## Runtime Issues

### "Database is locked"

**Cause:** Concurrent write contention
**Fix:** Should resolve automatically (retry logic). If persistent, check for hanging processes.

### "Permission denied" when writing

**Cause:** No write permissions to D:\agent-metrics
**Fix:** Run as administrator or check folder permissions

### Telemetry not appearing

**Checklist:**
1. Is storage initialized? `dir D:\agent-metrics`
2. Does database exist? `dir D:\agent-metrics\db\telemetry.sqlite`
3. Can you import telemetry? `python -c "import telemetry; print('OK')"`
4. Is AGENT_METRICS_DIR set (optional)? `echo %AGENT_METRICS_DIR%`

## Data Issues

### Wrong data in database

Query recent runs:
```bash
sqlite3 D:\agent-metrics\db\telemetry.sqlite "SELECT * FROM agent_runs ORDER BY start_time DESC LIMIT 10;"
```

### Database too large

Current size:
```bash
python -c "from pathlib import Path; size_mb = Path('D:\\agent-metrics\\db\\telemetry.sqlite').stat().st_size / (1024**2); print(f'{size_mb:.1f} MB')"
```

If > 500MB, consider archiving old data.

## Performance Issues

### Slow writes

Run performance test:
```bash
python scripts/measure_performance.py
```

If p95 > 100ms, check:
- Disk speed
- Antivirus interference
- Database fragmentation

### Slow queries

Add indexes:
```sql
CREATE INDEX idx_agent_runs_agent_name ON agent_runs(agent_name);
CREATE INDEX idx_agent_runs_start_time ON agent_runs(start_time);
CREATE INDEX idx_agent_runs_insight_id ON agent_runs(insight_id);
```

## Getting Help

1. Run health check: `python scripts/monitor_telemetry_health.py`
2. Check logs: `type D:\agent-metrics\logs\*.log`
3. Run validation: `python scripts/validate_installation.py`
4. Report issue with output from above
