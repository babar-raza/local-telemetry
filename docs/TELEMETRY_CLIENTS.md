# Telemetry Clients Architecture

## Overview

The local-telemetry library uses a **two-client architecture** to support different telemetry backends:

1. **HTTPAPIClient** - Local Telemetry HTTP API (recommended, default)
2. **APIClient** - Google Sheets Export (optional, disabled by default)

**Most users only need HTTPAPIClient** for local telemetry storage. Google Sheets export is optional and disabled by default to prevent misconfiguration and 404 errors.

## Quick Decision Guide

**Do you need Google Sheets export?**

- **No** → Use local-telemetry only (default configuration)
- **Yes** → Enable both clients (requires Google Sheets API setup)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│ Application (hugo-translator, etc.)                 │
└───────────────────┬─────────────────────────────────┘
                    │
                    ▼
        ┌───────────────────────────┐
        │  TelemetryClient          │
        │  (Facade/Coordinator)     │
        └─────────┬─────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌──────────────────────┐
│ HTTPAPIClient   │  │ APIClient            │
│ (Local HTTP)    │  │ (Google Sheets)      │
└────────┬────────┘  └─────────┬────────────┘
         │                     │
         │                     │
         ▼                     ▼
┌─────────────────┐  ┌──────────────────────┐
│ Local Telemetry │  │ Google Sheets API    │
│ HTTP API        │  │ (External Service)   │
│ localhost:8765  │  │ sheets.googleapis    │
│                 │  │                      │
│ POST /api/v1/   │  │ POST /v4/spreadsheet │
│      runs       │  │      /values/append  │
└─────────────────┘  └──────────────────────┘
```

## HTTPAPIClient (Local Telemetry HTTP API)

### Purpose

Sends telemetry events to the local-telemetry HTTP API running in Docker or as a standalone service.

### Endpoint

```
POST http://localhost:8765/api/v1/runs
```

### Configuration

```bash
# .env
TELEMETRY_API_URL=http://localhost:8765
```

Or use the legacy variable (still supported):

```bash
# .env
METRICS_API_URL=http://localhost:8765
```

### When to Use

- **Default choice** for all users
- Stores data locally in SQLite database
- Full query capabilities via `GET /api/v1/runs`
- No external dependencies or network egress
- Works offline
- Fast and reliable

### Features

- **Single-writer pattern**: Prevents database corruption
- **Idempotent POSTs**: Safe to retry with same `event_id`
- **PATCH updates**: Update runs without creating duplicates
- **Batch operations**: Upload multiple events efficiently
- **Health checks**: `GET /health` endpoint
- **Metrics**: `GET /metrics` endpoint

### Code Example

```python
from src.telemetry.client import TelemetryClient

# Initialize client (HTTPAPIClient is created automatically)
client = TelemetryClient()

# Start a run
run_id = client.start_run(
    agent_name="my-agent",
    job_type="translation",
    trigger_type="cli"
)

# Log events during the run
client.log_event(run_id, "checkpoint", {"step": 1, "status": "processing"})

# End the run with metrics
client.end_run(
    run_id,
    status="success",
    items_discovered=100,
    items_succeeded=98,
    items_failed=2
)

# Events are automatically posted to http://localhost:8765/api/v1/runs
```

### Context Manager Example

```python
from src.telemetry.client import TelemetryClient

client = TelemetryClient()

# Context manager handles start/end automatically
with client.track_run("my-agent", "translation") as ctx:
    ctx.log_event("start", {"input": "data.csv"})

    # Your agent logic here...
    items = process_files()

    ctx.set_metrics(
        items_discovered=len(items),
        items_succeeded=len([i for i in items if i.ok]),
        items_failed=len([i for i in items if not i.ok])
    )
# Automatically ends with status="success"
# If exception occurs, ends with status="failed"
```

### Failover Behavior

If the HTTP API is unavailable:

1. Event is written to local buffer file
2. Background sync worker retries periodically
3. Once API is available, buffered events are synced
4. Guaranteed delivery (at-least-once semantics)

## APIClient (Google Sheets Integration)

### Purpose

Exports telemetry events to a Google Sheets spreadsheet for external reporting and sharing with non-technical stakeholders.

### Endpoint

```
POST https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}/values/{RANGE}:append
```

### Configuration

```bash
# .env
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/abc123/values/Sheet1!A1:append
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_google_sheets_api_token
```

### When to Use

- You need external reporting in Google Sheets
- You want to share telemetry with non-technical stakeholders
- You have Google Sheets API credentials configured
- You need to integrate with existing Google Sheets workflows

### Features

- **Fire-and-forget**: Failures don't block agent execution
- **Exponential backoff retry**: 1s, 2s, 4s delays
- **Smart retry logic**: Retries 5xx errors, skips 4xx errors
- **Optional**: Disabled by default for safety

### Code Example

```python
from src.telemetry.client import TelemetryClient

# Initialize client with Google Sheets enabled
client = TelemetryClient()

# Both clients receive events automatically
run_id = client.start_run(
    agent_name="my-agent",
    job_type="translation",
    trigger_type="cli"
)

client.end_run(run_id, status="success", items_succeeded=100)

