# Local Telemetry Platform

A Python library for tracking agent runs, metrics, and performance with dual-write resilience and optional remote API posting.

## The Problem

When running autonomous agents (LLM-powered automation, data pipelines, batch processors), you need visibility into:

- **What happened?** - Did the agent succeed or fail? How long did it take?
- **What was processed?** - How many items discovered, succeeded, failed?
- **When things go wrong** - What was the error? Can we trace it back to a specific run?
- **Cross-system correlation** - Which git commit came from which agent run?

Traditional logging falls short because:
- Logs are unstructured and hard to query
- No built-in support for run boundaries (start/end)
- No metrics aggregation across runs
- Lost data if the agent crashes mid-run

## The Solution

Local Telemetry provides **structured run tracking** with **crash resilience**:

```python
from telemetry import TelemetryClient

client = TelemetryClient()

with client.track_run("my_agent", "process_files") as ctx:
    ctx.log_event("start", {"input": "data.csv"})

    # Your agent logic here...
    items = process_files()

    ctx.set_metrics(
        items_discovered=len(items),
        items_succeeded=len([i for i in items if i.ok]),
        items_failed=len([i for i in items if not i.ok])
    )
# Automatically ends with status="success"
# If an exception occurs, ends with status="failed"
```

## Key Features

### Dual-Write Storage
Every write goes to **two destinations** for resilience:
- **NDJSON files** (`raw/events_YYYYMMDD.ndjson`) - Append-only, crash-resilient, human-readable
- **SQLite database** (`db/telemetry.sqlite`) - Structured queries, DELETE journal mode for corruption prevention

### Never Crashes Your Agent
The library is designed to **never interrupt your agent's work**:
- Configuration errors become warnings
- Write failures are logged but don't throw
- API failures retry silently in the background

### Git Commit Tracking
Link agent runs to their resulting git commits:
```python
# After your agent commits changes
success, msg = client.associate_commit(
    run_id=run_id,
    commit_hash="a1b2c3d4...",
    commit_source="llm",  # 'manual', 'llm', or 'ci'
    commit_author="Claude Code <noreply@anthropic.com>"
)
```

### Optional API Posting
Fire-and-forget posting to remote APIs (Google Sheets, webhooks, etc.):
- Automatic retry with exponential backoff (1s, 2s, 4s)
- Smart retry logic: 4xx errors are not retried, only transient 5xx/network errors
- Tracks posting status per run

### Cross-Platform Support
Works on Windows, Linux, macOS, Docker, and Kubernetes with automatic path detection.

## Quick Start

### 1. Install

```bash
git clone <repo-url> local-telemetry
cd local-telemetry
pip install -e .
```

### 2. Initialize Database

```bash
python scripts/setup_database.py
```

Or set environment variables:
```bash
export TELEMETRY_BASE_DIR=/path/to/telemetry
# or on Windows: set TELEMETRY_BASE_DIR=D:\agent-metrics
```

### 3. Instrument Your Agent

```python
from telemetry import TelemetryClient

client = TelemetryClient()

# Option 1: Context manager (recommended)
with client.track_run("agent_name", "job_type") as ctx:
    ctx.log_event("checkpoint", {"step": 1})
    ctx.set_metrics(items_discovered=10, items_succeeded=10)

# Option 2: Explicit start/end
run_id = client.start_run("agent_name", "job_type")
client.log_event(run_id, "checkpoint", {"step": 1})
client.end_run(run_id, status="success", items_succeeded=10)
```

### 4. Configure Telemetry Clients (Optional)

The library uses a two-client architecture. Most users only need the default:

```bash
# .env (local-telemetry only)
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false
```

For Google Sheets export, see [docs/reference/config.md](docs/reference/config.md).

### 5. Query Your Data

