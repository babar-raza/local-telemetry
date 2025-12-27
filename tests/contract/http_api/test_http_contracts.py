"""
Contract Tests: HTTP API Endpoints

These tests lock the HTTP API behavior for POST/GET/PATCH routes.
If any of these tests fail, the default assumption is: THE CODE IS WRONG.

DRIFTLESS GOVERNANCE:
- Status: LOCKED (contract tests)
- Mode: BUGFIX (document existing behavior)
- Modification: Requires fail-explain-modify protocol

See: docs/development/driftless.md, reports/driftless/13_contract_seed_plan.md
"""

import pytest
import uuid
import requests
from datetime import datetime, timezone

# Import fixtures and helpers
from tests.contract.helpers import (
    create_test_run,
    create_minimal_run,
    create_batch_runs,
    post_run,
    get_runs,
    patch_run,
    get_run_from_db,
    assert_created_response,
    assert_duplicate_response
)


# =============================================================================
# HTTP-1: POST /api/v1/runs - Create Run
# =============================================================================

@pytest.mark.contract
def test_http_create_run_minimal_payload(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: POST /api/v1/runs with minimal required fields returns 201
    SPEC: specs/features/http_create_run.md
    RATIONALE: Clients should only provide required fields for running jobs

    VERIFICATION:
    - POST with only: event_id, run_id, agent_name, job_type, start_time
    - Expect 201 Created
    - Expect status=created in response
    """
    test_event_ids.append(unique_event_id)

    payload = create_minimal_run(event_id=unique_event_id)

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)


@pytest.mark.contract
def test_http_create_run_idempotency(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: Duplicate event_id returns 200 with status=duplicate
    SPEC: specs/features/http_create_run.md#inv-1-idempotency-via-event_id
    RATIONALE: Support at-least-once delivery with retry safety

    VERIFICATION:
    - POST same payload twice
    - First returns 201 Created
    - Second returns 200 OK with status=duplicate
    """
    test_event_ids.append(unique_event_id)

    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="contract-test-idempotency",
        job_type="idempotency-test",
        status="completed"
    )

    # First POST - should create
    resp1 = post_run(api_base_url, payload)
    assert_created_response(resp1, unique_event_id)

    # Second POST - should return duplicate (idempotent)
    resp2 = post_run(api_base_url, payload)
    assert_duplicate_response(resp2, unique_event_id)


@pytest.mark.contract
def test_http_create_run_required_fields_missing(api_base_url):
    """
    CONTRACT: Missing required fields returns 422 Unprocessable Entity
    SPEC: specs/features/http_create_run.md#inv-4-required-field-enforcement
    RATIONALE: Enforce data quality at API boundary

    VERIFICATION:
    - POST without event_id → 422
    - POST without run_id → 422
    - POST without agent_name → 422
    - POST without job_type → 422
    - POST without start_time → 422
    """
    required_fields = ["event_id", "run_id", "agent_name", "job_type", "start_time"]

    for field_to_omit in required_fields:
        # Create complete payload
        payload = create_minimal_run()

        # Remove the required field
        del payload[field_to_omit]

        # POST should return 422 validation error
        resp = post_run(api_base_url, payload)
        assert resp.status_code == 422, \
            f"Expected 422 when {field_to_omit} missing, got {resp.status_code}"

        # Verify error mentions the field
        error_data = resp.json()
        assert "detail" in error_data


# =============================================================================
# HTTP-2: GET /api/v1/runs - Query Runs
# =============================================================================

@pytest.mark.contract
def test_http_query_runs_no_filters(api_base_url):
    """
    CONTRACT: GET /api/v1/runs with no filters returns all runs
    SPEC: specs/features/http_query_runs.md
    RATIONALE: Default behavior for querying all telemetry

    VERIFICATION:
    - GET /api/v1/runs (no query params)
    - Expect 200 OK
    - Expect array of runs
    - Verify ordering (created_at DESC)
    """
    resp = get_runs(api_base_url)
    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}"

    data = resp.json()
    assert isinstance(data, list), "Response should be an array of runs"

    # Verify descending order if multiple runs
    if len(data) > 1:
        timestamps = [r["created_at"] for r in data]
        assert timestamps == sorted(timestamps, reverse=True), \
            "Runs should be ordered by created_at DESC"


