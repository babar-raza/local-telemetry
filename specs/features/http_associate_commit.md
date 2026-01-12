# Feature Spec: HTTP Associate Git Commit

**Feature ID:** `http.associate.commit`
**Category:** HTTP API
**Route:** `POST /api/v1/runs/{event_id}/associate-commit`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-12

---

## Summary

Link a git commit to an existing telemetry run by updating the run's git metadata fields. This endpoint enables post-hoc association of commits with runs, supporting workflows where the commit hash becomes available after the run completes.

**Key Features:**
- Updates git_commit_hash, git_commit_source, git_commit_author, git_commit_timestamp
- Validates commit_source against allowed values (manual, llm, ci)
- Validates commit_hash format (7-40 hex characters)
- Returns 404 if run doesn't exist
- Updates updated_at timestamp automatically

**Common Use Cases:**
- Associate commit after agent run completes
- Link manual commits to telemetry runs
- Track LLM-generated commits with agent runs
- CI/CD pipeline commit association

---

## Entry Points

### Route Registration
```python
@app.post("/api/v1/runs/{event_id}/associate-commit")
async def associate_commit(
    event_id: str,
    association: CommitAssociation,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
```

**Evidence:** `telemetry_service.py:1319-1325`

### Handler Function
**File:** `telemetry_service.py:1319-1409`
**Function:** `associate_commit()`

---

## Inputs/Outputs

### HTTP Request

**Method:** POST
**Path:** `/api/v1/runs/{event_id}/associate-commit`
**Content-Type:** `application/json`

**Path Parameters:**
- `event_id` (string, required) - Unique event ID of the run to update

**Body:**
```json
{
  "commit_hash": "a1b2c3d4e5f6789",
  "commit_source": "llm",
  "commit_author": "Claude Sonnet <claude@anthropic.com>",
  "commit_timestamp": "2026-01-12T10:30:00Z"
}
```

**Required Fields:**
- `commit_hash` (string) - Git commit SHA (7-40 hex characters)
- `commit_source` (string) - How commit was created: "manual", "llm", or "ci"

**Optional Fields:**
- `commit_author` (string) - Author of the commit (e.g., "Name <email>")
- `commit_timestamp` (string) - ISO8601 timestamp of when commit was made

**Evidence:** `telemetry_service.py:236-241` (CommitAssociation model)

---

### Field Validation

#### commit_hash Validation

**Constraints:**
- Min length: 7 characters (short SHA)
- Max length: 40 characters (full SHA)
- Format: Hex characters (validated by Pydantic Field)

**Example Valid Values:**
- `"a1b2c3d"` (short SHA, 7 chars)
- `"a1b2c3d4e5f6789"` (medium SHA, 15 chars)
- `"a1b2c3d4e5f67890123456789abcdef01234567"` (full SHA, 40 chars)

**Evidence:** `telemetry_service.py:238`

---

#### commit_source Validation

**Allowed Values:**
- `"manual"` - Human-created commit
- `"llm"` - LLM-generated commit (e.g., Claude Code)
- `"ci"` - CI/CD pipeline commit

**Validator:**
```python
@field_validator('commit_source')
@classmethod
def validate_source(cls, v):
    if v not in ['manual', 'llm', 'ci']:
        raise ValueError("commit_source must be 'manual', 'llm', or 'ci'")
    return v
```

**Evidence:** `telemetry_service.py:243-249`

**Error Response (422) if invalid:**
```json
{
  "detail": [
    {
      "loc": ["body", "commit_source"],
      "msg": "commit_source must be 'manual', 'llm', or 'ci'",
      "type": "value_error"
    }
  ]
}
```

---

#### commit_author Validation

**Format:** Optional string
**Common Format:** "Name <email>" (not enforced)
**Examples:**
- `"Claude Sonnet <claude@anthropic.com>"`
- `"John Doe <john@example.com>"`
- `"CI Bot"` (also valid, no strict format)

**Evidence:** `telemetry_service.py:240`

---

#### commit_timestamp Validation

**Format:** ISO8601 timestamp string (optional)
**Examples:**
- `"2026-01-12T10:30:00Z"` (UTC)
- `"2026-01-12T10:30:00-08:00"` (with timezone)

**Evidence:** `telemetry_service.py:241`

---

### HTTP Response

#### Success Response (200 OK)

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:**
```json
{
  "status": "success",
  "event_id": "evt_123",
  "run_id": "run_abc",
  "commit_hash": "a1b2c3d4e5f6789"
}
```

**Fields:**
- `status` (string) - Always "success" for 200 responses
- `event_id` (string) - Event ID from path parameter
- `run_id` (string) - Run ID from database record
- `commit_hash` (string) - Commit hash that was associated

