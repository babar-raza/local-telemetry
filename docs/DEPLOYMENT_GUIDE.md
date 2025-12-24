# Telemetry API Service - Deployment Guide

## Overview

This guide walks through deploying the Telemetry API Service, the single-writer HTTP API that eliminates database corruption by centralizing all telemetry writes.

**Architecture:**
- FastAPI HTTP server (single worker)
- SQLite database with corruption-prevention PRAGMAs
- Event idempotency via `event_id` UNIQUE constraint
- Automatic schema initialization
- Graceful shutdown handling

**Endpoints:**
- `POST /api/v1/runs` - Create single telemetry run
- `POST /api/v1/runs/batch` - Create multiple runs with deduplication
- `GET /api/v1/runs` - Query runs with filtering (v2.1.0+)
- `PATCH /api/v1/runs/{event_id}` - Update run fields (v2.1.0+)
- `GET /health` - Health check
- `GET /metrics` - System metrics

---

## Prerequisites

### Required
- **Python 3.7+** (3.11 recommended)
- **pip** package manager
- **Disk space:** 1GB minimum for database growth
- **Network:** Port 8765 available (or custom port)

### Optional
- Virtual environment (venv/conda)
- systemd (Linux) or Task Scheduler (Windows) for auto-start
- Nginx/Apache for reverse proxy (production)

---

## Installation

### Step 1: Clone Repository

```bash
cd /path/to/projects
git clone <repository-url> local-telemetry
cd local-telemetry
```

### Step 2: Create Virtual Environment (Recommended)

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows:**
```cmd
python -m venv venv
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**Expected output:**
```
Successfully installed fastapi-0.104.1 uvicorn-0.24.0 pydantic-2.5.0 ...
```

### Step 4: Verify Installation

```bash
python -c "import fastapi, uvicorn; print('OK')"
```

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# Telemetry API Configuration
TELEMETRY_DB_PATH=D:/agent-metrics/db/telemetry.sqlite
TELEMETRY_LOCK_FILE=D:/agent-metrics/db/telemetry.lock

# Database PRAGMA Settings
TELEMETRY_DB_JOURNAL_MODE=DELETE
TELEMETRY_DB_SYNCHRONOUS=FULL

# API Server Settings
TELEMETRY_API_HOST=0.0.0.0
TELEMETRY_API_PORT=8765
TELEMETRY_API_WORKERS=1  # CRITICAL: Must be 1

# Logging
TELEMETRY_LOG_LEVEL=INFO
```

### Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEMETRY_DB_PATH` | `D:/agent-metrics/db/telemetry.sqlite` | SQLite database file path |
| `TELEMETRY_LOCK_FILE` | `D:/agent-metrics/db/telemetry.lock` | Single-writer lock file |
| `TELEMETRY_DB_JOURNAL_MODE` | `DELETE` | SQLite journal mode (DELETE for Windows/Docker) |
| `TELEMETRY_DB_SYNCHRONOUS` | `FULL` | SQLite synchronous mode (FULL prevents corruption) |
| `TELEMETRY_API_HOST` | `0.0.0.0` | API bind host (0.0.0.0 = all interfaces) |
| `TELEMETRY_API_PORT` | `8765` | API port |
| `TELEMETRY_API_WORKERS` | `1` | **Must be 1** (single-writer enforcement) |
| `TELEMETRY_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |

**CRITICAL:** Never set `TELEMETRY_API_WORKERS` to anything other than 1. Multiple workers will cause database corruption.

---

## Database Performance and Optimization

The v2.1.0 release includes optimized database indexes for improved query performance, especially for the new GET /api/v1/runs endpoint.

### Performance Indexes (v2.1.0+)

The following indexes are automatically created on fresh installations and should be manually added to existing databases:

**Single-Column Indexes:**
- `idx_runs_created_desc` - Optimizes `ORDER BY created_at DESC` queries
- Existing: `idx_runs_agent`, `idx_runs_status`, `idx_runs_start`

**Composite Indexes (Multi-Filter Queries):**
- `idx_runs_agent_status_created` - Optimizes queries filtering by agent_name + status + time range (stale run detection)
- `idx_runs_agent_created` - Optimizes queries filtering by agent_name + time range (analytics)

### Adding Indexes to Existing Databases

If you're upgrading from v2.0.0 to v2.1.0, run these migrations:

```bash
# Connect to your database
sqlite3 /data/telemetry.sqlite