# Events are posted to BOTH:
# 1. http://localhost:8765/api/v1/runs (HTTPAPIClient)
# 2. https://sheets.googleapis.com/... (APIClient, if enabled)
```

### Behavior When Disabled

```python
# When GOOGLE_SHEETS_API_ENABLED=false (default):
client = TelemetryClient()

# Only HTTPAPIClient is created
# APIClient is None, Google Sheets exports are skipped
run_id = client.start_run("agent", "job")
# → Posted to http://localhost:8765/api/v1/runs only
```

## Configuration Scenarios

### Scenario 1: Local-telemetry Only (Recommended)

**Use Case**: You want local telemetry storage without external dependencies.

```bash
# .env
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false
```

**Result**:
- ✅ HTTPAPIClient is used
- ✅ Events posted to local HTTP API
- ✅ Data stored in SQLite database
- ❌ APIClient is NOT created
- ❌ No Google Sheets exports

**Client Initialization Log**:
```
[INFO] HTTP API client initialized: http://localhost:8765
[INFO] Google Sheets API client disabled (GOOGLE_SHEETS_API_ENABLED=false)
[INFO] Primary: HTTPAPIClient -> http://localhost:8765
[INFO] External: Google Sheets API -> DISABLED
```

### Scenario 2: Both Local-telemetry and Google Sheets

**Use Case**: You want local storage AND Google Sheets export.

```bash
# .env
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/abc123/values/Sheet1!A1:append
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_google_sheets_api_token
```

**Result**:
- ✅ HTTPAPIClient is used
- ✅ APIClient is used
- ✅ Events posted to local HTTP API
- ✅ Events exported to Google Sheets
- ✅ Both clients operate independently

**Client Initialization Log**:
```
[INFO] HTTP API client initialized: http://localhost:8765
[INFO] Google Sheets API client enabled: https://sheets.googleapis.com/...
[INFO] Primary: HTTPAPIClient -> http://localhost:8765
[INFO] External: Google Sheets API -> https://sheets.googleapis.com/...
```

### Scenario 3: Invalid Configuration (DO NOT USE)

**Problem**: Google Sheets enabled but URL not configured.

```bash
# .env (INVALID!)
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=true
GOOGLE_SHEETS_API_URL=  # Empty!
```

**Result**:
- ❌ Configuration validation error
- ❌ Error message: "GOOGLE_SHEETS_API_URL is required when GOOGLE_SHEETS_API_ENABLED=true"

**Fix**: Either set `GOOGLE_SHEETS_API_URL` or disable Google Sheets:

```bash
# Fix Option A: Disable Google Sheets
GOOGLE_SHEETS_API_ENABLED=false

# Fix Option B: Configure Google Sheets URL
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append
```

## Common Mistakes

### ❌ Mistake 1: Setting Google Sheets URL to localhost

**Problem**:

```bash
# .env (WRONG!)
GOOGLE_SHEETS_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=true
```

**What Happens**:
- APIClient posts to `http://localhost:8765/` (base URL, no endpoint)
- Local HTTP API returns 404 (no handler for `/`)
- Logs fill with 404 errors: `POST / HTTP/1.1" 404`
- HTTPAPIClient works correctly, but logs are polluted

**Why This Happens**:
- `GOOGLE_SHEETS_API_URL` is treated as a complete endpoint URL
- APIClient posts directly to the URL (no path appending)
- Local HTTP API only handles `/api/v1/runs`, not `/`

**Fix**:

```bash
# Option A: Disable Google Sheets (recommended)
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false

# Option B: Use correct Google Sheets URL
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append
GOOGLE_SHEETS_API_ENABLED=true
```

### ❌ Mistake 2: Using old METRICS_API_ENABLED variable

**Problem**:

```bash
# .env (OLD variable name)
METRICS_API_ENABLED=true  # Deprecated!
```

**What Happens**:
- Variable is ignored (superseded by `GOOGLE_SHEETS_API_ENABLED`)
- Google Sheets client might not be created
- Configuration warnings in logs

**Fix**:

```bash
# Use new variable name
GOOGLE_SHEETS_API_ENABLED=true
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append
```

### ❌ Mistake 3: Missing TELEMETRY_API_URL

**Problem**:

```bash
# .env (missing local API URL)
GOOGLE_SHEETS_API_ENABLED=true
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/...
# TELEMETRY_API_URL not set!
```

**What Happens**:
- HTTPAPIClient uses default: `http://localhost:8765`
- Works if service is running on default port
- Breaks if service runs on different port

**Fix**:

```bash
# Always explicitly set local API URL
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=true
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/...
```

## Troubleshooting

### Issue: 404 Errors in Logs

**Symptom**:
```
POST / HTTP/1.1" 404
POST / HTTP/1.1" 404
POST / HTTP/1.1" 404
```

**Cause**: Google Sheets client is enabled but `GOOGLE_SHEETS_API_URL` points to localhost

**Solution**:
```bash
# Disable Google Sheets
export GOOGLE_SHEETS_API_ENABLED=false

# Restart service
docker-compose restart

# Verify
docker-compose logs telemetry-api | grep "404"
# Expected: 0 results
```

