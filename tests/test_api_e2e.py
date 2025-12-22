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
print("  - Total events created: 4")
print("  - Duplicate events rejected: 2")
print()
print("The telemetry API service is ready for production use!")
print("=" * 70)
