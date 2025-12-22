# Telemetry API Service - Docker Deployment Guide

## Overview

This guide covers deploying the Telemetry API Service as a Docker container that runs continuously in the background. This is the recommended production deployment method.

**Benefits of Docker Deployment:**
- ✅ Always running (automatic restart on failure)
- ✅ Isolated environment (no dependency conflicts)
- ✅ Easy to start/stop/update
- ✅ Persistent data via Docker volumes
- ✅ Resource limits and monitoring
- ✅ Simple backup and migration

---

## Prerequisites

### Required Software

1. **Docker Desktop** (Windows/macOS) or **Docker Engine** (Linux)
   - Download: https://www.docker.com/products/docker-desktop
   - Minimum version: Docker 20.10+
   - Verify: `docker --version`

2. **Docker Compose**
   - Included with Docker Desktop
   - Verify: `docker compose version`

### System Requirements

- **CPU:** 1 core minimum (2+ cores recommended)
- **RAM:** 512MB minimum (1GB+ recommended)
- **Disk:** 2GB minimum for container + database growth
- **Network:** Port 8765 available

---

## Quick Start (5 Minutes)

### Step 1: Navigate to Project Directory

```bash
cd c:\Users\prora\OneDrive\Documents\GitHub\local-telemetry
```

### Step 2: Build and Start Container

```bash
docker compose up -d
```

**What this does:**
- Builds the Docker image from Dockerfile
- Creates and starts the container in detached mode (-d)
- Creates Docker volume for persistent data
- Exposes port 8765 on your host

**Expected output:**
```
[+] Building 45.2s (15/15) FINISHED
[+] Running 2/2
 ✔ Network telemetry-network      Created
 ✔ Container telemetry-api         Started
```

### Step 3: Verify Service is Running

```bash
# Check container status
docker compose ps

# Should show:
# NAME            STATUS          PORTS
# telemetry-api   Up (healthy)    0.0.0.0:8765->8765/tcp
```

### Step 4: Test Health Endpoint

```bash
curl http://localhost:8765/health
```

**Expected response:**
```json
{
  "status": "ok",
  "version": "2.0.0",
  "db_path": "/data/telemetry.sqlite",
  "journal_mode": "DELETE",
  "synchronous": "FULL"
}
```

**🎉 You're done! The service is now running continuously.**

---

## Detailed Setup

### File Structure

```
local-telemetry/
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # Service orchestration
├── .dockerignore             # Build exclusions
├── telemetry_service.py      # FastAPI application
├── requirements.txt          # Python dependencies
├── src/                      # Source code
│   └── telemetry/
│       ├── client.py
│       ├── config.py
│       ├── database.py
│       └── ...
└── schema/
    └── telemetry_v6.sql      # Database schema
```

### Dockerfile Explanation

```dockerfile
FROM python:3.11-slim          # Base image (minimal Python)

# Install system dependencies (curl for health checks, sqlite3 for debugging)
RUN apt-get update && apt-get install -y curl sqlite3

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY telemetry_service.py src/ schema/ ./

# Configuration via environment variables
ENV TELEMETRY_DB_PATH=/data/telemetry.sqlite
ENV TELEMETRY_API_WORKERS=1  # CRITICAL: Single writer

# Health check (runs every 30s)
HEALTHCHECK CMD curl -f http://localhost:8765/health

# Start uvicorn server
CMD ["uvicorn", "telemetry_service:app", "--host", "0.0.0.0", "--port", "8765"]
```

### docker-compose.yml Explanation

```yaml
services:
  telemetry-api:
    build: .                    # Build from current directory
    container_name: telemetry-api
    ports:
      - "8765:8765"             # Expose port 8765
    volumes:
      - telemetry-data:/data    # Persistent Docker volume
    restart: unless-stopped      # Auto-restart on failure
    healthcheck:                # Monitor service health
      test: ["CMD", "curl", "-f", "http://localhost:8765/health"]
      interval: 30s
    deploy:
      resources:
        limits:
          cpus: '1.0'           # Resource limits
          memory: 512M

volumes:
  telemetry-data:               # Named volume for database
```