### Issue: No Telemetry Data

**Symptom**: Events not appearing in database

**Cause**: HTTP API service might be down or unreachable

**Diagnostic Steps**:
```bash
# 1. Check service is running
docker ps | grep telemetry

# 2. Check health endpoint
curl http://localhost:8765/health

# 3. Check logs for errors
docker-compose logs telemetry-api --tail 50

# 4. Test POST directly
curl -X POST http://localhost:8765/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test-123",
    "run_id": "test-run",
    "agent_name": "test",
    "job_type": "test",
    "trigger_type": "cli",
    "start_time": "2025-01-01T00:00:00Z",
    "status": "running",
    "schema_version": 6,
    "duration_ms": 0,
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-01T00:00:00Z"
  }'

# 5. Query to verify
curl http://localhost:8765/api/v1/runs?agent_name=test
```

### Issue: Configuration Validation Error

**Symptom**:
```
ValueError: GOOGLE_SHEETS_API_URL is required when GOOGLE_SHEETS_API_ENABLED=true
```

**Cause**: Google Sheets is enabled but URL is not configured

**Solution**:
```bash
# Option A: Disable Google Sheets
GOOGLE_SHEETS_API_ENABLED=false

# Option B: Configure Google Sheets URL
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_token
```

## Client Lifecycle

### Initialization

```python
from src.telemetry.client import TelemetryClient

# Client initialization sequence:
# 1. Load configuration from environment
# 2. Validate configuration (errors become warnings)
# 3. Initialize HTTPAPIClient (always created)
# 4. Initialize APIClient (only if GOOGLE_SHEETS_API_ENABLED=true)
# 5. Initialize local buffer for failover
# 6. Log active clients summary

client = TelemetryClient()
```

### Event Flow (Local-telemetry Only)

```
Application
    │
    ▼
TelemetryClient.start_run()
    │
    ├─► HTTPAPIClient.post_event()
    │       │
    │       ├─► Try: POST http://localhost:8765/api/v1/runs
    │       │       Success → Log "Event created successfully"
    │       │
    │       └─► Catch: Connection Error
    │               └─► BufferFile.append() (failover)
    │
    └─► NDJSONWriter.append() (backup)
```

### Event Flow (Dual-Client)

```
Application
    │
    ▼
TelemetryClient.end_run()
    │
    ├─► HTTPAPIClient.patch_event()
    │       └─► PATCH http://localhost:8765/api/v1/runs/{event_id}
    │
    ├─► APIClient.post_run_sync()
    │       └─► POST https://sheets.googleapis.com/... (fire-and-forget)
    │
    └─► NDJSONWriter.append() (backup)
```

## Performance Characteristics

### HTTPAPIClient

| Operation | Latency | Notes |
|-----------|---------|-------|
| POST single event | < 50ms | Includes network + DB write |
| PATCH update | < 30ms | Updates existing record |
| POST batch | < 200ms | 100 events |
| Health check | < 5ms | Simple status check |

### APIClient

| Operation | Latency | Notes |
|-----------|---------|-------|
| POST single event | 200-500ms | External API call |
| Retry delay | 1s, 2s, 4s | Exponential backoff |
| Timeout | 10s | Configurable |

### Failover

| Operation | Latency | Notes |
|-----------|---------|-------|
| Buffer write | < 1ms | Local file append |
| Sync worker | 60s interval | Configurable |

## See Also

- **[Configuration Guide](CONFIGURATION.md)** - Complete environment variable reference
- **[Migration Guide](MIGRATION_GUIDE.md)** - Migrating from old to new configuration
- **[Troubleshooting Guide](TROUBLESHOOTING.md)** - Detailed debugging steps
- **[HTTP API Reference](reference/http-api.md)** - Complete API endpoint documentation
- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Production deployment best practices

## FAQ

### Q: Do I need Google Sheets export?

**A:** Most users do not need Google Sheets export. Use local-telemetry only (default configuration) unless you specifically need external reporting.

### Q: Can I use only Google Sheets without local-telemetry?

**A:** No. HTTPAPIClient (local-telemetry) is always used as the primary backend. Google Sheets is an optional secondary export destination.

### Q: What happens if Google Sheets export fails?

**A:** APIClient failures are logged but do not block agent execution. HTTPAPIClient continues to work normally. This is fire-and-forget behavior.

### Q: Can I add custom export destinations?

**A:** Yes. Follow the same pattern as APIClient:
1. Create a new client class
2. Implement retry logic with exponential backoff
3. Add to `TelemetryClient.end_run()` as fire-and-forget
4. Never block agent execution on external API failures

### Q: Why are there two separate API URLs?

**A:** Separating `TELEMETRY_API_URL` (local) and `GOOGLE_SHEETS_API_URL` (external) prevents misconfiguration. The old single `METRICS_API_URL` variable caused confusion and 404 errors when users set it to localhost but also enabled Google Sheets.

### Q: What is the recommended configuration for production?

**A:** Use local-telemetry only:

```bash
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false
```

Enable Google Sheets only if you have a specific need for external reporting and have properly configured Google Sheets API credentials.
