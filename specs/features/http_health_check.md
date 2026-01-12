# Feature Spec: HTTP Health Check

**Feature ID:** `http.health.check`
**Category:** System Monitoring
**Route:** `GET /health`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-12

---

## Summary

Standard health check endpoint for monitoring service availability and configuration. Returns service status, version, and critical database settings without authentication or rate limiting.

**Key Features:**
- Always returns 200 OK (no database checks)
- Shows service version (2.1.0)
- Exposes database configuration (path, journal mode, synchronous mode)
- No authentication required (public endpoint)
- No rate limiting applied
- Fast response (no I/O operations)

**Common Use Cases:**
- Docker health checks (`HEALTHCHECK` directive)
- Kubernetes liveness/readiness probes
- Load balancer health monitoring
- Service discovery verification
- Manual availability testing

---

## Entry Points

### Route Registration
```python
@app.get("/health")
async def health_check():
```

**Evidence:** `telemetry_service.py:529-530`

### Handler Function
**File:** `telemetry_service.py:529-543`
**Function:** `health_check()`

---

## Inputs/Outputs

### HTTP Request

**Method:** GET
**Path:** `/health`
**Query Parameters:** None
**Headers:** None (authentication not required)

**Example:**
```bash
curl http://localhost:8765/health
```

---

### HTTP Response

#### Success Response (200 OK)

**Status:** 200 OK (always)
**Content-Type:** `application/json`

**Body:**
```json
{
  "status": "ok",
  "version": "2.1.0",
  "db_path": "/data/telemetry/agent_runs.db",
  "journal_mode": "DELETE",
  "synchronous": "FULL"
}
```

**Fields:**
- `status` (string) - Always "ok" (service is running)
- `version` (string) - API version (hardcoded "2.1.0")
- `db_path` (string) - Absolute path to SQLite database file
- `journal_mode` (string) - SQLite journal mode (should be "DELETE")
- `synchronous` (string) - SQLite synchronous setting (should be "FULL")

**Evidence:** `telemetry_service.py:537-543`

**Note:** This endpoint does NOT perform database health checks. It only returns configuration values.

---

## Processing Logic

### Step 1: Return Configuration

**Implementation:**
```python
return {
    "status": "ok",
    "version": "2.1.0",
    "db_path": str(TelemetryAPIConfig.DB_PATH),
    "journal_mode": TelemetryAPIConfig.DB_JOURNAL_MODE,
    "synchronous": TelemetryAPIConfig.DB_SYNCHRONOUS
}
```

**Evidence:** `telemetry_service.py:537-543`

**Behavior:**
- No database connection opened
- No SQL queries executed
- No validation performed
- Returns immediately with configuration values

---

## Invariants

### INV-1: Always Returns 200 OK

**Statement:** Endpoint MUST always return 200 OK if service is running.

**Enforcement:** No error conditions in handler (no try-except, no database checks)

**Evidence:** `telemetry_service.py:537-543` (simple return statement)

**Rationale:** Health check indicates process is alive, not data integrity.

---

### INV-2: No Authentication Required

**Statement:** Endpoint MUST NOT require Bearer token authentication.

**Enforcement:** No `Depends(verify_auth)` dependency

**Evidence:** `telemetry_service.py:530` (no dependencies)

**Rationale:** Health checks must be accessible to monitoring systems without credentials.

---

### INV-3: No Rate Limiting

**Statement:** Endpoint MUST NOT apply rate limiting.

**Enforcement:** No `Depends(check_rate_limit)` dependency

**Evidence:** `telemetry_service.py:530` (no dependencies)

**Rationale:** Health checks may be polled frequently by orchestrators.

---

### INV-4: Configuration Exposure

**Statement:** Endpoint MUST expose critical database configuration.

**Enforcement:** Returns `db_path`, `journal_mode`, `synchronous`

**Evidence:** `telemetry_service.py:540-542`

**Rationale:** Enables validation of deployment configuration without direct database access.

---

## Configuration Values

### db_path

**Source:** `TelemetryAPIConfig.DB_PATH`

**Typical Values:**
- Docker: `/data/telemetry/agent_runs.db`
- Local Dev: `/path/to/project/data/agent_runs.db`