---

## Common Operations

### Starting the Service

```bash
# Start in detached mode (background)
docker compose up -d

# Start with logs visible (foreground)
docker compose up

# Start and rebuild image if code changed
docker compose up -d --build
```

### Stopping the Service

```bash
# Stop container (keeps data)
docker compose stop

# Stop and remove container (keeps data volume)
docker compose down

# Stop and remove everything including volumes (DANGER: deletes database!)
docker compose down -v
```

### Viewing Logs

```bash
# View all logs
docker compose logs

# Follow logs in real-time
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Filter by time
docker compose logs --since 30m
```

### Restarting the Service

```bash
# Restart container
docker compose restart

# Restart after code changes
docker compose down
docker compose up -d --build
```

### Checking Status

```bash
# Container status
docker compose ps

# Detailed container info
docker inspect telemetry-api

# Resource usage (CPU, memory)
docker stats telemetry-api

# Health check status
docker inspect telemetry-api | grep -A 10 Health
```

---

## Database Management

### Accessing the Database

```bash
# Connect to SQLite database inside container
docker compose exec telemetry-api sqlite3 /data/telemetry.sqlite

# Run a query
docker compose exec telemetry-api sqlite3 /data/telemetry.sqlite "SELECT COUNT(*) FROM agent_runs;"

# Check schema version
docker compose exec telemetry-api sqlite3 /data/telemetry.sqlite "SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1;"
```

### Backing Up the Database

```bash
# Copy database from container to host
docker compose cp telemetry-api:/data/telemetry.sqlite ./backup_$(date +%Y%m%d).sqlite

# Create backup using SQLite .backup command
docker compose exec telemetry-api sqlite3 /data/telemetry.sqlite ".backup /data/telemetry_backup.sqlite"
docker compose cp telemetry-api:/data/telemetry_backup.sqlite ./
```

### Restoring from Backup

```bash
# Stop service
docker compose stop

# Copy backup into container
docker compose cp ./backup_20251220.sqlite telemetry-api:/data/telemetry.sqlite

# Start service
docker compose start
```

### Migrating Existing Database to Docker

If you have an existing database at `D:/agent-metrics/db/telemetry.sqlite`:

**Option 1: Copy into Docker volume**

```bash
# Start container first
docker compose up -d

# Copy database into container
docker compose cp D:/agent-metrics/db/telemetry.sqlite telemetry-api:/data/telemetry.sqlite

# Restart to apply
docker compose restart
```

**Option 2: Mount Windows directory temporarily**

Edit `docker-compose.yml`:

```yaml
volumes:
  - telemetry-data:/data
  - D:/agent-metrics/db:/data-migration:ro  # Add this line
```

Then copy inside container:

```bash
docker compose up -d
docker compose exec telemetry-api cp /data-migration/telemetry.sqlite /data/telemetry.sqlite
docker compose restart
```

**Option 3: Use migration script**

```bash
# Run migration script inside container
docker compose exec telemetry-api python scripts/migrate_v5_to_v6.py --db-path /data/telemetry.sqlite
```

---

## Configuration

### Environment Variables

Edit `docker-compose.yml` to customize configuration:

```yaml
environment:
  # Database settings
  - TELEMETRY_DB_PATH=/data/telemetry.sqlite
  - TELEMETRY_LOCK_FILE=/data/telemetry.lock

  # PRAGMA settings
  - TELEMETRY_DB_JOURNAL_MODE=DELETE  # DELETE (Windows/Docker) or WAL (Linux native)
  - TELEMETRY_DB_SYNCHRONOUS=FULL     # FULL (safest) or NORMAL (faster)

  # API server
  - TELEMETRY_API_HOST=0.0.0.0
  - TELEMETRY_API_PORT=8765
  - TELEMETRY_API_WORKERS=1           # MUST be 1 (single-writer)

  # Logging
  - TELEMETRY_LOG_LEVEL=INFO          # DEBUG, INFO, WARNING, ERROR
```

