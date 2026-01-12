# Feature Spec: HTTP Get Metadata

**Feature ID:** `http.metadata.get`
**Category:** HTTP API
**Route:** `GET /api/v1/metadata`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-11

---

## Summary

Retrieve metadata about available filter options from the telemetry database. This endpoint returns **distinct lists** of agent names and job types, used by dashboards and UIs to populate filter dropdowns and provide autocomplete options.

**Key Features:**
- Returns distinct agent_names from all runs
- Returns distinct job_types from all runs
- Includes counts of unique values
- Ordered alphabetically
- Fast query (single table scan with DISTINCT)

**Common Use Cases:**
- Populate dashboard filter dropdowns
- Provide autocomplete suggestions
- Show available agents/job types to users

---

## Entry Points

### Route Registration
```python
@app.get("/api/v1/metadata")
async def get_metadata(
    _rate_limit: None = Depends(check_rate_limit)
):
```

**Evidence:** `telemetry_service.py:691-694`

### Handler Function
**File:** `telemetry_service.py:691-739`
**Function:** `get_metadata()`

---

## Inputs/Outputs

### HTTP Request

**Method:** GET
**Path:** `/api/v1/metadata`
**Query Parameters:** None

**Example:**
```
GET /api/v1/metadata
```

---

### HTTP Response

#### Success Response (200 OK)

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:**
```json
{
  "agent_names": [
    "hugo-translator",
    "seo_intelligence.insight_engine",
    "test-agent"
  ],
  "job_types": [
    "daily_report",
    "test",
    "translate_posts"
  ],
  "counts": {
    "agent_names": 3,
    "job_types": 3
  }
}
```

**Fields:**
- `agent_names` - Array of distinct agent names, sorted alphabetically
- `job_types` - Array of distinct job types, sorted alphabetically
- `counts` - Object with counts of unique values

**Evidence:** `telemetry_service.py:723-730`

---

## Invariants

### INV-1: Alphabetical Ordering
**Statement:** Results MUST be sorted alphabetically (ORDER BY).

**Enforcement:**
```sql
SELECT DISTINCT agent_name FROM agent_runs WHERE agent_name IS NOT NULL ORDER BY agent_name
SELECT DISTINCT job_type FROM agent_runs WHERE job_type IS NOT NULL ORDER BY job_type
```

**Evidence:** `telemetry_service.py:710`, `714`

---

### INV-2: NULL Exclusion
**Statement:** NULL values MUST be excluded from results.

**Enforcement:**
```sql
WHERE agent_name IS NOT NULL
WHERE job_type IS NOT NULL
```

**Evidence:** `telemetry_service.py:710`, `714`

**Rationale:** Empty filter options are not useful for UIs

---

### INV-3: No Duplicates
**Statement:** Results MUST contain only unique values (DISTINCT).

**Enforcement:** SQL DISTINCT keyword

**Evidence:** `telemetry_service.py:710`, `714`

---

## Errors and Edge Cases

### Error: Database Query Failure (500)

**Trigger:** SQLite error during query execution

**Response:**
- **Status:** 500 Internal Server Error
- **Body:** `{"detail": "Failed to fetch metadata: <error>"}`
- **Log:** `log_error("/api/v1/metadata", "DatabaseError", str(e))`
- **Log:** `logger.error(f"[ERROR] Failed to fetch metadata: {e}")`

**Evidence:** `telemetry_service.py:732-738`

---

### Error: Rate Limit Exceeded (429)

**Trigger:** Client exceeds `TELEMETRY_RATE_LIMIT_RPM` (if enabled)

**Response:**
- **Status:** 429 Too Many Requests
- **Headers:** `Retry-After: 60`
- **Body:** `{"detail": "Rate limit exceeded. Max <rpm> requests per minute."}`

**Evidence:** `telemetry_service.py:325-335` (check_rate_limit dependency)

---

### Edge Case: Empty Database

**Trigger:** No runs in database

**Response:**
- **Status:** 200 OK
- **Body:**
```json
{
  "agent_names": [],
  "job_types": [],
  "counts": {
    "agent_names": 0,
    "job_types": 0
  }
}
```

**Evidence:** Inferred from array construction logic

---

### Edge Case: All Values NULL

**Trigger:** All runs have `agent_name = NULL` and `job_type = NULL`

**Response:** Same as empty database (empty arrays)

**Evidence:** `WHERE agent_name IS NOT NULL` filter

---

## Side Effects

### Database Operations

**Table:** `agent_runs`
**Operation:** SELECT (read-only, two queries)