**Evidence:** `telemetry_service.py:540`

**Purpose:** Verify database location (useful for debugging mount issues in Docker).

---

### journal_mode

**Source:** `TelemetryAPIConfig.DB_JOURNAL_MODE`

**Expected Value:** `"DELETE"`

**Evidence:** `telemetry_service.py:541`

**Critical:** MUST be "DELETE" for Windows/Docker compatibility.

**Validation:** See `src/telemetry/config.py:320-324` (warns if not DELETE)

**Rationale:** WAL mode causes corruption in Docker on Windows.

---

### synchronous

**Source:** `TelemetryAPIConfig.DB_SYNCHRONOUS`

**Expected Value:** `"FULL"`

**Evidence:** `telemetry_service.py:542`

**Critical:** MUST be "FULL" for data durability guarantees.

**Validation:** See `src/telemetry/config.py:327-331` (raises error if not FULL)

**Rationale:** Ensures writes are committed to disk before ACK.

---

## Design Rationale

### Why No Database Checks?

**Decision:** Health check does NOT query database or validate connection.

**Rationale:**
1. **Fast Response:** Monitoring systems may poll every 5-10 seconds
2. **File Lock Contention:** Database checks would acquire lock unnecessarily
3. **Process Liveness:** Health check indicates service process is running
4. **Dedicated Endpoint:** Use `/metrics` for database-dependent health data

**Evidence:** No `get_db()` call or SQL queries in handler

**Alternative:** For deep health checks, use `/metrics` endpoint which queries database.

---

### Why Expose Database Configuration?

**Decision:** Return `db_path`, `journal_mode`, `synchronous` publicly.

**Rationale:**
1. **Deployment Verification:** Confirm correct environment variables loaded
2. **Debug Assistance:** Quickly identify misconfiguration without SSH access
3. **Security:** These are not secrets (file paths and SQLite settings)

**Evidence:** `telemetry_service.py:540-542`

---

## Errors and Edge Cases

### No Error Cases

**Behavior:** This endpoint cannot fail (by design).

**Rationale:** Health checks must be extremely reliable.

**Evidence:** No try-except blocks, no database calls

---

### Edge Case: Service Starting Up

**Scenario:** Service process started but not fully initialized.

**Behavior:** Returns 200 OK immediately (no initialization checks)

**Implication:** Health check passes before database is accessible.

**Mitigation:** Use `/metrics` for readiness probes (database-dependent).

---

### Edge Case: Database Locked or Corrupt

**Scenario:** Database is locked or corrupted.

**Behavior:** Still returns 200 OK (no database check performed)

**Implication:** Service appears healthy but cannot serve data.

**Mitigation:** Monitor `/metrics` endpoint separately for data availability.

---

### Edge Case: Misconfigured Database Settings

**Scenario:** `journal_mode` is "WAL" instead of "DELETE".

**Behavior:** Returns 200 OK with actual configuration:
```json
{
  "status": "ok",
  "journal_mode": "WAL",
  ...
}
```

**Detection:** Monitoring can alert if `journal_mode != "DELETE"` or `synchronous != "FULL"`.

**Evidence:** Returns actual config values from `TelemetryAPIConfig`

---

## Use Cases

### Use Case 1: Docker Health Check

**Scenario:** Docker Compose monitors service availability.

**docker-compose.yml:**
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8765/health"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 10s
```

**Behavior:**
- Every 10s: `docker exec` runs `curl http://localhost:8765/health`
- Success: HTTP 200 OK
- Failure: HTTP error or timeout
- After 3 failures: Container marked unhealthy

**Evidence:** Common pattern for Docker health checks

---

### Use Case 2: Kubernetes Liveness Probe

**Scenario:** Kubernetes restarts pod if service becomes unresponsive.

