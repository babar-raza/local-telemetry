# Database Schema Constraints

**Version:** 1.0
**Last Updated:** 2025-12-31
**Schema Version:** v6 (telemetry_v6.sql)
**Task:** CRID-IV-01 - Schema Constraint Documentation

---

## Overview

This document provides comprehensive documentation of database schema constraints for the telemetry platform, with special focus on the `run_id` field which accepts custom run identifiers from consumers.

## Table: `agent_runs`

### Primary Key

```sql
id INTEGER PRIMARY KEY AUTOINCREMENT
```

**Constraint Details:**
- Type: INTEGER
- Auto-incrementing sequence
- Unique per table
- NOT NULL (implicit for PRIMARY KEY)

### Field: `run_id`

The `run_id` field is a critical identifier that can be either auto-generated or consumer-provided.

#### Schema Definition

```sql
run_id TEXT NOT NULL
```

**Location:** `schema/telemetry_v6.sql`, line 17

#### Constraints

| Constraint Type | Value | Source | Enforced By |
|----------------|-------|--------|-------------|
| Data Type | TEXT | Schema | Database |
| NULL Constraint | NOT NULL | Schema | Database |
| Max Length | **NONE (unlimited)** | Schema | N/A |
| UNIQUE | No | Schema | N/A |
| PRIMARY KEY | No | Schema | N/A |
| CHECK | None | Schema | N/A |
| Default Value | None | Schema | N/A |
| Foreign Key | None | Schema | N/A |

#### Application-Level Validation

The client code enforces additional validation beyond database constraints:

**Location:** `src/telemetry/client.py`, lines 293-310

```python
@staticmethod
def _validate_custom_run_id(run_id: str) -> bool:
    """
    Validate custom run_id format.

    Args:
        run_id: Custom run ID to validate

    Returns:
        bool: True if valid, False otherwise
    """
    if not run_id or not run_id.strip():
        return False
    if len(run_id) > 255:  # HARDCODED LIMIT
        return False
    # Basic safety: no path separators or null bytes
    if '/' in run_id or '\\' in run_id or '\x00' in run_id:
        return False
    return True
```

**Application-Level Constraints:**

| Constraint | Value | Rationale |
|-----------|-------|-----------|
| Max Length | 255 characters | Practical limit for string identifiers, file system compatibility |
| Non-Empty | Required | Must not be empty or whitespace-only |
| No Path Separators | Forbidden: `/` `\` | Security: prevent directory traversal |
| No Null Bytes | Forbidden: `\x00` | Security: prevent string termination attacks |
| Must Trim | Must pass `.strip()` | Prevent whitespace-only IDs |

#### Generated run_id Format

When not provided by consumer, run_id is auto-generated:

**Location:** `src/telemetry/models.py`, lines 222-243

```python
def generate_run_id(agent_name: str) -> str:
    """
    Generate a unique run ID.

    Format: {YYYYMMDD}T{HHMMSS}Z-{agent_name}-{uuid8}

    Example:
        "20251210T120530Z-artifactguard-a1b2c3d4"
    """
    import uuid
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    uuid_short = str(uuid.uuid4())[:8]
    return f"{timestamp}-{agent_name}-{uuid_short}"
```

**Generated Format:**
- Pattern: `{YYYYMMDD}T{HHMMSS}Z-{agent_name}-{uuid8}`
- Length: ~40-60 characters (depends on agent_name length)
- Example: `20251231T153045Z-seo-analyzer-a1b2c3d4`

### Field: `event_id`

The `event_id` field provides idempotency for at-least-once delivery semantics.

#### Schema Definition

```sql
event_id TEXT NOT NULL UNIQUE
```

**Location:** `schema/telemetry_v6.sql`, line 16

#### Constraints

| Constraint Type | Value | Source | Enforced By |
|----------------|-------|--------|-------------|
| Data Type | TEXT | Schema | Database |
| NULL Constraint | NOT NULL | Schema | Database |
| UNIQUE | Yes | Schema | Database (unique index) |
| Max Length | NONE (unlimited) | Schema | N/A |
| Format | UUID v4 | Application | Client code |

**Application Implementation:**
- Generated as UUID v4: `str(uuid.uuid4())`
- Length: 36 characters (standard UUID format)
- Example: `550e8400-e29b-41d4-a716-446655440000`

### Indexes on run_id

**Direct Index:** None (run_id is not indexed directly)

**Foreign Key Reference:**

```sql
-- run_events table references agent_runs.run_id
FOREIGN KEY (run_id) REFERENCES agent_runs(run_id)
```

**Location:** `schema/telemetry_v6.sql`, line 118

**Index:** `idx_events_run` on `run_events(run_id)` for efficient lookups

**Note:** While run_id has a foreign key pointing TO it, there is no index ON agent_runs.run_id. This could cause performance issues for run_events lookups if there are many events per run.

### Related Constraints

#### Status Field

```sql
status TEXT NOT NULL DEFAULT 'running'
CHECK (status IN ('running', 'success', 'failure', 'partial', 'timeout', 'cancelled'))
```

**Location:** `schema/telemetry_v6.sql`, line 27, 90

#### Numeric Constraints

```sql
CHECK (items_discovered >= 0)
CHECK (items_succeeded >= 0)
CHECK (items_failed >= 0)
CHECK (items_skipped >= 0)
CHECK (duration_ms >= 0)
CHECK (api_retry_count >= 0)
```

**Location:** `schema/telemetry_v6.sql`, lines 84-89

---

## Schema-Code Alignment Analysis

### Critical Finding: Length Constraint Mismatch

**Issue:** The database schema has NO length constraint on `run_id`, but the application code enforces a 255-character limit.

| Layer | Constraint | Status |
|-------|-----------|--------|
| Database Schema | TEXT (unlimited) | ✓ Permits any length |
| Application Code | 255 character max | ✓ Enforces limit |
| Alignment | **MISALIGNED** | ⚠️ Code more restrictive |

**Impact:**
- **Risk Level:** LOW
- **Type:** Code is more restrictive than schema (safe direction)
- **Consequence:** Client will reject run_id > 255 chars before database sees them
- **Action:** Document this as intentional application-level constraint

**Recommendation:**
- Add database CHECK constraint to match code validation:
  ```sql
  CHECK (length(run_id) <= 255)
  ```
- This would provide defense-in-depth if other clients bypass application validation

### Code Constants

**Current State:**
- `MAX_RUN_ID_LENGTH` constant: **NOT DEFINED**
- Hardcoded value: `255` (line 305 in client.py)

**Required Action:**
- Add constant to `src/telemetry/client.py`:
  ```python
  # Database schema constraint for run_id field length
  # Note: Database schema (TEXT) allows unlimited length, but we enforce
  # a practical limit for file system compatibility and performance
  MAX_RUN_ID_LENGTH = 255
  ```

---

## Validation Examples

### Valid run_id Examples

```python
# Auto-generated (typical: 40-60 chars)
"20251231T153045Z-seo-analyzer-a1b2c3d4"