**After changing configuration:**

```bash
docker compose down
docker compose up -d
```

### Changing Port

To use a different port (e.g., 9000):

Edit `docker-compose.yml`:

```yaml
ports:
  - "9000:8765"  # Host port:Container port

environment:
  - TELEMETRY_API_PORT=8765  # Keep container port same
```

Then restart:

```bash
docker compose down
docker compose up -d
```

Access at `http://localhost:9000`

### Resource Limits

Adjust CPU and memory limits in `docker-compose.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # 2 CPU cores maximum
      memory: 1G       # 1GB RAM maximum
    reservations:
      cpus: '0.5'      # 0.5 CPU cores reserved
      memory: 256M     # 256MB RAM reserved
```

---

## Monitoring

### Health Checks

Docker automatically monitors service health:

```bash
# Check health status
docker inspect telemetry-api --format='{{.State.Health.Status}}'

# View health check logs
docker inspect telemetry-api --format='{{json .State.Health}}' | jq '.'
```

**Health states:**
- `starting` - Initial startup (40s grace period)
- `healthy` - Service responding to health checks
- `unhealthy` - Health check failing (after 3 retries)

### Metrics Endpoint

```bash
# Get current metrics
curl http://localhost:8765/metrics | jq '.'

# Watch metrics in real-time
watch -n 5 'curl -s http://localhost:8765/metrics | jq "."'
```

### Container Logs

```bash
# Real-time logs
docker compose logs -f

# Filter for errors
docker compose logs | grep ERROR

# Export logs to file
docker compose logs > telemetry-api.log
```

### Resource Monitoring

```bash
# Real-time resource usage
docker stats telemetry-api

# Output:
# CONTAINER       CPU %   MEM USAGE / LIMIT   MEM %   NET I/O
# telemetry-api   0.5%    45MiB / 512MiB      8.8%    1.2kB / 850B
```

### Setting Up Alerts

**Example: Email alert on unhealthy status**

Create `monitor.sh`:

```bash
#!/bin/bash
HEALTH=$(docker inspect telemetry-api --format='{{.State.Health.Status}}')

if [ "$HEALTH" != "healthy" ]; then
    echo "Telemetry API is $HEALTH" | mail -s "Alert: Telemetry API Down" admin@example.com
fi
```

Add to cron:

```bash
# Run every 5 minutes
*/5 * * * * /path/to/monitor.sh
```

---

## Updating the Service

### Updating Code

```bash
# Pull latest code
git pull origin main

# Rebuild and restart
docker compose down
docker compose up -d --build

# Verify new version
curl http://localhost:8765/health
```

### Zero-Downtime Update (Blue-Green Deployment)

**Step 1: Start new version on different port**

Create `docker-compose.new.yml`:

```yaml
services:
  telemetry-api-new:
    build: .
    container_name: telemetry-api-new
    ports:
      - "8766:8765"  # Different host port
    volumes:
      - telemetry-data:/data  # Same volume
    # ... other settings
```

**Step 2: Start new version**

```bash
docker compose -f docker-compose.new.yml up -d
```

**Step 3: Test new version**

```bash
curl http://localhost:8766/health
```

**Step 4: Switch traffic (update reverse proxy or load balancer)**

**Step 5: Stop old version**

```bash
docker compose down
mv docker-compose.new.yml docker-compose.yml
```

---

## Troubleshooting

### Container Won't Start

**Check logs:**

```bash
docker compose logs
```

**Common issues:**

1. **Port already in use**
   ```bash
   # Find process using port 8765
   netstat -ano | findstr :8765

   # Kill process or change port in docker-compose.yml
   ```

