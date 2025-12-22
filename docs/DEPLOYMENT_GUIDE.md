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
