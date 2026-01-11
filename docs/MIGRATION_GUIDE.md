# Configuration Migration Guide

## Overview

This guide helps you migrate from the old configuration format to the new dual-API configuration that separates local-telemetry and Google Sheets endpoints.

## What Changed

### Before (Old Configuration)

In the old configuration, `METRICS_API_URL` was used for both local-telemetry and Google Sheets, causing confusion and 404 errors:

```bash
# Old .env (INCORRECT - causes 404 errors)
METRICS_API_URL=http://localhost:8765
METRICS_API_ENABLED=true
# Result: Google Sheets client posts to local-telemetry (404 errors)
```

### After (New Configuration)

The new configuration separates concerns with dedicated environment variables:

- **`TELEMETRY_API_URL`**: Local HTTP API (local-telemetry)
- **`GOOGLE_SHEETS_API_URL`**: External Google Sheets API endpoint
- **`GOOGLE_SHEETS_API_ENABLED`**: Enable/disable Google Sheets export

## Valid Configuration Patterns

### Option 1: Local-telemetry Only (Default)

This is the recommended default configuration for most users:

```bash
# .env
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false
```

**What happens:**
- Telemetry data is sent to local-telemetry HTTP API
- Google Sheets export is disabled
- No external API calls

### Option 2: Both Local-telemetry and Google Sheets

Use this when you need both local storage and Google Sheets export:

```bash
# .env
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/...
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_google_sheets_api_token
```

**What happens:**
- Telemetry data is sent to local-telemetry HTTP API
- Telemetry data is ALSO exported to Google Sheets
- Two separate API clients are used

## Migration Steps

### Step 1: Identify Your Current Configuration

Check your current `.env` file or environment variables:

```bash
# Windows PowerShell
Get-ChildItem Env:METRICS_API_*
Get-ChildItem Env:TELEMETRY_API_*
Get-ChildItem Env:GOOGLE_SHEETS_API_*

# Linux/Mac
printenv | grep -E '(METRICS_API|TELEMETRY_API|GOOGLE_SHEETS_API)'
```

### Step 2: Choose Your Configuration Pattern

Decide which configuration pattern fits your use case:

- **Local-telemetry only**: Use Option 1 (recommended)
- **Local-telemetry + Google Sheets**: Use Option 2

### Step 3: Update Environment Variables

#### Migrating from Local-telemetry Only

**Old:**
```bash
METRICS_API_URL=http://localhost:8765
METRICS_API_ENABLED=true  # This was confusing!
```

**New:**
```bash
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_ENABLED=false
```

#### Migrating from Google Sheets Configuration

**Old:**
```bash
METRICS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/...
METRICS_API_ENABLED=true
METRICS_API_TOKEN=your_token
```

**New (if you want both):**
```bash
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/...
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_token
```

**New (if you want Google Sheets only):**
```bash
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/...
GOOGLE_SHEETS_API_ENABLED=true
METRICS_API_TOKEN=your_token
# TELEMETRY_API_URL not set or set to empty
```

### Step 4: Validate Configuration

Run the validation command to ensure your configuration is correct:

```bash
# Windows PowerShell
python -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); is_valid, errors = config.validate(strict=False); print('Valid!' if is_valid else '\n'.join(errors))"

# Linux/Mac
python3 -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); is_valid, errors = config.validate(strict=False); print('Valid!' if is_valid else '\n'.join(errors))"
```

### Step 5: Test Your Configuration

Test that telemetry is working correctly:

```bash
# Test local-telemetry API
python -c "from src.telemetry.client import HTTPAPIClient; client = HTTPAPIClient(); print('HTTPAPIClient OK')"

# Test Google Sheets API (if enabled)
python -c "from src.telemetry.client import APIClient; client = APIClient(); print('APIClient OK')"
```

## Common Pitfalls and Errors

### Error 1: GOOGLE_SHEETS_API_URL Required

**Error message:**
```
GOOGLE_SHEETS_API_ENABLED=true but GOOGLE_SHEETS_API_URL is not set.
Either set GOOGLE_SHEETS_API_URL to your Google Sheets endpoint, or set
GOOGLE_SHEETS_API_ENABLED=false. See docs/MIGRATION_GUIDE.md for help.
```

**Solution:**
- Set `GOOGLE_SHEETS_API_ENABLED=false` if you don't use Google Sheets
- OR set `GOOGLE_SHEETS_API_URL` to your Google Sheets endpoint

**Example fix:**
```bash
# Option 1: Disable Google Sheets
GOOGLE_SHEETS_API_ENABLED=false

# Option 2: Provide URL
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/YOUR_SHEET_ID/values/Sheet1!A1:append
GOOGLE_SHEETS_API_ENABLED=true
```

