# Configuration Reference

Canonical configuration surfaces derived from `src/telemetry/config.py`.

## Environment Variables

### Core Storage
| Key | Purpose | Default / Resolution |
| --- | --- | --- |
| `TELEMETRY_DB_PATH` | Explicit path to SQLite DB. Highest priority; base dir inferred from parent. | None; when set, `metrics_dir` = `Path(TELEMETRY_DB_PATH).parent.parent` |
| `TELEMETRY_BASE_DIR` | Preferred base directory for all telemetry data. | Auto-detected if unset |
| `AGENT_METRICS_DIR` | Legacy alias for base dir. | Auto-detected if unset |
| `TELEMETRY_NDJSON_DIR` | Override NDJSON raw events directory. | `{metrics_dir}/raw` |
| `TELEMETRY_SKIP_VALIDATION` | If true, missing dirs become warnings (not errors). | `false` |
| `AGENT_OWNER` | Default agent owner if not provided per run. | None |
| `TELEMETRY_TEST_MODE` | Test mode flag (`mock` or `live`). | None |

### HTTP API (Local Telemetry Service)
| Key | Purpose | Default / Resolution |
| --- | --- | --- |
| `TELEMETRY_API_URL` | Local HTTP API endpoint. | `http://localhost:8765` |
| `TELEMETRY_API_PORT` | API listen port. | `8765` |
| `TELEMETRY_API_HOST` | API listen address. | `0.0.0.0` |
| `TELEMETRY_API_WORKERS` | Uvicorn worker count. **Must be 1** (single-writer). | `1` |
| `TELEMETRY_LOG_LEVEL` | Log level: DEBUG, INFO, WARNING, ERROR. | `INFO` |
| `TELEMETRY_API_AUTH_ENABLED` | Enable Bearer token auth. | `false` |
| `TELEMETRY_API_AUTH_TOKEN` | Auth token (required when auth enabled). | None |
| `TELEMETRY_RATE_LIMIT_ENABLED` | Enable per-IP rate limiting. | `false` |
| `TELEMETRY_RATE_LIMIT_RPM` | Requests per minute per client IP. | `60` |

### Database PRAGMA (SQLite Tuning)
| Key | Purpose | Default / Resolution |
| --- | --- | --- |
| `TELEMETRY_DB_JOURNAL_MODE` | SQLite journal mode. | `DELETE` |
| `TELEMETRY_DB_SYNCHRONOUS` | SQLite synchronous mode. | `FULL` |
| `TELEMETRY_DB_BUSY_TIMEOUT_MS` | Lock wait timeout in ms. | `30000` |
| `TELEMETRY_DB_CONNECT_TIMEOUT_SECONDS` | Connection timeout. | `30` |
| `TELEMETRY_DB_MAX_RETRIES` | Max retry attempts on lock. | `3` |
| `TELEMETRY_DB_RETRY_BASE_DELAY_SECONDS` | Base delay between retries. | `0.1` |

### Google Sheets Export (Optional)
| Key | Purpose | Default / Resolution |
| --- | --- | --- |
| `GOOGLE_SHEETS_API_ENABLED` | Enable Google Sheets export. | `false` |
| `GOOGLE_SHEETS_API_URL` | Google Sheets append endpoint. | None; required when enabled |
| `METRICS_API_TOKEN` | Bearer token for Google Sheets. | None |
| `METRICS_API_AUTH_REQUIRED` | Require token for Google Sheets. | `false` |
| `METRICS_API_URL` | Legacy alias for `GOOGLE_SHEETS_API_URL`. | None |
| `METRICS_API_ENABLED` | Legacy alias for `GOOGLE_SHEETS_API_ENABLED`. | `true` |

### Retention
| Key | Purpose | Default / Resolution |
| --- | --- | --- |
| `TELEMETRY_RETENTION_DAYS` | Days to keep old runs. | `30` |
| `TELEMETRY_DRY_RUN_CLEANUP` | Dry-run mode for retention script. | `1` (enabled) |

## Path Resolution
1. Use `TELEMETRY_DB_PATH` if provided; derive `metrics_dir` from it.
2. Else choose base dir from `TELEMETRY_BASE_DIR` > `AGENT_METRICS_DIR` > auto-detect first existing among `/agent-metrics`, `/opt/telemetry`, `/data/telemetry`, `D:/agent-metrics`, `C:/agent-metrics`, `~/.telemetry`; if none exist, default to `D:/agent-metrics` on Windows, `/agent-metrics` otherwise.
3. `database_path` defaults to `{metrics_dir}/db/telemetry.sqlite`.
4. `ndjson_dir` defaults to `{metrics_dir}/raw` unless overridden.

## Validation Rules
1. **Google Sheets URL required when enabled** -- `GOOGLE_SHEETS_API_ENABLED=true` requires `GOOGLE_SHEETS_API_URL`.
2. **URL format** -- All URLs must include scheme (http/https) and host.
3. **Same-host warning** -- Warning if `TELEMETRY_API_URL` and `GOOGLE_SHEETS_API_URL` resolve to same host.
4. **Auth token required** -- When Google Sheets enabled and `METRICS_API_AUTH_REQUIRED=true`, `METRICS_API_TOKEN` must be set.
5. **Directory existence** -- Base dirs must exist unless `TELEMETRY_SKIP_VALIDATION=true`.

## Configuration Patterns
- **Local-telemetry only (default):** `TELEMETRY_API_URL=http://localhost:8765`, `GOOGLE_SHEETS_API_ENABLED=false`
- **Local + Google Sheets:** Both URLs set, `GOOGLE_SHEETS_API_ENABLED=true`, token provided.
- **Docker/Kubernetes:** `TELEMETRY_API_URL=http://telemetry-api:8765`, `TELEMETRY_SKIP_VALIDATION=true`

## API Posting Defaults
- API client retries: 3 attempts with delays 1s, 2s, 4s (`src/telemetry/api.py`).
- HTTP timeout default: 10s sync/async.
- If `httpx` is missing, posting is skipped with a warning.

## Test Mode Helpers
- `TelemetryConfig.is_test_mode()` returns true when `TELEMETRY_TEST_MODE` is `mock` or `live`.
- `is_mock_mode` / `is_live_mode` check specific values.

## Validate Configuration
```bash
python -c "from src.telemetry.config import TelemetryConfig; config = TelemetryConfig.from_env(); is_valid, errors = config.validate(strict=False); print('Valid!' if is_valid else '\n'.join(errors))"
```