**Evidence:** `telemetry_service.py:1389-1394`

---

## Processing Logic

### Step 1: Verify Run Exists

**SQL Query:**
```sql
SELECT run_id FROM agent_runs WHERE event_id = ?
```

**Evidence:** `telemetry_service.py:1344-1348`

**If Not Found:**
- Logs error: `log_error(f"/api/v1/runs/{event_id}/associate-commit", "NotFound", ...)`
- Returns 404 HTTPException

**Evidence:** `telemetry_service.py:1350-1359`

---

### Step 2: Update Git Metadata Fields

**SQL UPDATE:**
```sql
UPDATE agent_runs SET
    git_commit_hash = ?,
    git_commit_source = ?,
    git_commit_author = ?,
    git_commit_timestamp = ?,
    updated_at = ?
WHERE event_id = ?
```

**Parameters:**
- `git_commit_hash` ← `association.commit_hash`
- `git_commit_source` ← `association.commit_source`
- `git_commit_author` ← `association.commit_author` (may be None)
- `git_commit_timestamp` ← `association.commit_timestamp` (may be None)
- `updated_at` ← `datetime.now(timezone.utc).isoformat()` (auto-set)
- `event_id` ← path parameter

**Evidence:** `telemetry_service.py:1364-1382`

**Behavior:** Overwrites any existing git metadata for this run.

---

### Step 3: Commit Transaction

**Operation:**
```python
conn.commit()
```

**Evidence:** `telemetry_service.py:1383`

**Guarantees:** ACID transaction ensures atomic update.

---

### Step 4: Log Success and Return

**Log Entry:**
```python
logger.info(f"[OK] Associated commit {association.commit_hash} with run {event_id}")
```

**Evidence:** `telemetry_service.py:1385-1387`

**Response:**
```python
return {
    "status": "success",
    "event_id": event_id,
    "run_id": run_id,
    "commit_hash": association.commit_hash
}
```

**Evidence:** `telemetry_service.py:1389-1394`

---

## Invariants

### INV-1: Run Must Exist

**Statement:** Endpoint MUST return 404 if event_id doesn't exist in database.

**Enforcement:** SELECT query before UPDATE

**Evidence:** `telemetry_service.py:1344-1359`

**Rationale:** Can't associate commit with non-existent run.

---

### INV-2: commit_source Must Be Valid

**Statement:** commit_source MUST be one of: "manual", "llm", "ci".

**Enforcement:** Pydantic field validator

**Evidence:** `telemetry_service.py:243-249`

**Rationale:** Enables filtering and analytics by commit source.

---

### INV-3: commit_hash Format

**Statement:** commit_hash MUST be 7-40 characters (git SHA format).

**Enforcement:** Pydantic Field constraints

**Evidence:** `telemetry_service.py:238`

**Rationale:** Validates git SHA format (short or full).

---

### INV-4: updated_at Auto-Set

**Statement:** updated_at timestamp MUST be set to current UTC time on every update.

**Enforcement:** Explicit parameter in UPDATE query

**Evidence:** `telemetry_service.py:1371`, `1379`

**Rationale:** Track when git metadata was last modified.

---

## Errors and Edge Cases

### Error: Run Not Found (404)

**Trigger:** event_id doesn't exist in database

**Response:**
- **Status:** 404 Not Found
- **Body:** `{"detail": "Run not found: <event_id>"}`
- **Log:** `log_error(..., "NotFound", ...)`

**Evidence:** `telemetry_service.py:1350-1359`

**Example:**
```
POST /api/v1/runs/nonexistent-id/associate-commit
→ 404 {"detail": "Run not found: nonexistent-id"}
```

---

### Error: Invalid commit_source (422)

**Trigger:** commit_source not in ["manual", "llm", "ci"]

**Response:**
- **Status:** 422 Unprocessable Entity
- **Body:** Pydantic validation error

**Example Request:**
```json
{
  "commit_hash": "a1b2c3d",
  "commit_source": "invalid"
}
```

**Response:**
```json
{
  "detail": [
    {
      "loc": ["body", "commit_source"],
      "msg": "commit_source must be 'manual', 'llm', or 'ci'",
      "type": "value_error"
    }
  ]
}
```

**Evidence:** `telemetry_service.py:243-249`

---

### Error: Invalid commit_hash Length (422)

**Trigger:** commit_hash shorter than 7 or longer than 40 characters

**Response:**
- **Status:** 422 Unprocessable Entity
- **Body:** Pydantic validation error

**Example Request:**
```json
{
  "commit_hash": "abc",
  "commit_source": "manual"
}
```

**Response:**
```json
{
  "detail": [
    {
      "loc": ["body", "commit_hash"],
      "msg": "ensure this value has at least 7 characters",
      "type": "value_error.any_str.min_length"
    }
  ]
}
```