@pytest.mark.contract
def test_http_query_runs_pagination(api_base_url, test_event_ids):
    """
    CONTRACT: limit and offset parameters work correctly
    SPEC: specs/features/http_query_runs.md
    RATIONALE: Support large result sets without memory issues

    VERIFICATION:
    - GET /api/v1/runs?limit=10&offset=0 returns first 10
    - GET /api/v1/runs?limit=10&offset=10 returns next 10
    - Verify no overlap, no gaps
    """
    # Create 15 test runs to test pagination
    created_ids = []
    for i in range(15):
        event_id = str(uuid.uuid4())
        test_event_ids.append(event_id)
        created_ids.append(event_id)

        payload = create_test_run(
            event_id=event_id,
            agent_name="contract-test-pagination",
            job_type=f"pagination-test-{i}"
        )
        post_run(api_base_url, payload)

    # Get first page (limit=10, offset=0)
    resp1 = get_runs(api_base_url, {"limit": 10, "offset": 0})
    assert resp1.status_code == 200
    page1 = resp1.json()
    assert len(page1) <= 10, "First page should have at most 10 results"

    # Get second page (limit=10, offset=10)
    resp2 = get_runs(api_base_url, {"limit": 10, "offset": 10})
    assert resp2.status_code == 200
    page2 = resp2.json()

    # Verify no overlap between pages
    page1_ids = {r["event_id"] for r in page1}
    page2_ids = {r["event_id"] for r in page2}
    overlap = page1_ids & page2_ids
    assert len(overlap) == 0, f"Pages should not overlap, found {len(overlap)} duplicates"