```bash
# Recent runs
sqlite3 db/telemetry.sqlite "SELECT run_id, status, duration_ms FROM agent_runs ORDER BY start_time DESC LIMIT 10;"

# Success rate by agent
sqlite3 db/telemetry.sqlite "SELECT agent_name, COUNT(*) as runs, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as successes FROM agent_runs GROUP BY agent_name;"
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        TelemetryClient                          │
│                   (Main Public Interface)                       │
└─────────────┬───────────────────────────────────────┬───────────┘
              │                                       │
              ▼                                       ▼
┌─────────────────────────┐             ┌─────────────────────────┐
│      NDJSONWriter       │             │    DatabaseWriter       │
│   (Local Resilience)    │             │  (Structured Queries)   │
└─────────────────────────┘             └─────────────────────────┘
              │                                       │
              ▼                                       ▼
┌─────────────────────────┐             ┌─────────────────────────┐
│  {base}/raw/*.ndjson    │             │  {base}/db/*.sqlite     │
│  Daily rotating files   │             │  DELETE journal mode    │
└─────────────────────────┘             └─────────────────────────┘
```

### Storage Layout

```
{base}/
├── raw/                           # NDJSON logs (crash-resilient)
│   ├── events_20251215.ndjson
│   └── events_20251214.ndjson
├── db/                            # SQLite database
│   └── telemetry.sqlite           # DELETE journal mode
└── backups/                       # Automated backups
```

## HTTP API Service (v3.0.0)

The telemetry service includes a FastAPI-based HTTP server that provides single-writer access to the SQLite database, preventing corruption from concurrent writes.

**Key Features:**
- Single-writer pattern with file locking
- Event idempotency via `event_id` UNIQUE constraint
- Query and update endpoints for stale run cleanup
- Git commit association and URL construction
- Health and metrics endpoints

**Starting the Service:**

```bash
# Development
python telemetry_service.py

# Production (Docker - recommended)
docker-compose up -d
```

**API Endpoints:**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/runs` | Create a run |
| `POST` | `/api/v1/runs/batch` | Batch create runs |
| `GET` | `/api/v1/runs` | Query runs (filter by agent, status, date) |
| `PATCH` | `/api/v1/runs/{event_id}` | Update a run |
| `POST` | `/api/v1/runs/{event_id}/associate-commit` | Associate git commit |
| `GET` | `/api/v1/runs/{event_id}/commit-url` | Get commit URL |
| `GET` | `/api/v1/runs/{event_id}/repo-url` | Get repo URL |
| `GET` | `/api/v1/metadata/{field}` | Get distinct field values |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | System metrics |
| `GET` | `/version` | API version |

For complete API documentation, see [docs/reference/http-api.md](docs/reference/http-api.md).

## Configuration

All configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEMETRY_BASE_DIR` | Base storage directory | Auto-detected |
| `TELEMETRY_DB_PATH` | Direct database path | `{base}/db/telemetry.sqlite` |
| `TELEMETRY_API_URL` | HTTP API URL | `http://localhost:8765` |
| `TELEMETRY_API_PORT` | API server port | `8765` |
| `TELEMETRY_API_WORKERS` | Uvicorn workers (must be 1) | `1` |
| `TELEMETRY_DB_JOURNAL_MODE` | SQLite journal mode | `DELETE` |
| `TELEMETRY_DB_SYNCHRONOUS` | SQLite sync mode | `FULL` |
| `GOOGLE_SHEETS_API_ENABLED` | Enable Google Sheets export | `false` |

See [docs/reference/config.md](docs/reference/config.md) for the complete reference.

## Available Metrics

Track these fields on every run:

