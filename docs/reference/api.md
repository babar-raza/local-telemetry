# Library API Reference

Source of truth: `src/telemetry/client.py`, `src/telemetry/models.py`, `src/telemetry/api.py`.

## Two-Client Architecture

The library uses two independent API clients:

1. **HTTPAPIClient** (local, always active) -- POSTs to `http://localhost:8765/api/v1/runs`. Handles idempotency, PATCH updates, batch operations. If unavailable, events buffer to local NDJSON files and sync later (at-least-once delivery).
2. **APIClient** (Google Sheets, optional) -- Fire-and-forget export to Google Sheets. Disabled by default (`GOOGLE_SHEETS_API_ENABLED=false`). Failures never block agent execution.

**Event flow (local-only):**
```
Application -> TelemetryClient.start_run()
  -> HTTPAPIClient.post_event() -> POST /api/v1/runs
     on failure -> BufferFile.append() (retry later)
  -> NDJSONWriter.append() (backup)
```

**Performance characteristics:**

| Client | Operation | Typical Latency |
|--------|-----------|-----------------|
| HTTPAPIClient | POST single event | < 50ms |
| HTTPAPIClient | PATCH update | < 30ms |
| HTTPAPIClient | POST batch (100 events) | < 200ms |
| APIClient | POST to Google Sheets | 200-500ms |
| Failover | Buffer write | < 1ms |

**Common mistake:** Setting `GOOGLE_SHEETS_API_URL` to localhost causes 404 errors. Either disable Google Sheets or provide a real `sheets.googleapis.com` endpoint.

## TelemetryClient
- `TelemetryClient(config: TelemetryConfig | None = None)`
  - Loads config (from env if None), validates, and sets up NDJSON writer, SQLite writer, and API client.
- `start_run(agent_name, job_type, trigger_type="cli", **kwargs) -> run_id`
  - Creates `RunRecord`, writes to NDJSON + SQLite, registers active run.
- `log_event(run_id, event_type, payload=None)`
  - Writes `RunEvent` to NDJSON only (events are not persisted to DB).
- `end_run(run_id, status="success", **kwargs)`
  - Updates metrics/timestamps, writes NDJSON + SQLite update, posts to API (if enabled), marks API state or increments retry count.
- `track_run(agent_name, job_type, trigger_type="cli", **kwargs)` (context manager)
  - Wraps start/end with exception handling; on exception, ends run with `status="failed"` and re-raises.
- `get_stats() -> dict`
  - Returns counts by status and pending API posts via `DatabaseWriter.get_run_stats`.

## RunContext
- Returned by `track_run`; methods delegate to client:
  - `log_event(event_type, payload=None)`
  - `set_metrics(**kwargs)` -- updates active `RunRecord` fields (items_discovered/succeeded/failed, summaries, metrics_json, insight_id, product, platform, product_family, subdomain, git_repo/branch/run_tag, etc.).

## Models
- `RunRecord` -- matches SQLite `agent_runs` schema; helper methods `to_dict`, `to_json`, `from_dict`.
- `RunEvent` -- event payload for NDJSON; `to_dict`, `to_json`, `from_dict`.
- `APIPayload` -- subset of RunRecord for API posts; `from_run_record`.
- Helpers: `generate_run_id(agent_name)`, `get_iso8601_timestamp()`, `calculate_duration_ms(start, end)`.

## API Client (`APIClient`)
- Config: `api_url`, `api_token`, `api_enabled`, `max_retries` (default 3), `timeout` (default 10s).
- Methods:
  - `post_run_sync(payload: APIPayload) -> (success, message)`
  - `post_run_async(payload: APIPayload)` -- async variant.
  - `test_connection() -> (success, message)`
- Behavior:
  - Retries with delays 1s, 2s, 4s on server errors/timeouts/request errors.
  - Skips when disabled, missing config, or `httpx` not installed.
  - Auth: `Authorization: Bearer <token>`, `Content-Type: application/json`.

## Database Writer (`DatabaseWriter`)
- DELETE journal mode, `busy_timeout=30000`, `synchronous=FULL`.
- Retry on lock with delays 0.1/0.2/0.4s for inserts/updates.
- Methods: `insert_run`, `update_run`, `get_run`, `mark_api_posted`, `increment_api_retry_count`, `get_pending_api_posts`, `get_run_stats`, `check_integrity`.

## NDJSON Writer (`NDJSONWriter`)
- Daily file `events_YYYYMMDD.ndjson`, file locks per platform, fsync per write.
- Methods: `append`, `read_file(date_str)`, `list_files`, `get_file_info`.

## Configuration (`TelemetryConfig`)
- See `config.md` for env keys and resolution.
