# Configuration Guide

## Overview

This guide documents all configuration options, validation rules, and best practices for the local-telemetry platform.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Validation Rules](#validation-rules)
- [Configuration Patterns](#configuration-patterns)
- [Examples](#examples)
- [Troubleshooting](#troubleshooting)

## Environment Variables

### Core Configuration

#### TELEMETRY_BASE_DIR

Base directory for all telemetry data.

- **Type**: Path
- **Required**: No
- **Default**: Auto-detected (see below)
- **Example**: `D:/agent-metrics` or `/agent-metrics`

**Auto-detection order:**
1. `/agent-metrics` (Docker/Linux standard)
2. `/opt/telemetry` (Alternative Linux)
3. `/data/telemetry` (Kubernetes-style)
4. `D:/agent-metrics` (Windows D: drive)
5. `C:/agent-metrics` (Windows C: drive)
6. `~/.telemetry` (User home fallback)

#### TELEMETRY_DB_PATH

Direct path to SQLite database file (highest priority).

- **Type**: Path
- **Required**: No
- **Default**: `{TELEMETRY_BASE_DIR}/db/telemetry.sqlite`
- **Example**: `/data/telemetry.sqlite`

#### TELEMETRY_NDJSON_DIR

Directory for raw NDJSON event files.

- **Type**: Path
- **Required**: No
- **Default**: `{TELEMETRY_BASE_DIR}/raw`
- **Example**: `/agent-metrics/raw`

#### TELEMETRY_SKIP_VALIDATION

Skip directory validation (useful for containers where directories are created on first write).

- **Type**: Boolean
- **Required**: No
- **Default**: `false`
- **Values**: `true`, `1`, `yes`, `on` (case-insensitive)
- **Example**: `TELEMETRY_SKIP_VALIDATION=true`

### API Configuration

#### TELEMETRY_API_URL

Local HTTP API endpoint for local-telemetry storage.

- **Type**: URL
- **Required**: No
- **Default**: `http://localhost:8765`
- **Example**: `http://localhost:8765`
- **Validation**: Must be a valid URL with scheme and host

#### GOOGLE_SHEETS_API_URL

External Google Sheets API endpoint.

- **Type**: URL
- **Required**: Yes, when `GOOGLE_SHEETS_API_ENABLED=true`
- **Default**: None
- **Example**: `https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append`
- **Validation**: Must be a valid URL with scheme and host

#### GOOGLE_SHEETS_API_ENABLED

Enable Google Sheets export functionality.

- **Type**: Boolean
- **Required**: No
- **Default**: `false`
- **Values**: `true`, `1`, `yes`, `on` (case-insensitive) for enabled
- **Example**: `GOOGLE_SHEETS_API_ENABLED=true`

#### METRICS_API_TOKEN

API authentication token for Google Sheets endpoint.

- **Type**: String
- **Required**: When `METRICS_API_AUTH_REQUIRED=true` and `GOOGLE_SHEETS_API_ENABLED=true`
- **Default**: None
- **Example**: `your_api_token_here`
- **Security**: Never commit tokens to version control

#### METRICS_API_AUTH_REQUIRED

Require authentication token for Google Sheets endpoint.

- **Type**: Boolean
- **Required**: No
- **Default**: `false`
- **Values**: `true`, `1`, `yes`, `on` (case-insensitive)
- **Example**: `METRICS_API_AUTH_REQUIRED=true`

### Legacy Configuration (Deprecated)

#### AGENT_METRICS_DIR

Legacy name for base directory. Use `TELEMETRY_BASE_DIR` instead.

- **Type**: Path
- **Status**: Deprecated but still supported
- **Migration**: Use `TELEMETRY_BASE_DIR`

#### METRICS_API_URL

Legacy name for API URL. Use `TELEMETRY_API_URL` instead.

- **Type**: URL
- **Status**: Deprecated but still supported
- **Migration**: Use `TELEMETRY_API_URL`

#### METRICS_API_ENABLED

Legacy flag for API enabling. Use `GOOGLE_SHEETS_API_ENABLED` instead.

- **Type**: Boolean
- **Status**: Deprecated but still supported
- **Migration**: Use `GOOGLE_SHEETS_API_ENABLED`

### Other Configuration

#### AGENT_OWNER

Default owner name for agents.

- **Type**: String
- **Required**: No
- **Default**: None
- **Example**: `john_doe`

#### TELEMETRY_TEST_MODE

Test mode flag for development/testing.

- **Type**: String
- **Required**: No
- **Default**: None
- **Values**: `mock` or `live`
- **Example**: `TELEMETRY_TEST_MODE=mock`

#### TELEMETRY_RETRY_BACKOFF_FACTOR

Exponential backoff multiplier for API retries.

- **Type**: Float
- **Required**: No
- **Default**: `1.0`
- **Example**: `TELEMETRY_RETRY_BACKOFF_FACTOR=2.0`

## Validation Rules

### Rule 1: Google Sheets URL Required When Enabled

When `GOOGLE_SHEETS_API_ENABLED=true`, `GOOGLE_SHEETS_API_URL` must be set and non-empty.

**Valid:**
```bash
GOOGLE_SHEETS_API_ENABLED=true
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/...
```

**Invalid:**
```bash
GOOGLE_SHEETS_API_ENABLED=true
# GOOGLE_SHEETS_API_URL not set - ERROR
```

**Error message:**
```
GOOGLE_SHEETS_API_ENABLED=true but GOOGLE_SHEETS_API_URL is not set.
Either set GOOGLE_SHEETS_API_URL to your Google Sheets endpoint, or set
GOOGLE_SHEETS_API_ENABLED=false. See docs/MIGRATION_GUIDE.md for help.
```

### Rule 2: URL Format Validation

All URL configuration must include scheme (http/https) and host.

**Valid:**
```bash
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/...
```

**Invalid:**
```bash
TELEMETRY_API_URL=localhost:8765  # Missing scheme
GOOGLE_SHEETS_API_URL=sheets.googleapis.com  # Missing scheme
```

**Error message:**
```
TELEMETRY_API_URL is not a valid URL: localhost:8765.
URL must include scheme (http/https) and host.
Example: http://localhost:8765
```

### Rule 3: Same Host Warning

If both `TELEMETRY_API_URL` and `GOOGLE_SHEETS_API_URL` point to the same host, a warning is issued.

**Problematic:**
```bash
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=http://localhost:8765/sheets  # Same host!
GOOGLE_SHEETS_API_ENABLED=true
```

**Warning message:**
```
WARNING: Both TELEMETRY_API_URL and GOOGLE_SHEETS_API_URL point to
the same host (localhost:8765). This is likely a misconfiguration.
TELEMETRY_API_URL should point to your local-telemetry API (e.g.,
http://localhost:8765), while GOOGLE_SHEETS_API_URL should point to
the external Google Sheets API endpoint. See docs/MIGRATION_GUIDE.md
for proper configuration.
```

### Rule 4: Authentication Token Required

When `GOOGLE_SHEETS_API_ENABLED=true` and `METRICS_API_AUTH_REQUIRED=true`, `METRICS_API_TOKEN` must be set.

**Valid:**
```bash
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_AUTH_REQUIRED=true
METRICS_API_TOKEN=your_token_here
```

**Invalid:**
```bash
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_AUTH_REQUIRED=true
# METRICS_API_TOKEN not set - ERROR
```

**Error message:**
```
GOOGLE_SHEETS_API_ENABLED=true and METRICS_API_AUTH_REQUIRED=true
but METRICS_API_TOKEN is not set. Google Sheets export will fail.
```

### Rule 5: Directory Existence

Base directories must exist unless `TELEMETRY_SKIP_VALIDATION=true`.

**Validation can be skipped:**
```bash
TELEMETRY_SKIP_VALIDATION=true
```

**Error message (if validation not skipped):**
```
Metrics directory does not exist: D:/agent-metrics.
Run setup_storage.py first, or set TELEMETRY_SKIP_VALIDATION=true.
```

## Configuration Patterns

### Pattern 1: Local-telemetry Only (Recommended Default)

Use this for local development and when you don't need Google Sheets export.

```bash
# .env
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false
```

**Characteristics:**
- Simplest configuration
- No external API dependencies
- All data stored locally
- Fastest performance

### Pattern 2: Local-telemetry + Google Sheets

Use this when you need both local storage and Google Sheets export.

```bash
# .env
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_google_sheets_api_token
```

**Characteristics:**
- Dual storage (local + cloud)
- Requires external API access
- Higher reliability (local fallback)
- Slightly slower due to dual writes

### Pattern 3: Google Sheets Only

Use this when you only want Google Sheets export without local storage.

```bash
# .env
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_google_sheets_api_token
TELEMETRY_SKIP_VALIDATION=true
```

**Characteristics:**
- Cloud-only storage
- Requires external API access
- No local storage overhead
- Higher network dependency

### Pattern 4: Docker/Kubernetes Deployment

Use this for containerized deployments.

```bash
# .env
TELEMETRY_API_URL=http://telemetry-api:8765
TELEMETRY_BASE_DIR=/agent-metrics
TELEMETRY_SKIP_VALIDATION=true
GOOGLE_SHEETS_API_ENABLED=false
```

**Characteristics:**
- Container-friendly paths
- Skip validation (directories created at runtime)
- Service discovery via container names
- Optimized for orchestration

## Examples

### Example 1: Development Environment

```bash
# .env
TELEMETRY_BASE_DIR=D:/agent-metrics
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false
AGENT_OWNER=developer_local
TELEMETRY_TEST_MODE=live
```

### Example 2: CI/CD Pipeline

```bash
# .env
TELEMETRY_BASE_DIR=/tmp/telemetry
TELEMETRY_API_URL=http://localhost:8765
TELEMETRY_SKIP_VALIDATION=true
GOOGLE_SHEETS_API_ENABLED=false
TELEMETRY_TEST_MODE=mock
```

### Example 3: Production with Google Sheets

```bash
# .env
TELEMETRY_BASE_DIR=/opt/telemetry
TELEMETRY_API_URL=http://telemetry-api:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/1ABC.../values/Production!A1:append
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=${GOOGLE_SHEETS_TOKEN}
METRICS_API_AUTH_REQUIRED=true
AGENT_OWNER=production_system
```

### Example 4: Docker Compose

```yaml
# docker-compose.yml
version: '3.8'
services:
  telemetry:
    image: local-telemetry:latest
    environment:
      - TELEMETRY_BASE_DIR=/agent-metrics
      - TELEMETRY_API_URL=http://telemetry-api:8765
      - TELEMETRY_SKIP_VALIDATION=true
      - GOOGLE_SHEETS_API_ENABLED=false
    volumes:
      - telemetry-data:/agent-metrics

volumes:
  telemetry-data:
```

### Example 5: Kubernetes ConfigMap

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: telemetry-config
  namespace: default
data:
  TELEMETRY_BASE_DIR: "/agent-metrics"
  TELEMETRY_API_URL: "http://telemetry-api.default.svc.cluster.local:8765"
  TELEMETRY_SKIP_VALIDATION: "true"
  GOOGLE_SHEETS_API_ENABLED: "false"
```

## Validation Commands

### Check Configuration

```bash
# Quick validation
python -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); is_valid, errors = config.validate(strict=False); print('Valid!' if is_valid else '\n'.join(errors))"
```

### Print Configuration

```bash
# Print current config (tokens masked)
python -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); print(config)"
```

### Test Invalid Configuration

```bash
# Test error message for missing URL
GOOGLE_SHEETS_API_ENABLED=true GOOGLE_SHEETS_API_URL= python -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); is_valid, errors = config.validate(strict=False); print('\n'.join(errors) if errors else 'Valid')"
```

## Troubleshooting

### Issue: Configuration validation failed

**Symptom:** Validation errors on startup

**Solution:**
1. Run validation command to see specific errors
2. Check each error message for guidance
3. Update environment variables accordingly
4. Re-run validation to confirm

### Issue: URLs not recognized

**Symptom:** "Not a valid URL" errors

**Solution:**
Ensure URLs include scheme (http/https):

```bash
# Wrong
TELEMETRY_API_URL=localhost:8765

# Correct
TELEMETRY_API_URL=http://localhost:8765
```

### Issue: Same host warning

**Symptom:** Warning about both URLs pointing to same host

**Solution:**
Verify that:
- `TELEMETRY_API_URL` points to local-telemetry API
- `GOOGLE_SHEETS_API_URL` points to external Google Sheets API

If you don't use Google Sheets, set `GOOGLE_SHEETS_API_ENABLED=false`.

### Issue: Directory not found

**Symptom:** "Directory does not exist" errors

**Solution:**
1. Create directories: `python scripts/setup_storage.py`
2. OR skip validation: `TELEMETRY_SKIP_VALIDATION=true`
3. OR set correct base directory: `TELEMETRY_BASE_DIR=/your/path`

## Best Practices

### 1. Use Environment-Specific Configurations

Create separate `.env` files for each environment:

```
.env.development
.env.staging
.env.production
```

### 2. Never Commit Tokens

Add `.env` to `.gitignore`:

```gitignore
.env
.env.*
!.env.example
```

### 3. Validate on Startup

Always run validation when starting your application:

```python
from src.telemetry.config import TelemetryConfig

config = TelemetryConfig.from_env()
is_valid, errors = config.validate(strict=False)

if not is_valid:
    for error in errors:
        print(f"Configuration error: {error}")
    exit(1)
```

### 4. Use Skip Validation in Containers

For Docker/Kubernetes deployments, skip validation since directories are created at runtime:

```bash
TELEMETRY_SKIP_VALIDATION=true
```

### 5. Document Your Configuration

Create a `.env.example` file with documentation:

```bash
# .env.example
# Local telemetry API endpoint
TELEMETRY_API_URL=http://localhost:8765

# Google Sheets configuration (optional)
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/...
GOOGLE_SHEETS_API_ENABLED=false
```

## See Also

- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Step-by-step migration instructions
- [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) - Deployment best practices
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and solutions