**Evidence:** `telemetry_service.py:238` (min_length=7)

---

### Error: Missing Required Fields (422)

**Trigger:** commit_hash or commit_source not provided

**Response:**
- **Status:** 422 Unprocessable Entity
- **Body:** Pydantic validation error

**Example Request:**
```json
{
  "commit_author": "John Doe"
}
```

**Response:**
```json
{
  "detail": [
    {
      "loc": ["body", "commit_hash"],
      "msg": "field required",
      "type": "value_error.missing"
    },
    {
      "loc": ["body", "commit_source"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

**Evidence:** `telemetry_service.py:238-239` (Field(...) = required)

---

### Error: Database Failure (500)

**Trigger:** SQLite error during UPDATE operation

**Response:**
- **Status:** 500 Internal Server Error
- **Body:** `{"detail": "Database error: <error>"}`
- **Log:** `log_error(..., type(e).__name__, str(e), ...)`
- **Log:** `logger.error(f"[ERROR] Failed to associate commit: {e}")`

**Evidence:** `telemetry_service.py:1396-1409`

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

### Edge Case: Overwrite Existing Commit Data

**Trigger:** Run already has git metadata, POST with new commit data

**Behavior:** Existing values are overwritten with new values

**Example:**
```
# Initial state: git_commit_hash = "old_hash_123"
POST /api/v1/runs/evt_123/associate-commit
Body: {"commit_hash": "new_hash_456", "commit_source": "manual"}