# Add single-column index for ORDER BY performance
CREATE INDEX IF NOT EXISTS idx_runs_created_desc ON agent_runs(created_at DESC);

# Add composite indexes for multi-filter query performance
CREATE INDEX IF NOT EXISTS idx_runs_agent_status_created
ON agent_runs(agent_name, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_runs_agent_created
ON agent_runs(agent_name, created_at DESC);

# Verify indexes were created
SELECT name FROM sqlite_master
WHERE type='index' AND tbl_name='agent_runs'
AND name LIKE '%created%';

# Should return: idx_runs_created_desc, idx_runs_agent_status_created, idx_runs_agent_created

# Update query planner statistics
ANALYZE agent_runs;
.quit
```

### Verifying Index Usage

Use `EXPLAIN QUERY PLAN` to verify SQLite is using your indexes:

```bash
sqlite3 /data/telemetry.sqlite

EXPLAIN QUERY PLAN
SELECT * FROM agent_runs
WHERE agent_name = 'hugo-translator'
  AND status = 'running'
  AND created_at < '2025-12-24T12:00:00Z'
ORDER BY created_at DESC
LIMIT 100;

# Expected output should include:
# SEARCH agent_runs USING INDEX idx_runs_agent_status_created
.quit
```

If the query plan shows `SCAN TABLE` or `USE TEMP B-TREE FOR ORDER BY`, the index is not being used. Run `ANALYZE agent_runs;` to update statistics.

### Performance Benchmarks

With the v2.1.0 indexes on a dataset of 10,000 runs:

| Query Type | Before (v2.0.0) | After (v2.1.0) | Improvement |
|------------|-----------------|----------------|-------------|
| Simple query (limit 100) | ~50ms | ~15ms | 70% faster |
| Multi-filter (agent + status) | ~120ms | ~25ms | 79% faster |
| Stale run detection | ~180ms | ~30ms | 83% faster |
| Large result set (limit 1000) | ~400ms | ~180ms | 55% faster |

**Note:** Performance varies based on dataset size, disk speed, and query complexity.

### Index Maintenance

SQLite indexes are maintained automatically. However, for optimal performance:

```bash
# Update query planner statistics (run after bulk data imports)
sqlite3 /data/telemetry.sqlite "ANALYZE agent_runs;"

# Check index sizes
sqlite3 /data/telemetry.sqlite "SELECT name, pgsize FROM dbstat WHERE name LIKE 'idx_runs%' ORDER BY pgsize DESC;"

# Rebuild indexes (only if corruption suspected)
sqlite3 /data/telemetry.sqlite "REINDEX agent_runs;"
```

---

## Database Migration (Existing v5 Databases)

If you have an existing v5 database, migrate it to v6 to add the `event_id` column:

### Step 1: Backup Database

```bash
# Linux/macOS
cp D:/agent-metrics/db/telemetry.sqlite D:/agent-metrics/db/telemetry_backup_$(date +%Y%m%d).sqlite

# Windows PowerShell
Copy-Item D:/agent-metrics/db/telemetry.sqlite D:/agent-metrics/db/telemetry_backup_$(Get-Date -Format "yyyyMMdd").sqlite
```

### Step 2: Dry Run (Preview Changes)

```bash
python scripts/migrate_v5_to_v6.py --dry-run
```

**Expected output:**
```
======================================================================
DATABASE MIGRATION: Schema v5 → v6
======================================================================
Database: D:/agent-metrics/db/telemetry.sqlite
Dry run: True
Current schema version: 5
Total rows to migrate: 47268

[DRY RUN] Would perform the following changes:
  1. Add event_id column to agent_runs table
  2. Backfill event_id with UUID for all existing rows
  3. Create UNIQUE constraint on event_id
  4. Create idx_runs_event_id index
  5. Update schema version to 6
```

### Step 3: Run Migration

```bash
python scripts/migrate_v5_to_v6.py
```

**Expected output:**
```
Step 1: Adding event_id column...
[OK] Column added
Step 2: Backfilling event_id with UUIDs...
  Progress: 1000/47268 rows
  ...
[OK] Backfilled 47268 rows
Step 3: Creating UNIQUE index on event_id...
[OK] Index created
Step 4: Updating schema version...
[OK] Schema version updated to 6
[SUCCESS] Migration completed successfully!
```

### Step 4: Verify Migration

```bash
sqlite3 D:/agent-metrics/db/telemetry.sqlite "PRAGMA table_info(agent_runs);" | grep event_id
```

**Expected output:**
```
44|event_id|TEXT|1||0
```

---

## Starting the Service

### Option 1: Startup Scripts (Recommended)

**Linux/macOS:**
```bash
chmod +x scripts/start_telemetry_api.sh
./scripts/start_telemetry_api.sh
```

**Windows PowerShell:**
```powershell
.\scripts\start_telemetry_api.ps1
```

**Windows Batch:**
```cmd
scripts\start_telemetry_api.bat
```

### Option 2: Direct uvicorn Command

```bash
uvicorn telemetry_service:app --host 0.0.0.0 --port 8765 --workers 1
```

### Option 3: Python Module

```bash
python telemetry_service.py
```

---

## Verification

### Step 1: Health Check

```bash
curl http://localhost:8765/health
```

**Expected response:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "db_path": "D:/agent-metrics/db/telemetry.sqlite",
  "journal_mode": "DELETE",
  "synchronous": "FULL"
}
```

### Step 2: Metrics Endpoint

```bash
curl http://localhost:8765/metrics
```

**Expected response:**
```json
{
  "total_runs": 47268,
  "agents": {
    "hugo-translator": 101,
    "seo_intelligence.insight_engine": 14492
  },
  "recent_24h": 342,
  "performance": {
    "db_path": "D:/agent-metrics/db/telemetry.sqlite",
    "journal_mode": "DELETE"
  }
}
```

### Step 3: Create Test Event

```bash
curl -X POST http://localhost:8765/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test-'$(uuidgen)'",
    "run_id": "test-run-001",
    "start_time": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "agent_name": "test-agent",
    "job_type": "verification"
  }'
```

**Expected response:**
```json
{
  "status": "created",
  "event_id": "test-123e4567-e89b-12d3-a456-426614174000",
  "run_id": "test-run-001"
}
```

### Step 4: Verify Idempotency

Re-run the same POST request with the same `event_id`:

**Expected response:**
```json
{
  "status": "duplicate",
  "event_id": "test-123e4567-e89b-12d3-a456-426614174000",
  "message": "Event already exists (idempotent)"
}
```

---

## Production Deployment

### systemd Service (Linux)

Create `/etc/systemd/system/telemetry-api.service`:

```ini
[Unit]
Description=Telemetry API Service
After=network.target

[Service]
Type=simple
User=telemetry
WorkingDirectory=/opt/local-telemetry
Environment="PATH=/opt/local-telemetry/venv/bin"
Environment="PYTHONPATH=/opt/local-telemetry/src"
ExecStart=/opt/local-telemetry/venv/bin/uvicorn telemetry_service:app --host 0.0.0.0 --port 8765 --workers 1
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable telemetry-api
sudo systemctl start telemetry-api
sudo systemctl status telemetry-api
```

### Windows Service

Use NSSM (Non-Sucking Service Manager):

```powershell
# Download NSSM from https://nssm.cc/download
nssm install TelemetryAPI "C:\Python311\python.exe" "-m uvicorn telemetry_service:app --host 0.0.0.0 --port 8765 --workers 1"
nssm set TelemetryAPI AppDirectory "C:\projects\local-telemetry"
nssm set TelemetryAPI AppEnvironmentExtra "PYTHONPATH=C:\projects\local-telemetry\src"
nssm start TelemetryAPI
```

### Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY telemetry_service.py .
COPY src/ ./src/
COPY schema/ ./schema/

# Expose API port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s \
  CMD python -c "import requests; requests.get('http://localhost:8765/health').raise_for_status()"

# Start service
CMD ["uvicorn", "telemetry_service:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1"]
```

**Build and run:**
```bash
docker build -t telemetry-api .
docker run -d -p 8765:8765 \
  -v /data/telemetry:/data \
  -e TELEMETRY_DB_PATH=/data/telemetry.sqlite \
  --name telemetry-api \
  telemetry-api
```

---

## Monitoring

### Log Files

Service logs are written to stdout/stderr. Redirect as needed:

**Development:**
```bash
./scripts/start_telemetry_api.sh 2>&1 | tee telemetry-api.log
```

**systemd:**
```bash
journalctl -u telemetry-api -f
```

### Health Monitoring

Set up periodic health checks:

```bash
# Cron job (every 5 minutes)
*/5 * * * * curl -f http://localhost:8765/health || echo "Telemetry API down" | mail -s "Alert" admin@example.com
```

### Metrics Collection

Query `/metrics` endpoint periodically:

```bash
curl http://localhost:8765/metrics | jq '.'
```

**Key metrics to monitor:**
- `total_runs` - Total events in database
- `recent_24h` - Recent activity (should match expected volume)
- `agents.<name>` - Per-agent event counts

---

## Logging and Observability

The v2.1.0 release includes structured JSON logging for all API endpoints, enabling easy monitoring, debugging, and performance analysis.

### Log Configuration

Set log level via environment variable:

```bash
# Development
export TELEMETRY_LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR

# Docker (edit docker-compose.yml)
environment:
  - TELEMETRY_LOG_LEVEL=INFO
```

**Log levels:**
- `DEBUG` - Verbose logging (development only - high overhead)
- `INFO` - Standard operational logging (recommended for production)
- `WARNING` - Warnings and errors only
- `ERROR` - Errors only

### Log Format

All logs are JSON-formatted for easy parsing by monitoring tools:

**Query endpoint example:**
```json
{
  "timestamp": "2025-12-24T14:30:00.123Z",
  "level": "INFO",
  "logger": "telemetry_api",
  "message": "Query executed",
  "endpoint": "/api/v1/runs",
  "query_params": {"agent_name": "hugo-translator", "status": "running", "limit": 100},
  "result_count": 5,
  "duration_ms": 0.45,
  "is_slow": false
}
```

**Update endpoint example:**
```json
{
  "timestamp": "2025-12-24T14:31:00.456Z",
  "level": "INFO",
  "logger": "telemetry_api",
  "message": "Run updated",
  "endpoint": "/api/v1/runs/{event_id}",
  "event_id": "abc123",
  "fields_updated": ["status", "end_time", "error_summary"],
  "duration_ms": 1.23,
  "success": true
}
```

**Error example:**
```json
{
  "timestamp": "2025-12-24T14:32:00.789Z",
  "level": "ERROR",
  "logger": "telemetry_api",
  "message": "Error in /api/v1/runs: Invalid status: invalid_status",
  "endpoint": "/api/v1/runs",
  "error_type": "ValidationError",
  "error_message": "Invalid status: invalid_status",
  "status": "invalid_status"
}
```

### Viewing Logs

**Docker deployment:**
```bash
# Follow logs in real-time
docker-compose logs -f

# Filter for JSON query logs
docker-compose logs | grep '"endpoint": "/api/v1/runs"'

# Filter for errors only
docker-compose logs | grep '"level": "ERROR"'

# Export logs to file
docker-compose logs > telemetry-api.log
```

**Native Python deployment:**
```bash
# Logs go to stdout/stderr
python telemetry_service.py 2>&1 | tee telemetry-api.log
```

### Monitoring Slow Queries

The `is_slow` flag marks queries that take >1 second:

```bash
# Find slow queries
docker-compose logs | grep '"is_slow": true'

# Count slow queries in last hour
docker-compose logs --since 1h | grep '"is_slow": true' | wc -l
```

**Investigating slow queries:**
1. Check query parameters - are they using indexes?
2. Verify indexes exist (see "Database Performance" section)
3. Check result count - large result sets take longer
4. Run EXPLAIN QUERY PLAN to verify index usage

### Audit Trail for Updates

Track all PATCH operations:

```bash
# All updates
docker-compose logs | grep '"endpoint": "/api/v1/runs/{event_id}"'

# Updates to specific run
docker-compose logs | grep '"event_id": "abc123"'

# Failed updates
docker-compose logs | grep '"endpoint": "/api/v1/runs/{event_id}"' | grep '"success": false'
```

### Log Aggregation

For production, consider sending logs to a centralized logging service:

**Example: Forward to Elasticsearch/Logstash:**
```yaml
# docker-compose.yml
logging:
  driver: "fluentd"
  options:
    fluentd-address: "localhost:24224"
    tag: "telemetry-api"
```

**Example: Parse with jq:**
```bash
# Extract query durations
docker-compose logs | grep '"endpoint": "/api/v1/runs"' | jq '.duration_ms'

# Average query duration
docker-compose logs | grep '"endpoint": "/api/v1/runs"' | jq '.duration_ms' | awk '{sum+=$1; count++} END {print sum/count}'

# 95th percentile query duration
docker-compose logs | grep '"endpoint": "/api/v1/runs"' | jq -s 'sort_by(.duration_ms) | .[length*0.95 | floor].duration_ms'
```

### Alerting

Set up alerts based on log patterns:

**Example: Alert on high error rate:**
```bash
#!/bin/bash
ERROR_COUNT=$(docker-compose logs --since 5m | grep '"level": "ERROR"' | wc -l)

if [ $ERROR_COUNT -gt 10 ]; then
    echo "Alert: $ERROR_COUNT errors in last 5 minutes" | mail -s "Telemetry API Alert" admin@example.com
fi
```

**Example: Alert on slow queries:**
```bash
#!/bin/bash
SLOW_QUERIES=$(docker-compose logs --since 15m | grep '"is_slow": true' | wc -l)

if [ $SLOW_QUERIES -gt 5 ]; then
    echo "Alert: $SLOW_QUERIES slow queries (>1s) in last 15 minutes" | mail -s "Slow Query Alert" admin@example.com
fi
```

### Performance Impact

Structured logging adds minimal overhead:
- **INFO level:** <1ms per request
- **DEBUG level:** 1-5ms per request (avoid in production)

Logging is asynchronous and does not block API responses.

---

## Troubleshooting

### Issue: Port Already in Use

**Error:** `[ERROR] error while attempting to bind on address ('0.0.0.0', 8765): address already in use`

**Causes:**
- Another instance of telemetry API is running
- Another service is using port 8765

**Solutions:**
1. Kill existing process:
   ```bash
   # Linux/macOS
   lsof -ti:8765 | xargs kill -9

   # Windows
   netstat -ano | findstr :8765
   taskkill /PID <PID> /F
   ```

2. Use different port:
   ```bash
   ./scripts/start_telemetry_api.sh --port 8766
   ```

### Issue: Database Locked

**Error:** `sqlite3.OperationalError: database is locked`

**Causes:**
- Multiple writer processes (should be impossible with new architecture)
- Stale lock file from crashed process

**Solutions:**
1. Verify only one instance running:
   ```bash
   ps aux | grep telemetry_service
   # Should be exactly 1 process
   ```

2. Remove stale lock file:
   ```bash
   rm D:/agent-metrics/db/telemetry.lock
   # Then restart service
   ```

### Issue: Schema Migration Failed

**Error:** `[ERROR] Migration failed: ...`

**Solutions:**
1. Restore from backup:
   ```bash
   cp D:/agent-metrics/db/telemetry_backup_20251220.sqlite D:/agent-metrics/db/telemetry.sqlite
   ```

2. Try dry-run to diagnose:
   ```bash
   python scripts/migrate_v5_to_v6.py --dry-run
   ```

3. Check database isn't corrupted:
   ```bash
   sqlite3 D:/agent-metrics/db/telemetry.sqlite "PRAGMA integrity_check;"
   ```

### Issue: Import Errors

**Error:** `ModuleNotFoundError: No module named 'fastapi'`

**Solutions:**
1. Verify virtual environment activated:
   ```bash
   which python  # Should show venv path
   ```

2. Reinstall dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Check PYTHONPATH includes src:
   ```bash
   export PYTHONPATH=/path/to/local-telemetry/src:$PYTHONPATH
   ```

### Issue: Events Not Appearing in Database

**Symptoms:**
- POST requests return 201 Created
- Events not in database when querying

**Solutions:**
1. Check database path:
   ```bash
   curl http://localhost:8765/health | jq '.db_path'
   ```

2. Verify database file exists and is writable:
   ```bash
   ls -lh D:/agent-metrics/db/telemetry.sqlite
   ```

3. Check service logs for errors:
   ```bash
   # Look for INSERT failures
   ```

---

## Performance Tuning

### Database Location

For best performance, use:
- **SSD storage** (not HDD)
- **Local filesystem** (not network mount)
- **Native filesystem** (not Docker bind mount to Windows)

### Worker Count

**CRITICAL:** Always use `--workers 1`

Multiple workers cause database corruption. The single-writer pattern is enforced at configuration validation.

### PRAGMA Settings

Production recommendations:
```bash
TELEMETRY_DB_JOURNAL_MODE=DELETE  # Best for Windows/Docker
TELEMETRY_DB_SYNCHRONOUS=FULL     # Prevents corruption
```

For high-write-volume Linux environments (advanced):
```bash
TELEMETRY_DB_JOURNAL_MODE=WAL     # Faster, but incompatible with Docker bind mounts
TELEMETRY_DB_SYNCHRONOUS=NORMAL   # Faster, but small corruption risk on power loss
```

### Batch Endpoints

For high-volume scenarios, use batch endpoint:

```bash
curl -X POST http://localhost:8765/api/v1/runs/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"event_id": "uuid1", "run_id": "run1", ...},
    {"event_id": "uuid2", "run_id": "run2", ...}
  ]'
