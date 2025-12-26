# Feature Spec: TelemetryClient

**Feature ID:** `client.TelemetryClient`
**Category:** Python Client API
**Status:** VERIFIED (evidence-backed)
**Last Updated:** 2025-12-26

---

## Summary

`TelemetryClient` is the main public API for agent telemetry instrumentation. It provides both explicit (`start_run`/`end_run`) and context manager (`track_run`) patterns for tracking agent execution runs with metrics, events, and error handling.

**Key Design Principles:**
1. **Never crashes the agent** - All exceptions caught and logged
2. **Guaranteed delivery** - HTTP API primary, buffer failover, NDJSON backup
3. **Zero-configuration** - Loads config from environment, auto-detects paths
4. **Fire-and-forget** - External API posting (Google Sheets) is async and silent

---

## Entry Points

### Import Path
```python
from telemetry import TelemetryClient
```

**Evidence:** `src/telemetry/__init__.py:19`

### File Location
`src/telemetry/client.py:100-525`

---

## Inputs/Outputs

### Constructor

**Signature:**
```python
def __init__(self, config: Optional[TelemetryConfig] = None)
```

**Parameters:**
- `config` (Optional[TelemetryConfig]): Configuration object
  - Default: `TelemetryConfig.from_env()` (loads from environment)
  - Evidence: `src/telemetry/client.py:128`

**Returns:** TelemetryClient instance

**Side Effects:**
- Initializes HTTP API client (`HTTPAPIClient`)
- Initializes local buffer (`BufferFile`)
- Initializes NDJSON writer (`NDJSONWriter`)
- Initializes Google Sheets API client (`APIClient`)
- Optionally initializes database writer (backward compatibility)
- Creates `_active_runs` registry (Dict[str, RunRecord])

**Evidence:** `src/telemetry/client.py:121-169`

**Configuration Validation:**
- Calls `config.validate()` on initialization
- Validation failures logged as warnings, not raised
- Evidence: `src/telemetry/client.py:131-136`

---

### Method: start_run

**Signature:**
```python
def start_run(
    agent_name: str,
    job_type: str,
    trigger_type: str = "cli",
    **kwargs
) -> str
```

**Parameters:**
- `agent_name` (str, required): Name of the agent
- `job_type` (str, required): Type of job being run
- `trigger_type` (str, optional): How run was triggered
  - Default: "cli"
  - Options: "cli", "web", "scheduler", "mcp", "manual"
- `**kwargs`: Additional fields (insight_id, product, platform, agent_owner, etc.)

**Returns:**
- `str`: Unique run_id
  - Format: `{YYYYMMDD}T{HHMMSS}Z-{agent_name}-{uuid8}`
  - Example: `"20251210T120530Z-hugo-translator-a1b2c3d4"`

**Side Effects:**
1. Generates run_id via `generate_run_id(agent_name)`
2. Creates `RunRecord` with status="running"
3. Stores record in `_active_runs` registry
4. Writes to HTTP API (primary)
   - On success: Event posted to database
   - On APIUnavailableError: Falls back to buffer
   - On unexpected error: Falls back to buffer
5. Writes to NDJSON backup (always attempted)

**Evidence:** `src/telemetry/client.py:223-276`

**Error Handling:**
- **NEVER raises exceptions**
- On error: Returns `"error-" + generate_run_id(agent_name)`
- Prints error message: `"[ERROR] Telemetry start_run failed: {e}"`
- Evidence: `src/telemetry/client.py:271-275`

---

### Method: end_run

**Signature:**
```python
def end_run(
    run_id: str,
    status: str = "success",
    **kwargs
)
```

**Parameters:**
- `run_id` (str, required): Run ID from start_run()
- `status` (str, optional): Final status
  - Default: "success"
  - Options: "success", "failed", "partial", "timeout", "cancelled"
- `**kwargs`: Updated metrics (items_discovered, items_succeeded, error_summary, etc.)

**Returns:** None

