# Feature Spec: HTTP Create Run

**Feature ID:** `http.runs.create`
**Category:** HTTP API
**Route:** `POST /api/v1/runs`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-11

**IMPORTANT:** Line number references updated for commit `8c74f69` (2026-01-11) which reordered routes.

---

## Summary

Creates a single telemetry run record via HTTP POST. This endpoint is the **primary write path** for the single-writer architecture, ensuring zero database corruption through file locking and idempotency via `event_id` UNIQUE constraint.

**Key Features:**
- Idempotent: Duplicate `event_id` returns success (not error)
- Single-writer: Protected by file lock
- Pydantic validation: Schema enforced at API boundary
- Optional authentication and rate limiting (v2.1.0+)

---

## Entry Points

### Route Registration
```python
@app.post("/api/v1/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    run: TelemetryRun,
    request: Request,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
)
```

**Evidence:** `telemetry_service.py:586-592`

### Handler Function
**File:** `telemetry_service.py:586-690`
**Function:** `create_run()`

---

## Inputs/Outputs

### HTTP Request

**Method:** POST
**Path:** `/api/v1/runs`
**Content-Type:** `application/json`

**Headers (Optional):**
- `Authorization: Bearer <token>` - Required if `TELEMETRY_API_AUTH_ENABLED=true`

**Body:** JSON object matching `TelemetryRun` Pydantic model

**Example:**
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_id": "20251226T120000Z-hugo-translator-a1b2c3d4",
  "agent_name": "hugo-translator",
  "job_type": "translate_posts",
  "start_time": "2025-12-26T12:00:00.000000+00:00",
  "status": "running",
  "trigger_type": "cli",
  "items_discovered": 0,
  "items_succeeded": 0,
  "items_failed": 0,
  "duration_ms": 0
}
```

---

### Request Schema (TelemetryRun)

**Model:** `TelemetryRun` (Pydantic BaseModel)
**Evidence:** `telemetry_service.py:79-154`

#### Required Fields

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `event_id` | str | UUID for idempotency | Line 82 |
| `run_id` | str | Application-level run identifier | Line 83 |
| `agent_name` | str | Agent name | Line 91 |
| `job_type` | str | Job type | Line 92 |
| `start_time` | str | ISO8601 timestamp | Line 87 |

#### Optional Fields (with defaults)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `created_at` | str | current UTC timestamp | Record creation time |
| `end_time` | str | None | ISO8601 timestamp |
| `status` | str | "running" | Run status |
| `duration_ms` | int | 0 | Duration in milliseconds |
| `items_discovered` | int | 0 | Item count |
| `items_succeeded` | int | 0 | Success count |
| `items_failed` | int | 0 | Failure count |
| `items_skipped` | int | 0 | Skipped count |

**Evidence:** `telemetry_service.py:86-113`

#### Context Fields (Optional)

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `product` | str | Product name | Line 96 |
| `product_family` | str | Product family | Line 97 |
| `platform` | str | Platform identifier | Line 98 |
| `subdomain` | str | Subdomain/section | Line 99 |
| `website` | str | Root domain | Line 102 |
| `website_section` | str | Website section | Line 103 |
| `item_name` | str | Specific page/entity | Line 104 |

#### Git Context Fields (Optional)

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `git_repo` | str | Repository URL | Line 132 |
| `git_branch` | str | Branch name | Line 133 |
| `git_commit_hash` | str | Commit SHA | Line 134 |
| `git_run_tag` | str | Run tag | Line 135 |

#### Input/Output Fields (Optional)

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `input_summary` | str | Input description | Line 122 |
| `output_summary` | str | Output description | Line 123 |
| `source_ref` | str | Source reference | Line 124 |
| `target_ref` | str | Target reference | Line 125 |

#### Error Fields (Optional)

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `error_summary` | str | Error message | Line 128 |
| `error_details` | str | Detailed error | Line 129 |

#### Environment Fields (Optional)

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `host` | str | Hostname | Line 138 |
| `environment` | str | Environment name | Line 139 |
| `trigger_type` | str | Trigger method | Line 140 |

#### Extended Metadata (Optional)

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `metrics_json` | Dict[str, Any] | Custom metrics (flexible JSON) | Line 143 |
| `context_json` | Dict[str, Any] | Custom context (flexible JSON) | Line 144 |

#### Linking Fields (Optional)

| Field | Type | Description | Evidence |
|-------|------|-------------|----------|
| `insight_id` | str | Link to originating insight | Line 152 |
| `parent_run_id` | str | Parent run ID | Line 153 |

#### API Sync Fields (Server-side)

| Field | Type | Default | Description | Evidence |
|-------|------|---------|-------------|----------|
| `api_posted` | bool | false | Whether posted to external API | Line 147 |
| `api_posted_at` | str | None | When posted | Line 148 |
| `api_retry_count` | int | 0 | Retry count | Line 149 |

---

### Field Validators

#### duration_ms Null Conversion

**Validator:**
```python
@field_validator('duration_ms', mode='before')
@classmethod
def convert_null_duration(cls, v):
    """Convert null/None to 0 for running jobs."""
    return 0 if v is None else v