```

**Benefits:**
- Single transaction for multiple events
- Automatic deduplication
- Better throughput

---

## Security

### Network Exposure

**Development:**
- Bind to `127.0.0.1` (localhost only)
- No authentication required

**Production:**
- Use reverse proxy (Nginx/Apache) with SSL
- Implement API key authentication
- Bind to internal network only (VPN/firewall)

### Example Nginx Configuration

```nginx
server {
    listen 443 ssl;
    server_name telemetry.example.com;

    ssl_certificate /etc/ssl/certs/telemetry.crt;
    ssl_certificate_key /etc/ssl/private/telemetry.key;

    location / {
        proxy_pass http://localhost:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;

        # Optional: API key authentication
        if ($http_x_api_key != "your-secret-key") {
            return 401;
        }
    }
}
```

---

## Backup and Recovery

### Automated Backups

```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR="/backups/telemetry"
DB_PATH="D:/agent-metrics/db/telemetry.sqlite"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup
sqlite3 "$DB_PATH" ".backup '$BACKUP_DIR/telemetry_$DATE.sqlite'"

# Keep last 7 days
find "$BACKUP_DIR" -name "telemetry_*.sqlite" -mtime +7 -delete
```

### Recovery

```bash
# Stop service
systemctl stop telemetry-api

