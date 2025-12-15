# Configuration Reference

Canonical configuration surfaces derived from `src/telemetry/config.py`.

## Environment Variables
| Key | Purpose | Default / Resolution |
| --- | --- | --- |
| `TELEMETRY_DB_PATH` | Explicit path to SQLite DB. Highest priority; base dir inferred from parent. | None; when set, `metrics_dir` = `Path(TELEMETRY_DB_PATH).parent.parent` |
| `TELEMETRY_BASE_DIR` | Preferred base directory for all telemetry data. | Auto-detected if unset |
| `AGENT_METRICS_DIR` | Legacy alias for base dir. | Auto-detected if unset |
| `TELEMETRY_NDJSON_DIR` | Override NDJSON raw events directory. | `{metrics_dir}/raw` |
| `TELEMETRY_SKIP_VALIDATION` | If true, missing dirs become warnings (not errors). | `false` |
| `METRICS_API_URL` | Remote API endpoint (Google Apps Script style). | None |
| `METRICS_API_TOKEN` | Bearer token for API posting. | None |
| `METRICS_API_ENABLED` | Enable/disable API posting. | `true` (truthy values: true/1/yes/on) |
| `AGENT_OWNER` | Default agent owner if not provided per run. | None |
| `TELEMETRY_TEST_MODE` | Test mode flag (`mock` or `live`). | None |

## Path Resolution
1. Use `TELEMETRY_DB_PATH` if provided; derive `metrics_dir` from it.
2. Else choose base dir from `TELEMETRY_BASE_DIR` → `AGENT_METRICS_DIR` → auto-detect first existing among `/agent-metrics`, `/opt/telemetry`, `/data/telemetry`, `D:/agent-metrics`, `C:/agent-metrics`, `~/.telemetry`; if none exist, default to `D:/agent-metrics` on Windows, `/agent-metrics` otherwise.
3. `database_path` defaults to `{metrics_dir}/db/telemetry.sqlite`.
4. `ndjson_dir` defaults to `{metrics_dir}/raw` unless overridden.

## Validation Behavior
- `TelemetryConfig.validate(strict=True)` checks existence of `metrics_dir`, `database_path.parent`, and `ndjson_dir`. With `TELEMETRY_SKIP_VALIDATION=true` (or `strict=False`), missing dirs become warnings instead of errors.
- When `METRICS_API_ENABLED=true`, missing `METRICS_API_URL` or `METRICS_API_TOKEN` are reported as errors.

## API Posting Defaults
- API client retries: 3 attempts with delays 1s, 2s, 4s (`src/telemetry/api.py`).
- HTTP timeout default: 10s sync/async.
- If `httpx` is missing, posting is skipped with a warning.

## Test Mode Helpers
- `TelemetryConfig.is_test_mode()` returns true when `TELEMETRY_TEST_MODE` is `mock` or `live`.
- `is_mock_mode` / `is_live_mode` check specific values.

## Related Config Files (not env)
- `config/quality_gate_config.yaml` — severity/blocks, report paths, test timeouts for `scripts/quality_gate.py`.
- `config/verification_checklist.yaml` — claim patterns, min verification rate for `scripts/verify_analysis.py`.
Reference pages should link here rather than duplicating tables.
