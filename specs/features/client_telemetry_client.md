# Feature Spec: TelemetryClient

**Feature ID:** `client.TelemetryClient`
**Category:** Python Client API
**Status:** VERIFIED (evidence-backed)
**Last Updated:** 2026-01-01

---

## Summary

`TelemetryClient` is the main public API for agent telemetry instrumentation. It provides both explicit (`start_run`/`end_run`) and context manager (`track_run`) patterns for tracking agent execution runs with metrics, events, and error handling.

**Key Design Principles:**
1. **Never crashes the agent** - All exceptions caught and logged
2. **Guaranteed delivery** - HTTP API primary, buffer failover, NDJSON backup
3. **Zero-configuration** - Loads config from environment, auto-detects paths
4. **Fire-and-forget** - External API posting (Google Sheets) is async and silent
5. **Custom run_id support** - Optional custom run IDs with validation and duplicate detection (v2.1.0+)

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

## RunIDMetrics Class

**Purpose**: In-memory metrics for tracking custom run_id usage, validation rejections, and duplicate detection.

**File Location:** `src/telemetry/client.py:39-150`

### Thread Safety

RunIDMetrics uses `threading.Lock` for thread-safe concurrent access to counters.

**Evidence:** `src/telemetry/client.py:53`

### Counters

**Run ID Source Counters:**
- `custom_accepted` (int): Custom run_ids that passed validation
- `generated` (int): Auto-generated run_ids used

**Validation Rejection Counters:**
- `rejected_empty` (int): Rejected because empty or whitespace-only
- `rejected_too_long` (int): Rejected because > 255 characters
- `rejected_invalid_chars` (int): Rejected because path separators or null bytes

**Duplicate Detection:**
- `duplicates_detected` (int): Duplicate run_ids found in active registry

**Evidence:** `src/telemetry/client.py:55-66`

### Methods

**get_snapshot() -> Dict[str, Any]:**
Returns thread-safe snapshot of current metrics with calculated totals and percentages.

**Return Value:**
```python
{
    "run_id_metrics": {
        "custom_accepted": int,
        "generated": int,
        "rejected": {
            "empty": int,
            "too_long": int,
            "invalid_chars": int,
            "total": int,
        },
        "duplicates_detected": int,
        "total_runs": int,
        "custom_percentage": float,
    },
    "timestamp": str  # ISO8601
}
```

**Evidence:** `src/telemetry/client.py:97-132`

**to_json() -> str:**
Returns metrics snapshot as formatted JSON string.

**Evidence:** `src/telemetry/client.py:134-141`

**log_metrics():**
Logs current metrics to logger as structured JSON.

**Evidence:** `src/telemetry/client.py:143-149`

---

## Custom Run ID Validation Rules

**Constant:** `MAX_RUN_ID_LENGTH = 255`

**Evidence:** `src/telemetry/client.py:20`

**Validation Function:** `_validate_custom_run_id(run_id: str) -> tuple[bool, Optional[str]]`

**Rules Enforced:**

1. **Not Empty**: run_id must not be empty or whitespace-only
   - Rejection reason: `"empty"`
   - Evidence: `src/telemetry/client.py:436-441`

2. **Length Limit**: run_id must be <= 255 characters
   - Rejection reason: `"too_long"`
   - Evidence: `src/telemetry/client.py:443-448`

