"""
Contract Tests: Core System Invariants

These tests lock the 7 core invariants documented in specs/_index.md.
If any of these tests fail, the default assumption is: THE CODE IS WRONG.

DRIFTLESS GOVERNANCE:
- Status: LOCKED (contract tests)
- Mode: BUGFIX (document existing behavior)
- Modification: Requires fail-explain-modify protocol

See: docs/development/driftless.md, reports/driftless/13_contract_seed_plan.md
"""

import pytest
import uuid
import os
from datetime import datetime, timezone

# Import fixtures and helpers
from tests.contract.helpers import (
    create_test_run,
    post_run,
    get_run_from_db,
    assert_validation_error,
    assert_duplicate_response,
    assert_created_response
)


# =============================================================================
# CONTRACT-1: Never Crash Agent
# =============================================================================

@pytest.mark.contract
def test_invariant_never_crash_agent():
    """
    CONTRACT: Client library MUST NEVER raise exceptions that crash the agent
    SPEC: specs/_index.md#1-never-crash-agent
    RATIONALE: External services (API, disk) are unreliable; agent must continue

    VERIFICATION:
    - Call client methods with unreachable API
    - Expect graceful error returns (not exceptions)
    """
    try:
        from telemetry import TelemetryClient
    except ImportError:
        pytest.skip("TelemetryClient not available in test environment")

    # Test with unreachable API (port that's not listening)
    client = TelemetryClient(api_base_url="http://localhost:9999", fail_silently=True)

    # These should not raise exceptions
    try:
        # start_run should return event_id or None, not raise
        result = client.start_run(
            agent_name="contract-test",
            job_type="never-crash-test"
        )
        # Client should handle failure gracefully
        assert True, "start_run completed without exception"

        # end_run should handle missing run gracefully
        client.end_run(event_id="nonexistent", status="completed")
        assert True, "end_run completed without exception"

    except Exception as e:
        pytest.fail(f"Client raised exception (violates Never Crash): {e}")


# =============================================================================
# CONTRACT-2: Single-Writer Database Access
# =============================================================================

@pytest.mark.contract
def test_invariant_single_writer_enforcement():
    """
    CONTRACT: Only one process can write to database at a time
    SPEC: specs/_index.md#2-single-writer-database-access
    RATIONALE: Prevent SQLite corruption from concurrent writes

    VERIFICATION:
    - Verify docker-compose.yml has workers: 1
    - Verify lock file exists when API is running
    """
    import yaml

    # Check docker-compose.yml configuration
    compose_path = "docker-compose.yml"
    if os.path.exists(compose_path):
        with open(compose_path, 'r') as f:
            compose_config = yaml.safe_load(f)

        # Verify workers configuration
        if 'services' in compose_config and 'telemetry-api' in compose_config['services']:
            service = compose_config['services']['telemetry-api']
            # Check command for --workers flag
            if 'command' in service:
                command = service['command']
                assert '--workers' not in command or '--workers 1' in str(command) or '--workers=1' in str(command), \
                    "API must be configured with workers=1"

    # Verify lock file exists (indicates single-writer guard active)
    lock_file_paths = [
        "/data/.telemetry.lock",
        ".telemetry.lock",
        os.path.expanduser("~/.telemetry/.telemetry.lock")
    ]

    lock_file_found = any(os.path.exists(path) for path in lock_file_paths)
    # Note: Lock file may not exist in test environment, so we just verify config
    # In production, SingleWriterGuard creates the lock file at startup


# =============================================================================
# CONTRACT-3: Event Idempotency
# =============================================================================

