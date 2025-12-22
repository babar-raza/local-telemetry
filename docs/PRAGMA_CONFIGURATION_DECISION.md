# PRAGMA Configuration Decision: DELETE vs WAL Mode

**Date:** 2025-12-19
**Decision:** Use `journal_mode=DELETE` for production
**Status:** Final

---

## Executive Summary

After testing and analysis, we've chosen **DELETE mode** over WAL mode for the production telemetry database due to **Docker compatibility requirements**. This decision maintains corruption prevention while ensuring universal deployment compatibility.

---

## Critical PRAGMA Settings (Production)

```python
PRAGMA busy_timeout=30000      # 30s timeout for lock contention
PRAGMA journal_mode=DELETE     # Docker-compatible journaling
PRAGMA synchronous=FULL        # CRITICAL: Prevents corruption on crashes
```

**Key insight:** `synchronous=FULL` is the critical setting for corruption prevention, not the journal mode.

---

## Journal Mode Comparison

### DELETE Mode (Production Choice) ✅

**Advantages:**
- ✅ **Universal compatibility** - Works everywhere (Windows, Linux, macOS, Docker)
- ✅ **No special file system requirements**
- ✅ **Safe with network mounts** (NFS, CIFS, SMB)
- ✅ **Docker volume compatible** - No issues with shared memory files
- ✅ **Simpler recovery** - Single database file
- ✅ **Container restart safe** - No orphaned -shm or -wal files
- ✅ **Safe with synchronous=FULL** - Corruption prevention guaranteed

**Disadvantages:**
- ⚠️ Slightly slower concurrent writes (acceptable for our use case)
- ⚠️ Brief write locks (mitigated by busy_timeout=30000)

**Use cases:**
- Docker containers (our primary deployment)
- Network file systems
- Environments with frequent container restarts
- Multi-platform deployments

---

### WAL Mode (Not Used) ❌

**Advantages:**
- ✅ Better concurrent read/write performance
- ✅ Faster write operations
- ✅ Readers don't block writers

**Disadvantages:**
- ❌ **Docker compatibility issues**
  - Shared memory (-shm) file problems on volume mounts
  - WAL file can be lost on unclean container shutdown
  - Issues with Windows Docker Desktop volumes
- ❌ **Network file system problems**
  - NFS/CIFS don't properly support -shm files
  - Locking issues on network mounts
- ❌ **Complexity**
  - Requires 3 files: .sqlite, .sqlite-shm, .sqlite-wal
  - Checkpoint management needed
  - Recovery more complex
- ❌ **Container restart risks**
  - -shm and -wal files can become orphaned
  - Potential data loss on hard stops

**Why not used:**
- seo-intelligence runs in Docker containers
- Database on Windows volume mount (D:\agent-metrics)
- Docker Desktop + Windows volumes = WAL mode issues

---

## Docker Compatibility Issues with WAL

### Problem 1: Shared Memory File (-shm)

WAL mode creates a `-shm` (shared memory) file that:
- Requires proper shared memory support
- Fails on Windows Docker volumes
- Gets orphaned on container crashes
- Causes "database is locked" errors

### Problem 2: Volume Mount Challenges

```yaml
volumes:
  - D:/agent-metrics:/agent-metrics
```

**Issues:**
- Windows → Linux container shared memory incompatibility
- Docker Desktop uses VM layer, -shm files don't sync properly
- Container restarts can leave stale -shm files

### Problem 3: Unclean Shutdowns

When containers stop (docker-compose down, crashes, kills):
- WAL file may not get checkpointed
- -shm file becomes stale
- Next container start may fail to recover properly

---

## Testing Results

### DELETE Mode Performance

**Test:** 6 SEO Intelligence runs in 1 hour
- ✅ All 6 completed successfully (100% success rate)
- ✅ No "database is locked" errors
- ✅ Database integrity: OK
- ✅ busy_timeout=30000ms prevents lock timeouts

**Conclusion:** DELETE mode with synchronous=FULL and busy_timeout=30000 provides:
- Corruption prevention
- Acceptable performance
- Universal compatibility

### WAL Mode Issues Encountered

**Test environment:** Docker container with Windows volume mount
- ❌ Intermittent "database is locked" errors
- ❌ Orphaned -shm files after container restart
- ❌ Recovery issues requiring manual -shm deletion

---

## Corruption Prevention Hierarchy

**Priority 1: synchronous=FULL** ⭐ **CRITICAL**
- Ensures all writes are fully committed to disk
- Prevents corruption on crashes, power failures, hard stops
- **This is the key setting, not journal_mode**

**Priority 2: busy_timeout=30000**
- Prevents "database is locked" errors
- Allows time for lock contention to resolve
- 30 seconds handles all reasonable concurrent access

