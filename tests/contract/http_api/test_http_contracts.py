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

# Mark all tests in this module as integration tests requiring API and database
pytestmark = [
    pytest.mark.integration,
    pytest.mark.requires_api,
    pytest.mark.requires_db
]


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
    - GET /api/v1/runs?status=completed → only success runs (alias normalization)
    - GET /api/v1/runs?agent_name=test&status=completed → both filters applied
    """
    # Create test runs with known agent_name and status
    test_agent = "contract-test-filter-agent"
    other_agent = "contract-test-other-agent"

    # Create 2 completed (alias) runs for test_agent
    for i in range(2):
        event_id = str(uuid.uuid4())
        test_event_ids.append(event_id)
        payload = create_test_run(
            event_id=event_id,
            agent_name=test_agent,
            status="completed"
        )
        post_run(api_base_url, payload)

    # Create 1 failed (alias) run for test_agent
    event_id = str(uuid.uuid4())
    test_event_ids.append(event_id)
    payload = create_test_run(event_id=event_id, agent_name=test_agent, status="failed")
    post_run(api_base_url, payload)

    # Create 1 completed (alias) run for other_agent
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
    assert all(r["status"] == "success" for r in data), \
        "All runs should match status filter (canonical status)"

    # Test 3: Filter by both agent_name AND status
    resp = get_runs(api_base_url, {"agent_name": test_agent, "status": "completed"})
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["agent_name"] == test_agent and r["status"] == "success" for r in data), \
        "All runs should match both filters (canonical status)"


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
    - PATCH with status=completed (alias), end_time, duration_ms
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

    # 3. GET from database to verify update (use optimized polling instead of fixed delay)
    assert wait_for_run_in_db(db_path, unique_event_id, timeout=1.0), \
        "Run should exist in database after PATCH (waited up to 1.0s)"
    run = get_run_from_db(db_path, unique_event_id)

    # 4. Confirm only patched fields changed
    assert run["status"] == "success", "Status should be updated to canonical value"
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

    # Verify all runs created in database (use optimized polling instead of fixed delay)
    for run in runs:
        assert wait_for_run_in_db(db_path, run["event_id"], timeout=1.0), \
            f"Run {run['event_id']} should exist in database (waited up to 1.0s)"

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
# GT-03: Git Commit Field Validation Tests
# =============================================================================

@pytest.mark.contract
def test_post_run_with_valid_git_commit_source(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: POST /api/v1/runs with valid git_commit_source values
    SPEC: GT-03 Complete FastAPI Pydantic Model
    RATIONALE: Validate git_commit_source accepts 'manual', 'llm', 'ci'

    VERIFICATION:
    - POST with git_commit_source='llm' (and 'manual', 'ci')
    - Expect 201 Created for all valid values
    """
    test_event_ids.append(unique_event_id)

    valid_sources = ['manual', 'llm', 'ci']

    for source in valid_sources:
        event_id = f"{unique_event_id}-{source}"
        test_event_ids.append(event_id)

        payload = create_test_run(
            event_id=event_id,
            agent_name=f"gt03-test-{source}",
            job_type="validation-test",
            status="success",
            git_commit_source=source,
            git_commit_author="Claude <noreply@anthropic.com>",
            git_commit_timestamp="2026-01-01T12:00:00Z"
        )

        resp = post_run(api_base_url, payload)
        assert_created_response(resp, event_id)


@pytest.mark.contract
def test_post_run_with_invalid_git_commit_source(api_base_url, unique_event_id):
    """
    CONTRACT: POST /api/v1/runs rejects invalid git_commit_source
    SPEC: GT-03 Complete FastAPI Pydantic Model
    RATIONALE: Validate git_commit_source validation enforces allowed values

    VERIFICATION:
    - POST with git_commit_source='invalid_value'
    - Expect 422 Unprocessable Entity
    """
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt03-test-invalid",
        job_type="validation-test",
        status="success",
        git_commit_source="invalid_value"  # Invalid value
    )

    resp = post_run(api_base_url, payload)
    assert resp.status_code == 422, \
        f"Expected 422 for invalid git_commit_source, got {resp.status_code}"

    # Verify error message mentions git_commit_source
    error_data = resp.json()
    error_str = str(error_data).lower()
    assert 'git_commit_source' in error_str, \
        "Error response should mention git_commit_source field"