2. **Permission errors**
   ```bash
   # Check file permissions
   ls -l /data/telemetry.sqlite

   # Fix ownership (inside container runs as user 'telemetry')
   docker compose exec telemetry-api chown telemetry:telemetry /data/telemetry.sqlite
   ```

3. **Missing dependencies**
   ```bash
   # Rebuild image
   docker compose build --no-cache
   docker compose up -d
   ```

### Service Unhealthy

**Check health check logs:**

```bash
docker inspect telemetry-api --format='{{json .State.Health}}' | jq '.'
```

**Test health endpoint manually:**

```bash
docker compose exec telemetry-api curl http://localhost:8765/health
```

**Common causes:**
- Service crashed (check logs)
- Port not responding (firewall issue)
- Database locked (restart container)

### Database Locked

**Symptoms:**
- Health check fails
- Logs show "database is locked"

**Solution:**

```bash
# Stop container
docker compose stop

# Remove lock file
docker compose exec telemetry-api rm /data/telemetry.lock

# Start container
docker compose start
```

### High Memory Usage

**Check current usage:**

```bash
docker stats telemetry-api --no-stream
```

**Increase limit if needed:**

Edit `docker-compose.yml`:

```yaml
deploy:
  resources:
    limits:
      memory: 1G  # Increase from 512M
```

```bash
docker compose down
docker compose up -d
```

### Container Keeps Restarting

**Check restart count:**

```bash
docker inspect telemetry-api --format='{{.RestartCount}}'
```

**View crash logs:**

```bash
docker compose logs --tail=50
```

**Common causes:**
- Configuration error (check environment variables)
- Database corruption (restore from backup)
- Resource limits too low (increase limits)

---

## Production Best Practices

### 1. Use Docker Volume for Data

**✅ DO:**
```yaml
volumes:
  - telemetry-data:/data  # Docker-managed volume
```

**❌ DON'T:**
```yaml
volumes:
  - D:/agent-metrics/db:/data  # Windows bind mount (slower, corruption risk)
```

### 2. Set Restart Policy

```yaml
restart: unless-stopped  # Auto-restart except when manually stopped
```

Options:
- `no` - Never restart
- `always` - Always restart
- `on-failure` - Restart only on error
- `unless-stopped` - Restart except when stopped manually

### 3. Enable Health Checks

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8765/health"]
  interval: 30s       # Check every 30 seconds
  timeout: 10s        # Timeout after 10 seconds
  retries: 3          # Mark unhealthy after 3 failures
  start_period: 40s   # Grace period during startup
```

### 4. Limit Resources

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 512M
```

Prevents runaway container from consuming all host resources.

### 5. Configure Logging

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"   # Rotate after 10MB
    max-file: "3"     # Keep 3 files (30MB total)
```

### 6. Regular Backups

**Automated daily backup script:**

```bash
#!/bin/bash
# backup_telemetry.sh
BACKUP_DIR="/backups/telemetry"
DATE=$(date +%Y%m%d_%H%M%S)

docker compose cp telemetry-api:/data/telemetry.sqlite "$BACKUP_DIR/telemetry_$DATE.sqlite"

# Keep last 7 days
find "$BACKUP_DIR" -name "telemetry_*.sqlite" -mtime +7 -delete
```

Add to cron:

```bash
# Daily at 2 AM
0 2 * * * /path/to/backup_telemetry.sh
```

### 7. Monitor Health

Set up monitoring with alerts (see Monitoring section above).

### 8. Use Specific Image Tags

Instead of `latest`, use version tags:

```yaml
image: telemetry-api:2.0.0
```

### 9. Network Security

**Internal network only:**

```yaml
ports:
  - "127.0.0.1:8765:8765"  # Only accessible from localhost
```

**With reverse proxy:**

```yaml
# No ports exposed directly
# ports:
#   - "8765:8765"

networks:
  - internal-network  # Only accessible via reverse proxy