# Custom consumer-provided
"my-custom-run-2025-12-31"
"prod-deployment-v1.2.3"
"task-12345-retry-3"

# Maximum length (255 chars)
"a" * 255
```

### Invalid run_id Examples

```python
# Empty or whitespace
""
"   "
"\t\n"

# Exceeds max length
"a" * 256  # REJECTED: > 255 chars

# Path separators (security)
"../../etc/passwd"
"C:\\Windows\\System32"

# Null bytes (security)
"malicious\x00payload"

# None/null
None  # REJECTED: NOT NULL constraint
```

---

## Testing Recommendations

### Unit Tests

1. **Length Validation**
   - Test run_id at boundary: 254, 255, 256 characters
   - Verify rejection of oversized IDs

2. **Character Validation**
   - Test path separator rejection: `/`, `\`
   - Test null byte rejection: `\x00`
   - Test empty string rejection

3. **Null Constraint**
   - Verify NOT NULL enforcement
   - Test empty string vs None

4. **Foreign Key Integrity**
   - Verify run_events can reference agent_runs.run_id
   - Test CASCADE behavior (if implemented)

### Integration Tests

1. **End-to-End Validation**
   - Start run with custom run_id (valid)
   - Start run with custom run_id (invalid, expect rejection)
   - Verify auto-generation when not provided

2. **Database Constraint Testing**
   - Attempt direct SQL INSERT with invalid data
   - Verify database-level enforcement

---

## Migration Considerations

### Adding Length Constraint to Schema

If adding CHECK constraint to database:

```sql
-- Migration: Add run_id length constraint
-- CAUTION: This may fail if existing data exceeds 255 chars

-- Step 1: Verify no existing violations
SELECT run_id, length(run_id) as len
FROM agent_runs
WHERE length(run_id) > 255;

-- Step 2: If no violations, add constraint
-- Note: SQLite doesn't support ADD CONSTRAINT directly
-- Must recreate table or use ALTER TABLE workarounds

-- Alternative: Add CHECK at column level in new table
-- (requires table recreation)
```

### Backward Compatibility

**Risk Assessment:**
- Current code already enforces 255 limit
- Adding database constraint is backward compatible (no existing data exceeds limit)
- Future-proofing against schema drift

---

## References

### Schema Files

- **Primary Schema:** `schema/telemetry_v6.sql`
- **Migrations:**
  - `migrations/v5_add_website_fields.sql` (no run_id changes)
  - `migrations/003_add_created_at_index.sql` (no run_id changes)
  - `migrations/004_add_composite_indexes.sql` (no run_id changes)

### Code Files

- **Validation Logic:** `src/telemetry/client.py` (lines 293-310)
- **Model Definition:** `src/telemetry/models.py` (line 41)
- **ID Generation:** `src/telemetry/models.py` (lines 222-243)

### Related Documentation

- See `docs/reference/schema.md` for table overview
- See `docs/reference/file-contracts.md` for NDJSON format
- See `specs/features/client_telemetry_client.md` for API specification

---

## Change History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-31 | Agent-A | Initial documentation (CRID-IV-01) |

---

**Next Steps:**
1. Add `MAX_RUN_ID_LENGTH` constant to client.py
2. Create verification script to validate alignment
3. Consider adding database CHECK constraint for defense-in-depth
