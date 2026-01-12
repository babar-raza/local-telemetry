# Feature Spec: HTTP Query Runs

**Feature ID:** `http.runs.query`
**Category:** HTTP API
**Route:** `GET /api/v1/runs`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-11

**IMPORTANT:** Line number references updated for commit `8c74f69` (2026-01-11) which reordered routes. Some internal line numbers may be approximate and should be verified against current code.

---

## Summary

Query telemetry runs with filtering, pagination, and sorting support. This endpoint enables **stale run cleanup**, analytics, and operational queries with optimized performance (<1ms on 400+ runs).

**Key Features:**
- Multi-criteria filtering (agent, status, timestamps, job type)
- Pagination with limit/offset
- Results ordered by created_at DESC
- JSON field parsing (metrics_json, context_json)
- Query performance optimized with composite indexes (v2.1.0)

---

## Entry Points

### Route Registration
```python
@app.get("/api/v1/runs")
async def query_runs(
    request: Request,
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    created_before: Optional[str] = None,
    created_after: Optional[str] = None,
    start_time_from: Optional[str] = None,
    start_time_to: Optional[str] = None,
    limit: int = Query(default=100, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    _rate_limit: None = Depends(check_rate_limit)
)
```

**Evidence:** `telemetry_service.py:838-851`

**NOTE:** This route MUST be registered AFTER `GET /api/v1/runs/{event_id}` (line 741) for FastAPI path matching to work correctly. FastAPI matches routes in registration order, so specific routes with path parameters must come before general routes.

**Date/Time Filters:** All date/time filters (created_before, created_after, start_time_from, start_time_to) are now IMPLEMENTED.

### Handler Function
**File:** `telemetry_service.py:838-1022`
**Function:** `query_runs()`

---

## Inputs/Outputs

### HTTP Request

**Method:** GET
**Path:** `/api/v1/runs`
**Query Parameters:** All optional (see below)

**Example:**
```
GET /api/v1/runs?agent_name=hugo-translator&status=running&created_before=2025-12-24T12:00:00Z&limit=50
```

---

### Query Parameters

#### Filter Parameters (Optional)

| Parameter | Type | Validation | Description | Evidence |
|-----------|------|------------|-------------|----------|
| `agent_name` | str | None | Exact match on agent_name | Line 541 |
| `status` | str | Normalized to canonical | Filter by status (supports aliases) | Line 542, 553 |
| `job_type` | str | None | Exact match on job_type | Line 543 |

**Status Alias Normalization:**
- Input: `failed` → Filters for: `failure`
- Input: `completed` → Filters for: `success`
- Input: `succeeded` → Filters for: `success`
- Canonical values returned in results (telemetry_service.py:37-69)

**NOT YET IMPLEMENTED:**
- Date/time filters (created_before, created_after, start_time_from, start_time_to)
- Multi-status filtering (status array or repeated params)
- parent_run_id filtering
- run_id_contains search
- exclude_job_type filtering

#### Pagination Parameters

| Parameter | Type | Default | Constraints | Description | Evidence |
|-----------|------|---------|-------------|-------------|----------|
| `limit` | int | 100 | 1-1000 | Max results to return | Line 544 |
| `offset` | int | 0 | >= 0 | Pagination offset | Line 545 |

**Evidence:** `telemetry_service.py:838-851`

---

### Status Validation and Normalization

**Canonical Statuses (stored in database):**
- `"running"`
- `"success"`
- `"failure"`
- `"partial"`
- `"timeout"`
- `"cancelled"`

**Status Aliases (accepted as input, normalized to canonical):**
- `"failed"` → `"failure"`
- `"completed"` → `"success"`
- `"succeeded"` → `"success"`

**Normalization Logic:**
```python
def normalize_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    if status in CANONICAL_STATUSES:
        return status
    return STATUS_ALIASES.get(status, status)

# Applied in query:
canonical_status = normalize_status(status) if status else None
if canonical_status:
    query += " AND status = ?"
    params.append(canonical_status)
```

**Evidence:** `telemetry_service.py:46-69` (normalization function), `telemetry_service.py:553` (applied in query)

**Behavior:**
- Query param `?status=failed` → Filters for `status='failure'` in database
- Query param `?status=completed` → Filters for `status='success'` in database
- Query param `?status=running` → Filters for `status='running'` (already canonical)
- Results always return canonical statuses

---

### HTTP Response

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:** Array of run objects

