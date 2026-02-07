# Operator Quickstart

Deploy and operate the Local Telemetry Platform.

## Docker Deployment (Recommended)

```bash
cd <project-root>
docker compose up -d --build     # Build image and start container
docker compose ps                # Verify: should show "Up (healthy)"
curl http://localhost:8765/health # Test health endpoint
```

Key settings in `docker-compose.yml`:
- `TELEMETRY_API_WORKERS=1` -- **must be 1** (single-writer; multiple workers corrupt the DB)
- `TELEMETRY_LOG_LEVEL=INFO` -- set to DEBUG only for development
- Volume: `telemetry-data:/data` for SQLite persistence

Common operations:
```bash
docker compose logs -f                                    # Follow logs
docker compose restart                                    # Restart service
docker compose down && docker compose up -d --build       # Rebuild after code changes
docker compose exec local-telemetry-api sqlite3 /data/telemetry.sqlite ".tables"  # Inspect DB
```

### System Requirements

- CPU: 1 core minimum (2+ recommended)
- RAM: 512MB minimum (1GB recommended)
- Disk: 2GB minimum for container + database growth

### Docker Best Practices

- Use Docker volumes (not bind mounts) for SQLite data.
- Resource limits are pre-configured: 1 CPU, 512MB memory.
- Log rotation is configured: 10MB max per file, 3 files retained.
- `restart: always` ensures auto-start on Docker/system restart.
- Bind to localhost only in production: change ports to `"127.0.0.1:8765:8765"`.

### Docker Backup / Restore

```bash
# Backup
docker compose cp local-telemetry-api:/data/telemetry.sqlite ./backup_$(date +%Y%m%d).sqlite

# Restore
docker compose stop
docker compose cp ./backup_file.sqlite local-telemetry-api:/data/telemetry.sqlite
docker compose start
```

Or use the backup script: `scripts/backup_docker_telemetry.ps1`

### Cross-Container Access

Other Docker containers on the same network use `http://local-telemetry-api:8765`. Add the telemetry network to their compose file:
```yaml
networks:
  telemetry-network:
    name: local-telemetry_telemetry-network
    external: true
```

## Local Development (Without Docker)

```bash
pip install -e .
python scripts/setup_database.py   # Create database schema
python telemetry_service.py        # Start API server
```

## Auto-Start (Production)

**Linux (systemd):** Create `/etc/systemd/system/telemetry-api.service`:
```ini
[Unit]
Description=Telemetry API Service
After=network.target
[Service]
Type=simple
User=telemetry
WorkingDirectory=/opt/local-telemetry
ExecStart=/opt/local-telemetry/venv/bin/uvicorn telemetry_service:app --host 0.0.0.0 --port 8765 --workers 1
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
Then: `sudo systemctl enable --now telemetry-api`

**Windows:** Use Docker Desktop with `restart: always` (pre-configured), or NSSM for non-Docker setups.

## Verify

```bash
curl http://localhost:8765/health    # {"status": "ok", "version": "3.0.0", ...}
curl http://localhost:8765/metrics   # System metrics
curl http://localhost:8765/api/v1/metadata  # Available agents and job types
```

## Next
- Instrument agents: `../guides/instrumentation.md`
- HTTP API reference: `../reference/http-api.md`
- Operational runbooks: `../operations/runbook.md`
- Backup/restore details: `../guides/backup-and-restore.md`
- Configuration: `../reference/config.md`
