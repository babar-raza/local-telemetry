# User Quickstart (Agent Developer)

## Prerequisites
- Python 3.9–3.13
- Storage initialized by operator (see `quickstart-operator.md`)
- Optional: `httpx` for API posting (`pip install httpx`)

## Install
```bash
git clone <repo-url> local-telemetry
cd local-telemetry
pip install -e .
```

## Minimal Instrumentation
```python
from telemetry import TelemetryClient

client = TelemetryClient()  # loads env per reference/config.md

with client.track_run("my_agent", "my_job") as ctx:
    ctx.log_event("start", {"info": "begin"})
    ctx.set_metrics(items_discovered=10)
    # do work...
```
- Context manager auto-ends with `status="success"`; exceptions mark `status="failed"`.

## Configure (if needed)
Set environment for custom paths or API posting:
- `TELEMETRY_BASE_DIR` / `AGENT_METRICS_DIR` (base storage)
- `TELEMETRY_DB_PATH` (direct DB path)
- `METRICS_API_URL` / `METRICS_API_TOKEN` / `METRICS_API_ENABLED`
See `reference/config.md` for defaults and validation behavior.

## Validate
- Check latest NDJSON: `{base}/raw/events_YYYYMMDD.ndjson`
- Check DB: `sqlite3 {base}/db/telemetry.sqlite "SELECT run_id,status FROM agent_runs ORDER BY start_time DESC LIMIT 5;"`

## Next Steps
- Scenario guide: `guides/instrumentation.md`
- CLI reference: `reference/cli.md`
- File/storage contracts: `reference/file-contracts.md`