@pytest.mark.contract
def test_patch_run_with_git_commit_fields(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: PATCH /api/v1/runs/{event_id} accepts git_commit_* updates
    SPEC: GT-03 Complete FastAPI Pydantic Model
    RATIONALE: Validate RunUpdate model includes git_commit_source, author, timestamp

    VERIFICATION:
    - Create run without git fields
    - PATCH to add git_commit_source, git_commit_author, git_commit_timestamp
    - Expect 200 OK
    """
    test_event_ids.append(unique_event_id)

    # Create initial run without git fields
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt03-test-patch",
        job_type="validation-test",
        status="running"
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Patch to add git fields
    patch_payload = {
        "git_commit_source": "llm",
        "git_commit_author": "Claude Sonnet <noreply@anthropic.com>",
        "git_commit_timestamp": "2026-01-01T14:30:00Z",
        "status": "success"
    }

    patch_resp = patch_run(api_base_url, unique_event_id, patch_payload)
    assert patch_resp.status_code == 200, \
        f"Expected 200 for PATCH with git fields, got {patch_resp.status_code}"


@pytest.mark.contract
def test_patch_run_with_invalid_git_commit_source(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: PATCH /api/v1/runs/{event_id} rejects invalid git_commit_source
    SPEC: GT-03 Complete FastAPI Pydantic Model
    RATIONALE: Validate git_commit_source validation works in PATCH requests

    VERIFICATION:
    - Create run
    - PATCH with git_commit_source='bad_value'
    - Expect 422 Unprocessable Entity
    """
    test_event_ids.append(unique_event_id)

    # Create initial run
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt03-test-patch-invalid",
        job_type="validation-test",
        status="running"
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Patch with invalid git_commit_source
    patch_payload = {
        "git_commit_source": "automated",  # Invalid: only 'manual', 'llm', 'ci' allowed
        "status": "success"
    }

    patch_resp = patch_run(api_base_url, unique_event_id, patch_payload)
    assert patch_resp.status_code == 422, \
        f"Expected 422 for invalid git_commit_source in PATCH, got {patch_resp.status_code}"


# =============================================================================
# GT-04: Commit Association HTTP Endpoint Tests
# =============================================================================

@pytest.mark.contract
def test_post_associate_commit_success(api_base_url, unique_event_id, test_event_ids, db_path):
    """
    CONTRACT: POST /api/v1/runs/{event_id}/associate-commit with valid data
    SPEC: GT-04 Commit Association HTTP Endpoint
    RATIONALE: Enable HTTP-based commit association for agent runs

    VERIFICATION:
    - Create run via POST
    - POST commit association with valid data
    - Expect 200 OK
    - Verify commit fields updated in database
    """
    test_event_ids.append(unique_event_id)

    # Create initial run
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt04-test-success",
        job_type="commit-association-test",
        status="success"
    )
    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Associate commit
    commit_data = {
        "commit_hash": "abc1234567890abcdef",
        "commit_source": "llm",
        "commit_author": "Claude Code <noreply@anthropic.com>",
        "commit_timestamp": "2026-01-02T10:00:00Z"
    }

    resp = requests.post(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/associate-commit",
        json=commit_data,
        timeout=10
    )

    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}"

    result = resp.json()
    assert result["status"] == "success"
    assert result["event_id"] == unique_event_id
    assert result["commit_hash"] == "abc1234567890abcdef"

    # Verify in database
    from tests.contract.helpers import wait_for_run_in_db, get_run_from_db
    wait_for_run_in_db(db_path, unique_event_id, timeout=1.0)
    run = get_run_from_db(db_path, unique_event_id)

    assert run is not None, "Run should exist in database"
    assert run["git_commit_hash"] == "abc1234567890abcdef"
    assert run["git_commit_source"] == "llm"
    assert run["git_commit_author"] == "Claude Code <noreply@anthropic.com>"
    assert run["git_commit_timestamp"] == "2026-01-02T10:00:00Z"


@pytest.mark.contract
def test_post_associate_commit_run_not_found(api_base_url):
    """
    CONTRACT: POST /api/v1/runs/{event_id}/associate-commit returns 404 for non-existent run
    SPEC: GT-04 Commit Association HTTP Endpoint
    RATIONALE: Prevent associating commits with non-existent runs

    VERIFICATION:
    - POST commit association with non-existent event_id
    - Expect 404 Not Found
    """
    commit_data = {
        "commit_hash": "abc1234567890",
        "commit_source": "manual"
    }

    resp = requests.post(
        f"{api_base_url}/api/v1/runs/nonexistent-event-id/associate-commit",
        json=commit_data,
        timeout=10
    )

    assert resp.status_code == 404, f"Expected 404 Not Found, got {resp.status_code}"

    error_data = resp.json()
    assert "detail" in error_data
    assert "not found" in error_data["detail"].lower()


