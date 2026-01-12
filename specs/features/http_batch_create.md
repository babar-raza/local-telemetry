# Feature Spec: HTTP Batch Create Runs

**Feature ID:** `http.batch.create`
**Category:** HTTP API
**Route:** `POST /api/v1/runs/batch`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-12

---

## Summary

Bulk insert multiple telemetry runs in a single HTTP request with automatic deduplication and error handling. This endpoint enables efficient batch uploads from buffered clients, NDJSON file imports, and bulk data migrations.

**Key Features:**
- Accepts array of TelemetryRun objects
- Automatic deduplication via event_id UNIQUE constraint
- Per-run error handling (one failure doesn't block others)
- Returns detailed statistics (inserted, duplicates, errors)
- Transactional commit (all successful inserts committed together)

**Common Use Cases:**
- Buffer sync worker uploading queued events
- NDJSON file import via migration scripts
- Bulk historical data import
- Batch retry after API downtime

---

## Entry Points

### Route Registration
```python
@app.post("/api/v1/runs/batch", response_model=BatchResponse)
async def create_runs_batch(
    runs: List[TelemetryRun],
    request: Request,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
```

**Evidence:** `telemetry_service.py:1023-1029`

### Handler Function
**File:** `telemetry_service.py:1023-1116`
**Function:** `create_runs_batch()`

---

## Inputs/Outputs

### HTTP Request

**Method:** POST
**Path:** `/api/v1/runs/batch`
**Content-Type:** `application/json`

**Body:**
```json
[
  {
    "event_id": "evt_001",
    "run_id": "run_001",
    "agent_name": "test-agent",
    "job_type": "test",
    "status": "success",
    "created_at": "2026-01-12T10:00:00Z",
    "start_time": "2026-01-12T10:00:00Z",
    "end_time": "2026-01-12T10:01:00Z",
    "duration_ms": 60000,
    "items_succeeded": 10
  },
  {
    "event_id": "evt_002",
    "run_id": "run_002",
    "agent_name": "test-agent",
    "job_type": "test",
    "status": "failure",
    "created_at": "2026-01-12T10:05:00Z",
    "start_time": "2026-01-12T10:05:00Z",
    "end_time": "2026-01-12T10:06:00Z",
    "duration_ms": 60000,
    "error_summary": "Connection timeout"
  }
]
```

**Body Schema:** Array of `TelemetryRun` objects (see [Create Run](http_create_run.md) for full field spec)

**Evidence:** `telemetry_service.py:1025` (runs: List[TelemetryRun])

---

### HTTP Response

#### Success Response (200 OK)

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:**
```json
{
  "inserted": 2,
  "duplicates": 0,
  "errors": [],
  "total": 2
}
```

**Fields:**
- `inserted` (int) - Number of new runs successfully inserted
- `duplicates` (int) - Number of duplicate event_ids (idempotent skips)
- `errors` (array) - List of error messages for failed inserts (format: `"event_id: error"`)
- `total` (int) - Total number of runs in request (inserted + duplicates + errors.length)

**Evidence:** `telemetry_service.py:177-182` (BatchResponse model)

**Evidence:** `telemetry_service.py:1111-1116` (response construction)

---

#### Partial Success Response (200 OK with Errors)

**Status:** 200 OK (endpoint never returns 400/500 for partial failures)

**Body:**
```json
{
  "inserted": 1,
  "duplicates": 1,
  "errors": [
    "evt_003: CHECK constraint failed: status IN ('running', 'success', 'failure', 'partial', 'timeout', 'cancelled')"
  ],
  "total": 3
}
```

**Behavior:** Individual run failures don't stop batch processing. Endpoint processes all runs and returns statistics.

**Evidence:** `telemetry_service.py:1099-1106` (per-run exception handling)

---

## Processing Logic

### Step 1: Status Normalization

For each run in the batch:
```python
normalized_status = normalize_status(run.status)
```

**Transformation Rules:**
- `"failed"` → `"failure"`
- `"completed"` → `"success"`
- `"succeeded"` → `"success"`
- Other canonical statuses pass through unchanged

**Evidence:** `telemetry_service.py:1048`

---

### Step 2: Database Insertion

**SQL Operation:**
```sql
INSERT INTO agent_runs (
    event_id, run_id, created_at, start_time, end_time,
    agent_name, job_type, status,
    product, product_family, platform, subdomain,
    website, website_section, item_name,
    items_discovered, items_succeeded, items_failed, items_skipped,
    duration_ms,
    input_summary, output_summary, source_ref, target_ref,
    error_summary, error_details,
    git_repo, git_branch, git_commit_hash, git_run_tag,
    host, environment, trigger_type,
    metrics_json, context_json,
    api_posted, api_posted_at, api_retry_count,
    insight_id, parent_run_id
) VALUES (?, ?, ?, ...)
```

**Evidence:** `telemetry_service.py:1050-1095`

**Field Transformations:**
- `metrics_json`: Serialized with `json.dumps()` if not None
- `context_json`: Serialized with `json.dumps()` if not None
- `status`: Normalized before insert

**Evidence:** `telemetry_service.py:1091-1092` (JSON serialization)

---

### Step 3: Error Handling

**Duplicate Detection:**
```python
except sqlite3.IntegrityError as e:
    if "UNIQUE constraint failed: agent_runs.event_id" in str(e):
        duplicates += 1  # Idempotent - already processed
    else:
        errors.append(f"{run.event_id}: {str(e)}")
```

**Evidence:** `telemetry_service.py:1099-1103`

**Other Exceptions:**
```python
except Exception as e:
    errors.append(f"{run.event_id}: {str(e)}")
```

**Evidence:** `telemetry_service.py:1104-1105`

**Behavior:** All exceptions captured per-run. Processing continues for remaining runs.

---

### Step 4: Transaction Commit

**Operation:**
```python
conn.commit()
```

**Evidence:** `telemetry_service.py:1107`

**Guarantees:**
- All successful inserts committed together
- Failed inserts skipped (don't rollback successful ones)
- Database consistency maintained via transaction

---

### Step 5: Logging and Response

**Log Entry:**
```python
logger.info(f"[OK] Batch insert: {inserted} new, {duplicates} duplicates, {len(errors)} errors")
```

**Evidence:** `telemetry_service.py:1109`

**Response:**
```python
return BatchResponse(
    inserted=inserted,
    duplicates=duplicates,
    errors=errors,
    total=len(runs)
)
```

**Evidence:** `telemetry_service.py:1111-1116`

---

## Invariants

### INV-1: Idempotency via event_id

**Statement:** Duplicate event_id values MUST be silently counted as duplicates (not errors).

**Enforcement:**
```python
if "UNIQUE constraint failed: agent_runs.event_id" in str(e):
    duplicates += 1  # Don't add to errors array
```

**Evidence:** `telemetry_service.py:1100-1101`

**Rationale:** Supports retries, buffered uploads, and at-least-once delivery guarantees.

---

### INV-2: Partial Failure Tolerance

**Statement:** Individual run failures MUST NOT stop processing of remaining runs.

**Enforcement:** Try-except block per run in loop

**Evidence:** `telemetry_service.py:1045-1106` (for loop with per-run exception handling)

**Rationale:** Maximize data ingestion even with some invalid records.

---

### INV-3: Status Normalization

**Statement:** Status aliases MUST be normalized before database insert.

**Enforcement:** `normalize_status()` called before INSERT

**Evidence:** `telemetry_service.py:1048`, `1082`

**Canonical Statuses:** running, success, failure, partial, timeout, cancelled

---

### INV-4: Transaction Boundary

**Statement:** All successful inserts MUST be committed together in a single transaction.

**Enforcement:** `conn.commit()` after loop completes

**Evidence:** `telemetry_service.py:1107`

**Rationale:** Ensures atomicity of batch operation (all-or-nothing for successful records).

---

## Errors and Edge Cases

### Error: Empty Batch (200 OK)

**Trigger:** Request body is `[]`

**Response:**
```json
{
  "inserted": 0,
  "duplicates": 0,
  "errors": [],
  "total": 0
}
```

**Status:** 200 OK

**Evidence:** Inferred from loop logic (no iterations = all counters stay at 0)

---

### Error: Invalid JSON Schema (422)

**Trigger:** Request body doesn't match `List[TelemetryRun]` schema

**Response:**
- **Status:** 422 Unprocessable Entity
- **Body:** Pydantic validation errors

**Evidence:** FastAPI automatic validation (telemetry_service.py:1025)

**Example:**
```json
{
  "detail": [
    {
      "loc": ["body", 0, "event_id"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

### Error: All Runs Duplicates (200 OK)

**Trigger:** All event_ids already exist in database

**Response:**
```json
{
  "inserted": 0,
  "duplicates": 5,
  "errors": [],
  "total": 5
}
```

**Status:** 200 OK

**Evidence:** `telemetry_service.py:1100-1101` (duplicate counting)

**Rationale:** Idempotent behavior - client can safely retry entire batch.

---

### Error: All Runs Failed (200 OK)

**Trigger:** All runs have validation errors (e.g., invalid status values)

**Response:**
```json
{
  "inserted": 0,
  "duplicates": 0,
  "errors": [
    "evt_001: CHECK constraint failed: status IN (...)",
    "evt_002: CHECK constraint failed: status IN (...)"
  ],
  "total": 2
}
```

**Status:** 200 OK (not 400!)

**Evidence:** `telemetry_service.py:1111-1116` (always returns BatchResponse)

**Rationale:** Partial success model - endpoint doesn't fail on data errors.

---

### Error: Rate Limit Exceeded (429)

**Trigger:** Client exceeds `TELEMETRY_RATE_LIMIT_RPM` (if enabled)

**Response:**
- **Status:** 429 Too Many Requests
- **Headers:** `Retry-After: 60`
- **Body:** `{"detail": "Rate limit exceeded. Max <rpm> requests per minute."}`

**Evidence:** `telemetry_service.py:325-335` (check_rate_limit dependency)

---

### Error: Authentication Failed (401)

**Trigger:** Invalid/missing Bearer token when `TELEMETRY_API_AUTH_ENABLED=true`

**Response:**
- **Status:** 401 Unauthorized
- **Headers:** `WWW-Authenticate: Bearer`
- **Body:** `{"detail": "Invalid or missing authentication token"}`

**Evidence:** `telemetry_service.py:195-243` (verify_auth dependency)

---

### Edge Case: Mixed Results

**Trigger:** Batch contains valid, duplicate, and invalid runs

**Response:**
```json
{
  "inserted": 2,
  "duplicates": 1,
  "errors": [
    "evt_004: CHECK constraint failed: status"
  ],
  "total": 4
}
```

**Status:** 200 OK

**Behavior:** Common scenario for buffer sync workers retrying queued events.

**Evidence:** `telemetry_service.py:1040-1106` (counters incremented per category)

---

## Side Effects

### Database Operations

**Table:** `agent_runs`
**Operation:** INSERT (multiple rows)

**Transaction Scope:** All successful inserts in single transaction

**Evidence:** `telemetry_service.py:1044` (with get_db()), `1107` (conn.commit())

**Performance:** O(n) where n = number of runs in batch

---

### Logging

**Success Log:**
```python
logger.info(f"[OK] Batch insert: {inserted} new, {duplicates} duplicates, {len(errors)} errors")
```

**Evidence:** `telemetry_service.py:1109`

**Format:** Summary statistics for entire batch

---

## Use Cases

### Use Case 1: Buffer Sync Worker

**Scenario:** Agent has queued 50 telemetry events in local buffer while API was unavailable. API comes back online.

**Flow:**
1. Buffer sync worker reads all queued events
2. POST to `/api/v1/runs/batch` with all 50 events
3. Receives response: `{"inserted": 50, "duplicates": 0, "errors": [], "total": 50}`
4. Worker marks all 50 events as synced, removes from buffer

**Client Code:**
```python
def flush_buffer(buffer_events: List[Dict]) -> bool:
    response = requests.post(
        f"{api_url}/api/v1/runs/batch",
        json=buffer_events
    )
    response.raise_for_status()
    result = response.json()
    logger.info(f"Synced {result['inserted']} events, {result['duplicates']} duplicates")
    return result['inserted'] + result['duplicates'] == len(buffer_events)
```

**Evidence:** Inferred from buffer failover architecture (README.md)

---

### Use Case 2: NDJSON File Import

**Scenario:** User has 1000 telemetry events in NDJSON backup file. Wants to import into database.

**Flow:**
1. Parse NDJSON file into array of run objects
2. Split into batches of 100 (avoid oversized requests)
3. POST each batch to `/api/v1/runs/batch`
4. Aggregate statistics from all batch responses

**Migration Script:**
```python
def import_ndjson(file_path: str, batch_size: int = 100):
    with open(file_path) as f:
        runs = [json.loads(line) for line in f]

    for i in range(0, len(runs), batch_size):
        batch = runs[i:i+batch_size]
        response = requests.post(f"{api_url}/api/v1/runs/batch", json=batch)
        result = response.json()
        print(f"Batch {i//batch_size + 1}: {result['inserted']} inserted, {result['duplicates']} duplicates")
```

---

### Use Case 3: Idempotent Retry

**Scenario:** Network error occurs during batch upload. Client doesn't know if data was saved.

**Flow:**
1. Client sends batch: 10 runs
2. Network error before response received
3. Client retries with same 10 runs (same event_ids)
4. Server responds: `{"inserted": 0, "duplicates": 10, "errors": [], "total": 10}`
5. Client knows all data was already saved (idempotent)

**Rationale:** event_id UNIQUE constraint ensures safe retries.

**Evidence:** `telemetry_service.py:1100-1101` (duplicate detection)

---

### Use Case 4: Mixed Data Quality

**Scenario:** Importing legacy data with some invalid records.

**Request:**
```json
[
  {"event_id": "valid_001", "status": "success", ...},
  {"event_id": "valid_002", "status": "failure", ...},
  {"event_id": "invalid_003", "status": "invalid_status", ...}
]
```

**Response:**
```json
{
  "inserted": 2,
  "duplicates": 0,
  "errors": [
    "invalid_003: CHECK constraint failed: status IN (...)"
  ],
  "total": 3
}
```

**Client Action:** Log error for invalid_003, continue processing. Valid records still saved.

---

## Performance

### Batch Size Considerations

**Recommended:** 50-500 runs per batch

**Rationale:**
- Too small: HTTP overhead dominates
- Too large: JSON parsing, memory, request timeout risks

**No Hard Limit:** Endpoint accepts any array size, but larger batches increase failure risk.

---

### Transaction Performance

**Operation:** Single transaction for entire batch

**Benefit:** Faster than individual POST requests (no per-run ACID overhead)

**Trade-off:** Long batches hold database lock longer

**Evidence:** `telemetry_service.py:1107` (single commit after loop)

---

### Expected Latency

| Batch Size | Expected Latency |
|------------|------------------|
| 10 runs    | < 50ms           |
| 100 runs   | < 500ms          |
| 1000 runs  | < 5s             |

**Evidence:** Inferred from single INSERT performance (DELETE journal mode with FULL sync)

---

## Dependencies

### FastAPI Dependencies

**verify_auth:**
- Function: Bearer token authentication
- File: `telemetry_service.py:195-243`
- Skipped if: `TELEMETRY_API_AUTH_ENABLED=false`

**check_rate_limit:**
- Function: IP-based rate limiting
- File: `telemetry_service.py:298-337`
- Skipped if: `TELEMETRY_RATE_LIMIT_ENABLED=false`

**Evidence:** `telemetry_service.py:1027-1028`

---

### Database Connection

**Context Manager:** `get_db()`
- Evidence: `telemetry_service.py:341-361`
- Acquires SQLite connection
- Auto-closes on exit

**Used in:** `telemetry_service.py:1044`

---

### Data Models

**TelemetryRun:**
- Module: `src/telemetry/models.py`
- Purpose: Pydantic model for run validation
- Evidence: `telemetry_service.py:1025` (List[TelemetryRun])

**BatchResponse:**
- Module: `telemetry_service.py:177-182`
- Purpose: Response model for batch statistics
- Evidence: `telemetry_service.py:1023` (response_model=BatchResponse)

---

### Status Normalization

**normalize_status() function:**
- File: `telemetry_service.py:46-69`
- Purpose: Convert aliases to canonical status values
- Evidence: `telemetry_service.py:1048`

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:1023-1116`
- **Batch loop:** `telemetry_service.py:1045-1106`
- **Status normalization:** `telemetry_service.py:1048`
- **INSERT statement:** `telemetry_service.py:1050-1095`
- **Duplicate detection:** `telemetry_service.py:1100-1101`
- **Error handling:** `telemetry_service.py:1104-1105`
- **Transaction commit:** `telemetry_service.py:1107`
- **Response assembly:** `telemetry_service.py:1111-1116`

### Dependencies
- **Authentication:** `telemetry_service.py:195-243`
- **Rate limiting:** `telemetry_service.py:298-337`
- **Database context:** `telemetry_service.py:341-361`
- **BatchResponse model:** `telemetry_service.py:177-182`

---

## Verification Status

**Status:** VERIFIED

**Verification Method:**
- Direct file read of handler implementation
- SQL INSERT statement confirmed
- Error handling paths verified
- Response model confirmed

**Confidence:** HIGH

**Inferred Behaviors:**
- Empty batch returns all-zero statistics (standard loop logic)
- Batch size limits (no hard limit in code, practical limits inferred)
- Latency estimates (based on SQLite FULL sync mode)

**Evidence Strength:**
- Handler logic: STRONG (direct code read)
- Batch processing: STRONG (explicit per-run loop)
- Idempotency: STRONG (UNIQUE constraint check)
- Performance: MEDIUM (inferred from configuration)