### Error 2: Invalid URL Format

**Error message:**
```
GOOGLE_SHEETS_API_URL is not a valid URL: localhost:8765.
URL must include scheme (http/https) and host.
```

**Solution:**
URLs must include the scheme (http/https):

```bash
# WRONG
TELEMETRY_API_URL=localhost:8765

# CORRECT
TELEMETRY_API_URL=http://localhost:8765
```

### Error 3: Same Host Warning

**Warning message:**
```
WARNING: Both TELEMETRY_API_URL and GOOGLE_SHEETS_API_URL point to
the same host (localhost:8765). This is likely a misconfiguration.
```

**What this means:**
You've configured both URLs to point to the same host. This is usually a mistake because:
- `TELEMETRY_API_URL` should point to your local-telemetry API
- `GOOGLE_SHEETS_API_URL` should point to the external Google Sheets API

**Common cause:**
You set `GOOGLE_SHEETS_API_ENABLED=true` but forgot to change the URL:

```bash
# WRONG - both point to localhost
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=http://localhost:8765  # Should be Google Sheets!
GOOGLE_SHEETS_API_ENABLED=true
```

**Solution:**
```bash
# CORRECT
TELEMETRY_API_URL=http://localhost:8765
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/...
GOOGLE_SHEETS_API_ENABLED=true
```

### Error 4: Empty URL String

**Error message:**
```
GOOGLE_SHEETS_API_URL is not a valid URL: .
URL must include scheme (http/https) and host.
```

**Solution:**
Don't set environment variables to empty strings. Either:
- Don't set the variable at all
- OR set it to a valid URL

```bash
# WRONG
GOOGLE_SHEETS_API_URL=

# CORRECT (omit the variable)
# GOOGLE_SHEETS_API_URL not set

# OR CORRECT (provide valid URL)
GOOGLE_SHEETS_API_URL=https://sheets.googleapis.com/v4/spreadsheets/...
```

## Validation Commands

### Quick Validation

Test if your configuration is valid:

```bash
# Test invalid config (should raise error)
GOOGLE_SHEETS_API_ENABLED=true GOOGLE_SHEETS_API_URL= python -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); is_valid, errors = config.validate(strict=False); print('Valid!' if is_valid else 'ERRORS:\n' + '\n'.join(errors))"
```

### Expected output (invalid config):
```
ERRORS:
GOOGLE_SHEETS_API_ENABLED=true but GOOGLE_SHEETS_API_URL is not set. Either set GOOGLE_SHEETS_API_URL to your Google Sheets endpoint, or set GOOGLE_SHEETS_API_ENABLED=false. See docs/MIGRATION_GUIDE.md for help.
```

### Full Configuration Check

Print your current configuration (tokens are masked):

```bash
python -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); print(config)"
```

## Configuration Reference

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `TELEMETRY_API_URL` | Local HTTP API endpoint | No | `http://localhost:8765` |
| `GOOGLE_SHEETS_API_URL` | Google Sheets API endpoint | When `GOOGLE_SHEETS_API_ENABLED=true` | None |
| `GOOGLE_SHEETS_API_ENABLED` | Enable Google Sheets export | No | `false` |
| `METRICS_API_TOKEN` | API authentication token | When auth required | None |
| `METRICS_API_ENABLED` | Legacy: use `GOOGLE_SHEETS_API_ENABLED` | No | Deprecated |

### Backward Compatibility

The following legacy variables are still supported but deprecated:

- `METRICS_API_URL` - Use `TELEMETRY_API_URL` instead
- `METRICS_API_ENABLED` - Use `GOOGLE_SHEETS_API_ENABLED` instead

**Migration recommendation:**
Update to the new variable names to avoid confusion and ensure compatibility with future versions.

## Docker/Kubernetes Configuration

### Docker Compose

```yaml
services:
  telemetry:
    environment:
      - TELEMETRY_API_URL=http://telemetry-api:8765
      - GOOGLE_SHEETS_API_ENABLED=false
```

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: telemetry-config
data:
  TELEMETRY_API_URL: "http://telemetry-api:8765"
  GOOGLE_SHEETS_API_ENABLED: "false"
```

## Getting Help

If you encounter issues during migration:

1. Check the validation output for specific error messages
2. Review the configuration examples in this guide
3. See `docs/CONFIGURATION.md` for detailed configuration reference
4. Check `docs/TROUBLESHOOTING.md` for common issues

## Summary

- **Default configuration**: Local-telemetry only (`GOOGLE_SHEETS_API_ENABLED=false`)
- **Dual configuration**: Both local-telemetry and Google Sheets
- **Validation**: Run validation commands to catch errors early
- **Backward compatibility**: Legacy variables still work but are deprecated
