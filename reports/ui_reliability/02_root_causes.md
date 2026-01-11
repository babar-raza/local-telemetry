# Root Causes Analysis - UI Reliability Issues

**Date:** 2026-01-11
**Analyst:** Autonomous Agent
**Evidence:** Direct file reads + line citations

---

## Executive Summary

The telemetry dashboard experiences filter failures due to **status enum mismatch** between the dashboard UI and the database/API. Additionally, the dashboard's filter implementation has architectural issues that cause poor performance and incorrect query semantics.

### Critical Issues Found

1. **Status Enum Mismatch** - Dashboard uses 'failed', DB stores 'failure'
2. **Multi-Status Filter Broken** - Only uses first selected status
3. **Client-Side Filtering** - job_type filtered client-side instead of server-side
4. **Inefficient Event ID Lookup** - Scans 1000 records instead of direct fetch
5. **Schema Drift** - Two conflicting schema definitions

---

## Issue 1: Status Enum Mismatch (CRITICAL)

### Canonical Status Values

**Source of Truth:** `schema/telemetry_v6.sql:90` and `specs/_index.md:194`

```sql
CHECK (status IN ('running', 'success', 'failure', 'partial', 'timeout', 'cancelled'))
```

### Files Using CORRECT Values ('failure')

1. **telemetry_service.py:215**
   ```python
   allowed = ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']
   ```

2. **telemetry_service.py:742**
   ```python
   allowed_statuses = ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']
   ```

3. **scripts/sync_to_sheets_weekly.py:46, 62**
   ```python
   WHERE status IN ('success', 'failure', 'partial')
   ```

### Files Using WRONG Values ('failed')

1. **src/telemetry/schema.py:48**
   ```python
   status TEXT CHECK(status IN ('running', 'success', 'failed', 'partial', 'timeout', 'cancelled'))
   ```
   **Impact:** Creates databases with wrong CHECK constraint if this schema is used

2. **scripts/dashboard.py:103**
   ```python
   def validate_status(status: str) -> bool:
       return status in ["running", "success", "failed", "partial", "timeout", "cancelled"]
   ```

3. **scripts/dashboard.py:176-179**
   ```python
   filter_status = st.multiselect(
       "Status",
       options=["running", "success", "failed", "partial", "timeout", "cancelled"],
   ```

4. **scripts/dashboard.py:410**
   ```python
   index=["running", "success", "failed", "partial", "timeout", "cancelled"].index(...)
   ```

### Evidence of Impact

When a user selects "failed" in the dashboard filter:
1. Dashboard sends `status=failed` to API (dashboard.py:265)
2. API validates against ['running', 'success', 'failure', ...] (telemetry_service.py:742)
3. Query returns 0 results because DB contains 'failure' not 'failed'

### Root Cause

The `src/telemetry/schema.py` was likely created before the canonical schema was standardized in `schema/telemetry_v6.sql`. The dashboard was built referencing the Python schema instead of the SQL schema.

---

## Issue 2: Multi-Status Filter Only Uses First Value

### Evidence

**scripts/dashboard.py:263-265**
```python
if filter_status:
    # API accepts single status, so we'll query multiple times
    # For simplicity, let's just use the first status for now
    query_params["status"] = filter_status[0] if filter_status else None
```

### Impact

User selects multiple statuses like ['success', 'failure', 'partial'] but only 'success' is queried. The other selections are silently ignored.

### Expected Behavior

Multi-status filter should use OR semantics:
- Either: Make multiple API calls and merge results
- Or: API should accept `status_in=success,failure,partial` parameter
- Or: API should accept repeated `status=success&status=failure` parameters

---

## Issue 3: Client-Side job_type Filtering

### Evidence

**scripts/dashboard.py:284-288**
```python
# Filter out test data if requested
if exclude_test:
    runs = [r for r in runs if r.get("job_type") != "test"]

# Filter by job_type if specified (exact match)
if filter_job_type:
    runs = [r for r in runs if r.get("job_type") == filter_job_type]
```

### Impact

1. Fetches more data than needed from API
2. Pagination is incorrect (if page size is 100, after filtering you might get 50)
3. Performance degrades with large datasets

### Evidence of Proper Server-Side Support

**telemetry_service.py:710, 784-786**
```python
async def query_runs(
    ...
    job_type: Optional[str] = None,
    ...
):
    ...
    if job_type:
        query += " AND job_type = ?"
        params.append(job_type)
```

The API already supports server-side job_type filtering, but the dashboard doesn't use it.

---

## Issue 4: Inefficient Event ID Lookup

### Evidence

**scripts/dashboard.py:370-376**
```python
if fetch_button and event_id_input:
    try:
        with st.spinner("Fetching run data..."):
            # Query by event_id - we need to get all runs and filter
            all_runs = client.get_runs(limit=1000)
            run_data = next((r for r in all_runs if r.get("event_id") == event_id_input), None)
```