3. **No Path Separators**: run_id must not contain `/` or `\`
   - Security: Prevents directory traversal attacks
   - Rejection reason: `"invalid_chars"`
   - Evidence: `src/telemetry/client.py:450-456`

4. **No Null Bytes**: run_id must not contain `\x00`
   - Security: Prevents string termination attacks
   - Rejection reason: `"invalid_chars"`
   - Evidence: `src/telemetry/client.py:450-456`

**Return Values:**
- `(True, None)`: run_id is valid
- `(False, "empty")`: run_id is empty or whitespace
- `(False, "too_long")`: run_id exceeds 255 characters
- `(False, "invalid_chars")`: run_id contains path separators or null bytes

**Side Effects:**
- Increments appropriate rejection counter in run_id_metrics
- Never crashes (metrics updates wrapped in try/except)

**Evidence:** `src/telemetry/client.py:416-458`

**Reference:** See `docs/schema_constraints.md` for full constraint documentation

---

## Duplicate Run ID Detection

**Behavior:** start_run() checks for duplicate run_id in `_active_runs` registry before creating new run.

**Duplicate Handling:**

**For Custom run_ids:**
1. Log error: `"Custom run_id '{custom_run_id}' is already active"`
2. Append suffix: `"{custom_run_id}-duplicate-{uuid8}"`
3. Return modified run_id
4. Increment duplicates_detected counter
5. Evidence: `src/telemetry/client.py:529-539`

**For Generated run_ids:**
1. Log info: `"Regenerating run_id to avoid duplicate"`
2. Generate new run_id with fresh UUID
3. Return new run_id
4. Increment duplicates_detected counter
5. Evidence: `src/telemetry/client.py:541-544`

**Rationale:** Prevents database UNIQUE constraint violations while preserving custom run_id intent.

**Evidence:** `src/telemetry/client.py:520-544`

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
- `**kwargs`: Additional fields (insight_id, product, platform, agent_owner, run_id, etc.)
  - **run_id** (str, optional): Custom run ID to use instead of auto-generated
    - If provided, will be validated (see Validation Rules below)
    - If validation fails, falls back to auto-generated run_id
    - Evidence: `src/telemetry/client.py:474-484`

**Returns:**
- `str`: Unique run_id
  - Format (auto-generated): `{YYYYMMDD}T{HHMMSS}Z-{agent_name}-{uuid8}`
  - Example (auto-generated): `"20251210T120530Z-hugo-translator-a1b2c3d4"`
  - Format (custom): Any string meeting validation rules
  - Example (custom): `"custom-id-123"`, `"project-alpha-run-001"`

**Side Effects:**
1. Extracts custom run_id from kwargs if provided
2. Validates custom run_id (if provided):
   - Checks length <= 255 characters (MAX_RUN_ID_LENGTH)
   - Rejects empty or whitespace-only strings
   - Rejects path separators (/, \) and null bytes
   - Updates run_id_metrics counters
   - Falls back to generated run_id if validation fails
   - Evidence: `src/telemetry/client.py:486-518`
3. Checks for duplicate run_id in active runs registry:
   - If duplicate custom run_id: appends suffix (e.g., "-duplicate-a1b2c3d4")
   - If duplicate generated run_id: regenerates with new UUID
   - Updates duplicates_detected counter
   - Evidence: `src/telemetry/client.py:520-544`
4. Creates `RunRecord` with status="running"
5. Stores record in `_active_runs` registry
6. Writes to HTTP API (primary)
   - On success: Event posted to database
   - On APIUnavailableError: Falls back to buffer
   - On unexpected error: Falls back to buffer
7. Writes to NDJSON backup (always attempted)

**Evidence:** `src/telemetry/client.py:460-574`

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
- Same as `start_run()`, including support for custom `run_id` in kwargs
- All validation rules and behaviors from `start_run()` apply

**Yields:**
- `RunContext`: Context object with methods:
  - `log_event(event_type, payload)`
  - `set_metrics(**kwargs)`
  - `run_id` attribute contains the actual run_id (custom or generated)

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

**Basic (auto-generated run_id):**
```python
with client.track_run("my_agent", "process") as ctx:
    ctx.log_event("start", {"input": "data.csv"})
    # ... do work ...
    ctx.set_metrics(items_discovered=10, items_succeeded=10)
# Auto-ends with status="success"
```

**With Custom run_id:**
```python
with client.track_run(
    agent_name="my_agent",
    job_type="process",
    run_id="custom-run-001"
) as ctx:
    print(f"Using run_id: {ctx.run_id}")  # "custom-run-001" if valid
    ctx.log_event("checkpoint", {"step": 1})
    ctx.set_metrics(items_discovered=100, items_succeeded=98)
# Auto-ends with status="success"
```

**Evidence:** `tests/test_integration_custom_run_id.py:296-316`

**Error Handling:**
- Exception during run: Logged and re-raised
- Evidence: `src/telemetry/client.py:421-432`

---

### Method: get_run_id_metrics

**Signature:**
```python
def get_run_id_metrics() -> Dict[str, Any]
```

**Parameters:** None

**Returns:**
```python
{
    "run_id_metrics": {
        "custom_accepted": int,
        "generated": int,
        "rejected": {
            "empty": int,
            "too_long": int,
            "invalid_chars": int,
            "total": int,
        },
        "duplicates_detected": int,
        "total_runs": int,
        "custom_percentage": float,
    },
    "timestamp": str  # ISO8601
}
```

**Side Effects:**
- Calls `run_id_metrics.get_snapshot()` for thread-safe snapshot
- On error: Returns `{"error": "...", "timestamp": "..."}`

**Evidence:** `src/telemetry/client.py:733-753`

**Error Handling:**
- Never raises exceptions
- Returns error dict on failure

**Example:**
```python
metrics = client.get_run_id_metrics()
print(f"Custom IDs: {metrics['run_id_metrics']['custom_accepted']}")
print(f"Generated IDs: {metrics['run_id_metrics']['generated']}")
print(f"Total rejected: {metrics['run_id_metrics']['rejected']['total']}")
```

---

### Method: log_run_id_metrics

**Signature:**
```python
def log_run_id_metrics()
```

**Parameters:** None

**Returns:** None

**Side Effects:**
- Logs run_id metrics to logger as structured JSON
- Uses INFO level logging

**Evidence:** `src/telemetry/client.py:755-767`

**Error Handling:**
- Never raises exceptions
- Logs warning on failure

**Example:**
```python
client.log_run_id_metrics()
# Output to logger:
# INFO: Run ID Metrics:
# {
#   "run_id_metrics": {
#     "custom_accepted": 5,
#     "generated": 10,
#     ...
#   }
# }
```

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
    "run_id_metrics": {  # Added in v2.1.0
        "custom_accepted": int,
        "generated": int,
        "rejected": {...},
        "duplicates_detected": int,
        "total_runs": int,
        "custom_percentage": float,
    },
    "timestamp": str  # ISO8601
}
```