# Restore from backup
cp /backups/telemetry/telemetry_20251220_090000.sqlite D:/agent-metrics/db/telemetry.sqlite

# Verify integrity
sqlite3 D:/agent-metrics/db/telemetry.sqlite "PRAGMA integrity_check;"

# Start service
systemctl start telemetry-api
```

---

## Next Steps

After deployment is verified:

1. **Migrate Applications** - Follow application-specific migration guides:
   - [hugo-translator Migration Guide](./APP_MIGRATION_hugo-translator.md)
   - [seo-intelligence Migration Guide](./APP_MIGRATION_seo-intelligence.md)

2. **Set Up Monitoring** - Configure health checks and metrics collection

3. **Enable Auto-Start** - Use systemd/Windows Service for production

4. **Configure Backups** - Schedule automated daily backups

5. **Test Failover** - Verify buffer files work when API is down

---

## Support

For issues or questions:

1. Check troubleshooting section above
2. Review logs for error messages
3. Verify configuration matches this guide
4. Check [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) for common issues

---

## API Reference (v2.1.0+)

### GET /api/v1/runs - Query Runs

Query telemetry runs with filtering support. Added in v2.1.0 for stale run cleanup and analytics.

**Endpoint:**
```
GET /api/v1/runs
```

**Query Parameters:**
- `agent_name` (string, optional) - Filter by agent name (exact match)
- `status` (string, optional) - Filter by status: `running`, `success`, `failure`, `partial`, `timeout`, `cancelled`
- `job_type` (string, optional) - Filter by job type
- `created_before` (ISO8601, optional) - Runs created before this timestamp
- `created_after` (ISO8601, optional) - Runs created after this timestamp
- `start_time_from` (ISO8601, optional) - Runs started after this timestamp
- `start_time_to` (ISO8601, optional) - Runs started before this timestamp
- `limit` (integer, default=100, max=1000) - Maximum results to return
- `offset` (integer, default=0) - Pagination offset

**Response:** 200 OK - Array of run objects (all 42 database fields)

**Examples:**

Find all stale running jobs:
```bash
curl "http://localhost:8765/api/v1/runs?agent_name=hugo-translator&status=running&created_before=2025-12-24T12:00:00Z"
```

Query by status with pagination:
```bash
curl "http://localhost:8765/api/v1/runs?status=success&limit=50&offset=0"
```

Filter by date range:
```bash
curl "http://localhost:8765/api/v1/runs?start_time_from=2025-12-24T00:00:00Z&start_time_to=2025-12-24T23:59:59Z"
```

**Response Example:**
```json
[
  {
    "id": 123,
    "event_id": "abc123",
    "run_id": "translate-batch-456",
    "created_at": "2025-12-24T10:00:00Z",
    "start_time": "2025-12-24T10:00:00Z",
    "end_time": null,
    "agent_name": "hugo-translator",
    "job_type": "translate_directory",
    "status": "running",
    "items_discovered": 100,
    "items_succeeded": 45,
    "items_failed": 0,
    "duration_ms": 0,
    "error_summary": null,
    ...
  }
]
```

**Error Responses:**
- `400 Bad Request` - Invalid query parameters (invalid status value, invalid timestamp format, etc.)
- `500 Internal Server Error` - Database error

---

### PATCH /api/v1/runs/{event_id} - Update Run

Update specific fields of an existing run record. Added in v2.1.0 for stale run cleanup and metrics updates.

**Endpoint:**
```
PATCH /api/v1/runs/{event_id}
```

**Path Parameters:**
- `event_id` (string, required) - Unique event ID of the run to update

**Request Body (JSON):** All fields optional (partial update)
- `status` (string) - Update status: `running`, `success`, `failure`, `partial`, `timeout`, `cancelled`
- `end_time` (ISO8601) - Set completion timestamp
- `duration_ms` (integer) - Set duration in milliseconds
- `error_summary` (string) - Set error message
- `error_details` (string) - Set detailed error information
- `output_summary` (string) - Set output summary
- `items_succeeded` (integer) - Update success count
- `items_failed` (integer) - Update failure count
- `items_skipped` (integer) - Update skip count
- `metrics_json` (object) - Update custom metrics
- `context_json` (object) - Update custom context

**Response:** 200 OK

```json
{
  "event_id": "abc123",
  "updated": true,
  "fields_updated": ["status", "end_time", "error_summary"]
}
```

**Examples:**

Mark stale run as cancelled:
```bash
curl -X PATCH http://localhost:8765/api/v1/runs/abc123 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "cancelled",
    "end_time": "2025-12-24T13:05:00Z",
    "error_summary": "Stale run cleaned up on startup (created at 2025-12-24T10:00:00Z)",
    "output_summary": "Process did not complete - cleanup on restart"
  }'