### Impact

- Fetches 1000 records from API just to find 1 record
- Slow performance (O(n) scan vs O(1) index lookup)
- Breaks when database has > 1000 records

### Missing API Endpoint

**telemetry_service.py** - No `GET /api/v1/runs/{event_id}` endpoint exists

Existing endpoints:
- GET /api/v1/runs/{event_id}/commit-url (line 1076)
- GET /api/v1/runs/{event_id}/repo-url (line 1128)
- POST /api/v1/runs/{event_id}/associate-commit (line 1180)

But no direct GET /api/v1/runs/{event_id} for fetching the full run record.

---

## Issue 5: Schema Drift Between Python and SQL

### Evidence

**Two Schema Definitions:**

1. **schema/telemetry_v6.sql** (SQL, 149 lines)
   - Used by: telemetry_service.py:434
   - Status CHECK: `'running', 'success', 'failure', ...`
   - Primary key: `id INTEGER PRIMARY KEY AUTOINCREMENT`

2. **src/telemetry/schema.py** (Python, 365 lines)
   - Used by: Potentially by setup_database.py (needs verification)
   - Status CHECK: `'running', 'success', 'failed', ...` (WRONG)
   - Primary key: `run_id TEXT PRIMARY KEY` (different!)

### Impact

If both schemas are used in different contexts:
1. Database created with Python schema has wrong constraints
2. API validation (using 'failure') rejects data from Python-schema DB

### Service Actually Uses

**telemetry_service.py:434-444**
```python
# Read and execute schema file
schema_file = Path(__file__).parent / "schema" / "telemetry_v6.sql"

if not schema_file.exists():
    logger.error(f"Schema file not found: {schema_file}")
    raise FileNotFoundError(f"Schema file not found: {schema_file}")

with open(schema_file, 'r') as f:
    schema_sql = f.read()

# Execute schema
conn.executescript(schema_sql)
```

The service reads `schema/telemetry_v6.sql` (correct), so `src/telemetry/schema.py` might be dead code or used by legacy scripts.

---

## Issue 6: Config Variable Ambiguity

### Evidence

**src/telemetry/config.py:119**
```python
api_url = os.getenv("TELEMETRY_API_URL") or os.getenv("METRICS_API_URL", "http://localhost:8765")
```

### Issue

Two environment variables for the same purpose:
- TELEMETRY_API_URL (new, preferred)
- METRICS_API_URL (legacy)

Additionally:
- GOOGLE_SHEETS_API_URL (external API, different system)
- METRICS_API_ENABLED (deprecated, use GOOGLE_SHEETS_API_ENABLED)

### Impact

User confusion: which variable to set? Documentation drift.

---

## Summary of Changes Needed

### Immediate Fixes (Breaking Issues)

1. **Fix status enum mismatch**
   - Change dashboard.py:103, 176, 410 from 'failed' to 'failure'
   - Fix src/telemetry/schema.py:48 or deprecate the file

2. **Add GET /api/v1/runs/{event_id} endpoint**
   - Direct fetch by event_id
   - Returns 404 if not found

3. **Fix dashboard multi-status filter**
   - Either: Accept multiple statuses in API (status_in=val1,val2)
   - Or: Make multiple API calls and merge results
   - Remove client-side filtering workaround

### Performance Improvements

4. **Use server-side job_type filtering**
   - Pass job_type to API query params
   - Remove client-side filtering (dashboard.py:284-288)

5. **Use direct event_id endpoint**
   - Replace dashboard.py:374 with GET /api/v1/runs/{event_id}

### Schema Cleanup

6. **Resolve schema drift**
   - Make schema/telemetry_v6.sql the single source of truth
   - Deprecate or align src/telemetry/schema.py
   - Add migration check for existing DBs with wrong schema

---

## Evidence File Paths (Quick Reference)

- Canonical status spec: `specs/_index.md:194`
- SQL schema (correct): `schema/telemetry_v6.sql:90`
- Python schema (wrong): `src/telemetry/schema.py:48`
- Dashboard status validation (wrong): `scripts/dashboard.py:103`
- Dashboard status filter (wrong): `scripts/dashboard.py:176`
- Dashboard status dropdown (wrong): `scripts/dashboard.py:410`
- API status validation (correct): `telemetry_service.py:215, 742`
- Sheets sync (correct): `scripts/sync_to_sheets_weekly.py:46, 62`
- Multi-status bug: `scripts/dashboard.py:265`
- Client-side filtering bug: `scripts/dashboard.py:284-288`
- Event ID scan bug: `scripts/dashboard.py:374`
- Service schema loader: `telemetry_service.py:434`