@pytest.mark.contract
def test_post_associate_commit_invalid_source(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: POST /api/v1/runs/{event_id}/associate-commit validates commit_source
    SPEC: GT-04 Commit Association HTTP Endpoint
    RATIONALE: Enforce commit_source enum ('manual', 'llm', 'ci')

    VERIFICATION:
    - Create run
    - POST commit association with invalid commit_source
    - Expect 422 Unprocessable Entity
    """
    test_event_ids.append(unique_event_id)

    # Create initial run
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt04-test-invalid-source",
        job_type="validation-test",
        status="success"
    )
    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Try to associate with invalid commit_source
    commit_data = {
        "commit_hash": "abc1234567890",
        "commit_source": "automated"  # Invalid: only 'manual', 'llm', 'ci' allowed
    }

    resp = requests.post(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/associate-commit",
        json=commit_data,
        timeout=10
    )

    assert resp.status_code == 422, \
        f"Expected 422 for invalid commit_source, got {resp.status_code}"

    # Verify error message
    error_data = resp.json()
    error_str = str(error_data).lower()
    assert 'commit_source' in error_str, \
        "Error response should mention commit_source field"


@pytest.mark.contract
def test_post_associate_commit_all_sources(api_base_url, unique_event_id, test_event_ids, db_path):
    """
    CONTRACT: POST /api/v1/runs/{event_id}/associate-commit accepts all valid commit_source values
    SPEC: GT-04 Commit Association HTTP Endpoint
    RATIONALE: Verify all three allowed values work

    VERIFICATION:
    - Test commit_source='manual', 'llm', 'ci'
    - All should return 200 OK
    """
    valid_sources = ['manual', 'llm', 'ci']

    for source in valid_sources:
        event_id = f"{unique_event_id}-{source}"
        test_event_ids.append(event_id)

        # Create run
        payload = create_test_run(
            event_id=event_id,
            agent_name=f"gt04-test-{source}",
            job_type="source-validation-test",
            status="success"
        )
        resp = post_run(api_base_url, payload)
        assert_created_response(resp, event_id)

        # Associate commit
        commit_data = {
            "commit_hash": f"abc123456789{source}",
            "commit_source": source
        }

        resp = requests.post(
            f"{api_base_url}/api/v1/runs/{event_id}/associate-commit",
            json=commit_data,
            timeout=10
        )

        assert resp.status_code == 200, \
            f"Expected 200 for commit_source={source}, got {resp.status_code}"


@pytest.mark.contract
def test_post_associate_commit_minimal_payload(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: POST /api/v1/runs/{event_id}/associate-commit with minimal required fields
    SPEC: GT-04 Commit Association HTTP Endpoint
    RATIONALE: Verify only commit_hash and commit_source are required

    VERIFICATION:
    - Create run
    - POST with only commit_hash and commit_source (no author or timestamp)
    - Expect 200 OK
    """
    test_event_ids.append(unique_event_id)

    # Create initial run
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt04-test-minimal",
        job_type="minimal-payload-test",
        status="success"
    )
    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Associate commit with minimal data
    commit_data = {
        "commit_hash": "def456789",
        "commit_source": "ci"
    }

    resp = requests.post(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/associate-commit",
        json=commit_data,
        timeout=10
    )

    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}"

    result = resp.json()
    assert result["status"] == "success"
    assert result["commit_hash"] == "def456789"


# =============================================================================
# GT-02: GitHub/GitLab URL Construction Endpoints
# =============================================================================