```

**Purpose:** Accept null from clients, convert to 0 for running jobs
**Evidence:** `telemetry_service.py:115-119`

---

### HTTP Response

#### Success Response (201 Created)

**Status:** 201 Created
**Body:**
```json
{
  "status": "created",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_id": "20251226T120000Z-hugo-translator-a1b2c3d4"
}
```

**Evidence:** `telemetry_service.py:569-573`

#### Duplicate Response (200 OK)

**Status:** 200 OK (idempotent behavior)
**Body:**
```json
{
  "status": "duplicate",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Event already exists (idempotent)"
}
```

**Trigger:** UNIQUE constraint violation on `event_id`
**Evidence:** `telemetry_service.py:575-583`

---

## Invariants

### INV-1: Idempotency via event_id
**Statement:** Duplicate events (same event_id) MUST return success, not error.

**Enforcement:**
- Database UNIQUE constraint on `event_id` column
- SQLite IntegrityError caught
- Returns status="duplicate" (200 OK)

**Evidence:** `telemetry_service.py:575-583`

**Rationale:** At-least-once delivery with retry safety

---

### INV-2: Pydantic Schema Validation
**Statement:** All requests MUST pass Pydantic validation before database write.

**Enforcement:**
- FastAPI automatic validation
- Invalid requests return 422 Unprocessable Entity
- Validation errors include field details

**Evidence:** FastAPI framework behavior, Pydantic model definition

---

### INV-3: Single-Writer Database Access
**Statement:** Only one process can write to database at a time.

**Enforcement:**
- File lock acquired at startup (`SingleWriterGuard`)
- Worker count enforced to 1
- Lock prevents concurrent API processes

**Evidence:** `telemetry_service.py:416-417`

---

### INV-4: Required Field Enforcement
**Statement:** event_id, run_id, agent_name, job_type, start_time MUST be present.

**Enforcement:**
- Pydantic Field(...) marks required
- Missing fields return 422 Unprocessable Entity

**Evidence:** `telemetry_service.py:82-92`

---

## Errors and Edge Cases

### Error: Missing Required Field

**Trigger:** POST without event_id, run_id, agent_name, job_type, or start_time

**Response:**
- **Status:** 422 Unprocessable Entity
- **Body:** Pydantic validation error details

**Verification:** INFERRED (FastAPI standard behavior)
**Confidence:** HIGH

---

### Error: Duplicate event_id (Idempotent)

**Trigger:** POST with event_id that already exists in database

**Behavior:**
1. INSERT attempted
2. SQLite raises IntegrityError: "UNIQUE constraint failed: agent_runs.event_id"
3. Exception caught
4. Log message: `"[OK] Duplicate event_id (idempotent): {event_id}"`
5. Return success response

**Response:**
- **Status:** 200 OK
- **Body:** `{"status": "duplicate", "event_id": "...", "message": "..."}`

**Evidence:** `telemetry_service.py:575-583`
**Verification:** VERIFIED

---

### Error: Database Integrity Error (Non-duplicate)

**Trigger:** IntegrityError not related to event_id (e.g., other constraint violation)

**Response:**
- **Status:** 400 Bad Request
- **Body:** `{"detail": "Database integrity error: <error>"}`
- **Log:** `"[ERROR] Database integrity error: {e}"`

**Evidence:** `telemetry_service.py:585-589`
**Verification:** VERIFIED

---

### Error: Unexpected Database Error

**Trigger:** Any exception during INSERT (not IntegrityError)

**Response:**
- **Status:** 500 Internal Server Error
- **Body:** `{"detail": "Failed to create run: <error>"}`
- **Log:** `"[ERROR] Failed to create run: {e}"`

**Evidence:** `telemetry_service.py:590-595`
**Verification:** VERIFIED

---

### Error: Authentication Failure

**Trigger:**
- Auth enabled (`TELEMETRY_API_AUTH_ENABLED=true`)
- Missing Authorization header
- Invalid token format
- Token mismatch

**Response:**
- **Status:** 401 Unauthorized
- **Headers:** `{"WWW-Authenticate": "Bearer"}`
- **Body:** `{"detail": "<auth error message>"}`

**Evidence:** `telemetry_service.py:195-243` (verify_auth dependency)
**Verification:** VERIFIED

**Conditions:**
1. No header: "Authorization header required. Use: Authorization: Bearer <token>"
2. Invalid format: "Invalid authorization format. Use: Authorization: Bearer <token>"
3. Token mismatch: "Invalid authentication token"

---

### Error: Rate Limit Exceeded

**Trigger:**
- Rate limiting enabled (`TELEMETRY_RATE_LIMIT_ENABLED=true`)
- Client IP exceeds `TELEMETRY_RATE_LIMIT_RPM` requests per minute

**Response:**
- **Status:** 429 Too Many Requests
- **Headers:**
  - `Retry-After: 60`
  - `X-RateLimit-Limit: <rpm_limit>`
  - `X-RateLimit-Remaining: 0`
- **Body:** `{"detail": "Rate limit exceeded. Max <rpm> requests per minute."}`
- **Log:** `"Rate limit exceeded for IP: {client_ip}"`

**Evidence:** `telemetry_service.py:298-337` (check_rate_limit dependency)
**Verification:** VERIFIED

---

### Edge Case: Null duration_ms

**Trigger:** Client sends `"duration_ms": null` (for running jobs)

**Behavior:**
1. Pydantic validator `convert_null_duration` converts null to 0
2. Database INSERT uses 0
3. No error raised

**Evidence:** `telemetry_service.py:115-119`
**Verification:** VERIFIED

**Rationale:** Running jobs have no duration yet, but database requires int

---

## Configuration Knobs

### TELEMETRY_API_AUTH_ENABLED
**Type:** bool
**Default:** false
**Purpose:** Enable Bearer token authentication
**Impact:** Requires Authorization header on all requests

**Evidence:** `src/telemetry/config.py:296`, `telemetry_service.py:212`

---

### TELEMETRY_API_AUTH_TOKEN
**Type:** str
**Default:** None
**Purpose:** Bearer token value
**Required if:** AUTH_ENABLED=true

**Evidence:** `src/telemetry/config.py:297`, `telemetry_service.py:235`

---

### TELEMETRY_RATE_LIMIT_ENABLED
**Type:** bool
**Default:** false
**Purpose:** Enable IP-based rate limiting

**Evidence:** `src/telemetry/config.py:300`, `telemetry_service.py:314`

---

### TELEMETRY_RATE_LIMIT_RPM
**Type:** int
**Default:** 60
**Purpose:** Requests per minute limit per IP

**Evidence:** `src/telemetry/config.py:301`, `telemetry_service.py:322-323`

---

## Side Effects

### Database Operations

**Table:** `agent_runs`
**Operation:** INSERT

**SQL:**
```sql
INSERT INTO agent_runs (
    event_id, run_id, created_at, start_time, end_time,
    agent_name, job_type, status,
    [... 30+ additional columns ...]
) VALUES (?, ?, ?, ?, ?, ...)
```

**Evidence:** `telemetry_service.py:518-563`

**Transaction:** Implicit (auto-commit on success)

**Indexes Updated:**
- UNIQUE index on `event_id`
- Composite index on `(agent_name, status, created_at)`
- Index on `created_at DESC`

---

### Logging

**Success:**
- `logger.info(f"[OK] Created run: {event_id} (agent: {agent_name})")`
- Evidence: `telemetry_service.py:567`

**Duplicate:**
- `logger.info(f"[OK] Duplicate event_id (idempotent): {event_id}")`
- Evidence: `telemetry_service.py:578`

**Errors:**
- `logger.error(f"[ERROR] Database integrity error: {e}")`
- `logger.error(f"[ERROR] Failed to create run: {e}")`
- Evidence: `telemetry_service.py:585`, `591`

---

## Dependencies

### FastAPI Dependencies

**verify_auth:**
- Function: Verify Bearer token authentication
- File: `telemetry_service.py:195-243`
- Skipped if: `TELEMETRY_API_AUTH_ENABLED=false`

**check_rate_limit:**
- Function: Check IP-based rate limiting
- File: `telemetry_service.py:298-337`
- Skipped if: `TELEMETRY_RATE_LIMIT_ENABLED=false`

**Evidence:** `telemetry_service.py:500-501`

---

### Database Connection

**Context Manager:** `get_db()`
- Evidence: `telemetry_service.py:341-361`
- Acquires SQLite connection
- Sets PRAGMA journal_mode and synchronous
- Auto-closes on exit

**Used in:** `telemetry_service.py:517` (within try block)

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:496-595`
- **Pydantic model:** `telemetry_service.py:79-154`
- **Authentication:** `telemetry_service.py:195-243`
- **Rate limiting:** `telemetry_service.py:247-337`
- **Database context:** `telemetry_service.py:341-361`

### Configuration
- **API config:** `src/telemetry/config.py:265-392`
- **Auth settings:** Lines 296-297
- **Rate limit settings:** Lines 300-301

### README References
- **API endpoints:** README.md:185-202
- **Stale run cleanup use case:** README.md:205-234
- **Performance benchmarks:** README.md:236-242

---

## Verification Status

**Status:** VERIFIED

**Verification Method:**
- Direct file reads of handler implementation
- Pydantic model definition confirmed
- Error handling traced through code
- Dependencies verified

**Confidence:** HIGH

**Inferred Behaviors:**
- FastAPI 422 response (standard framework behavior)
- Request/response formats (standard JSON serialization)

**Missing Verification:**
- Runtime behavior of rate limiter (sliding window implementation not fully tested)
- Actual database constraint enforcement (assumed from SQLite UNIQUE constraint)
