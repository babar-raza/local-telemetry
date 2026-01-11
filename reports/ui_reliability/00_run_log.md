# UI Reliability Fix - Run Log

**Started:** 2026-01-11
**Branch:** fix/ui-reliability
**Goal:** Make telemetry dashboard robust and consistent, especially filters

## Phase 0 - Setup + Baseline

### Environment Setup
- Working directory: c:\Users\prora\OneDrive\Documents\GitHub\local-telemetry
- Found existing git repo
- Found zip file: local-telemetry-share.zip (not extracting - working in existing repo)

### Actions
1. Created reports/ui_reliability/ directory
2. Created this run log
3. Created branch fix/ui-reliability ✓
4. Read key files:
   - scripts/dashboard.py (Streamlit UI)
   - telemetry_service.py (FastAPI service)
   - schema/telemetry_v6.sql (canonical SQL schema)
   - src/telemetry/schema.py (Python schema - DRIFT DETECTED)
   - src/telemetry/config.py (configuration)
   - specs/_index.md (canonical spec)
   - scripts/sync_to_sheets_weekly.py (sheets sync)

### Initial Findings (Evidence-Based)

#### CRITICAL: Status Enum Mismatch
- **Canonical (per specs/_index.md:194 and schema/telemetry_v6.sql:90)**:
  ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']
- **WRONG (schema.py:48)**: Uses 'failed' instead of 'failure'
- **WRONG (dashboard.py:103, 176, 410)**: Uses 'failed' instead of 'failure'
- **CORRECT (telemetry_service.py:215, 742)**: Uses 'failure' ✓
- **CORRECT (sync_to_sheets_weekly.py:46, 62)**: Uses 'failure' ✓

#### Dashboard Filter Issues
1. Line 265: Multi-status filter only uses first value `filter_status[0]` (should support OR semantics)
2. Line 284: Filters job_type client-side after API fetch (should use API parameter)
3. Line 374: Fetches by event_id by scanning limit=1000 runs (should use direct endpoint)

#### Missing API Endpoint
- No GET /api/v1/runs/{event_id} for direct fetch (only has commit-url and repo-url endpoints)

#### Schema Drift
- telemetry_service.py:434 reads schema/telemetry_v6.sql (correct)
- src/telemetry/schema.py exists but has WRONG status enum
- Need to align or deprecate src/telemetry/schema.py

### Implementation Complete

5. Installed core dependencies (fastapi, streamlit, pytest, etc.)
6. Created filter verification harness: scripts/verify_dashboard_filters_headless.py ✓
7. Fixed status enum mismatch in:
   - src/telemetry/schema.py:48 ('failed' → 'failure') ✓
   - scripts/dashboard.py:103, 176, 410, 652 (all 'failed' → 'failure') ✓
8. Added GET /api/v1/runs/{event_id} endpoint in telemetry_service.py ✓
9. Added status alias normalization (failed → failure, completed → success) ✓
10. Fixed dashboard multi-status filter to support OR semantics ✓
11. Fixed dashboard to use server-side job_type filtering ✓
12. Updated dashboard to use direct event_id endpoint (no more 1000-record scans) ✓

### Changes Made (File Summary)

**API Service (telemetry_service.py):**
- Added normalize_status() function with STATUS_ALIASES mapping
- Added GET /api/v1/runs/{event_id} endpoint for direct fetch
- Applied status normalization in POST /api/v1/runs
- Applied status normalization in POST /api/v1/runs/batch
- Applied status normalization in GET /api/v1/runs query endpoint

**Dashboard (scripts/dashboard.py):**
- Fixed validate_status() to use 'failure' instead of 'failed'
- Fixed all status dropdowns and multiselects (4 locations)
- Added get_run_by_id() method to TelemetryAPIClient
- Fixed multi-status filter to query multiple times and merge (OR semantics)
- Fixed job_type filtering to use server-side API parameter
- Updated Edit Single Run to use direct fetch instead of scanning 1000 records

**Schema (src/telemetry/schema.py):**
- Fixed CHECK constraint to use 'failure' instead of 'failed'

**Documentation:**
- Created reports/ui_reliability/00_run_log.md (this file)
- Created reports/ui_reliability/02_root_causes.md (comprehensive evidence)
- Created scripts/verify_dashboard_filters_headless.py (test harness)
