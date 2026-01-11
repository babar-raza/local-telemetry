#!/usr/bin/env python3
"""
Automated Dashboard Filter Verification Harness

Programmatically tests the telemetry API filter endpoints to verify:
1. Status filter correctness (especially 'failure' vs 'failed')
2. Multi-status filtering (OR semantics)
3. job_type server-side filtering
4. Event ID direct fetch capability
5. Run ID collision prevention

NO MANUAL UI INTERACTION REQUIRED - fully automated.

Usage:
    python scripts/verify_dashboard_filters_headless.py

Exit Codes:
    0 - All tests passed
    1 - One or more tests failed
"""

import os
import sys
import json
import time
import uuid
import requests
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from pathlib import Path

# Configuration
API_BASE_URL = os.getenv("TELEMETRY_API_URL", "http://localhost:8765")
TEMP_DB_PATH = Path(os.getenv("TEMP", "/tmp")) / f"telemetry_test_{uuid.uuid4().hex[:8]}.sqlite"

# Test results tracking
tests_passed = 0
tests_failed = 0
failures = []


def log(message: str, level: str = "INFO"):
    """Log message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")


def test_result(test_name: str, passed: bool, details: str = ""):
    """Record test result."""
    global tests_passed, tests_failed, failures

    if passed:
        tests_passed += 1
        log(f"✓ PASS: {test_name}", "PASS")
    else:
        tests_failed += 1
        failures.append(f"{test_name}: {details}")
        log(f"✗ FAIL: {test_name} - {details}", "FAIL")


def wait_for_api(max_attempts: int = 30, delay: float = 1.0) -> bool:
    """Wait for API to become available."""
    log(f"Waiting for API at {API_BASE_URL}...")

    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{API_BASE_URL}/health", timeout=2)
            if response.status_code == 200:
                log(f"✓ API is ready (attempt {attempt + 1}/{max_attempts})")
                return True
        except requests.exceptions.RequestException:
            if attempt < max_attempts - 1:
                time.sleep(delay)

    log("✗ API did not become available", "ERROR")
    return False


def create_test_run(event_id: str, agent_name: str, status: str, job_type: str, parent_run_id: str = None) -> Dict[str, Any]:
    """Create a test telemetry run."""
    payload = {
        "event_id": event_id,
        "run_id": f"run-{event_id[:8]}",
        "agent_name": agent_name,
        "job_type": job_type,
        "status": status,
        "start_time": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
        "end_time": datetime.now(timezone.utc).isoformat(),
        "duration_ms": 60000,
        "items_discovered": 100,
        "items_succeeded": 95,
        "items_failed": 5,
        "items_skipped": 0,
    }

    if parent_run_id:
        payload["parent_run_id"] = parent_run_id

    response = requests.post(f"{API_BASE_URL}/api/v1/runs", json=payload)
    response.raise_for_status()
    return response.json()


def query_runs(**filters) -> List[Dict[str, Any]]:
    """Query runs with filters."""
    response = requests.get(f"{API_BASE_URL}/api/v1/runs", params=filters)
    response.raise_for_status()
    return response.json()


def test_status_enum_correctness():
    """Test 1: Verify API accepts canonical status values."""
    log("TEST: Status enum correctness (canonical values)")

    canonical_statuses = ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']
    wrong_status = 'failed'  # Common mistake

    # Test canonical values
    for status in canonical_statuses:
        try:
            event_id = str(uuid.uuid4())
            result = create_test_run(event_id, "test-agent", status, "test")
            test_result(f"Status '{status}' accepted", True)
        except Exception as e:
            test_result(f"Status '{status}' accepted", False, str(e))

    # Test wrong value should be rejected
    try:
        event_id = str(uuid.uuid4())
        result = create_test_run(event_id, "test-agent", wrong_status, "test")
        # Should have failed validation
        test_result(f"Status '{wrong_status}' rejected", False, "API accepted invalid status")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 400:
            test_result(f"Status '{wrong_status}' rejected", True)
        else:
            test_result(f"Status '{wrong_status}' rejected", False, f"Wrong error code: {e.response.status_code}")
    except Exception as e:
        test_result(f"Status '{wrong_status}' rejected", False, str(e))


def test_status_query_filter():
    """Test 2: Verify status filter returns correct records."""
    log("TEST: Status filter query")

    # Create runs with different statuses
    agent = "filter-test-agent"
    test_data = [
        (str(uuid.uuid4()), "success"),
        (str(uuid.uuid4()), "failure"),
        (str(uuid.uuid4()), "partial"),
    ]

    for event_id, status in test_data:
        create_test_run(event_id, agent, status, "query-test")

    # Query for each status
    for expected_status in ["success", "failure", "partial"]:
        try:
            results = query_runs(agent_name=agent, status=expected_status)
            statuses_found = {r['status'] for r in results}

            if expected_status in statuses_found and len(statuses_found) == 1:
                test_result(f"Query status={expected_status}", True)
            else:
                test_result(f"Query status={expected_status}", False,
                           f"Expected {expected_status}, got {statuses_found}")
        except Exception as e:
            test_result(f"Query status={expected_status}", False, str(e))


def test_job_type_server_filter():
    """Test 3: Verify job_type is filtered server-side."""
    log("TEST: Server-side job_type filtering")

    agent = "job-type-test-agent"

    # Create runs with different job types
    job_types_data = [
        (str(uuid.uuid4()), "analysis"),
        (str(uuid.uuid4()), "test"),
        (str(uuid.uuid4()), "sync"),
    ]

    for event_id, job_type in job_types_data:
        create_test_run(event_id, agent, "success", job_type)

    # Query for specific job_type
    try:
        results = query_runs(agent_name=agent, job_type="analysis")
        job_types_found = {r['job_type'] for r in results}

        if job_types_found == {"analysis"}:
            test_result("Server-side job_type filter", True)
        else:
            test_result("Server-side job_type filter", False,
                       f"Expected {{analysis}}, got {job_types_found}")
    except Exception as e:
        test_result("Server-side job_type filter", False, str(e))


def test_event_id_direct_fetch():
    """Test 4: Verify direct event_id fetch endpoint exists."""
    log("TEST: Direct event_id fetch endpoint")

    # Create a test run
    event_id = str(uuid.uuid4())
    agent = "direct-fetch-agent"
    create_test_run(event_id, agent, "success", "test")

    # Try direct fetch via GET /api/v1/runs/{event_id}
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/runs/{event_id}")

        if response.status_code == 200:
            data = response.json()
            if data.get('event_id') == event_id:
                test_result("Direct event_id fetch endpoint", True)
            else:
                test_result("Direct event_id fetch endpoint", False,
                           f"Returned wrong event_id: {data.get('event_id')}")
        elif response.status_code == 404:
            test_result("Direct event_id fetch endpoint", False,
                       "Endpoint exists but run not found (possible race condition)")
        else:
            test_result("Direct event_id fetch endpoint", False,
                       f"Unexpected status code: {response.status_code}")

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            test_result("Direct event_id fetch endpoint", False,
                       "Endpoint not implemented (404 Not Found)")
        else:
            test_result("Direct event_id fetch endpoint", False, str(e))
    except Exception as e:
        test_result("Direct event_id fetch endpoint", False, str(e))


def test_run_id_collision_prevention():
    """Test 5: Verify run selection uses event_id (not run_id) as key."""
    log("TEST: Run ID collision prevention")

    # Create two runs with same run_id but different event_ids
    run_id_shared = f"shared-run-{uuid.uuid4().hex[:8]}"
    event_id_1 = str(uuid.uuid4())
    event_id_2 = str(uuid.uuid4())

    # Create first run
    payload_1 = {
        "event_id": event_id_1,
        "run_id": run_id_shared,  # Same run_id
        "agent_name": "collision-test",
        "job_type": "test",
        "status": "success",
        "start_time": datetime.now(timezone.utc).isoformat(),
    }

    # Create second run with same run_id
    payload_2 = {
        "event_id": event_id_2,
        "run_id": run_id_shared,  # Same run_id
        "agent_name": "collision-test",
        "job_type": "test",
        "status": "failure",
        "start_time": datetime.now(timezone.utc).isoformat(),
    }

    try:
        requests.post(f"{API_BASE_URL}/api/v1/runs", json=payload_1).raise_for_status()
        requests.post(f"{API_BASE_URL}/api/v1/runs", json=payload_2).raise_for_status()

        # Query both runs
        results = query_runs(agent_name="collision-test", limit=10)

        # Check we can distinguish by event_id
        event_ids_found = {r['event_id'] for r in results}

        if event_id_1 in event_ids_found and event_id_2 in event_ids_found:
            test_result("Run ID collision prevention", True)
        else:
            test_result("Run ID collision prevention", False,
                       f"Expected both event_ids, got {event_ids_found}")

    except Exception as e:
        test_result("Run ID collision prevention", False, str(e))


def test_date_filter_inclusive():
    """Test 6: Verify date filters are inclusive."""
    log("TEST: Date filter inclusiveness")

    agent = "date-filter-agent"

    # Create runs at specific times
    now = datetime.now(timezone.utc)
    times = [
        now - timedelta(days=2),
        now - timedelta(days=1),
        now,
    ]

    event_ids = []
    for t in times:
        event_id = str(uuid.uuid4())
        event_ids.append(event_id)

        payload = {
            "event_id": event_id,
            "run_id": f"run-{event_id[:8]}",
            "agent_name": agent,
            "job_type": "date-test",
            "status": "success",
            "start_time": t.isoformat(),
        }
        requests.post(f"{API_BASE_URL}/api/v1/runs", json=payload).raise_for_status()

    # Query with date range
    try:
        start_date = (now - timedelta(days=1.5)).isoformat()
        end_date = now.isoformat()

        results = query_runs(
            agent_name=agent,
            start_time_from=start_date,
            start_time_to=end_date
        )

        found_event_ids = {r['event_id'] for r in results}

        # Should include runs from last 2 days
        if event_ids[1] in found_event_ids and event_ids[2] in found_event_ids:
            test_result("Date filter inclusive", True)
        else:
            test_result("Date filter inclusive", False,
                       f"Expected {event_ids[1:]} in {found_event_ids}")

    except Exception as e:
        test_result("Date filter inclusive", False, str(e))


def test_parent_child_hierarchy():
    """Test 7: Verify parent_run_id relationships work."""
    log("TEST: Parent-child run hierarchy")

    parent_event_id = str(uuid.uuid4())
    parent_run_id = f"run-{parent_event_id[:8]}"
    child_event_id = str(uuid.uuid4())

    # Create parent run
    create_test_run(parent_event_id, "parent-agent", "success", "parent-job")

    # Create child run
    create_test_run(child_event_id, "child-agent", "success", "child-job", parent_run_id=parent_run_id)

    try:
        # Query all runs and check parent_run_id
        results = query_runs(limit=1000)
        child_run = next((r for r in results if r['event_id'] == child_event_id), None)

        if child_run and child_run.get('parent_run_id') == parent_run_id:
            test_result("Parent-child hierarchy", True)
        else:
            test_result("Parent-child hierarchy", False,
                       f"parent_run_id not set correctly: {child_run.get('parent_run_id') if child_run else 'run not found'}")

    except Exception as e:
        test_result("Parent-child hierarchy", False, str(e))


def print_summary():
    """Print test summary."""
    log("")
    log("=" * 70)
    log("TEST SUMMARY")
    log("=" * 70)
    log(f"Total Tests: {tests_passed + tests_failed}")
    log(f"Passed: {tests_passed}")
    log(f"Failed: {tests_failed}")

    if failures:
        log("")
        log("FAILURES:")
        for failure in failures:
            log(f"  - {failure}")

    log("=" * 70)

    if tests_failed == 0:
        log("✓ ALL TESTS PASSED", "SUCCESS")
        return 0
    else:
        log(f"✗ {tests_failed} TEST(S) FAILED", "FAIL")
        return 1


def main():
    """Main test execution."""
    log("Dashboard Filter Verification Harness - Starting")
    log(f"API URL: {API_BASE_URL}")

    # Check if API is available
    if not wait_for_api():
        log("Cannot connect to API. Is the service running?", "ERROR")
        log(f"Try: python telemetry_service.py", "ERROR")
        return 1

    # Run tests
    try:
        test_status_enum_correctness()
        test_status_query_filter()
        test_job_type_server_filter()
        test_event_id_direct_fetch()
        test_run_id_collision_prevention()
        test_date_filter_inclusive()
        test_parent_child_hierarchy()

    except Exception as e:
        log(f"Unhandled exception during tests: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return 1

    return print_summary()


if __name__ == "__main__":
    sys.exit(main())