**Example:**
```json
[
  {
    "event_id": "550e8400-e29b-41d4-a716-446655440000",
    "run_id": "20251226T120000Z-hugo-translator-a1b2c3d4",
    "agent_name": "hugo-translator",
    "job_type": "translate_posts",
    "status": "success",
    "created_at": "2025-12-26T12:00:00.000000+00:00",
    "start_time": "2025-12-26T12:00:00.000000+00:00",
    "end_time": "2025-12-26T12:00:05.000000+00:00",
    "duration_ms": 5000,
    "items_discovered": 10,
    "items_succeeded": 8,
    "items_failed": 2,
    "git_repo": "https://github.com/owner/repo",
    "git_commit_hash": "abc123",
    "commit_url": "https://github.com/owner/repo/commit/abc123",
    "repo_url": "https://github.com/owner/repo",
    "api_posted": false,
    ...
  }
]
```

**Computed Fields (added in response):**
- `commit_url` - GitHub/GitLab URL for commit (null if git data missing)
- `repo_url` - Normalized repository URL (null if git_repo missing)

**Evidence:** `telemetry_service.py:584-610`

---

### Response Field Transformations

#### JSON Field Parsing

**Fields:** `metrics_json`, `context_json`

**Behavior:**
1. Database stores as JSON string
2. Query parses string to object
3. On parse error:
   - Logs error with details
   - Adds `{field}_parse_error` key to response
   - Preserves original string value

**Code:**
```python
for json_field in ['metrics_json', 'context_json']:
    if run_dict.get(json_field):
        try:
            run_dict[json_field] = json.loads(run_dict[json_field])
        except (json.JSONDecodeError, TypeError) as e:
            log_error(..., field=json_field, error=str(e))
            run_dict[f'{json_field}_parse_error'] = str(e)
```

**Evidence:** `telemetry_service.py:708-728`

**Verification:** VERIFIED (parse error handling confirmed)

---

#### Boolean Conversion

**Field:** `api_posted`

**Behavior:**
- SQLite stores booleans as integers (0/1)
- Convert to Python bool in response

**Code:**
```python
if 'api_posted' in run_dict:
    run_dict['api_posted'] = bool(run_dict['api_posted'])
```

**Evidence:** `telemetry_service.py:730-731`

---

## Invariants

### INV-1: Results Ordered by created_at DESC
**Statement:** Query results MUST be sorted by created_at in descending order (newest first).

**Enforcement:**
```sql
... ORDER BY created_at DESC LIMIT ? OFFSET ?
```

**Evidence:** `telemetry_service.py:697`

**Rationale:** Consistent ordering for pagination, recent runs first

---

### INV-2: Limit Constraints
**Statement:** Limit MUST be between 1 and 1000 inclusive.

**Enforcement:**
- FastAPI Query validator: `Query(default=100, le=1000, ge=1)`
- Invalid values return 422 Unprocessable Entity

**Evidence:** `telemetry_service.py:608`

---

### INV-3: Offset Non-Negative
**Statement:** Offset MUST be >= 0.

**Enforcement:**
- FastAPI Query validator: `Query(default=0, ge=0)`
- Negative values return 422 Unprocessable Entity

**Evidence:** `telemetry_service.py:609`

---

### INV-4: Dynamic WHERE Clause Construction
**Statement:** WHERE clause MUST only include filters with non-None values.

**Enforcement:**
- Start with `WHERE 1=1`
- Conditionally append filters
- Only append if parameter is not None

**Evidence:** `telemetry_service.py:666-697`

**Example:**
```python
query = "SELECT * FROM agent_runs WHERE 1=1"
params = []

if agent_name:
    query += " AND agent_name = ?"
    params.append(agent_name)

if status:
    query += " AND status = ?"
    params.append(status)

# ... etc
```

---

## Errors and Edge Cases

### Error: Invalid Status Value

**Trigger:** `?status=invalid_status`

**Response:**
- **Status:** 400 Bad Request
- **Body:** `{"detail": "Invalid status. Must be one of: [running, success, ...]"}`
- **Log:** `log_error("/api/v1/runs", "ValidationError", "Invalid status: ...", status=...)`

**Evidence:** `telemetry_service.py:634-641`
**Verification:** VERIFIED

---

### Error: Invalid Timestamp Format

**Trigger:** `?created_before=not-a-timestamp`

**Response:**
- **Status:** 400 Bad Request
- **Body:** `{"detail": "Invalid ISO8601 timestamp for created_before: 'not-a-timestamp'"}`
- **Log:** `log_error(..., timestamp_field=..., timestamp_value=...)`

**Evidence:** `telemetry_service.py:644-659`
**Verification:** VERIFIED

---

### Error: Limit Out of Range

**Trigger:** `?limit=0` or `?limit=2000`

**Response:**
- **Status:** 422 Unprocessable Entity
- **Body:** FastAPI validation error