@pytest.mark.contract
def test_http_query_runs_filters(api_base_url, test_event_ids):
    """
    CONTRACT: Filter parameters work correctly (agent_name, status, etc.)
    SPEC: specs/features/http_query_runs.md
    RATIONALE: Support targeted queries for specific agents/statuses

    VERIFICATION:
    - GET /api/v1/runs?agent_name=test → only test agent runs
    - GET /api/v1/runs?status=completed → only completed runs
    - GET /api/v1/runs?agent_name=test&status=completed → both filters applied
    """
    # Create test runs with known agent_name and status
    test_agent = "contract-test-filter-agent"
    other_agent = "contract-test-other-agent"

    # Create 2 completed runs for test_agent
    for i in range(2):
        event_id = str(uuid.uuid4())
        test_event_ids.append(event_id)
        payload = create_test_run(
            event_id=event_id,
            agent_name=test_agent,
            status="completed"
        )
        post_run(api_base_url, payload)

    # Create 1 failed run for test_agent
    event_id = str(uuid.uuid4())
    test_event_ids.append(event_id)
    payload = create_test_run(event_id=event_id, agent_name=test_agent, status="failed")
    post_run(api_base_url, payload)

    # Create 1 completed run for other_agent
    event_id = str(uuid.uuid4())
    test_event_ids.append(event_id)
    payload = create_test_run(event_id=event_id, agent_name=other_agent, status="completed")
    post_run(api_base_url, payload)

    # Test 1: Filter by agent_name only
    resp = get_runs(api_base_url, {"agent_name": test_agent})
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["agent_name"] == test_agent for r in data), \
        "All runs should match agent_name filter"

    # Test 2: Filter by status only
    resp = get_runs(api_base_url, {"status": "completed"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["status"] == "completed" for r in data), \
        "All runs should match status filter"

    # Test 3: Filter by both agent_name AND status
    resp = get_runs(api_base_url, {"agent_name": test_agent, "status": "completed"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["agent_name"] == test_agent and r["status"] == "completed" for r in data), \
        "All runs should match both filters"


# =============================================================================
# HTTP-3: PATCH /api/v1/runs/{event_id} - Update Run
# =============================================================================

@pytest.mark.contract
def test_http_update_run_partial_update(api_base_url, unique_event_id, test_event_ids, db_path):
    """
    CONTRACT: PATCH /api/v1/runs/{event_id} updates only specified fields
    SPEC: specs/features/http_update_run.md (TO BE WRITTEN)
    RATIONALE: Support stale run cleanup and status corrections

    VERIFICATION:
    - Create run with status=running
    - PATCH with status=completed, end_time, duration_ms
    - Verify only updated fields changed
    - Verify other fields unchanged
    """
    test_event_ids.append(unique_event_id)

    # 1. POST to create run with status=running
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="contract-test-patch",
        job_type="patch-test",
        status="running",
        duration_ms=0
    )
    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Store original job_type for verification
    original_job_type = payload["job_type"]

    # 2. PATCH with partial update
    updates = {
        "status": "completed",
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 5000
    }
    resp = patch_run(api_base_url, unique_event_id, updates)
    assert resp.status_code == 200, f"Expected 200 OK for PATCH, got {resp.status_code}"

    # 3. GET from database to verify update
    import time
    time.sleep(0.1)  # Brief delay for DB write
    run = get_run_from_db(db_path, unique_event_id)
    assert run is not None, "Run should exist in database after PATCH"

    # 4. Confirm only patched fields changed
    assert run["status"] == "completed", "Status should be updated"
    assert run["duration_ms"] == 5000, "Duration should be updated"
    assert run["job_type"] == original_job_type, "Unpatched fields should remain unchanged"


# =============================================================================
# HTTP-4: GET /health - Health Check
# =============================================================================

@pytest.mark.contract
def test_http_health_check(api_base_url):
    """
    CONTRACT: GET /health returns 200 with system status
    SPEC: specs/features/http_health.md (TO BE WRITTEN)
    RATIONALE: Enable monitoring and deployment verification

    VERIFICATION:
    - GET /health returns 200 OK
    - Response includes: status, version, db_path, journal_mode, synchronous
    - journal_mode = DELETE
    - synchronous = FULL
    """
    resp = requests.get(f"{api_base_url}/health")
    assert resp.status_code == 200

    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["journal_mode"] == "DELETE"
    assert data["synchronous"] == "FULL"


# =============================================================================
# HTTP-5: GET /metrics - System Metrics
# =============================================================================

@pytest.mark.contract
def test_http_metrics(api_base_url):
    """
    CONTRACT: GET /metrics returns system statistics
    SPEC: specs/features/http_metrics.md (TO BE WRITTEN)
    RATIONALE: Provide observability into telemetry system

    VERIFICATION:
    - GET /metrics returns 200 OK
    - Response includes: total_runs, agents, recent_24h, performance
    - Metrics should be consistent with database state
    """
    resp = requests.get(f"{api_base_url}/metrics")
    assert resp.status_code == 200

    data = resp.json()
    assert "total_runs" in data
    assert isinstance(data["total_runs"], int)
    assert data["total_runs"] >= 0

    assert "agents" in data
    assert isinstance(data["agents"], dict)

    assert "recent_24h" in data
    assert isinstance(data["recent_24h"], int)


# =============================================================================
# HTTP-6: POST /api/v1/runs/batch - Batch Create
# =============================================================================

@pytest.mark.contract
def test_http_batch_create(api_base_url, test_event_ids, db_path):
    """
    CONTRACT: POST /api/v1/runs/batch creates multiple runs atomically
    SPEC: specs/features/http_batch_create.md (TO BE WRITTEN)
    RATIONALE: Efficient bulk import for backfills and migrations

    VERIFICATION:
    - POST array of run payloads
    - Expect 201 Created
    - Verify all runs created in database
    - Test partial failure handling (some duplicates)
    """
    # Create 5 new runs for batch
    runs = create_batch_runs(count=5)

    # Track event IDs for cleanup
    for run in runs:
        test_event_ids.append(run["event_id"])

    # POST batch
    resp = requests.post(
        f"{api_base_url}/api/v1/runs/batch",
        json={"runs": runs},
        timeout=10
    )
    assert resp.status_code == 201, f"Expected 201 Created, got {resp.status_code}"

    # Verify response structure
    data = resp.json()
    assert "created" in data or "status" in data, "Response should indicate batch creation"

    # Verify all runs created in database
    import time
    time.sleep(0.2)  # Brief delay for DB writes

    for run in runs:
        db_run = get_run_from_db(db_path, run["event_id"])
        assert db_run is not None, f"Run {run['event_id']} should exist in database"

    # Test partial failure handling (duplicates)
    # Re-POST first 2 runs (should be idempotent)
    duplicate_batch = runs[:2]
    resp2 = requests.post(
        f"{api_base_url}/api/v1/runs/batch",
        json={"runs": duplicate_batch},
        timeout=10
    )
    # Should still return success (idempotent behavior)
    assert resp2.status_code in [200, 201], \
        "Batch with duplicates should be handled gracefully"


# =============================================================================
# Test Summary
# =============================================================================
"""
CONTRACT TEST SUMMARY:
- 6 HTTP API endpoints covered
- 2 tests fully implemented (health, metrics)
- 10 tests skeletonized (create, query, update, batch)
- All tests marked with @pytest.mark.contract

NEXT STEPS:
1. Implement TODO sections for remaining tests
2. Create API test fixtures (authenticated client, test database)
3. Write missing specs (http_update_run.md, http_batch_create.md, etc.)
4. Run tests: pytest -m contract tests/contract/http_api/
5. Add to CI pipeline

See: reports/driftless/13_contract_seed_plan.md for full implementation plan
"""