# Result: git_commit_hash = "new_hash_456" (overwrites old value)
```

**Rationale:** Allows correcting mistakes or updating commit associations.

**Evidence:** `telemetry_service.py:1364-1382` (UPDATE without conditional logic)

---

### Edge Case: Optional Fields Omitted

**Trigger:** Only required fields provided (commit_hash, commit_source)

**Behavior:** Optional fields (commit_author, commit_timestamp) set to NULL

**Example Request:**
```json
{
  "commit_hash": "a1b2c3d",
  "commit_source": "manual"
}
```

**SQL Result:**
- `git_commit_hash` = "a1b2c3d"
- `git_commit_source` = "manual"
- `git_commit_author` = NULL
- `git_commit_timestamp` = NULL

**Evidence:** `telemetry_service.py:1375-1378` (passes association fields directly, which may be None)

---

## Side Effects

### Database Operations

**Table:** `agent_runs`
**Operations:**
1. SELECT (read run_id for response)
2. UPDATE (set git metadata fields)

**Transaction Scope:** Single transaction with commit

**Evidence:** `telemetry_service.py:1342-1383`

**Modified Fields:**
- `git_commit_hash`
- `git_commit_source`
- `git_commit_author`
- `git_commit_timestamp`
- `updated_at` (auto-set to current UTC time)

---

### Logging

**Success Log:**
```python
logger.info(f"[OK] Associated commit {association.commit_hash} with run {event_id}")
```

**Evidence:** `telemetry_service.py:1385-1387`

**Error Logs:**

1. **Run Not Found:**
```python
log_error(
    f"/api/v1/runs/{event_id}/associate-commit",
    "NotFound",
    f"Run not found: {event_id}",
    event_id=event_id
)
```
**Evidence:** `telemetry_service.py:1350-1355`

2. **Database Error:**
```python
log_error(
    f"/api/v1/runs/{event_id}/associate-commit",
    type(e).__name__,
    str(e),
    event_id=event_id
)
logger.error(f"[ERROR] Failed to associate commit: {e}")
```
**Evidence:** `telemetry_service.py:1399-1405`

---

## Use Cases

### Use Case 1: LLM-Generated Commit Tracking

**Scenario:** Claude Code generates a commit after completing an agent task. The telemetry run is created first, then the commit is made and associated.

**Flow:**
1. Agent starts: `POST /api/v1/runs` → event_id: "evt_001"
2. Agent completes work
3. LLM generates commit: `git commit -m "fix: resolve bug"`
4. Get commit SHA: `a1b2c3d4e5f6789`
5. Associate commit:
   ```
   POST /api/v1/runs/evt_001/associate-commit
   Body: {
     "commit_hash": "a1b2c3d4e5f6789",
     "commit_source": "llm",
     "commit_author": "Claude Sonnet <claude@anthropic.com>",
     "commit_timestamp": "2026-01-12T10:30:00Z"
   }
   ```
6. Response: `{"status": "success", "event_id": "evt_001", "run_id": "run_abc", "commit_hash": "a1b2c3d4e5f6789"}`

**Client Code:**
```python
# After commit is created
commit_sha = subprocess.check_output(['git', 'rev-parse', 'HEAD']).decode().strip()
response = requests.post(
    f"{api_url}/api/v1/runs/{event_id}/associate-commit",
    json={
        "commit_hash": commit_sha,
        "commit_source": "llm",
        "commit_author": "Claude Sonnet <claude@anthropic.com>",
        "commit_timestamp": datetime.now(timezone.utc).isoformat()
    }
)
```

---

### Use Case 2: Manual Commit Association

**Scenario:** Developer runs an agent manually, creates a commit, then links them.

**Flow:**
1. Run agent: `python agent.py` (creates telemetry run)
2. Review changes and commit: `git commit -m "feature: add new module"`
3. Get event_id from telemetry logs or dashboard
4. Associate manually:
   ```
   POST /api/v1/runs/evt_789/associate-commit
   Body: {
     "commit_hash": "b2c3d4e5f67890a",
     "commit_source": "manual",
     "commit_author": "Dev Name <dev@example.com>"
   }
   ```

---

### Use Case 3: CI/CD Pipeline Integration

**Scenario:** CI pipeline runs tests, creates telemetry run, then commits results and associates.

**Flow:**
1. CI starts: `POST /api/v1/runs` → event_id from env var
2. Run tests and generate report
3. Commit report: `git commit -m "ci: add test report [ci skip]"`
4. CI script associates commit:
   ```bash
   COMMIT_SHA=$(git rev-parse HEAD)
   curl -X POST "$API_URL/api/v1/runs/$EVENT_ID/associate-commit" \
     -H "Content-Type: application/json" \
     -d "{
       \"commit_hash\": \"$COMMIT_SHA\",
       \"commit_source\": \"ci\",
       \"commit_author\": \"CI Bot\",
       \"commit_timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"
     }"
   ```

---

### Use Case 4: Correcting Wrong Association

**Scenario:** User accidentally associated wrong commit, needs to fix it.

**Flow:**
1. Check current association: `GET /api/v1/runs/evt_456`
2. See wrong commit: `"git_commit_hash": "wrong_hash"`
3. Correct it:
   ```
   POST /api/v1/runs/evt_456/associate-commit
   Body: {
     "commit_hash": "correct_hash",
     "commit_source": "manual"
   }
   ```
4. Verify: `GET /api/v1/runs/evt_456` → `"git_commit_hash": "correct_hash"`

**Behavior:** Update overwrites previous association (no history kept).

---

## Performance

### Expected Latency

| Operation | Expected Time |
|-----------|---------------|
| SELECT (verify run) | < 5ms |
| UPDATE (git fields) | < 10ms |
| Total latency | < 20ms |

**Evidence:** Inferred from SQLite FULL sync mode with indexed lookup

---

### Indexes Used

**event_id Lookup:** UNIQUE constraint provides index for fast SELECT

**Evidence:** Schema v6 (event_id UNIQUE)

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

**Evidence:** `telemetry_service.py:1323-1324`

---

### Database Connection

**Context Manager:** `get_db()`
- Evidence: `telemetry_service.py:341-361`
- Acquires SQLite connection
- Auto-closes on exit

**Used in:** `telemetry_service.py:1342`

---

### Data Models

**CommitAssociation:**
- Module: `telemetry_service.py:236-249`
- Purpose: Pydantic model for request validation
- Evidence: `telemetry_service.py:1322` (association: CommitAssociation)

---

### Utility Functions

**log_error:**
- Module: `src/telemetry/logger.py`
- Purpose: Structured error logging
- Evidence: `telemetry_service.py:1350-1355`, `1399-1404`

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:1319-1409`
- **CommitAssociation model:** `telemetry_service.py:236-249`
- **Run existence check:** `telemetry_service.py:1344-1359`
- **UPDATE statement:** `telemetry_service.py:1364-1382`
- **Success response:** `telemetry_service.py:1389-1394`
- **Error handling:** `telemetry_service.py:1396-1409`

### Dependencies
- **Authentication:** `telemetry_service.py:195-243`
- **Rate limiting:** `telemetry_service.py:298-337`
- **Database context:** `telemetry_service.py:341-361`
- **Logger utilities:** `src/telemetry/logger.py`

---

## Verification Status

**Status:** VERIFIED

**Verification Method:**
- Direct file read of handler implementation
- CommitAssociation model confirmed
- SQL UPDATE statement verified
- Field validators confirmed

**Confidence:** HIGH

**Inferred Behaviors:**
- Overwrite behavior (no conditional UPDATE logic found)
- NULL handling for optional fields (standard Pydantic behavior)
- Latency estimates (based on SQLite configuration)

**Evidence Strength:**
- Handler logic: STRONG (direct code read)
- Validation: STRONG (explicit Pydantic validators)
- Database operations: STRONG (explicit SQL)
- Performance: MEDIUM (inferred from configuration)