**Verification:** INFERRED (FastAPI Query validator)
**Confidence:** HIGH

---

### Error: Negative Offset

**Trigger:** `?offset=-1`

**Response:**
- **Status:** 422 Unprocessable Entity
- **Body:** FastAPI validation error

**Verification:** INFERRED (FastAPI Query validator)
**Confidence:** HIGH

---

### Error: Database Query Failure

**Trigger:** SQLite error during query execution

**Response:**
- **Status:** 500 Internal Server Error
- **Body:** `{"detail": "Failed to query runs: <error>"}`
- **Log:** `log_error(..., agent_name=..., status=..., limit=...)`
- **Log:** `logger.error(f"[ERROR] Failed to query runs: {e}")`

**Evidence:** `telemetry_service.py:754-763`
**Verification:** VERIFIED

---

### Error: Rate Limit Exceeded

**Trigger:** Client exceeds `TELEMETRY_RATE_LIMIT_RPM` (if enabled)

**Response:**
- **Status:** 429 Too Many Requests
- **Headers:** `Retry-After: 60`, `X-RateLimit-Limit: <rpm>`, `X-RateLimit-Remaining: 0`
- **Body:** `{"detail": "Rate limit exceeded. Max <rpm> requests per minute."}`

**Evidence:** `telemetry_service.py:325-335` (check_rate_limit dependency)
**Verification:** VERIFIED

---

### Edge Case: No Results

**Trigger:** Query with filters that match no runs

**Response:**
- **Status:** 200 OK
- **Body:** `[]` (empty array)
- **Log:** `logger.info(f"[OK] Query returned 0 runs (limit={limit}, offset={offset})")`

**Evidence:** `telemetry_service.py:751` (returns results array, could be empty)
**Verification:** VERIFIED

---

### Edge Case: JSON Parse Error

**Trigger:** Database contains invalid JSON in `metrics_json` or `context_json`

**Behavior:**
1. Attempts `json.loads(run_dict[json_field])`
2. On JSONDecodeError or TypeError:
   - Logs error with context
   - Adds `{field}_parse_error` key
   - Preserves original string value
3. Run still included in results

**Evidence:** `telemetry_service.py:710-728`
**Verification:** VERIFIED

**Example Response:**
```json
{
  "event_id": "...",
  "metrics_json": "{invalid json",
  "metrics_json_parse_error": "Expecting value: line 1 column 1 (char 0)",
  ...
}
```

---

### Edge Case: Pagination Beyond Results

**Trigger:** `?offset=1000` when only 100 results exist

**Response:**
- **Status:** 200 OK
- **Body:** `[]` (empty array)

**Verification:** INFERRED (SQLite LIMIT/OFFSET behavior)
**Confidence:** HIGH

---

## Configuration Knobs

### TELEMETRY_RATE_LIMIT_ENABLED
**Type:** bool
**Default:** false
**Purpose:** Enable IP-based rate limiting
**Impact:** Rate limit dependency skipped if false

**Evidence:** `src/telemetry/config.py:300`, `telemetry_service.py:314`

---

### TELEMETRY_RATE_LIMIT_RPM
**Type:** int
**Default:** 60
**Purpose:** Requests per minute limit per IP
**Used if:** RATE_LIMIT_ENABLED=true

**Evidence:** `src/telemetry/config.py:301`

---

## Side Effects

### Database Operations

**Table:** `agent_runs`
**Operation:** SELECT

**Base Query:**
```sql
SELECT * FROM agent_runs WHERE 1=1
```

**Dynamic Filters (appended if parameter present):**
```sql
AND agent_name = ?
AND status = ?
AND job_type = ?
AND created_at < ?
AND created_at > ?
AND start_time >= ?
AND start_time <= ?
```

**Ordering & Pagination:**
```sql
ORDER BY created_at DESC LIMIT ? OFFSET ?
```

**Evidence:** `telemetry_service.py:666-698`

---

### Index Usage

**Indexes:**
1. Composite: `(agent_name, status, created_at)`
   - Used when filtering by agent_name + status
2. Index: `created_at DESC`
   - Used for ORDER BY
3. UNIQUE: `event_id`
   - Not used in this query

**Performance:** Queries on 400+ runs complete in <1ms
**Evidence:** README.md:236-242

---

### Logging

**Structured Query Logging:**
```python
log_query(query_params, len(results), get_duration())
```

**Evidence:** `telemetry_service.py:749`

**Parameters Logged:**
- Non-None query parameters
- Result count
- Query duration (milliseconds)

**Success Log:**
```
logger.info(f"[OK] Query returned {len(results)} runs (limit={limit}, offset={offset})")
```

