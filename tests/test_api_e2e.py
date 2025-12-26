#!/usr/bin/env python3
"""
End-to-end test script for Telemetry API.

Tests:
1. POST single event
2. Verify event appears in metrics
3. POST duplicate event (test idempotency)
4. POST batch of events
5. Verify all events in database
"""

import sys
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

# Add src to path for user packages
sys.path.insert(0, r"C:\Users\prora\AppData\Roaming\Python\Python313\site-packages")

try:
    import requests
except ImportError:
    print("[ERROR] requests module not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "requests"])
    import requests

API_URL = "http://localhost:8765"

print("=" * 70)
print("TELEMETRY API - END-TO-END TEST")
print("=" * 70)
print()

# Test 1: Health Check
print("[Test 1] Health Check")
try:
    response = requests.get(f"{API_URL}/health", timeout=5)
    response.raise_for_status()
    health = response.json()
    print(f"  [OK] Status: {health['status']}")
    print(f"  [OK] Version: {health['version']}")
    print(f"  [OK] DB Path: {health['db_path']}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 2: Initial Metrics
print("[Test 2] Initial Metrics (should be 0)")
try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()
    print(f"  [OK] Total runs: {metrics['total_runs']}")
    print(f"  [OK] Agents: {metrics['agents']}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 3: POST Single Event
print("[Test 3] POST Single Event")
event1_id = str(uuid.uuid4())
event1 = {
    "event_id": event1_id,
    "run_id": "test-run-001",
    "start_time": datetime.now(timezone.utc).isoformat(),
    "agent_name": "test-agent",
    "job_type": "e2e-test",
    "status": "success",
    "items_discovered": 100,
    "items_succeeded": 95,
    "items_failed": 5,
    "duration_ms": 5000,
    "product": "test-product",
    "platform": "windows",
    "host": "localhost"
}

try:
    response = requests.post(f"{API_URL}/api/v1/runs", json=event1, timeout=5)
    response.raise_for_status()
    result = response.json()
    print(f"  [OK] Status: {result['status']}")
    print(f"  [OK] Event ID: {result['event_id']}")
    print(f"  [OK] Run ID: {result['run_id']}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 4: Verify Metrics Updated
print("[Test 4] Verify Metrics Updated")
try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()
    print(f"  [OK] Total runs: {metrics['total_runs']}")
    print(f"  [OK] Agents: {metrics['agents']}")

    if metrics['total_runs'] != 1:
        print(f"  [FAIL] Expected 1 run, got {metrics['total_runs']}")
        sys.exit(1)

    if metrics['agents'].get('test-agent') != 1:
        print(f"  [FAIL] Expected 1 run for test-agent, got {metrics['agents'].get('test-agent')}")
        sys.exit(1)

    print("  [OK] Metrics match expected values")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 5: POST Duplicate Event (Idempotency Test)
print("[Test 5] POST Duplicate Event (Idempotency)")
try:
    response = requests.post(f"{API_URL}/api/v1/runs", json=event1, timeout=5)
    result = response.json()

    if result['status'] == 'duplicate':
        print(f"  [OK] Duplicate detected (idempotent)")
        print(f"  [OK] Message: {result.get('message', 'N/A')}")
    else:
        print(f"  [FAIL] Expected 'duplicate' status, got '{result['status']}'")
        sys.exit(1)
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 6: Verify Metrics Unchanged (duplicate shouldn't add)
print("[Test 6] Verify Metrics Unchanged After Duplicate")
try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()

    if metrics['total_runs'] != 1:
        print(f"  [FAIL] Expected 1 run (duplicate shouldn't add), got {metrics['total_runs']}")
        sys.exit(1)

    print(f"  [OK] Total runs still: {metrics['total_runs']} (correct)")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 7: POST Batch of Events
print("[Test 7] POST Batch of Events (3 new + 1 duplicate)")
batch_events = []

# Add 3 new events
for i in range(2, 5):
    batch_events.append({
        "event_id": str(uuid.uuid4()),
        "run_id": f"test-run-{i:03d}",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "agent_name": "test-agent-batch",
        "job_type": "batch-test",
        "status": "success",
        "items_discovered": i * 10,
        "items_succeeded": i * 9,
        "items_failed": i * 1,
        "duration_ms": i * 1000
    })

# Add duplicate of first event
batch_events.append(event1)

try:
    response = requests.post(f"{API_URL}/api/v1/runs/batch", json=batch_events, timeout=5)
    response.raise_for_status()
    result = response.json()

    print(f"  [OK] Inserted: {result['inserted']}")
    print(f"  [OK] Duplicates: {result['duplicates']}")
    print(f"  [OK] Errors: {len(result['errors'])}")
    print(f"  [OK] Total: {result['total']}")

    if result['inserted'] != 3:
        print(f"  [FAIL] Expected 3 new inserts, got {result['inserted']}")
        sys.exit(1)

    if result['duplicates'] != 1:
        print(f"  [FAIL] Expected 1 duplicate, got {result['duplicates']}")
        sys.exit(1)

    print("  [OK] Batch results match expected values")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 8: Final Metrics Check
print("[Test 8] Final Metrics Check")
try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()

    print(f"  [OK] Total runs: {metrics['total_runs']}")
    print(f"  [OK] Agents: {json.dumps(metrics['agents'], indent=4)}")

    expected_total = 4  # 1 from test 3 + 3 from batch
    if metrics['total_runs'] != expected_total:
        print(f"  [FAIL] Expected {expected_total} total runs, got {metrics['total_runs']}")
        sys.exit(1)

    if metrics['agents'].get('test-agent') != 1:
        print(f"  [FAIL] Expected 1 run for test-agent, got {metrics['agents'].get('test-agent')}")
        sys.exit(1)

    if metrics['agents'].get('test-agent-batch') != 3:
        print(f"  [FAIL] Expected 3 runs for test-agent-batch, got {metrics['agents'].get('test-agent-batch')}")
        sys.exit(1)

    print("  [OK] Final metrics correct!")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 9: Query Database Directly
print("[Test 9] Query Database Directly (via Docker)")
import subprocess

try:
    # Query total count
    result = subprocess.run(
        ['docker', 'compose', 'exec', '-T', 'telemetry-api',
         'sqlite3', '/data/telemetry.sqlite',
         'SELECT COUNT(*) FROM agent_runs;'],
        capture_output=True,
        text=True,
        check=True,
        cwd=r"C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"
    )
    count = int(result.stdout.strip())
    print(f"  [OK] Database row count: {count}")

    if count != 4:
        print(f"  [FAIL] Expected 4 rows in database, got {count}")
        sys.exit(1)

    # Query distinct event_ids
    result = subprocess.run(
        ['docker', 'compose', 'exec', '-T', 'telemetry-api',
         'sqlite3', '/data/telemetry.sqlite',
         'SELECT COUNT(DISTINCT event_id) FROM agent_runs;'],
        capture_output=True,
        text=True,
        check=True,
        cwd=r"C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"
    )
    unique_events = int(result.stdout.strip())
    print(f"  [OK] Unique event_ids: {unique_events}")

    if unique_events != 4:
        print(f"  [FAIL] Expected 4 unique event_ids, got {unique_events}")
        sys.exit(1)

    # Query agents
    result = subprocess.run(
        ['docker', 'compose', 'exec', '-T', 'telemetry-api',
         'sqlite3', '/data/telemetry.sqlite',
         'SELECT agent_name, COUNT(*) FROM agent_runs GROUP BY agent_name;'],
        capture_output=True,
        text=True,
        check=True,
        cwd=r"C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"
    )
    print(f"  [OK] Agent breakdown:")
    for line in result.stdout.strip().split('\n'):
        if '|' in line:
            agent, count = line.split('|')
            print(f"       {agent}: {count} runs")

    print("  [OK] Database queries successful!")

except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 10: GET /api/v1/runs - Query All Runs
print("[Test 10] GET /api/v1/runs - Query All Runs")
try:
    response = requests.get(f"{API_URL}/api/v1/runs", timeout=5)
    response.raise_for_status()
    runs = response.json()

    print(f"  [OK] Returned {len(runs)} runs")

    if len(runs) < 4:
        print(f"  [FAIL] Expected at least 4 runs, got {len(runs)}")
        sys.exit(1)

    # Verify structure of first run
    first_run = runs[0]
    required_fields = ['event_id', 'run_id', 'agent_name', 'status', 'created_at']
    for field in required_fields:
        if field not in first_run:
            print(f"  [FAIL] Missing required field: {field}")
            sys.exit(1)

    print(f"  [OK] All runs have required fields")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 11: GET /api/v1/runs - Filter by Agent Name
print("[Test 11] GET /api/v1/runs - Filter by Agent Name")
try:
    response = requests.get(
        f"{API_URL}/api/v1/runs?agent_name=test-agent",
        timeout=5
    )
    response.raise_for_status()
    runs = response.json()

    print(f"  [OK] Returned {len(runs)} runs for test-agent")

    if len(runs) != 1:
        print(f"  [FAIL] Expected 1 run for test-agent, got {len(runs)}")
        sys.exit(1)

    if runs[0]['agent_name'] != 'test-agent':
        print(f"  [FAIL] Expected agent_name='test-agent', got '{runs[0]['agent_name']}'")
        sys.exit(1)

    print(f"  [OK] Filter by agent_name works correctly")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 12: GET /api/v1/runs - Filter by Status
print("[Test 12] GET /api/v1/runs - Filter by Status")
try:
    response = requests.get(
        f"{API_URL}/api/v1/runs?status=success",
        timeout=5
    )
    response.raise_for_status()
    runs = response.json()

    print(f"  [OK] Returned {len(runs)} runs with status=success")

    # Verify all have success status
    for run in runs:
        if run['status'] != 'success':
            print(f"  [FAIL] Expected status='success', got '{run['status']}'")
            sys.exit(1)

    print(f"  [OK] Filter by status works correctly")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 13: GET /api/v1/runs - Pagination (Limit)
print("[Test 13] GET /api/v1/runs - Pagination (Limit)")
try:
    response = requests.get(
        f"{API_URL}/api/v1/runs?limit=2",
        timeout=5
    )
    response.raise_for_status()
    runs = response.json()

    print(f"  [OK] Returned {len(runs)} runs (limit=2)")

    if len(runs) != 2:
        print(f"  [FAIL] Expected 2 runs with limit=2, got {len(runs)}")
        sys.exit(1)

    print(f"  [OK] Pagination limit works correctly")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 14: GET /api/v1/runs - Invalid Status (400 Error)
print("[Test 14] GET /api/v1/runs - Invalid Status (400 Error)")
try:
    response = requests.get(
        f"{API_URL}/api/v1/runs?status=invalid_status",
        timeout=5
    )

    if response.status_code == 400:
        error = response.json()
        print(f"  [OK] Got 400 error as expected")
        print(f"  [OK] Error: {error['detail']}")
    else:
        print(f"  [FAIL] Expected 400 error, got {response.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 15: Create a Stale Running Record for PATCH Tests
print("[Test 15] Create Stale Running Record")
stale_event_id = str(uuid.uuid4())
stale_event = {
    "event_id": stale_event_id,
    "run_id": "stale-run-001",
    "start_time": "2025-12-24T10:00:00Z",
    "created_at": "2025-12-24T10:00:00Z",
    "agent_name": "hugo-translator",
    "job_type": "translate_file",
    "status": "running",
    "items_discovered": 100,
    "items_succeeded": 50,
    "items_failed": 0
}

try:
    response = requests.post(f"{API_URL}/api/v1/runs", json=stale_event, timeout=5)
    response.raise_for_status()
    result = response.json()
    print(f"  [OK] Created stale running record: {result['event_id']}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 16: Query Stale Running Records
print("[Test 16] Query Stale Running Records")
try:
    response = requests.get(
        f"{API_URL}/api/v1/runs?agent_name=hugo-translator&status=running",
        timeout=5
    )
    response.raise_for_status()
    runs = response.json()

    print(f"  [OK] Found {len(runs)} stale running records")

    if len(runs) != 1:
        print(f"  [FAIL] Expected 1 stale run, got {len(runs)}")
        sys.exit(1)

    if runs[0]['event_id'] != stale_event_id:
        print(f"  [FAIL] Event ID mismatch")
        sys.exit(1)

    print(f"  [OK] Query for stale runs works correctly")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 17: PATCH /api/v1/runs/{event_id} - Update to Cancelled
print("[Test 17] PATCH /api/v1/runs/{event_id} - Update to Cancelled")
update_data = {
    "status": "cancelled",
    "end_time": datetime.now(timezone.utc).isoformat(),
    "error_summary": "Stale run cleaned up on startup",
    "output_summary": "Process did not complete - cleanup on restart"
}

try:
    response = requests.patch(
        f"{API_URL}/api/v1/runs/{stale_event_id}",
        json=update_data,
        timeout=5
    )
    response.raise_for_status()
    result = response.json()

    print(f"  [OK] Updated: {result['updated']}")
    print(f"  [OK] Fields updated: {result['fields_updated']}")

    if not result['updated']:
        print(f"  [FAIL] Expected update success")
        sys.exit(1)

    expected_fields = ['status', 'end_time', 'error_summary', 'output_summary']
    if set(result['fields_updated']) != set(expected_fields):
        print(f"  [FAIL] Fields mismatch. Expected {expected_fields}, got {result['fields_updated']}")
        sys.exit(1)

    print(f"  [OK] PATCH update successful")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 18: Verify Update Persisted
print("[Test 18] Verify Update Persisted")
try:
    response = requests.get(
        f"{API_URL}/api/v1/runs?event_id={stale_event_id}",
        timeout=5
    )
    # Note: We don't have event_id filter, so use agent_name
    response = requests.get(
        f"{API_URL}/api/v1/runs?agent_name=hugo-translator",
        timeout=5
    )
    response.raise_for_status()
    runs = response.json()

    updated_run = None
    for run in runs:
        if run['event_id'] == stale_event_id:
            updated_run = run
            break

    if not updated_run:
        print(f"  [FAIL] Could not find updated run")
        sys.exit(1)

    if updated_run['status'] != 'cancelled':
        print(f"  [FAIL] Expected status='cancelled', got '{updated_run['status']}'")
        sys.exit(1)

    if not updated_run['error_summary']:
        print(f"  [FAIL] Expected error_summary to be set")
        sys.exit(1)

    print(f"  [OK] Status: {updated_run['status']}")
    print(f"  [OK] Error summary: {updated_run['error_summary'][:50]}...")
    print(f"  [OK] Update persisted successfully")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 19: PATCH Non-Existent Event (404 Error)
print("[Test 19] PATCH Non-Existent Event (404 Error)")
fake_event_id = str(uuid.uuid4())

try:
    response = requests.patch(
        f"{API_URL}/api/v1/runs/{fake_event_id}",
        json={"status": "cancelled"},
        timeout=5
    )

    if response.status_code == 404:
        error = response.json()
        print(f"  [OK] Got 404 error as expected")
        print(f"  [OK] Error: {error['detail']}")
    else:
        print(f"  [FAIL] Expected 404 error, got {response.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 20: PATCH Invalid Status (400 Error)
print("[Test 20] PATCH Invalid Status (400 Error)")
try:
    response = requests.patch(
        f"{API_URL}/api/v1/runs/{stale_event_id}",
        json={"status": "invalid_status"},
        timeout=5
    )

    if response.status_code == 422:  # Pydantic validation error
        error = response.json()
        print(f"  [OK] Got 422 validation error as expected")
        print(f"  [OK] Error details available")
    else:
        print(f"  [FAIL] Expected 422 validation error, got {response.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 21: PATCH Update Metrics Fields
print("[Test 21] PATCH Update Metrics Fields")
metrics_update = {
    "items_succeeded": 75,
    "items_failed": 25,
    "duration_ms": 120000
}

try:
    response = requests.patch(
        f"{API_URL}/api/v1/runs/{stale_event_id}",
        json=metrics_update,
        timeout=5
    )
    response.raise_for_status()
    result = response.json()

    print(f"  [OK] Updated metrics fields: {result['fields_updated']}")

    if set(result['fields_updated']) != set(['items_succeeded', 'items_failed', 'duration_ms']):
        print(f"  [FAIL] Fields mismatch")
        sys.exit(1)

    print(f"  [OK] Metrics update successful")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()
print("=" * 70)
print("[SUCCESS] All end-to-end tests passed!")
print("=" * 70)
print()
print("Summary:")
print("  - Docker container: Running and healthy")
print("  - Health endpoint: Working")
print("  - Metrics endpoint: Working")
print("  - Single event POST: Working")
print("  - Event idempotency: Working")
print("  - Batch POST: Working")
print("  - Database integrity: Verified")
print("  - GET /api/v1/runs query: Working")
print("  - GET filters (agent_name, status): Working")
print("  - GET pagination (limit): Working")
print("  - GET validation (400 errors): Working")
print("  - PATCH /api/v1/runs/{event_id}: Working")
print("  - PATCH validation (404, 422 errors): Working")
print("  - Stale run cleanup flow: Working")
print("  - Total events created: 5")
print("  - Duplicate events rejected: 2")
print()
print("The telemetry API service is ready for production use!")
print("=" * 70)
