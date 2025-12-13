# Configuration Guide

The telemetry library is configured via environment variables with sensible defaults.

## Environment Variables

### Storage Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEMETRY_BASE_DIR` | Base directory for all telemetry data | Auto-detected (see below) |
| `AGENT_METRICS_DIR` | Legacy alias for `TELEMETRY_BASE_DIR` | - |
| `TELEMETRY_DB_PATH` | Direct path to SQLite database (highest priority) | `{base}/db/telemetry.sqlite` |
| `TELEMETRY_NDJSON_DIR` | Directory for NDJSON event logs | `{base}/raw` |
| `TELEMETRY_SKIP_VALIDATION` | Skip directory validation (for containers) | `false` |

### API Configuration (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `METRICS_API_URL` | Google Apps Script URL for remote posting | - |
| `METRICS_API_TOKEN` | API authentication token | - |
| `METRICS_API_ENABLED` | Enable/disable API posting | `true` |

### Metadata

| Variable | Description | Default |
|----------|-------------|---------|
| `AGENT_OWNER` | Default owner name for runs | - |
| `TELEMETRY_TEST_MODE` | Test mode (`mock` or `live`) | - |

## Auto-Detection

If no base directory is configured, the library auto-detects by checking:

1. `/agent-metrics` (Docker/Linux)
2. `/opt/telemetry` (Alternative Linux)
3. `/data/telemetry` (Kubernetes)
4. `D:\agent-metrics` (Windows D: drive)
5. `C:\agent-metrics` (Windows C: drive)
6. `~/.telemetry` (User home fallback)

The first existing directory is used. If none exist, a platform-appropriate default is used.

## Directory Structure

After initialization, the base directory contains:

```
{base}/
├── raw/           # NDJSON event logs (events_YYYYMMDD.ndjson)
├── db/            # SQLite database (telemetry.sqlite)
├── reports/       # Generated reports
├── exports/       # CSV exports
├── config/        # Configuration files
└── logs/          # System logs
```

## Configuration in Code

```python
from telemetry import TelemetryClient, TelemetryConfig

# Auto-load from environment
client = TelemetryClient()

# Or create explicit config
config = TelemetryConfig.from_env()
print(config.metrics_dir)
print(config.database_path)

# Validate configuration
is_valid, errors = config.validate()
if not is_valid:
    print("Configuration errors:", errors)
```

## Configuration Priority

1. **Explicit environment variables** (highest priority)
2. **Auto-detection** of existing directories
3. **Platform defaults** (lowest priority)

## Windows Setup Example

```powershell
# Set permanent environment variable (User scope)
[System.Environment]::SetEnvironmentVariable('AGENT_METRICS_DIR', 'D:\agent-metrics', 'User')

# Verify
$env:AGENT_METRICS_DIR

# Initialize storage
python scripts/setup_storage.py
python scripts/setup_database.py
```

## Docker/Linux Setup Example

```bash
# Set environment variable
export TELEMETRY_BASE_DIR=/agent-metrics

# Or use Docker volume
docker run -v /data/telemetry:/agent-metrics -e TELEMETRY_BASE_DIR=/agent-metrics ...
```

## Disabling Features

```bash
# Disable API posting
export METRICS_API_ENABLED=false

# Skip validation (for containers where directories are created at runtime)
export TELEMETRY_SKIP_VALIDATION=true
```
