# Quick Start Guide

## Prerequisites

- Python 3.9-3.13
- Windows OS
- 10GB free disk space

## Installation (15 minutes)

### Step 1: Clone and Install

```bash
git clone [repo-url] local-telemetry
cd local-telemetry
pip install -e .[dev]
```

### Step 2: Setup Storage

```bash
python scripts/setup_storage.py
```

**Expected output:** `[SUCCESS] Telemetry storage initialized`

### Step 3: Create Database

```bash
python scripts/setup_database.py
```

**Expected output:** `[SUCCESS] Telemetry database initialized`

### Step 4: Configure Environment

```powershell
[System.Environment]::SetEnvironmentVariable('AGENT_METRICS_DIR', 'D:\agent-metrics', 'User')
```

Close and reopen your terminal.

**Note:** Environment variable is optional - the system auto-detects `D:\agent-metrics` if it exists.

### Step 5: Validate

```bash
python scripts/validate_installation.py
```

**Expected output:** `[SUCCESS] ALL CHECKS PASSED - Installation is valid!`

## First Telemetry

Create `test_telemetry.py`:

```python
from telemetry import TelemetryClient

client = TelemetryClient()

with client.track_run(
    agent_name="my-first-agent",
    job_type="hello-world"
) as ctx:
    print("Doing work...")
    ctx.set_metrics(items_discovered=1)
    print("Done!")

print("Telemetry recorded!")
```

Run it:

```bash
python test_telemetry.py
```

Verify data:

```bash
sqlite3 D:\agent-metrics\db\telemetry.sqlite "SELECT agent_name, job_type, status FROM agent_runs ORDER BY start_time DESC LIMIT 5;"
```

## Next Steps

- Read the [Architecture Overview](architecture.md)
- See [Configuration Guide](configuration.md) for all options
- Set up monitoring: `python scripts/monitor_telemetry_health.py`
- Schedule backups: `python scripts/backup_telemetry_db.py`
- See [Integration Guide](seo-intelligence-integration-guide.md) for advanced usage