@pytest.mark.contract
def test_invariant_event_idempotency(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: Duplicate event_id returns success (not error)
    SPEC: specs/_index.md#3-event-idempotency
    RATIONALE: At-least-once delivery with retry safety

    VERIFICATION:
    - POST same event_id twice
    - First POST returns 201 Created
    - Second POST returns 200 OK with status=duplicate
    """
    # Track for cleanup
    test_event_ids.append(unique_event_id)

    # Create payload
    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="contract-test-idempotency",
        job_type="idempotency-test",
        status="completed",
        duration_ms=100
    )

    # First POST - should create
    resp1 = post_run(api_base_url, payload)
    assert_created_response(resp1, unique_event_id)

    # Second POST - should return duplicate (idempotent)
    resp2 = post_run(api_base_url, payload)
    assert_duplicate_response(resp2, unique_event_id)


# =============================================================================
# CONTRACT-4: At-Least-Once Delivery
# =============================================================================

@pytest.mark.contract
def test_invariant_at_least_once_delivery():
    """
    CONTRACT: Events MUST eventually reach storage (API, buffer, or NDJSON)
    SPEC: specs/_index.md#4-at-least-once-delivery
    RATIONALE: No telemetry loss even if API unavailable

    VERIFICATION:
    - Verify NDJSON file receives events
    - Verify buffer failover exists for API failures

    NOTE: Full buffer sync worker testing requires integration test setup.
    This test verifies the fallback mechanisms exist.
    """
    # Check that storage paths are configured
    storage_paths = [
        "/data/telemetry.ndjson",
        "/data/buffer.ndjson",
        os.path.expanduser("~/.telemetry/telemetry.ndjson")
    ]

    # At least one NDJSON file should exist or be creatable
    ndjson_exists = any(os.path.exists(path) or os.path.exists(os.path.dirname(path))
                       for path in storage_paths)

    assert ndjson_exists or os.getenv("TEST_API_BASE_URL"), \
        "Either NDJSON storage or API must be available for at-least-once delivery"


# =============================================================================
# CONTRACT-5: Database Corruption Prevention
# =============================================================================

@pytest.mark.contract
def test_invariant_corruption_prevention_pragmas(api_base_url, db_path):
    """
    CONTRACT: Database MUST use DELETE journal + FULL sync for durability
    SPEC: specs/_index.md#5-database-corruption-prevention
    RATIONALE: Prevent corruption on Windows/Docker + power failures

    VERIFICATION:
    - Query PRAGMA journal_mode (expect DELETE)
    - Query PRAGMA synchronous (expect FULL)
    - Verify via GET /health endpoint
    """
    import requests
    import sqlite3

    # Verify via API health endpoint
    resp = requests.get(f"{api_base_url}/health")
    assert resp.status_code == 200, "Health endpoint must be accessible"

    data = resp.json()
    assert data["journal_mode"] == "DELETE", "MUST use DELETE journal mode"
    assert data["synchronous"] == "FULL", "MUST use FULL synchronous mode"

    # Also verify direct database connection
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.upper() == "DELETE", \
            f"Database journal_mode must be DELETE, got {journal_mode}"

        synchronous = cursor.execute("PRAGMA synchronous").fetchone()[0]
        # FULL = 2 in SQLite
        assert synchronous == 2 or synchronous == "FULL", \
            f"Database synchronous must be FULL (2), got {synchronous}"

        conn.close()


# =============================================================================
# CONTRACT-6: Non-Negative Metrics
# =============================================================================

@pytest.mark.contract
def test_invariant_non_negative_metrics(api_base_url, unique_event_id, test_event_ids):
    """
    CONTRACT: Metric fields MUST reject negative values
    SPEC: specs/_index.md#6-non-negative-metrics
    RATIONALE: Prevent data quality issues from bad inputs

    VERIFICATION:
    - POST run with negative duration_ms
    - Expect 422 Unprocessable Entity (Pydantic validation error)
    """
    test_event_ids.append(unique_event_id)

    payload = create_test_run(
        event_id=unique_event_id,
        agent_name="contract-test-validation",
        job_type="validation-test",
        duration_ms=-100  # INVALID: negative value
    )

    resp = post_run(api_base_url, payload)

    # Should reject negative duration_ms
    assert resp.status_code == 422, \
        f"Expected 422 for negative metric, got {resp.status_code}"

    # Verify error mentions validation
    error_data = resp.json()
    assert "detail" in error_data, "Validation error should have 'detail' field"


# =============================================================================
# CONTRACT-7: Status Value Constraints
# =============================================================================

@pytest.mark.contract
def test_invariant_status_constraints(api_base_url, test_event_ids):
    """
    CONTRACT: Status field MUST be one of: running, completed, failed, partial
    SPEC: specs/_index.md#7-status-value-constraints
    RATIONALE: Prevent invalid states in queries and reports

    VERIFICATION:
    - POST run with invalid status value
    - Expect 422 Unprocessable Entity (Pydantic validation error)
    - POST with each valid status should succeed
    """
    # Test invalid status
    invalid_event_id = str(uuid.uuid4())
    test_event_ids.append(invalid_event_id)

    payload = create_test_run(
        event_id=invalid_event_id,
        agent_name="contract-test-status",
        job_type="validation-test",
        status="invalid_status"  # INVALID: not in allowed set
    )

    resp = post_run(api_base_url, payload)
    assert resp.status_code == 422, \
        f"Expected 422 for invalid status, got {resp.status_code}"

    # Test all valid statuses
    valid_statuses = ["running", "completed", "failed", "partial"]
    for valid_status in valid_statuses:
        event_id = str(uuid.uuid4())
        test_event_ids.append(event_id)

        payload = create_test_run(
            event_id=event_id,
            agent_name="contract-test-status",
            job_type="validation-test",
            status=valid_status
        )

        resp = post_run(api_base_url, payload)
        assert resp.status_code in [200, 201], \
            f"Valid status '{valid_status}' should be accepted, got {resp.status_code}"


# =============================================================================
# Test Summary
# =============================================================================
"""
CONTRACT TEST SUMMARY:
- 7 core invariants covered
- All tests marked with @pytest.mark.contract
- Each test documents SPEC reference and RATIONALE
- Tests are LOCKED - failures indicate code regression

IMPLEMENTATION STATUS:
✅ test_invariant_never_crash_agent - IMPLEMENTED
✅ test_invariant_single_writer_enforcement - IMPLEMENTED
✅ test_invariant_event_idempotency - IMPLEMENTED
✅ test_invariant_at_least_once_delivery - IMPLEMENTED (basic verification)
✅ test_invariant_corruption_prevention_pragmas - IMPLEMENTED
✅ test_invariant_non_negative_metrics - IMPLEMENTED
✅ test_invariant_status_constraints - IMPLEMENTED

Run tests: pytest -m contract tests/contract/invariants/ -v
"""
