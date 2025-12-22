# Troubleshooting Guide - Local Telemetry Platform

## When to Run Diagnostic Scripts

This platform includes several diagnostic scripts to help identify and resolve issues. Here's when to use each:

### Daily/Regular Operations

**Run validation before critical operations:**
```bash
python scripts/validate_installation.py
```

**When to run:**
- Before deploying to a new environment
- After system updates or configuration changes
- As part of daily health checks
- Before running large batch operations

**What it checks:**
- Python environment and dependencies
- Storage directories and permissions
- Database schema and PRAGMA settings (automatic)
- Configuration validity
- Test suite availability

### When You Suspect Issues

**Run PRAGMA diagnostic if you see:**
- "database is locked" errors
- Database corruption messages
- Unexpected PRAGMA values in logs
- Performance degradation

```bash
python scripts/diagnose_pragma_settings.py
```

**What it shows:**
- Raw connection settings (SQLite defaults)
- DatabaseWriter settings (production)
- TelemetryClient settings
- Discrepancies between connection methods

**Run database integrity check if you suspect corruption:**
```bash
python scripts/check_db_integrity.py
```

**When to run:**
- After system crashes or power loss
- Before/after database migrations
- When seeing "malformed database" errors
- As part of backup validation

### Recommended Schedule

| Script | Frequency | Purpose |
|--------|-----------|---------|
| `validate_installation.py` | Daily / Before deploys | Comprehensive health check |
| `diagnose_pragma_settings.py` | On-demand (when issues occur) | Deep PRAGMA analysis |
| `check_db_integrity.py` | Weekly / After crashes | Corruption detection |

### Integration with CI/CD

The validation script is designed to run in CI/CD pipelines:

```yaml
# Example GitHub Actions
- name: Validate Installation
  run: python scripts/validate_installation.py
```

Exit codes:
- `0` - All checks passed
- `1` - One or more checks failed (CI should fail)

---

## Database PRAGMA Settings

### Problem: PRAGMA Settings Not Applied or Show Incorrect Values

**Symptoms:**
- Database operations fail with "database locked" errors
- Database corrupts after system crashes
- PRAGMA verification logs show unexpected values
- Performance issues with database writes

**Root Cause:**

SQLite PRAGMA settings are **per-connection**, not database-wide. This means:

1. Each new `sqlite3.connect()` call starts with SQLite defaults
2. PRAGMA settings must be set on **every** new connection
3. Testing with raw connections won't show production settings
4. Connection pooling can cause old settings to persist

**How to Verify Settings:**

Run the diagnostic script:

```bash
python scripts/diagnose_pragma_settings.py
```

This will test three connection methods:
1. Raw `sqlite3.connect()` - Shows SQLite defaults
2. `DatabaseWriter._get_connection()` - Shows our production settings
3. `TelemetryClient` - Should match DatabaseWriter

**Expected Production Values:**

| Setting | Value | Purpose |
|---------|-------|---------|
| `busy_timeout` | 30000 ms | Waits 30 seconds for locks (handles concurrent access) |
| `journal_mode` | WAL | Write-Ahead Logging (enables concurrent readers) |
| `synchronous` | 2 (FULL) | **CRITICAL**: Prevents corruption on system crashes |
| `wal_autocheckpoint` | 100 | Checkpoints every 100 pages (~400 KB) to prevent WAL bloat |

**Why synchronous=FULL is Critical:**

- `synchronous=OFF` (0): Fastest, but **very high corruption risk**
- `synchronous=NORMAL` (1): Fast, but **can corrupt on crashes** ❌
- `synchronous=FULL` (2): Safe, survives crashes ✅ (production setting)
- `synchronous=EXTRA` (3): Maximum safety, slower

**Common Causes of Discrepancies:**

#### 1. Testing with Raw Connections

**Problem:**
```python
# This won't have our PRAGMA settings!
conn = sqlite3.connect("D:/agent-metrics/db/telemetry.sqlite")
cursor = conn.cursor()
cursor.execute("PRAGMA busy_timeout").fetchone()[0]  # Returns 0, not 30000
```

**Solution:**
Always use `DatabaseWriter` or `TelemetryClient`:
```python
from telemetry.database import DatabaseWriter
writer = DatabaseWriter(Path("D:/agent-metrics/db/telemetry.sqlite"))
conn = writer._get_connection()  # Has correct PRAGMA settings
```

#### 2. Old Connections Before Code Fix

**Problem:** Testing with connections created before the PRAGMA fix was applied.

**Solution:**
- Restart the application
- Create new `TelemetryClient()` instances
- All new connections will have correct settings

#### 3. Connection Pooling

**Problem:** If using connection pooling, old connections may be reused with old settings.

**Solution:** Current implementation doesn't use connection pooling, so this shouldn't occur. If you add pooling, ensure PRAGMAs are reset on connection reuse.

#### 4. External Tools

**Problem:** Using `sqlite3` CLI or DB Browser connects without our PRAGMA settings.

**Solution:** When using external tools, manually set PRAGMAs:
```sql
PRAGMA busy_timeout=30000;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA wal_autocheckpoint=100;
```

### Verification Checklist

When troubleshooting PRAGMA issues, verify:

