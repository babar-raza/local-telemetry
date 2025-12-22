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
- **SQLite database** (`db/telemetry.sqlite`) - Structured queries, WAL mode for concurrent access

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
- Tracks posting status per run
- Batch retry for failed posts

### Cross-Platform Support
Works on Windows, Linux, macOS, Docker, and Kubernetes with automatic path detection.

## Quick Start

### 1. Install

```bash
git clone <repo-url> local-telemetry
cd local-telemetry
pip install -e .
```

### 2. Initialize Storage

```bash
python scripts/setup_storage.py
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

### 4. Query Your Data

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
│  Daily rotating files   │             │  WAL mode database      │
└─────────────────────────┘             └─────────────────────────┘
```

### Storage Layout

```
{base}/
├── raw/                           # NDJSON logs (crash-resilient)
│   ├── events_20251215.ndjson
│   └── events_20251214.ndjson
├── db/                            # SQLite database
│   ├── telemetry.sqlite
│   ├── telemetry.sqlite-wal       # Write-ahead log
│   └── telemetry.sqlite-shm       # Shared memory
└── backups/                       # Automated backups
```

## Configuration

All configuration via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEMETRY_BASE_DIR` | Base storage directory | Auto-detected |
| `TELEMETRY_DB_PATH` | Direct database path (overrides base) | `{base}/db/telemetry.sqlite` |
| `TELEMETRY_NDJSON_DIR` | NDJSON directory override | `{base}/raw` |
| `METRICS_API_URL` | Remote API endpoint | None (disabled) |
| `METRICS_API_TOKEN` | API authentication token | None |
| `METRICS_API_ENABLED` | Enable/disable API posting | `true` |
| `AGENT_OWNER` | Default agent owner | None |

See [docs/reference/config.md](docs/reference/config.md) for complete configuration reference.

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
| `scripts/setup_storage.py` | Initialize storage directories |
| `scripts/setup_database.py` | Create database schema |
| `scripts/backup_database.py` | Backup SQLite database |
| `scripts/recover_database.py` | Recover from NDJSON logs |
| `scripts/monitor_telemetry_health.py` | Health check monitoring |
| `scripts/validate_installation.py` | Verify installation |
| `scripts/diagnose_pragma_settings.py` | Diagnose database PRAGMA settings |
| `scripts/check_db_integrity.py` | Check database integrity |

## Troubleshooting

### Quick Diagnostics

**Validate installation:**
```bash
python scripts/validate_installation.py
```
Checks: environment, storage, database (including PRAGMA settings), configuration, tests.

**Diagnose PRAGMA issues:**
```bash
python scripts/diagnose_pragma_settings.py
```
Shows connection-level PRAGMA settings and identifies discrepancies.

**Check database integrity:**
```bash
python scripts/check_db_integrity.py
```
Verifies database is not corrupted.

For detailed troubleshooting, see [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## Documentation

### By Role

| Role | Start Here |
|------|------------|
| **Agent Developer** | [docs/getting-started/quickstart-user.md](docs/getting-started/quickstart-user.md) |
| **Platform Operator** | [docs/getting-started/quickstart-operator.md](docs/getting-started/quickstart-operator.md) |
| **Contributor** | [docs/getting-started/quickstart-contributor.md](docs/getting-started/quickstart-contributor.md) |

### Guides

- [Instrumentation Guide](docs/guides/instrumentation.md) - Detailed instrumentation patterns
- [Backup & Restore](docs/guides/backup-and-restore.md) - Data protection
- [Recovery from NDJSON](docs/guides/recovery-from-ndjson.md) - Disaster recovery
- [Monitoring & Health](docs/guides/monitoring-and-health.md) - Operational monitoring
- [Quality Gates](docs/guides/quality-gates.md) - CI/CD integration

### Reference

- [API Reference](docs/reference/api.md) - TelemetryClient API
- [Configuration](docs/reference/config.md) - Environment variables
- [CLI Reference](docs/reference/cli.md) - Command-line tools
- [Schema Reference](docs/reference/schema.md) - Database schema
- [File Contracts](docs/reference/file-contracts.md) - Storage formats

### Architecture

- [System Architecture](docs/architecture/system.md) - Component overview
- [Design Decisions](docs/architecture/decisions.md) - ADRs and rationale

## Project Structure

```
local-telemetry/
├── src/telemetry/          # Core library
│   ├── __init__.py         # Public exports
│   ├── client.py           # TelemetryClient, RunContext
│   ├── config.py           # TelemetryConfig
│   ├── models.py           # RunRecord, RunEvent, APIPayload
│   ├── database.py         # DatabaseWriter (SQLite)
│   ├── local.py            # NDJSONWriter
│   ├── api.py              # APIClient
│   └── schema.py           # Database schema
├── scripts/                # Utility scripts
├── tests/                  # Test suite
├── docs/                   # Documentation
│   ├── getting-started/    # Quickstart guides
│   ├── guides/             # How-to guides
│   ├── reference/          # API/config reference
│   ├── architecture/       # System design
│   └── operations/         # Runbooks
├── config/                 # Configuration templates
└── pyproject.toml          # Package configuration
```

## Performance

| Operation | Target Latency | Notes |
|-----------|----------------|-------|
| `start_run` | < 10ms | NDJSON + DB insert |
| `log_event` | < 5ms | NDJSON only |
| `end_run` | < 50ms | NDJSON + DB update + optional API |
| Throughput | > 20 writes/sec | With WAL mode |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run specific test
pytest tests/test_client.py -v
```

## License

See LICENSE file for details.

## Support

- Issues: [GitHub Issues](https://github.com/your-org/local-telemetry/issues)
- Documentation: [docs/README.md](docs/README.md)