**Side Effects:**
1. Retrieves record from `_active_runs` registry
2. Updates record:
   - Sets `end_time` (ISO8601 timestamp)
   - Sets `status`
   - Calculates `duration_ms` (start_time to end_time)
   - Updates metrics from kwargs
3. Writes to HTTP API (primary)
   - Failover to buffer on error
4. Posts to Google Sheets API (fire-and-forget)
   - Failures logged, not raised
5. Removes from `_active_runs` registry

**Evidence:** `src/telemetry/client.py:277-341`

**Error Handling:**
- **NEVER raises exceptions**
- If run_id not found: Prints warning and returns
- On error: Prints `"[ERROR] Telemetry end_run failed: {e}"`
- Evidence: `src/telemetry/client.py:297-300`, `338-340`

---

### Method: log_event

**Signature:**
```python
def log_event(
    run_id: str,
    event_type: str,
    payload: Optional[Dict[str, Any]] = None
)
```

**Parameters:**
- `run_id` (str, required): Run ID from start_run()
- `event_type` (str, required): Type of event
  - Examples: "checkpoint", "error", "info", "debug"
- `payload` (Optional[Dict[str, Any]]): Event data as dictionary

**Returns:** None

**Side Effects:**
1. Creates `RunEvent` with current timestamp
2. **Writes to NDJSON only** (NOT database)
   - Rationale: Avoid SQLite lock contention on high-frequency logging
   - Design: TEL-03

**Evidence:** `src/telemetry/client.py:342-377`

**Error Handling:**
- **NEVER raises exceptions**
- On error: Prints `"[WARN] Telemetry log_event failed: {e}"`
- Evidence: `src/telemetry/client.py:374-376`

---

### Method: track_run (Context Manager)

**Signature:**
```python
@contextmanager
def track_run(
    agent_name: str,
    job_type: str,
    trigger_type: str = "cli",
    **kwargs
) -> RunContext
```

**Parameters:**
- Same as `start_run()`

**Yields:**
- `RunContext`: Context object with methods:
  - `log_event(event_type, payload)`
  - `set_metrics(**kwargs)`

**Behavior:**
1. **On Entry:**
   - Calls `start_run()` with provided arguments
   - Yields `RunContext` instance
2. **On Normal Exit:**
   - Calls `end_run(run_id, status="success")`
3. **On Exception:**
   - Calls `end_run(run_id, status="failed", error_summary=<exception>)`
   - **Re-raises exception** so agent can handle it

**Evidence:** `src/telemetry/client.py:378-433`

**Example Usage:**
```python
with client.track_run("my_agent", "process") as ctx:
    ctx.log_event("start", {"input": "data.csv"})
    # ... do work ...
    ctx.set_metrics(items_discovered=10, items_succeeded=10)
# Auto-ends with status="success"
```

**Error Handling:**
- Exception during run: Logged and re-raised
- Evidence: `src/telemetry/client.py:421-432`

---

### Method: get_stats

**Signature:**
```python
def get_stats() -> Dict[str, Any]
```

**Parameters:** None

**Returns:**
```python
{
    "total_runs": int,
    "agents": dict,  # {agent_name: count}
    "recent_24h": int,
}
```

**Side Effects:**
1. Tries HTTP API `GET /metrics` first
2. On failure, falls back to `database_writer.get_run_stats()`
3. On all failures, returns `{"error": "Statistics unavailable"}`

**Evidence:** `src/telemetry/client.py:434-464`

**Error Handling:**
- HTTP API errors logged as debug
- Database errors logged as error
- Never raises

---

### Method: associate_commit

**Signature:**
```python
def associate_commit(
    run_id: str,
    commit_hash: str,
    commit_source: str,
    commit_author: Optional[str] = None,
    commit_timestamp: Optional[str] = None
) -> tuple[bool, str]
```

**Parameters:**
- `run_id` (str, required): Run ID to associate commit with
- `commit_hash` (str, required): Git commit SHA (7-40 hex chars)
- `commit_source` (str, required): How commit was created
  - Options: "manual", "llm", "ci"