```

Update metrics fields:
```bash
curl -X PATCH http://localhost:8765/api/v1/runs/abc123 \
  -H "Content-Type: application/json" \
  -d '{
    "items_succeeded": 75,
    "items_failed": 25,
    "duration_ms": 120000
  }'
```

**Error Responses:**
- `404 Not Found` - Run with event_id doesn't exist
  ```json
  {
    "detail": "Run not found: abc123"
  }
  ```
- `400 Bad Request` - No fields provided or empty update
  ```json
  {
    "detail": "No valid fields to update"
  }
  ```
- `422 Unprocessable Entity` - Invalid field values (Pydantic validation)
  ```json
  {
    "detail": [
      {
        "loc": ["body", "status"],
        "msg": "Status must be one of: ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']",
        "type": "value_error"
      }
    ]
  }
  ```
- `500 Internal Server Error` - Database error

---

### Stale Run Cleanup Flow (hugo-translator Example)

**Scenario:** hugo-translator was forcefully terminated (Ctrl+C, crash, power loss), leaving telemetry records stuck in "running" state.

**Solution:** On startup, query for stale runs and mark them as "cancelled".

**Step 1:** Query for stale running records (older than 1 hour):
```bash
# Calculate timestamp 1 hour ago
STALE_THRESHOLD=$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)