**Priority 3: journal_mode=DELETE**
- Standard journaling mechanism
- Works everywhere
- Safe with synchronous=FULL

---

## Configuration Files

### database.py (Production)

```python
def _get_connection(self):
    conn = sqlite3.connect(self.database_path)

    # Corruption prevention settings (production-grade)
    conn.execute("PRAGMA busy_timeout=30000")  # Wait 30s for locks
    conn.execute("PRAGMA journal_mode=DELETE") # Docker-compatible
    conn.execute("PRAGMA synchronous=FULL")    # CRITICAL: Prevent corruption

    return conn
```

### Why This Works

1. **synchronous=FULL** - Every write is fully committed before continuing
   - Crash during write? Journal can recover
   - Power failure? Data is on disk
   - Container kill? Transaction is complete

2. **busy_timeout=30000** - Concurrent access handled gracefully
   - Writer holding lock? Other writers wait 30s
   - Prevents "database is locked" errors
   - Sufficient for all realistic concurrent access patterns

3. **journal_mode=DELETE** - Universal compatibility
   - Works in Docker
   - Works on Windows volume mounts
   - Works on network file systems
   - Simpler recovery

---

## Alternative Considered: WAL with Workarounds

**Option:** Use WAL mode with special Docker configuration

**Rejected because:**
- Requires tmpfs mount for -shm file (complex setup)
- Need manual -shm cleanup on container restarts
- Checkpoint management complexity
- Not compatible with Windows host volumes
- Over-engineering for our access patterns

**Example rejected approach:**
```yaml
volumes:
  - D:/agent-metrics:/agent-metrics
  - type: tmpfs
    target: /agent-metrics/db/shm  # Complex workaround
```

---

## Future Considerations

### If We Move Away from Docker

If deployment changes to:
- Native processes (no containers)
- Linux-only deployment
- Local file systems (not network mounts)

Then **WAL mode could be reconsidered** for better concurrency.

### Migration Path to WAL (If Needed)

```python
# One-time migration script
import sqlite3
conn = sqlite3.connect('/agent-metrics/db/telemetry.sqlite')
conn.execute("PRAGMA journal_mode=WAL")
conn.close()
```

**Requirements for WAL mode:**
- ✅ No Docker containers
- ✅ Local file system (not NFS/CIFS)
- ✅ Proper shared memory support
- ✅ File system supports mmap

---

## Validation

### How to Verify Current Settings

```bash
cd C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry
python scripts/diagnose_pragma_settings.py
```

**Expected output:**
```
Expected production values (Docker-compatible):
  busy_timeout:       30000 ms
  journal_mode:       delete (Docker-compatible)
  synchronous:        2 (FULL) - CRITICAL for corruption prevention
  wal_autocheckpoint: 1000 (N/A in DELETE mode)

[OK] All connection methods show consistent production settings!
```

### Database Health Check

```bash
python scripts/check_db_integrity.py
```

**Expected output:**
```
[OK] Database integrity check passed: ok
```

---

## Related Documentation

- **SR-01:** PRAGMA Verification Logging (original corruption fix)
- **SR-02:** busy_timeout Discrepancy Investigation
- **VAL-04:** PRAGMA Diagnostic Integration
- **TROUBLESHOOTING.md:** Diagnostic procedures

---

## Decision Matrix

| Criterion | DELETE Mode | WAL Mode | Winner |
|-----------|-------------|----------|--------|
| Docker compatible | ✅ Yes | ❌ No | DELETE |
| Windows volume mount | ✅ Yes | ❌ No | DELETE |
| Corruption prevention | ✅ Yes (with sync=FULL) | ✅ Yes | Tie |
| Concurrent reads | ✅ Good | ✅ Better | WAL |
| Concurrent writes | ⚠️ Fair | ✅ Good | WAL |
| Simplicity | ✅ Simple (1 file) | ⚠️ Complex (3 files) | DELETE |
| Recovery | ✅ Simple | ⚠️ Complex | DELETE |
| File system requirements | ✅ None | ❌ Many | DELETE |

**Overall winner: DELETE mode** (6-2 in favor)

---

## Summary

**Configuration:**
```python
PRAGMA busy_timeout=30000
PRAGMA journal_mode=DELETE
PRAGMA synchronous=FULL     # CRITICAL
```

**Why:**
- ✅ Docker compatible
- ✅ Prevents corruption (synchronous=FULL)
- ✅ Handles concurrent access (busy_timeout=30000)
- ✅ Universal compatibility
- ✅ Production tested and validated

**Performance:**
- 100% success rate in testing
- No "database is locked" errors
- Database integrity maintained
- Acceptable for our write patterns (agent telemetry)

**Recommendation:** Keep DELETE mode for all production deployments using Docker.