- `commit_author` (Optional[str]): Git author string (e.g., "Name <email>")
- `commit_timestamp` (Optional[str]): ISO8601 timestamp of commit

**Returns:**
- `tuple[bool, str]`: (success, message)

**Side Effects:**
- Updates database with git commit metadata
- Currently uses `database_writer.associate_commit()`
- **TODO (MIG-008):** Add HTTP API endpoint for commit association

**Evidence:** `src/telemetry/client.py:466-525`

**Error Handling:**
- **NEVER raises exceptions**
- On error: Returns `(False, "[ERROR] associate_commit failed: {e}")`
- If database unavailable: Returns `(False, "[ERROR] Commit association not available")`

---

## Invariants

### INV-1: Never Crash Agent
**Statement:** All public methods MUST catch exceptions and return gracefully.

**Enforcement:**
- All methods wrapped in try/except
- Exceptions printed to stderr, never raised
- Return error values instead of raising

**Evidence:**
- start_run: `src/telemetry/client.py:271-275`
- end_run: `src/telemetry/client.py:338-340`
- log_event: `src/telemetry/client.py:374-376`
- track_run: `src/telemetry/client.py:421-432` (re-raises after logging)
- associate_commit: `src/telemetry/client.py:520-522`

**Exceptions:** `track_run()` re-raises exceptions after logging to allow agent error handling.

---

### INV-2: At-Least-Once Delivery
**Statement:** Telemetry data MUST eventually reach storage, even if HTTP API fails.

**Enforcement:**
1. Primary: HTTP API POST
2. Failover: Local buffer write on APIUnavailableError
3. Backup: NDJSON write always attempted
4. Sync worker retries buffered events

**Evidence:**
- `src/telemetry/client.py:171-221` - _write_run_to_api implementation
- `src/telemetry/client.py:198-215` - Failover logic

---

### INV-3: Active Run Registry
**Statement:** All active runs MUST be tracked in `_active_runs` dict.

**Enforcement:**
- start_run: Adds to registry (line 264)
- end_run: Removes from registry (line 335-336)
- track_run: Uses registry via start_run/end_run

**Evidence:** `src/telemetry/client.py:264`, `335-336`

---

### INV-4: Idempotent Event IDs
**Statement:** Each run record MUST have unique event_id for idempotency.

**Enforcement:**
- RunRecord generates event_id via uuid4 by default
- HTTP API enforces UNIQUE constraint
- Duplicate POSTs return success (not error)

**Evidence:**
- `src/telemetry/models.py:46` - event_id generation
- `telemetry_service.py:575-583` - Duplicate handling

---

## Errors and Edge Cases

### Error: HTTP API Unavailable

**Trigger:** HTTP API unreachable or returning errors

**Behavior:**
1. `APIUnavailableError` caught
2. Event written to local buffer
3. Log message: `"API unavailable, buffering event: {e}"`
4. Sync worker retries later

**Evidence:** `src/telemetry/client.py:206-210`

**Verification:** EVIDENCE_ONLY (read from code)

---

### Error: Invalid Run ID in end_run

**Trigger:** `end_run()` called with run_id not in registry

**Behavior:**
1. Check `_active_runs` registry
2. If not found: Print warning and return
3. Warning: `"[WARN] Run ID not found: {run_id}"`

**Evidence:** `src/telemetry/client.py:297-300`

**Verification:** EVIDENCE_ONLY

---

### Edge Case: NDJSON Write Failure

**Trigger:** NDJSON writer raises exception

**Behavior:**
1. Exception caught
2. Warning logged: `"NDJSON write failed: {e}"`
3. Does NOT prevent HTTP API write
4. Agent continues normally

**Evidence:** `src/telemetry/client.py:217-221`

**Verification:** EVIDENCE_ONLY

---

### Edge Case: Google Sheets API Failure

**Trigger:** External API POST fails

**Behavior:**
1. Exception caught in `end_run()`
2. Debug log: `"Google Sheets API post failed: {e}"`
3. Does NOT affect run completion
4. Fire-and-forget pattern

