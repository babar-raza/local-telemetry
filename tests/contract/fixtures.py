"""
Test Fixtures for Contract Tests

Provides reusable fixtures for HTTP API testing, database access, and test data generation.
All fixtures support configuration via environment variables.
"""

import pytest
import uuid
import requests
import sqlite3
import os
from datetime import datetime, timezone
from typing import Generator, Dict, Any


# =============================================================================
# HTTP API Client Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def api_base_url() -> str:
    """Base URL for telemetry API (configurable via TEST_API_BASE_URL)."""
    return os.getenv("TEST_API_BASE_URL", "http://localhost:8765")


@pytest.fixture(scope="function")
def api_client(api_base_url: str) -> requests.Session:
    """
    HTTP client session for API requests.

    Returns a requests.Session configured with:
    - Base URL pre-configured
    - Retry logic for transient failures
    - Timeout settings

    Example:
        resp = api_client.post("/api/v1/runs", json=payload)
        assert resp.status_code == 201
    """
    session = requests.Session()

    # Store base URL for helpers to use
    session.base_url = api_base_url

    # Configure default headers
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json"
    })

    # Set reasonable timeout (10s)
    session.request = lambda method, url, *args, **kwargs: requests.Session.request(
        session, method, f"{api_base_url}{url}", timeout=kwargs.pop('timeout', 10), *args, **kwargs
    )

    yield session

    # Cleanup
    session.close()


# =============================================================================
# Database Connection Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def db_path() -> str:
    """Database path (configurable via TEST_DB_PATH)."""
    return os.getenv("TEST_DB_PATH", "/data/telemetry.sqlite")


@pytest.fixture(scope="function")
def db_connection(db_path: str) -> Generator[sqlite3.Connection, None, None]:
    """
    SQLite database connection for direct queries.

    Yields a connection to the telemetry database.
    Automatically commits and closes after test.

    Example:
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM agent_runs WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Enable dict-like row access

    yield conn

    # Cleanup
    conn.commit()
    conn.close()


# =============================================================================
# Test Data Generation Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def unique_event_id() -> str:
    """
    Generate a unique event ID for each test.

    Returns a UUID4 string suitable for use as event_id.

    Example:
        payload = {"event_id": unique_event_id, ...}
    """
    return str(uuid.uuid4())


@pytest.fixture(scope="function")
def unique_run_id() -> str:
    """
    Generate a unique run ID for each test.

    Returns a run ID in the format: YYYYMMDDTHHMMSSZ-contract-test-{uuid}

    Example:
        payload = {"run_id": unique_run_id, ...}
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid = uuid.uuid4().hex[:8]
    return f"{timestamp}-contract-test-{uid}"


@pytest.fixture(scope="function")
def sample_run_payload(unique_event_id: str, unique_run_id: str) -> Dict[str, Any]:
    """
    Factory fixture for creating test run payloads.

    Returns a complete run payload with all required fields and sensible defaults.
    Can be customized by the test via dictionary update.

    Example:
        payload = sample_run_payload
        payload["status"] = "failure"
        api_client.post("/api/v1/runs", json=payload)
    """
    return {
        "event_id": unique_event_id,
        "run_id": unique_run_id,
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


# =============================================================================
# Test Cleanup Fixtures
# =============================================================================

@pytest.fixture(scope="function")
def test_event_ids() -> Generator[list, None, None]:
    """
    Track event IDs created during test for cleanup.

    Yields a list that tests can append event_ids to.
    After test completes, all tracked events are deleted from database.

    Example:
        test_event_ids.append(event_id)
        # ... test code ...
        # Cleanup happens automatically
    """
    event_ids = []
    yield event_ids

    # Cleanup: Delete all test events from database
    if event_ids:
        db_path = os.getenv("TEST_DB_PATH", "/data/telemetry.sqlite")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        placeholders = ','.join(['?'] * len(event_ids))
        cursor.execute(
            f"DELETE FROM agent_runs WHERE event_id IN ({placeholders})",
            event_ids
        )

        conn.commit()
        conn.close()


@pytest.fixture(scope="function", autouse=False)
def cleanup_test_runs(request, db_path: str):
    """
    Automatically cleanup runs created by contract tests.

    This fixture deletes all runs with agent_name='contract-test-agent'
    after the test completes. Use autouse=True in conftest.py for automatic cleanup.

    Example:
        # Cleanup happens automatically if autouse=True in conftest
        # Or explicitly use:
        def test_something(cleanup_test_runs):
            # test code
            pass
    """
    yield  # Run the test

    # Cleanup: Delete all contract test runs
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM agent_runs WHERE agent_name LIKE 'contract-test%'"
    )

    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    if deleted_count > 0:
        print(f"\n[Cleanup] Deleted {deleted_count} test runs")


# =============================================================================
# Parameterized Fixtures for Test Variations
# =============================================================================

@pytest.fixture(params=["running", "success", "failure", "partial", "timeout", "cancelled"])
def valid_status(request) -> str:
    """
    Parameterized fixture for testing all valid status values.

    Example:
        def test_status_values(valid_status):
            payload["status"] = valid_status
            # Test will run 4 times (once per status)
    """
    return request.param


@pytest.fixture(params=[-1, -100, -9999])
def negative_integer(request) -> int:
    """
    Parameterized fixture for testing negative integer validation.

    Example:
        def test_non_negative_validation(negative_integer):
            payload["duration_ms"] = negative_integer
            # Expect 422 validation error
    """
    return request.param


# =============================================================================
# Environment State Fixtures
# =============================================================================

@pytest.fixture(scope="session")
def api_health(api_base_url: str) -> Dict[str, Any]:
    """
    Check API health before running tests.

    Ensures the API is running and accessible before executing contract tests.
    Returns health check response data.

    Raises:
        RuntimeError: If API is not accessible
    """
    try:
        resp = requests.get(f"{api_base_url}/health", timeout=5)
        resp.raise_for_status()
        health_data = resp.json()

        # Verify expected fields
        assert "status" in health_data, "Health check missing 'status' field"
        assert health_data["status"] == "ok", f"API not healthy: {health_data}"

        return health_data

    except requests.RequestException as e:
        raise RuntimeError(
            f"API not accessible at {api_base_url}/health. "
            f"Ensure telemetry service is running. Error: {e}"
        )


@pytest.fixture(scope="session")
def verify_database_schema(db_path: str) -> None:
    """
    Verify database schema is correct before running tests.

    Checks that agent_runs table exists with expected columns.

    Raises:
        RuntimeError: If schema is incorrect or database inaccessible
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_runs'"
        )
        if not cursor.fetchone():
            raise RuntimeError(f"Table 'agent_runs' not found in {db_path}")

        # Check critical columns exist
        cursor.execute("PRAGMA table_info(agent_runs)")
        columns = {row[1] for row in cursor.fetchall()}

        required_columns = {
            "event_id", "run_id", "agent_name", "job_type",
            "start_time", "status", "duration_ms"
        }

        missing = required_columns - columns
        if missing:
            raise RuntimeError(
                f"Missing required columns in agent_runs: {missing}"
            )

        conn.close()

    except sqlite3.Error as e:
        raise RuntimeError(f"Database error: {e}")