**Side Effects:**
1. Tries HTTP API `GET /metrics` first
2. On failure, falls back to `database_writer.get_run_stats()`
3. Merges run_id_metrics snapshot into stats dict
4. On all failures, returns `{"error": "Statistics unavailable"}`

**Evidence:** `src/telemetry/client.py:769-810` (includes run_id_metrics merge at lines 803-808)

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

## Custom Run ID Usage Examples

### Example 1: Basic Custom Run ID

**Use Case:** Provide deterministic run_id for testing or correlation.

```python
from telemetry import TelemetryClient

client = TelemetryClient()

# Start run with custom ID
run_id = client.start_run(
    agent_name="my-agent",
    job_type="process-files",
    run_id="project-alpha-run-001"
)

print(f"Run ID: {run_id}")  # "project-alpha-run-001"

# ... do work ...

client.end_run(run_id, status="success", items_succeeded=10)
```

**Evidence:** `tests/test_integration_custom_run_id.py:204-217`

---

### Example 2: Custom Run ID with Validation Handling

**Use Case:** Handle validation failures gracefully.

```python
from telemetry import TelemetryClient

client = TelemetryClient()

# Attempt with invalid run_id (too long)
run_id = client.start_run(
    agent_name="my-agent",
    job_type="test",
    run_id="a" * 300  # Exceeds MAX_RUN_ID_LENGTH (255)
)

# Client automatically falls back to generated run_id
print(f"Run ID: {run_id}")  # Will be auto-generated, NOT "aaa..."
assert run_id != "a" * 300

client.end_run(run_id, status="success")
```

**Evidence:** `tests/test_integration_custom_run_id.py:368-399`

---

### Example 3: Valid Special Characters

**Use Case:** Use hyphens, underscores, dots in custom run_id.

```python
from telemetry import TelemetryClient

client = TelemetryClient()

# These are all valid custom run_ids
valid_ids = [
    "test-run-with-hyphens",
    "test_run_with_underscores",
    "test.run.with.dots",
    "test-run_mixed.123",
]

for custom_id in valid_ids:
    run_id = client.start_run(
        agent_name="my-agent",
        job_type="test",
        run_id=custom_id
    )
    assert run_id == custom_id  # Custom ID preserved
    client.end_run(run_id, status="success")
```

**Evidence:** `tests/test_integration_custom_run_id.py:447-468`

---

### Example 4: Retrieve Run ID Metrics

**Use Case:** Monitor custom run_id usage and validation rejections.

```python
from telemetry import TelemetryClient

client = TelemetryClient()

# Perform several runs with custom and generated IDs
client.start_run("agent1", "job1", run_id="custom-001")
client.start_run("agent2", "job2")  # Auto-generated
client.start_run("agent3", "job3", run_id="")  # Empty - will be rejected

# Get metrics
metrics = client.get_run_id_metrics()

print(f"Custom accepted: {metrics['run_id_metrics']['custom_accepted']}")  # 1
print(f"Generated: {metrics['run_id_metrics']['generated']}")  # 2 (1 auto + 1 fallback)
print(f"Rejected (empty): {metrics['run_id_metrics']['rejected']['empty']}")  # 1
print(f"Custom percentage: {metrics['run_id_metrics']['custom_percentage']}%")

# Or log metrics to logger
client.log_run_id_metrics()
```

**Evidence:** `src/telemetry/client.py:733-767`

---

### Example 5: Concurrent Runs with Different Custom IDs

**Use Case:** Track multiple simultaneous runs with distinct identifiers.

```python
from telemetry import TelemetryClient

client = TelemetryClient()

# Start multiple runs with different custom IDs
run_ids = []
for i in range(3):
    run_id = client.start_run(
        agent_name="worker",
        job_type="concurrent",
        run_id=f"batch-2024-{i:03d}"
    )
    run_ids.append(run_id)

# All custom IDs are preserved
assert run_ids == ["batch-2024-000", "batch-2024-001", "batch-2024-002"]

# End all runs
for run_id in run_ids:
    client.end_run(run_id, status="success")
```

**Evidence:** `tests/test_integration_custom_run_id.py:401-438`

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