**Evidence:** `src/telemetry/client.py:324-332`

**Verification:** EVIDENCE_ONLY

---

## Configuration Knobs

### api_url
**Type:** str
**Default:** "http://localhost:8765"
**Purpose:** HTTP API endpoint for telemetry posting
**Source:** `self.config.api_url` or default

**Evidence:** `src/telemetry/client.py:139-141`

---

### buffer_dir
**Type:** Path
**Default:** "./telemetry_buffer"
**Purpose:** Local buffer directory for failover
**Source:** `getattr(self.config, 'buffer_dir', None)` or default

**Evidence:** `src/telemetry/client.py:144-146`

---

### ndjson_dir
**Type:** Path
**Purpose:** NDJSON backup directory
**Source:** `self.config.ndjson_dir`

**Evidence:** `src/telemetry/client.py:149`

---

### External API Config
- `api_url` (Google Sheets): `self.config.api_url`
- `api_token`: `self.config.api_token`
- `api_enabled`: `self.config.api_enabled` (default: true)

**Evidence:** `src/telemetry/client.py:152-156`

---

## Side Effects

### Database Operations
- **Via HTTP API:** POST to /api/v1/runs (INSERT or UPDATE)
- **Fallback:** Via database_writer (backward compatibility, read-only)

---

### File System Operations

**Buffer Writes:**
- File: `{buffer_dir}/<timestamp>_<uuid>.json`
- Trigger: HTTP API unavailable
- Evidence: Buffer.append() called in `src/telemetry/client.py:209`

**NDJSON Writes:**
- File: `{ndjson_dir}/events_{YYYYMMDD}.ndjson`
- Trigger: Every start_run, end_run, log_event
- Format: One JSON object per line
- Evidence: NDJSONWriter.append() called in `src/telemetry/client.py:219`, `372`

---

### Network Operations

**HTTP API POST:**
- Endpoint: `{api_url}/api/v1/runs`
- Method: POST
- Body: RunRecord as JSON
- Evidence: HTTPAPIClient.post_event() called in `src/telemetry/client.py:200`

**Google Sheets API POST:**
- Endpoint: Configured via METRICS_API_URL
- Method: POST (via APIClient)
- Trigger: end_run() only
- Fire-and-forget: Failures logged, not raised
- Evidence: `src/telemetry/client.py:325-326`

---

## Evidence

### Code Locations
- **File:** `src/telemetry/client.py`
- **Class definition:** Lines 100-525
- **Constructor:** Lines 121-169
- **start_run:** Lines 223-276
- **end_run:** Lines 277-341
- **log_event:** Lines 342-377
- **track_run:** Lines 378-433
- **get_stats:** Lines 434-464
- **associate_commit:** Lines 466-525
- **_write_run_to_api:** Lines 171-221 (private helper)

### Dependencies
- `src/telemetry/config.py` - TelemetryConfig
- `src/telemetry/models.py` - RunRecord, RunEvent, APIPayload, helper functions
- `src/telemetry/local.py` - NDJSONWriter
- `src/telemetry/database.py` - DatabaseWriter (backward compat)
- `src/telemetry/api.py` - APIClient (Google Sheets)
- `src/telemetry/http_client.py` - HTTPAPIClient, APIUnavailableError
- `src/telemetry/buffer.py` - BufferFile

### Usage Examples
- **README:** Lines 24-42 (context manager pattern)
- **README:** Lines 100-116 (explicit start/end pattern)

---

## Verification Status

**Status:** VERIFIED

**Verification Method:** Direct file reads
- All method signatures verified from source
- All side effects traced through code
- Error handling verified via try/except blocks
- No hallucinated behaviors

**Confidence:** HIGH

**Inferred Behaviors:** None (all behavior directly observed in code)

**Missing Verification:**
- Runtime behavior of sync worker (implementation not fully traced)
- Google Sheets API integration (external dependency, not verified)
- Buffer sync timing (assumes implementation exists, not verified)
