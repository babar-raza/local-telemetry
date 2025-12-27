"""
Test Helper Functions for Contract Tests

Utility functions for common test operations:
- Creating test payloads
- Making API requests
- Database queries
- Assertions

All helpers follow the "never crash" pattern - they return error states
rather than raising unexpected exceptions.
"""

import uuid
import sqlite3
import time
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
import requests


# =============================================================================
# Payload Creation Helpers
# =============================================================================

def create_test_run(event_id: Optional[str] = None, **overrides) -> Dict[str, Any]:
    """
    Create a test run payload with sensible defaults.

    Args:
        event_id: Event ID (generates UUID if None)
        **overrides: Override any default field values

    Returns:
        Complete run payload dict ready for POST /api/v1/runs

    Example:
        payload = create_test_run(status="completed", duration_ms=1000)
        resp = requests.post(url, json=payload)
    """
    if event_id is None:
        event_id = str(uuid.uuid4())

    # Generate run_id from event_id
    run_id = f"test-{event_id[:8]}"

    # Base payload with all required fields
    payload = {
        "event_id": event_id,
        "run_id": run_id,
        "agent_name": "contract-test-agent",
        "job_type": "contract-test-job",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "duration_ms": 0,
        "items_discovered": 0,
        "items_succeeded": 0,
        "items_failed": 0,
        "items_skipped": 0,
        "trigger_type": "test",
        "environment": "test"
    }

    # Apply overrides
    payload.update(overrides)

    return payload


def create_minimal_run(event_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Create a minimal run payload (only required fields).

    Args:
        event_id: Event ID (generates UUID if None)

    Returns:
        Minimal payload with only required fields

    Example:
        payload = create_minimal_run()
        # Payload has only: event_id, run_id, agent_name, job_type, start_time
    """
    if event_id is None:
        event_id = str(uuid.uuid4())

    return {
        "event_id": event_id,
        "run_id": f"test-minimal-{event_id[:8]}",
        "agent_name": "contract-test-agent",
        "job_type": "minimal-test",
        "start_time": datetime.now(timezone.utc).isoformat()
    }


def create_batch_runs(count: int = 10) -> list:
    """
    Create a batch of test run payloads.

    Args:
        count: Number of runs to create

    Returns:
        List of run payloads

    Example:
        runs = create_batch_runs(5)
        resp = requests.post("/api/v1/runs/batch", json={"runs": runs})
    """
    return [create_test_run() for _ in range(count)]


# =============================================================================
# API Request Helpers
# =============================================================================

def post_run(api_base_url: str, payload: Dict[str, Any], timeout: int = 10) -> requests.Response:
    """
    POST a run to the API.

    Args:
        api_base_url: API base URL (e.g., "http://localhost:8765")
        payload: Run payload dict
        timeout: Request timeout in seconds

    Returns:
        requests.Response object

    Example:
        resp = post_run("http://localhost:8765", payload)
        assert resp.status_code == 201
    """
    url = f"{api_base_url}/api/v1/runs"
    return requests.post(url, json=payload, timeout=timeout)


def get_runs(
    api_base_url: str,
    filters: Optional[Dict[str, Any]] = None,
    timeout: int = 10
) -> requests.Response:
    """
    GET runs from the API with optional filters.

    Args:
        api_base_url: API base URL
        filters: Query parameters (e.g., {"agent_name": "test", "limit": 10})
        timeout: Request timeout in seconds

    Returns:
        requests.Response object

    Example:
        resp = get_runs("http://localhost:8765", {"status": "completed"})
        runs = resp.json()
    """
    url = f"{api_base_url}/api/v1/runs"
    return requests.get(url, params=filters or {}, timeout=timeout)


def patch_run(
    api_base_url: str,
    event_id: str,
    updates: Dict[str, Any],
    timeout: int = 10
) -> requests.Response:
    """
    PATCH a run (partial update).

    Args:
        api_base_url: API base URL
        event_id: Event ID to update
        updates: Fields to update
        timeout: Request timeout in seconds

    Returns:
        requests.Response object

    Example:
        updates = {"status": "completed", "duration_ms": 1000}
        resp = patch_run("http://localhost:8765", event_id, updates)
        assert resp.status_code == 200
    """
    url = f"{api_base_url}/api/v1/runs/{event_id}"
    return requests.patch(url, json=updates, timeout=timeout)


# =============================================================================
# Database Query Helpers
# =============================================================================

def get_run_from_db(db_path: str, event_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a run from the database by event_id.

    Args:
        db_path: Path to SQLite database
        event_id: Event ID to fetch

    Returns:
        Run data as dict, or None if not found

    Example:
        run = get_run_from_db("/data/telemetry.sqlite", event_id)
        if run:
            assert run["status"] == "completed"
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM agent_runs WHERE event_id = ?",
        (event_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def delete_run_from_db(db_path: str, event_id: str) -> int:
    """
    Delete a run from the database.

    Args:
        db_path: Path to SQLite database
        event_id: Event ID to delete

    Returns:
        Number of rows deleted (0 or 1)

    Example:
        deleted = delete_run_from_db("/data/telemetry.sqlite", event_id)
        assert deleted == 1
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM agent_runs WHERE event_id = ?",
        (event_id,)
    )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted


