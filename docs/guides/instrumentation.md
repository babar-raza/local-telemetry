# Instrumentation Guide (Users)

Goal: record agent runs/events with `TelemetryClient` while avoiding crashes.

## Prerequisites
- Configure storage/env: see `reference/config.md`.
- Install dependencies: `pip install -e .` (httpx optional for API posting).

## Steps
1. **Create client**
   ```python
   from telemetry import TelemetryClient
   client = TelemetryClient()  # loads env config, validates dirs
   ```
2. **Track a run (recommended)**
   ```python
   with client.track_run("my_agent", "my_job", trigger_type="cli") as ctx:
       ctx.log_event("start", {"info": "begin"})
       ctx.set_metrics(items_discovered=10)
       # ... work ...
       ctx.log_event("checkpoint", {"step": 1})
   # Auto-ends with status="success"; exceptions mark status="failed"
   ```
3. **Explicit start/end (optional)**
   ```python
   run_id = client.start_run("my_agent", "my_job", trigger_type="cli")
   client.log_event(run_id, "checkpoint", {"step": 1})
   client.end_run(run_id, status="success", items_succeeded=10)
   ```
4. **Metrics you can set** (delegates to `RunRecord` fields):
   - counts: `items_discovered`, `items_succeeded`, `items_failed`
   - summaries: `input_summary`, `output_summary`, `error_summary`
   - metadata: `metrics_json` (JSON string), `insight_id`, `product`, `platform`, `product_family`, `subdomain`, `git_repo`, `git_branch`, `git_run_tag`

## What happens under the hood
- Dual write: NDJSON append (`raw/events_YYYYMMDD.ndjson`) + SQLite insert/update (`db/telemetry.sqlite`).
- Events: NDJSON only (no DB writes) to avoid lock contention.
- API posting: `end_run` posts to remote API if enabled; retries 3x (1s/2s/4s) then records retry count.

## Validate
- NDJSON: check `{base}/raw/events_YYYYMMDD.ndjson` for JSON lines with `record_type`.
- DB: `sqlite3 {base}/db/telemetry.sqlite "SELECT run_id,status FROM agent_runs ORDER BY start_time DESC LIMIT 5;"`.
- API: DB fields `api_posted`, `api_retry_count` indicate posting status.

## Links
- Configuration: `reference/config.md`
- API surface: `reference/api.md`
- File contracts: `reference/file-contracts.md`