```

---

## Integration with External Applications

### Connection from Host Machine

Applications on the Windows host can connect to:

```
http://localhost:8765
```

Example configuration:

```bash
TELEMETRY_API_URL=http://localhost:8765
```

### Connection from Other Docker Containers

Applications in other Docker containers should use the service name:

```
http://telemetry-api:8765
```

**Example docker-compose.yml for another service:**

```yaml
services:
  my-app:
    image: my-app:latest
    environment:
      - TELEMETRY_API_URL=http://telemetry-api:8765
    networks:
      - telemetry-network  # Same network as telemetry-api

networks:
  telemetry-network:
    external: true  # Use existing network
```

### Connection from Windows Applications

For applications like hugo-translator running on Windows:

```python
# .env file
TELEMETRY_API_URL=http://localhost:8765
TELEMETRY_BUFFER_DIR=C:/telemetry/hugo-translator/buffer
```

No changes needed - applications access via localhost.

---

## Backup and Restore

### Manual Backup

```bash
# Create timestamped backup
docker compose cp telemetry-api:/data/telemetry.sqlite ./backup_$(date +%Y%m%d_%H%M%S).sqlite

# Verify backup
sqlite3 ./backup_20251220_143000.sqlite "PRAGMA integrity_check;"
```

### Automated Backup

**Windows Task Scheduler:**

Create `backup_docker_telemetry.ps1`:

```powershell
$BackupDir = "D:\backups\telemetry"
$Date = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = "$BackupDir\telemetry_$Date.sqlite"

# Create backup
docker compose -f "C:\path\to\local-telemetry\docker-compose.yml" cp telemetry-api:/data/telemetry.sqlite $BackupFile

# Keep last 7 days
Get-ChildItem $BackupDir -Filter "telemetry_*.sqlite" | Where-Object {$_.LastWriteTime -lt (Get-Date).AddDays(-7)} | Remove-Item
```

Schedule daily at 2 AM:

```powershell
$Action = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-File C:\path\to\backup_docker_telemetry.ps1"
$Trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -TaskName "Backup Telemetry Docker" -Action $Action -Trigger $Trigger
```

### Restore from Backup

```bash
# Stop service
docker compose stop

# Copy backup into container
docker compose cp ./backup_20251220_143000.sqlite telemetry-api:/data/telemetry.sqlite

# Remove lock file
docker compose exec telemetry-api rm -f /data/telemetry.lock

# Start service
docker compose start

# Verify
curl http://localhost:8765/health
```

---

## Uninstalling

### Remove Container and Image

```bash
# Stop and remove container
docker compose down

# Remove image
docker rmi telemetry-api:2.0.0

# Remove all unused images
docker image prune -a
```

### Remove Data Volume

**⚠️ WARNING: This deletes all telemetry data!**

```bash
# Remove container and volume
docker compose down -v

# Or manually remove volume
docker volume rm telemetry-data
```

### Complete Cleanup

```bash
# Stop and remove everything
docker compose down -v --rmi all

# Remove networks
docker network prune

# Verify cleanup
docker ps -a          # Should not show telemetry-api
docker images         # Should not show telemetry-api image
docker volume ls      # Should not show telemetry-data
```

---

## Summary

### Quick Reference Commands

```bash
# Start service
docker compose up -d

# Stop service
docker compose stop

# View logs
docker compose logs -f

# Restart service
docker compose restart

# Check status
docker compose ps

# Health check
curl http://localhost:8765/health

# Backup database
docker compose cp telemetry-api:/data/telemetry.sqlite ./backup.sqlite

# Access database
docker compose exec telemetry-api sqlite3 /data/telemetry.sqlite

# Update service
docker compose down && docker compose up -d --build
```

### Next Steps

1. ✅ Deploy Docker container (`docker compose up -d`)
2. ✅ Verify health (`curl http://localhost:8765/health`)
3. ✅ Set up automated backups
4. ✅ Configure monitoring/alerts
5. ✅ Integrate external applications

**The service is now running 24/7 with automatic restarts!**