def count_runs_by_agent(db_path: str, agent_name: str) -> int:
    """
    Count runs for a specific agent.

    Args:
        db_path: Path to SQLite database
        agent_name: Agent name to count

    Returns:
        Number of runs

    Example:
        count = count_runs_by_agent("/data/telemetry.sqlite", "contract-test-agent")
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM agent_runs WHERE agent_name = ?",
        (agent_name,)
    )

    count = cursor.fetchone()[0]
    conn.close()

    return count


def cleanup_test_runs_from_db(db_path: str) -> int:
    """
    Delete all contract test runs from database.

    Args:
        db_path: Path to SQLite database

    Returns:
        Number of runs deleted

    Example:
        deleted = cleanup_test_runs_from_db("/data/telemetry.sqlite")
        print(f"Cleaned up {deleted} test runs")
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM agent_runs WHERE agent_name LIKE 'contract-test%'"
    )

    deleted = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted


# =============================================================================
# Wait/Retry Helpers
# =============================================================================

def wait_for_condition(
    predicate: Callable[[], bool],
    timeout: float = 5.0,
    interval: float = 0.1
) -> bool:
    """
    Wait for a condition to become true.

    Args:
        predicate: Function that returns True when condition is met
        timeout: Maximum time to wait in seconds
        interval: Time between checks in seconds

    Returns:
        True if condition met, False if timeout

    Example:
        def check_run_exists():
            return get_run_from_db(db_path, event_id) is not None

        success = wait_for_condition(check_run_exists, timeout=3)
        assert success, "Run never appeared in database"
    """
    start_time = time.time()

    while time.time() - start_time < timeout:
        if predicate():
            return True
        time.sleep(interval)

    return False


def wait_for_run_in_db(
    db_path: str,
    event_id: str,
    timeout: float = 5.0
) -> bool:
    """
    Wait for a run to appear in the database.

    Useful for testing async operations (e.g., buffer sync worker).

    Args:
        db_path: Path to SQLite database
        event_id: Event ID to wait for
        timeout: Maximum time to wait in seconds

    Returns:
        True if run appeared, False if timeout

    Example:
        # Post to API, wait for DB write
        post_run(api_url, payload)
        assert wait_for_run_in_db(db_path, event_id, timeout=3)
    """
    def check():
        return get_run_from_db(db_path, event_id) is not None

    return wait_for_condition(check, timeout=timeout)


# =============================================================================
# Assertion Helpers
# =============================================================================

def assert_validation_error(response: requests.Response, field_name: str) -> None:
    """
    Assert that response is a 422 validation error mentioning a specific field.

    Args:
        response: requests.Response object
        field_name: Expected field name in error message

    Raises:
        AssertionError: If response is not 422 or field not mentioned

    Example:
        resp = post_run(api_url, {"event_id": None})  # Invalid
        assert_validation_error(resp, "event_id")
    """
    assert response.status_code == 422, (
        f"Expected 422 Unprocessable Entity, got {response.status_code}"
    )

    error_data = response.json()
    assert "detail" in error_data, "Response missing 'detail' field"

    # Check if field mentioned in error details
    error_str = str(error_data["detail"]).lower()
    assert field_name.lower() in error_str, (
        f"Field '{field_name}' not mentioned in validation error: {error_data}"
    )


def assert_duplicate_response(response: requests.Response, event_id: str) -> None:
    """
    Assert that response is a 200 duplicate (idempotent) response.

    Args:
        response: requests.Response object
        event_id: Expected event_id in response

    Raises:
        AssertionError: If response is not correct duplicate format

    Example:
        # POST same event twice
        resp1 = post_run(api_url, payload)  # 201
        resp2 = post_run(api_url, payload)  # 200 duplicate
        assert_duplicate_response(resp2, event_id)
    """
    assert response.status_code == 200, (
        f"Expected 200 OK for duplicate, got {response.status_code}"
    )

    data = response.json()
    assert data.get("status") == "duplicate", (
        f"Expected status='duplicate', got {data.get('status')}"
    )
    assert data.get("event_id") == event_id, (
        f"Event ID mismatch: expected {event_id}, got {data.get('event_id')}"
    )


def assert_created_response(response: requests.Response, event_id: str) -> None:
    """
    Assert that response is a 201 created response.

    Args:
        response: requests.Response object
        event_id: Expected event_id in response

    Raises:
        AssertionError: If response is not correct created format

    Example:
        resp = post_run(api_url, payload)
        assert_created_response(resp, event_id)
    """
    assert response.status_code == 201, (
        f"Expected 201 Created, got {response.status_code}"
    )

    data = response.json()
    assert data.get("status") == "created", (
        f"Expected status='created', got {data.get('status')}"
    )
    assert data.get("event_id") == event_id, (
        f"Event ID mismatch: expected {event_id}, got {data.get('event_id')}"
    )