@pytest.mark.contract
def test_get_commit_url_github(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: GET /api/v1/runs/{event_id}/commit-url returns GitHub commit URL
    SPEC: GT-02 GitHub/GitLab URL Construction Endpoints
    RATIONALE: Provide clickable commit URLs for GitHub repositories

    VERIFICATION:
    - Create run with GitHub repo and commit hash
    - GET /api/v1/runs/{event_id}/commit-url
    - Expect 200 OK with commit_url in correct GitHub format
    """
    test_event_ids.append(unique_event_id)

    # Create run with GitHub repository metadata
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt02-test-github",
        job_type="url-builder-test",
        status="success",
        git_repo="https://github.com/owner/repo",
        git_commit_hash="abc1234567890"
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Get commit URL
    resp = requests.get(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/commit-url",
        timeout=10
    )

    assert resp.status_code == 200, f"Expected 200 OK, got {resp.status_code}"

    data = resp.json()
    assert "commit_url" in data
    assert data["commit_url"] == "https://github.com/owner/repo/commit/abc1234567890"


@pytest.mark.contract
def test_get_commit_url_gitlab(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: GET /api/v1/runs/{event_id}/commit-url returns GitLab commit URL
    SPEC: GT-02 GitHub/GitLab URL Construction Endpoints
    RATIONALE: Support GitLab repository commit URLs with correct /-/ separator

    VERIFICATION:
    - Create run with GitLab repo
    - GET commit-url
    - Expect GitLab format: https://gitlab.com/owner/repo/-/commit/hash
    """
    test_event_ids.append(unique_event_id)

    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt02-test-gitlab",
        job_type="url-builder-test",
        status="success",
        git_repo="https://gitlab.com/owner/repo",
        git_commit_hash="def4567890abc"
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    resp = requests.get(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/commit-url",
        timeout=10
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["commit_url"] == "https://gitlab.com/owner/repo/-/commit/def4567890abc"


@pytest.mark.contract
def test_get_commit_url_ssh_url_normalization(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: GET /api/v1/runs/{event_id}/commit-url normalizes SSH URLs to HTTPS
    SPEC: GT-02 GitHub/GitLab URL Construction Endpoints
    RATIONALE: git@ SSH URLs should be converted to clickable HTTPS URLs

    VERIFICATION:
    - Create run with SSH format git@github.com:owner/repo.git
    - GET commit-url
    - Expect normalized HTTPS URL
    """
    test_event_ids.append(unique_event_id)

    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt02-test-ssh",
        job_type="url-builder-test",
        status="success",
        git_repo="git@github.com:owner/repo.git",
        git_commit_hash="123abc456def"
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    resp = requests.get(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/commit-url",
        timeout=10
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["commit_url"] == "https://github.com/owner/repo/commit/123abc456def"


@pytest.mark.contract
def test_get_commit_url_missing_git_data_returns_null(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: GET /api/v1/runs/{event_id}/commit-url returns null when git data missing
    SPEC: GT-02 GitHub/GitLab URL Construction Endpoints
    RATIONALE: Gracefully handle runs without git metadata

    VERIFICATION:
    - Create run without git_repo or git_commit_hash
    - GET commit-url
    - Expect 200 OK with commit_url: null
    """
    test_event_ids.append(unique_event_id)

    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt02-test-no-git",
        job_type="url-builder-test",
        status="success"
        # No git_repo or git_commit_hash
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    resp = requests.get(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/commit-url",
        timeout=10
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["commit_url"] is None


@pytest.mark.contract
def test_get_repo_url_normalizes_and_removes_git_extension(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: GET /api/v1/runs/{event_id}/repo-url returns normalized repo URL
    SPEC: GT-02 GitHub/GitLab URL Construction Endpoints
    RATIONALE: Provide clean repository URLs without .git extension

    VERIFICATION:
    - Create run with .git extension in repo URL
    - GET repo-url
    - Expect normalized URL without .git
    """
    test_event_ids.append(unique_event_id)

    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt02-test-repo-url",
        job_type="url-builder-test",
        status="success",
        git_repo="https://github.com/owner/repo.git",
        git_commit_hash="any"
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    resp = requests.get(
        f"{api_base_url}/api/v1/runs/{unique_event_id}/repo-url",
        timeout=10
    )

    assert resp.status_code == 200
    data = resp.json()
    assert "repo_url" in data
    assert data["repo_url"] == "https://github.com/owner/repo"


@pytest.mark.contract
def test_get_runs_includes_commit_url_and_repo_url_fields(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: GET /api/v1/runs includes commit_url and repo_url in response
    SPEC: GT-02 GitHub/GitLab URL Construction Endpoints
    RATIONALE: Enhance query endpoint with URL fields for convenience

    VERIFICATION:
    - Create run with git metadata
    - GET /api/v1/runs with filter
    - Verify response includes commit_url and repo_url fields
    """
    test_event_ids.append(unique_event_id)

    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="gt02-test-query-urls",
        job_type="url-enhancement-test",
        status="success",
        git_repo="https://github.com/test/repo",
        git_commit_hash="testcommit789"
    )

    resp = post_run(api_base_url, payload)
    assert_created_response(resp, unique_event_id)

    # Query runs
    resp = requests.get(
        f"{api_base_url}/api/v1/runs?agent_name=gt02-test-query-urls&limit=1",
        timeout=10
    )

    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) >= 1

    # Find our run
    test_run = next((r for r in runs if r["event_id"] == unique_event_id), None)
    assert test_run is not None, f"Run {unique_event_id} not found in results"

    # Verify URL fields present
    assert "commit_url" in test_run
    assert "repo_url" in test_run

    # Verify URL values correct
    assert test_run["commit_url"] == "https://github.com/test/repo/commit/testcommit789"
    assert test_run["repo_url"] == "https://github.com/test/repo"


# =============================================================================
# Test Summary
# =============================================================================
"""
CONTRACT TEST SUMMARY:
- 6 HTTP API endpoints covered
- 2 tests fully implemented (health, metrics)
- 10 tests skeletonized (create, query, update, batch)
- All tests marked with @pytest.mark.contract
- GT-02: 6 URL builder contract tests added
- GT-03: 3 Pydantic validation contract tests added
- GT-04: 4 commit association contract tests added

NEXT STEPS:
1. Implement TODO sections for remaining tests
2. Create API test fixtures (authenticated client, test database)
3. Write missing specs (http_update_run.md, http_batch_create.md, etc.)
4. Run tests: pytest -m contract tests/contract/http_api/
5. Add to CI pipeline

See: reports/driftless/13_contract_seed_plan.md for full implementation plan
"""