**Queries:**
```sql
SELECT DISTINCT agent_name FROM agent_runs WHERE agent_name IS NOT NULL ORDER BY agent_name
SELECT DISTINCT job_type FROM agent_runs WHERE job_type IS NOT NULL ORDER BY job_type
```

**Evidence:** `telemetry_service.py:710`, `714`

**Performance:** Full table scan with DISTINCT (acceptable for metadata queries)

---

### Logging

**Success Log:**
```python
log_query(
    query_params={},
    result_count=len(agent_names) + len(job_types),
    duration_ms=get_duration()
)
```

**Evidence:** `telemetry_service.py:717-721`

**Error Log:**
```python
log_error("/api/v1/metadata", "DatabaseError", str(e))
logger.error(f"[ERROR] Failed to fetch metadata: {e}")
```

**Evidence:** `telemetry_service.py:733-734`

---

## Use Cases

### Use Case 1: Dashboard Filter Dropdowns

**Scenario:** Dashboard needs to populate agent and job type filter dropdowns.

**Flow:**
1. On dashboard load, fetch: `GET /api/v1/metadata`
2. Parse response and populate dropdowns:
   - Agent Name dropdown with `agent_names` array
   - Job Type dropdown with `job_types` array

**Dashboard Code:**
```python
def get_metadata(self) -> Dict[str, Any]:
    """Get metadata including distinct agent names and job types."""
    response = requests.get(f"{self.base_url}/api/v1/metadata")
    response.raise_for_status()
    return response.json()

# Usage
metadata = client.get_metadata()
agent_names = metadata['agent_names']  # For dropdown options
```

**Evidence:** `scripts/dashboard.py:77-81`

---

### Use Case 2: Autocomplete Suggestions

**Scenario:** User types in search field, client provides autocomplete suggestions.

**Flow:**
1. Client pre-fetches metadata on load
2. Filter locally based on user input
3. Show matching agents/job types

---

### Use Case 3: API Discovery

**Scenario:** New API user wants to know what agents/jobs exist.

**Request:**
```
GET /api/v1/metadata
```

**Response shows available options** for filtering in subsequent queries.

---

## Performance

### Query Performance

**Operation:** Two DISTINCT queries with ORDER BY
**Complexity:** O(n log n) where n = number of runs
**Expected Latency:** < 50ms for databases with < 10K runs

**Evidence:** Inferred from query structure

**Optimization Opportunities:**
- Add indexes on (agent_name, job_type) if this becomes slow
- Consider caching results (metadata changes infrequently)

---

### Duration Tracking

**Instrumentation:**
```python
with track_duration() as get_duration:
    # ... query execution ...
    log_query(..., duration_ms=get_duration())
```

**Evidence:** `telemetry_service.py:704`, `720`

---

## Dependencies

### FastAPI Dependencies

**check_rate_limit:**
- Function: IP-based rate limiting
- File: `telemetry_service.py:298-337`
- Skipped if: `TELEMETRY_RATE_LIMIT_ENABLED=false`

**Evidence:** `telemetry_service.py:693`

---

### Database Connection

**Context Manager:** `get_db()`
- Evidence: `telemetry_service.py:341-361`
- Acquires SQLite connection
- Auto-closes on exit

**Used in:** `telemetry_service.py:706`

---

### Utility Functions

**track_duration:**
- Module: `src/telemetry/logger.py`
- Purpose: Context manager for timing operations

**log_query:**
- Module: `src/telemetry/logger.py`
- Purpose: Structured logging for query operations

**log_error:**
- Module: `src/telemetry/logger.py`
- Purpose: Structured error logging

**Evidence:** `telemetry_service.py:58` (imports)

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:691-739`
- **Agent names query:** `telemetry_service.py:710-711`
- **Job types query:** `telemetry_service.py:714-715`
- **Response assembly:** `telemetry_service.py:723-730`
- **Error handling:** `telemetry_service.py:732-738`

### Dependencies
- **Rate limiting:** `telemetry_service.py:298-337`
- **Database context:** `telemetry_service.py:341-361`
- **Logger utilities:** `src/telemetry/logger.py`

### Dashboard Integration
- **Client method:** `scripts/dashboard.py:77-81` (get_metadata)

---

## Verification Status

**Status:** VERIFIED

**Verification Method:**
- Direct file read of handler implementation
- SQL queries confirmed
- Dashboard integration verified

**Confidence:** HIGH

**Inferred Behaviors:**
- Empty array response for empty database (standard SQL/Python behavior)
- Alphabetical ordering (explicit ORDER BY clause)

**Evidence Strength:**
- Handler logic: STRONG (direct code read)
- Database queries: STRONG (explicit SQL)
- Dashboard usage: STRONG (referenced in dashboard.py)
- Performance: MEDIUM (inferred from query structure)