| Field | Type | Description |
|-------|------|-------------|
| `items_discovered` | int | Total items found/processed |
| `items_succeeded` | int | Successfully processed items |
| `items_failed` | int | Failed items |
| `input_summary` | str | Description of input |
| `output_summary` | str | Description of output |
| `error_summary` | str | Error message if failed |
| `metrics_json` | str | Arbitrary JSON for custom metrics |
| `insight_id` | str | Link to originating insight |
| `product` | str | Product being processed |
| `platform` | str | Platform identifier |
| `git_repo` | str | Git repository URL |
| `git_branch` | str | Git branch name |
| `git_commit_hash` | str | Associated commit SHA |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/setup_database.py` | Create/initialize database schema |
| `scripts/db_retention_policy.py` | Database retention cleanup |
| `scripts/db_retention_policy_batched.py` | Production retention (batched, preferred) |
| `scripts/docker_retention_cleanup.ps1` | Docker wrapper for retention |
| `scripts/setup_docker_retention_task.ps1` | Task Scheduler retention automation |
| `scripts/start_telemetry_api.ps1` | Service startup (Windows PowerShell) |
| `scripts/start_telemetry_api.sh` | Service startup (Linux/Docker) |
| `scripts/start_telemetry_api.bat` | Service startup (Windows batch) |
| `scripts/backup_docker_telemetry.ps1` | Docker volume backup |
| `scripts/restore_docker_backup.ps1` | Docker backup restore |
| `scripts/setup_docker_backup_task.ps1` | Backup automation via Task Scheduler |
| `scripts/sql/telemetry_audit.sql` | Useful SQL audit queries |

## Documentation

### By Role

| Role | Start Here |
|------|------------|
| **Agent Developer** | [docs/getting-started/quickstart-user.md](docs/getting-started/quickstart-user.md) |
| **Platform Operator** | [docs/getting-started/quickstart-operator.md](docs/getting-started/quickstart-operator.md) |
| **Contributor** | [docs/development/contributing.md](docs/development/contributing.md) |

### Guides

- [Instrumentation Guide](docs/guides/instrumentation.md) - Detailed instrumentation patterns
- [Backup & Restore](docs/guides/backup-and-restore.md) - Data protection and recovery
- [Monitoring & Health](docs/guides/monitoring-and-health.md) - Operational monitoring

### Reference

- [HTTP API Reference](docs/reference/http-api.md) - Complete endpoint documentation
- [Python API Reference](docs/reference/api.md) - TelemetryClient API
- [Configuration](docs/reference/config.md) - Environment variables
- [Schema Reference](docs/reference/schema.md) - Database schema (v7)

### Architecture

- [System Architecture](docs/architecture/system.md) - Component overview
- [Design Decisions](docs/architecture/decisions.md) - ADRs and rationale

### Operations

- [Runbook](docs/operations/runbook.md) - Operational procedures
- [Troubleshooting](docs/operations/troubleshooting.md) - Common issues and solutions

## Project Structure

```
local-telemetry/
├── src/telemetry/             # Core library
│   ├── __init__.py            # Public exports
│   ├── client.py              # TelemetryClient, RunContext
│   ├── config.py              # TelemetryConfig
│   ├── models.py              # RunRecord, RunEvent, APIPayload
│   ├── database.py            # DatabaseWriter (SQLite)
│   ├── local.py               # NDJSONWriter
│   ├── api.py                 # APIClient (Google Sheets)
│   ├── http_client.py         # HTTPAPIClient (local API)
│   ├── schema.py              # Database schema management
│   ├── git_detector.py        # Auto Git context detection
│   ├── url_builder.py         # GitHub/GitLab/Bitbucket URLs
│   ├── buffer.py              # Write buffer
│   ├── logger.py              # Logging configuration
│   ├── single_writer_guard.py # File lock guard
│   ├── status.py              # Run status management
│   └── helpers/               # Helper modules
├── scripts/                   # Operational scripts (12 files)
├── tests/                     # Test suite
│   ├── contract/              # Contract tests (locked behavior)
│   ├── integration/           # Integration tests
│   ├── durability/            # Crash recovery tests
│   ├── regression/            # Bug fix regression tests
│   ├── stress/                # Concurrent write tests
│   └── test_*.py              # Unit tests
├── docs/                      # Documentation (16 files)
├── schema/                    # SQL schema definitions
├── migrations/                # SQL migration scripts
├── telemetry_service.py       # FastAPI HTTP server
├── docker-compose.yml         # Docker deployment
├── Dockerfile                 # Container image
└── pyproject.toml             # Package configuration
```

## Performance

| Operation | Target Latency | Notes |
|-----------|----------------|-------|
| `start_run` | < 10ms | NDJSON + DB insert |
| `log_event` | < 5ms | NDJSON only |
| `end_run` | < 50ms | NDJSON + DB update + optional API |
| Throughput | > 20 writes/sec | DELETE journal mode |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run contract tests only
pytest tests/ -m contract -v

# Run specific test
pytest tests/test_client.py -v
```

## License

See LICENSE file for details.

## Support

- Documentation: [docs/README.md](docs/README.md)
