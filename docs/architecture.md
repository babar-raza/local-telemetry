# Architecture Overview

## System Purpose

The Local Telemetry Platform is a Python library for tracking agent runs, metrics, and performance. It provides:

- **Run tracking**: Start/end timestamps, status, metrics
- **Event logging**: Checkpoint events during runs
- **Dual-write storage**: NDJSON for resilience, SQLite for queries
- **Optional API posting**: Fire-and-forget to remote endpoints

## Core Components

```
┌─────────────────────────────────────────────────────────────────┐
│                        TelemetryClient                          │
│                   (Main Public Interface)                       │
└─────────────┬───────────────────────────────────────┬───────────┘
              │                                       │
              ▼                                       ▼
┌─────────────────────────┐             ┌─────────────────────────┐
│      NDJSONWriter       │             │    DatabaseWriter       │
│   (Local Resilience)    │             │  (Structured Queries)   │
└─────────────────────────┘             └─────────────────────────┘
              │                                       │
              ▼                                       ▼
┌─────────────────────────┐             ┌─────────────────────────┐
│  {base}/raw/*.ndjson    │             │  {base}/db/*.sqlite     │
│  Daily rotating files   │             │  WAL mode database      │
└─────────────────────────┘             └─────────────────────────┘
```

## Module Descriptions

### `telemetry.client` - Main Client

- `TelemetryClient`: Entry point for all telemetry operations
- `RunContext`: Context object yielded by `track_run()` context manager
- Handles start/end runs, logging events, and updating metrics

### `telemetry.config` - Configuration

- `TelemetryConfig`: Dataclass holding all configuration
- Loads from environment variables with multi-tier resolution
- Auto-detects storage paths across Windows/Linux/Docker

### `telemetry.database` - SQLite Storage

- `DatabaseWriter`: Writes to SQLite with retry logic
- WAL mode for concurrent access
- Exponential backoff on lock contention (100ms, 200ms, 400ms)
- Creates database directory if missing

### `telemetry.local` - NDJSON Storage

- `NDJSONWriter`: Appends JSON lines to daily rotating files
- File locking for concurrent writes (Windows: msvcrt, Unix: fcntl)
- Crash resilience via explicit flush + fsync

### `telemetry.models` - Data Models

- `RunRecord`: Full agent run record (matches SQLite schema)
- `RunEvent`: Single event within a run
- `APIPayload`: Simplified payload for API posting
- Helper functions for timestamps and run IDs

### `telemetry.schema` - Database Schema

- SQLite table definitions (agent_runs, run_events, commits, schema_migrations)
- Index definitions for query performance
- Schema version tracking (currently v3)

### `telemetry.api` - API Client

- `APIClient`: Posts to remote endpoints (Google Sheets API)
- Exponential backoff retry (1s, 2s, 4s)
- Fire-and-forget: failures logged but don't crash agents

## Data Flow

### Writing a Run

```
1. client.start_run(agent_name, job_type)
   └─> Generate run_id (timestamp + agent + uuid8)
   └─> Create RunRecord with status="running"
   └─> NDJSONWriter.append() → raw/events_YYYYMMDD.ndjson
   └─> DatabaseWriter.insert_run() → db/telemetry.sqlite

2. client.log_event(run_id, event_type, payload)
   └─> Create RunEvent
   └─> NDJSONWriter.append() only (per TEL-03 design, avoids DB contention)

3. client.end_run(run_id, status, metrics)
   └─> Update RunRecord with end_time, status, metrics
   └─> NDJSONWriter.append() → raw/events_YYYYMMDD.ndjson
   └─> DatabaseWriter.update_run() → db/telemetry.sqlite
   └─> APIClient.post_run_sync() → remote API (optional)
```

### Context Manager Pattern

```python
with client.track_run("agent", "job") as ctx:
    ctx.log_event("checkpoint", {"step": 1})
    ctx.set_metrics(items_discovered=10)
    # ... do work ...
# Auto-end with status="success"
# If exception raised: auto-end with status="failed"
```

## Concurrency Strategy

- **NDJSON**: File locking ensures atomic appends
- **SQLite**: WAL mode + retry logic handles concurrent writes
- **Events**: Written to NDJSON only to avoid DB lock contention
- **Run summaries**: 1 INSERT at start, 1 UPDATE at end (low frequency)

## Schema Version History

| Version | Changes |
|---------|---------|
| v1 | Initial schema |
| v2 | Added `insight_id` for SEO Intelligence integration |
| v3 | Added `product_family`, `subdomain` for business context |

## Storage Paths

| Component | Path | Purpose |
|-----------|------|---------|
| NDJSON logs | `{base}/raw/events_YYYYMMDD.ndjson` | Crash-resilient raw logs |
| SQLite DB | `{base}/db/telemetry.sqlite` | Structured queries |
| WAL files | `{base}/db/telemetry.sqlite-wal` | SQLite write-ahead log |
| SHM file | `{base}/db/telemetry.sqlite-shm` | SQLite shared memory |

## Error Handling

The library is designed to **never crash the agent**:

1. Configuration validation errors → logged as warnings
2. Write failures → logged, operation continues
3. API failures → logged, marked for retry
4. Exceptions in user code → run marked as "failed", exception re-raised

## Performance Characteristics

| Operation | Target | Notes |
|-----------|--------|-------|
| start_run | < 10ms | NDJSON + DB insert |
| log_event | < 5ms | NDJSON only |
| end_run | < 50ms | NDJSON + DB update + API |
| Throughput | > 20 writes/sec | With WAL mode |