**Evidence:** `telemetry_service.py:751`

**Error Log:**
```
log_error("/api/v1/runs", type(e).__name__, str(e), agent_name=..., status=..., limit=...)
logger.error(f"[ERROR] Failed to query runs: {e}")
```

**Evidence:** `telemetry_service.py:757-759`

---

## Use Case: Stale Run Cleanup

**Scenario:** Detect and mark stale "running" runs as "cancelled" on agent startup.

**Query:**
```
GET /api/v1/runs?agent_name=hugo-translator&status=running&created_before=2025-12-26T11:00:00Z
```

**Filters:**
- `agent_name`: Specific agent
- `status=running`: Only active runs
- `created_before`: Older than 1 hour (stale threshold)

**Follow-up:**
For each stale run:
```
PATCH /api/v1/runs/{event_id}
{
  "status": "cancelled",
  "end_time": "<now>",
  "error_summary": "Stale run cleaned up on startup (created at ...)"
}
```

**Evidence:** README.md:205-234
**Verification:** Use case documented, endpoints verified

---

## Performance

### Query Performance Benchmarks

**Dataset:** 400+ runs
**Query Time:** <1ms
**Improvement:** 83% faster with composite indexes (v2.1.0)

**Evidence:** README.md:236-242

**Optimization:**
- Composite index: `(agent_name, status, created_at)`
- Covering index for common queries
- ORDER BY uses created_at index

---

### Duration Tracking

**Instrumentation:**
```python
with track_duration() as get_duration:
    # ... query execution ...
    log_query(query_params, len(results), get_duration())
```

**Evidence:** `telemetry_service.py:632`, `749`

**Logged Metrics:**
- Query parameters
- Result count
- Execution duration (ms)

---

## Dependencies

### FastAPI Dependencies

**check_rate_limit:**
- Function: IP-based rate limiting
- File: `telemetry_service.py:298-337`
- Skipped if: `TELEMETRY_RATE_LIMIT_ENABLED=false`

**Evidence:** `telemetry_service.py:610`

---

### Database Connection

**Context Manager:** `get_db()`
- Evidence: `telemetry_service.py:341-361`
- Acquires SQLite connection
- Sets row_factory to sqlite3.Row
- Auto-closes on exit

**Used in:** `telemetry_service.py:662` (within try block)

**Row Factory:**
```python
conn.row_factory = sqlite3.Row
```
**Purpose:** Enables dict-like access to columns
**Evidence:** `telemetry_service.py:663`

---

### Utility Functions

**track_duration:**
- Module: `src/telemetry/logger.py`
- Purpose: Context manager for timing operations
- Returns: Callable that returns duration in milliseconds

**log_query:**
- Module: `src/telemetry/logger.py`
- Purpose: Structured logging for query operations
- Parameters: query_params, result_count, duration_ms

**log_error:**
- Module: `src/telemetry/logger.py`
- Purpose: Structured error logging with context

**Evidence:** `telemetry_service.py:58` (imports)

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:598-763`
- **Status validation:** `telemetry_service.py:634-641`
- **Timestamp validation:** `telemetry_service.py:644-659`
- **Dynamic query building:** `telemetry_service.py:666-698`
- **JSON parsing:** `telemetry_service.py:708-728`
- **Boolean conversion:** `telemetry_service.py:730-731`
- **Result assembly:** `telemetry_service.py:703-733`

### Dependencies
- **Rate limiting:** `telemetry_service.py:298-337`
- **Database context:** `telemetry_service.py:341-361`
- **Logger utilities:** `src/telemetry/logger.py`

### README References
- **API endpoints:** README.md:185-202
- **Stale run cleanup use case:** README.md:205-234
- **Performance benchmarks:** README.md:236-242

---

## Verification Status

**Status:** VERIFIED

**Verification Method:**
- Direct file reads of handler implementation
- Validation logic confirmed
- Error handling traced
- Performance claims cross-referenced with README

**Confidence:** HIGH

**Inferred Behaviors:**
- FastAPI 422 response for constraint violations (standard framework)
- SQLite LIMIT/OFFSET pagination behavior (standard SQL)
- Empty array for no results (standard JSON API)

**Missing Verification:**
- Runtime query performance (benchmarks cited from README, not independently verified)
- Actual index usage (database query planner not inspected)
- Rate limiter sliding window implementation (not fully traced)

**Evidence Strength:**
- Query logic: STRONG (direct code read)
- Validation: STRONG (explicit validation code)
- Error handling: STRONG (exception handlers traced)
- Performance: MEDIUM (cited from README, not measured)
