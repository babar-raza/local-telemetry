# Local Telemetry Platform

A Python library for tracking multi-agent runs, metrics, and performance with local-first storage.

## Features

- **Run Tracking**: Record start/end times, status, and metrics for agent executions
- **Event Logging**: Log checkpoint events during runs
- **Dual-Write Storage**: NDJSON for crash resilience + SQLite for structured queries
- **Optional API Posting**: Fire-and-forget to remote endpoints (Google Sheets)
- **Never Crashes**: All telemetry operations are wrapped in error handling
- **Cross-Platform**: Windows, Linux, and Docker support
- **Concurrent Safe**: File locking and WAL mode for concurrent writes

## Quick Start

### 1. Install

```bash
pip install -e .

# With development dependencies
pip install -e ".[dev]"
```

### 2. Initialize Storage

```bash
python scripts/setup_storage.py
python scripts/setup_database.py
```

### 3. Verify Installation

```bash
python scripts/validate_installation.py
```

### 4. Use in Your Code

```python
from telemetry import TelemetryClient

client = TelemetryClient()

# Context manager (recommended)
with client.track_run("my-agent", "my-job") as ctx:
    ctx.log_event("checkpoint", {"step": 1})
    ctx.set_metrics(items_discovered=10, items_succeeded=10)
    # ... do work ...
# Auto-ends with status="success"
# If exception: auto-ends with status="failed"
```

Or use explicit start/end:

```python
run_id = client.start_run("my-agent", "my-job")
client.log_event(run_id, "progress", {"status": "working"})
client.end_run(run_id, status="success", items_succeeded=5)
```

## Configuration

The library auto-detects storage location or uses environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEMETRY_BASE_DIR` | Base storage directory | Auto-detected |
| `AGENT_METRICS_DIR` | Legacy alias | - |
| `TELEMETRY_DB_PATH` | Direct database path | `{base}/db/telemetry.sqlite` |
| `METRICS_API_ENABLED` | Enable API posting | `true` |

Auto-detection checks (in order):
- `/agent-metrics` (Docker/Linux)
- `D:\agent-metrics` (Windows)
- `C:\agent-metrics` (Windows fallback)
- `~/.telemetry` (User home)

See [docs/configuration.md](docs/configuration.md) for full options.

## Storage

### Directory Structure

```
{base}/
├── raw/           # NDJSON logs (events_YYYYMMDD.ndjson)
├── db/            # SQLite (telemetry.sqlite)
├── reports/       # Generated reports
├── exports/       # CSV exports
├── config/        # Config files
└── logs/          # System logs
```

### Query Data

```bash
# Recent runs
sqlite3 D:\agent-metrics\db\telemetry.sqlite \
  "SELECT agent_name, job_type, status FROM agent_runs ORDER BY start_time DESC LIMIT 10;"

# Statistics
sqlite3 D:\agent-metrics\db\telemetry.sqlite \
  "SELECT status, COUNT(*) FROM agent_runs GROUP BY status;"
```

## Operations

```bash
# Health check
python scripts/monitor_telemetry_health.py

# Backup database
python scripts/backup_telemetry_db.py

# Performance test
python scripts/measure_performance.py
```

## Testing

```bash
# Run all tests
pytest

# Run smoke test
python tests/smoke_test.py

# Run with coverage
pytest --cov=src/telemetry
```

## Project Structure

```
local-telemetry/
├── src/telemetry/       # Main package
│   ├── client.py        # TelemetryClient, RunContext
│   ├── config.py        # Configuration loading
│   ├── database.py      # SQLite writer
│   ├── local.py         # NDJSON writer
│   ├── models.py        # Data models
│   └── schema.py        # Database schema
├── tests/               # Test suite
├── scripts/             # Utility scripts
├── docs/                # Documentation
└── config/              # Config files
```

## Documentation

- [Quick Start](docs/QUICK_START.md) - Get started in 15 minutes
- [Configuration](docs/configuration.md) - All configuration options
- [Architecture](docs/architecture.md) - System design and data flow
- [Development](docs/development.md) - Contributing and testing
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues
- [Runbook](docs/RUNBOOK.md) - Operations guide

## API Reference

### TelemetryClient

```python
client = TelemetryClient(config=None)  # Auto-loads from environment

# Start/end pattern
run_id = client.start_run(agent_name, job_type, trigger_type="cli", **kwargs)
client.log_event(run_id, event_type, payload=None)
client.end_run(run_id, status="success", **kwargs)

# Context manager pattern
with client.track_run(agent_name, job_type) as ctx:
    ctx.log_event(event_type, payload)
    ctx.set_metrics(items_discovered=N, items_succeeded=N, ...)

# Statistics
stats = client.get_stats()
```

### Supported Metrics

```python
ctx.set_metrics(
    items_discovered=10,
    items_succeeded=8,
    items_failed=2,
    input_summary="Description of input",
    output_summary="Description of output",
    error_summary="Error details if any",
    metrics_json='{"custom": "data"}',  # Flexible JSON
    insight_id="link-to-originating-insight",
    product="product-name",
    platform="platform-name",
    product_family="product-family",
    subdomain="site-subdomain",
    git_repo="repo-name",
    git_branch="branch-name",
)
```

## Requirements

- Python 3.9-3.13
- httpx (for API posting)

## License

MIT License