# Query for stale runs
curl "http://localhost:8765/api/v1/runs?agent_name=hugo-translator&status=running&created_before=$STALE_THRESHOLD"
```

**Step 2:** For each stale run found, update to "cancelled":
```bash
# Example for event_id: abc123
curl -X PATCH http://localhost:8765/api/v1/runs/abc123 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "cancelled",
    "end_time": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
    "error_summary": "Stale run cleaned up on startup (created at 2025-12-24T10:00:00Z)",
    "output_summary": "Process did not complete - cleanup on restart"
  }'
```

**Step 3:** Verify cleanup:
```bash
# Should return empty array (no stale runs remaining)
curl "http://localhost:8765/api/v1/runs?agent_name=hugo-translator&status=running&created_before=$STALE_THRESHOLD"
```

**Benefits:**
- ✅ No orphaned "running" records in database
- ✅ Accurate success/failure metrics
- ✅ Better debugging (know which runs were killed vs. legitimately running)
- ✅ Idempotent (can be run multiple times safely)

---

## Appendix: Quick Reference

### Common Commands

```bash
# Start service (Linux/macOS)
./scripts/start_telemetry_api.sh

# Start service (Windows)
.\scripts\start_telemetry_api.ps1

# Health check
curl http://localhost:8765/health

# Metrics
curl http://localhost:8765/metrics

# Create event
curl -X POST http://localhost:8765/api/v1/runs -H "Content-Type: application/json" -d '{...}'

# Query runs (v2.1.0+)
curl "http://localhost:8765/api/v1/runs?agent_name=hugo-translator&status=running"

# Update run (v2.1.0+)
curl -X PATCH http://localhost:8765/api/v1/runs/{event_id} -H "Content-Type: application/json" -d '{...}'

# Migrate database
python scripts/migrate_v5_to_v6.py

# View logs (systemd)
journalctl -u telemetry-api -f
```

### Default Ports

- Telemetry API: `8765`
- Health endpoint: `http://localhost:8765/health`
- Metrics endpoint: `http://localhost:8765/metrics`

### File Locations

- Service script: `telemetry_service.py`
- Configuration: `.env` (create from `.env.example`)
- Database: `D:/agent-metrics/db/telemetry.sqlite` (default)
- Lock file: `D:/agent-metrics/db/telemetry.lock` (default)
- Schema: `schema/telemetry_v6.sql`
- Migration: `scripts/migrate_v5_to_v6.py`