**k8s manifest:**
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8765
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 3
```

**Behavior:**
- Kubernetes polls `/health` every 10s
- 3 consecutive failures → Pod restarted

---

### Use Case 3: Load Balancer Health Monitoring

**Scenario:** AWS ALB or NGINX routes traffic only to healthy instances.

**ALB Configuration:**
```
Health Check Path: /health
Interval: 30s
Timeout: 5s
Healthy Threshold: 2
Unhealthy Threshold: 3
```

**Behavior:**
- Load balancer polls `/health`
- 200 OK → Instance remains in rotation
- Non-200 or timeout → Instance removed from rotation

---

### Use Case 4: Manual Availability Test

**Scenario:** Developer or operator tests if service is running.

**Command:**
```bash
curl http://localhost:8765/health
```

**Response:**
```json
{
  "status": "ok",
  "version": "2.1.0",
  "db_path": "/data/telemetry/agent_runs.db",
  "journal_mode": "DELETE",
  "synchronous": "FULL"
}
```

**Interpretation:**
- Service is running ✓
- Database path correct ✓
- Journal mode is DELETE ✓ (Windows-safe)
- Synchronous is FULL ✓ (durability enabled)

---

### Use Case 5: Monitoring Alert on Misconfiguration

**Scenario:** Monitoring system alerts if database settings are wrong.

**Check Script:**
```python
response = requests.get("http://api:8765/health")
health = response.json()

if health["journal_mode"] != "DELETE":
    alert("CRITICAL: Journal mode is not DELETE (corruption risk)")

if health["synchronous"] != "FULL":
    alert("CRITICAL: Synchronous mode is not FULL (data loss risk)")
```

**Benefit:** Catch deployment misconfigurations immediately.

---

## Performance

### Expected Latency

| Operation | Expected Time |
|-----------|---------------|
| Return response | < 1ms |

**Evidence:** No I/O operations, simple dictionary return

**Rationale:** This is the fastest possible endpoint (pure CPU, no blocking).

---

### Throughput

**Concurrent Requests:** Can handle thousands/sec (limited by FastAPI/Uvicorn)

**Evidence:** No database lock contention, no file I/O

**Rationale:** Safe for high-frequency polling.

---

## Comparison with /metrics Endpoint

| Feature | `/health` | `/metrics` |
|---------|-----------|------------|
| **Purpose** | Liveness check | Observability |
| **Database Query** | No | Yes (3 queries) |
| **Latency** | < 1ms | < 50ms |
| **Authentication** | No | Yes (if enabled) |
| **Rate Limiting** | No | Yes (if enabled) |
| **Use Case** | Uptime monitoring | Usage statistics |
| **Fails If** | Process dead | Database unavailable |

**Evidence:** Compare `telemetry_service.py:529-543` with `546-583`

**Recommendation:**
- Use `/health` for liveness probes (is process running?)
- Use `/metrics` for readiness probes (can service handle requests?)

---

## Dependencies

### Configuration Module

**TelemetryAPIConfig:**
- Module: `src/telemetry/config.py`
- Fields Used:
  - `DB_PATH` (line 540)
  - `DB_JOURNAL_MODE` (line 541)
  - `DB_SYNCHRONOUS` (line 542)

**Evidence:** `telemetry_service.py:56` (import), `540-542` (usage)

---

### No FastAPI Dependencies

**Authentication:** NOT applied (no `Depends(verify_auth)`)

**Rate Limiting:** NOT applied (no `Depends(check_rate_limit)`)

**Evidence:** `telemetry_service.py:530` (no function parameters)

**Rationale:** Health checks must be accessible without credentials or quotas.

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:529-543`
- **Response body:** `telemetry_service.py:537-543`

### Configuration
- **TelemetryAPIConfig import:** `telemetry_service.py:56`
- **Journal mode validation:** `src/telemetry/config.py:320-324`
- **Synchronous validation:** `src/telemetry/config.py:327-331`

---

## Verification Status

**Status:** VERIFIED

**Verification Method:**
- Direct file read of handler implementation
- Configuration imports confirmed
- No dependencies verified (no auth, no rate limit)

**Confidence:** HIGH

**Inferred Behaviors:**
- Docker health check patterns (industry standard)
- Kubernetes probe configuration (k8s best practices)
- Load balancer monitoring (common pattern)

**Evidence Strength:**
- Handler logic: STRONG (direct code read)
- Configuration exposure: STRONG (explicit return values)
- Use cases: MEDIUM (inferred from common patterns)
- Performance: HIGH (no I/O operations)