1. **Check logs** - Look for "SQLite PRAGMA settings" in application logs
   ```bash
   python -c "import logging; logging.basicConfig(level=logging.INFO); from telemetry import TelemetryClient; TelemetryClient()" 2>&1 | grep PRAGMA
   ```

2. **Run diagnostic** - Use the diagnostic script (auto-detects database path)
   ```bash
   python scripts/diagnose_pragma_settings.py
   ```
   The script uses `TelemetryConfig.from_env()` to auto-detect the database location.
   You can override with environment variables:
   - `TELEMETRY_DB_PATH` - Direct path to database file
   - `TELEMETRY_BASE_DIR` - Base directory (database at `{base}/db/telemetry.sqlite`)

3. **Verify in code** - Confirm `_get_connection()` sets all 4 PRAGMAs
   - File: `src/telemetry/database.py`
   - Lines: ~101-105

4. **Check for warnings** - Look for PRAGMA mismatch warnings in logs
   ```bash
   python -c "from telemetry import TelemetryClient; TelemetryClient()" 2>&1 | grep -i warning
   ```

### Resolution Steps

If PRAGMA settings are incorrect:

1. **Verify code is up-to-date:**
   ```bash
   grep "synchronous=FULL" src/telemetry/database.py
   # Should show: conn.execute("PRAGMA synchronous=FULL")
   ```

2. **Check for multiple code paths:**
   - Search codebase for other `sqlite3.connect()` calls
   - Ensure all use `DatabaseWriter._get_connection()`

3. **Test with fresh connection:**
   ```python
   from telemetry import TelemetryClient
   client = TelemetryClient()
   # Check logs for PRAGMA settings
   ```

4. **Verify WAL files cleaned up:**
   ```bash
   ls -lh D:\agent-metrics\db\*.sqlite-wal
   # Should be small (<1 MB) or non-existent
   ```

---

## Database Corruption

### Problem: "database disk image is malformed"

**Immediate Actions:**

1. **Stop all database access** - Close all applications using the database

2. **Run recovery script:**
   ```bash
   python scripts/recover_from_backup.py
   ```

3. **If no backup available:**
   ```bash
   python scripts/recover_database.py --rebuild-from-ndjson
   ```

**Prevention:**

The corruption prevention fixes are now in place:
- `synchronous=FULL` - Database survives crashes
- `wal_autocheckpoint=100` - Prevents large WAL files
- `busy_timeout=30000` - Handles concurrent access

Verify these are applied: `python scripts/diagnose_pragma_settings.py`

**See Also:**
- [Database Corruption Root Cause Analysis](DATABASE_CORRUPTION_ROOT_CAUSE.md)
- [Recovery Documentation](../CORRUPTION_RESOLVED.md)

---

## Performance Issues

### Problem: Database writes are slow

**Diagnosis:**

1. **Check PRAGMA settings:**
   ```bash
   python scripts/diagnose_pragma_settings.py
   ```

2. **Benchmark performance:**
   ```bash
   python scripts/benchmark_db_performance.py --operations 1000
   ```

**Expected Performance:**
- ≥100 inserts/sec with `synchronous=FULL`
- ≥500 reads/sec

**Tuning Options:**

If performance is unacceptable:

1. **Batch operations** - Group multiple inserts in one transaction
2. **Use PASSIVE checkpoints** - Non-blocking WAL checkpoints
3. **Increase checkpoint interval** - If <100 causes issues (not recommended)

**Do NOT:**
- Change `synchronous` back to NORMAL (corruption risk)
- Disable WAL mode (loses concurrent access)
- Reduce `busy_timeout` (causes lock errors)

---

## Concurrent Access Issues

### Problem: "database is locked" errors

**Diagnosis:**

Check `busy_timeout` setting:
```bash
python scripts/diagnose_pragma_settings.py | grep busy_timeout
```

Should show: `busy_timeout: 30000 ms`

**Common Causes:**

1. **Operation exceeds timeout** - Rare with 30-second timeout
2. **WAL mode not enabled** - Check `journal_mode=wal`
3. **Exclusive lock held** - Check for long-running transactions

**Solutions:**

1. **Verify WAL mode:**
   ```python
   import sqlite3
   conn = sqlite3.connect("D:/agent-metrics/db/telemetry.sqlite")
   print(conn.execute("PRAGMA journal_mode").fetchone())  # Should be 'wal'
   ```

2. **Check for stuck processes:**
   - Look for `.sqlite-shm` or `.sqlite-wal` files
   - These indicate active connections

3. **Increase timeout** (if needed):
   - Edit `src/telemetry/database.py`
   - Change `PRAGMA busy_timeout=30000` to higher value

---

## Getting Help

If issues persist after following this guide:

1. **Collect diagnostics:**
   ```bash
   python scripts/diagnose_pragma_settings.py > diagnostics.txt
   python scripts/check_db_integrity.py >> diagnostics.txt
   python scripts/validate_installation.py >> diagnostics.txt
   ```

2. **Check application logs** for PRAGMA warnings

3. **Review recent changes** to database code

4. **Consult documentation:**
   - [SQLite PRAGMA Documentation](https://www.sqlite.org/pragma.html)
   - [WAL Mode Guide](https://www.sqlite.org/wal.html)
   - [Corruption Prevention](https://www.sqlite.org/howtocorrupt.html)
