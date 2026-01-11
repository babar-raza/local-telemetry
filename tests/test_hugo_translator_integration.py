#!/usr/bin/env python3
"""
Test script to verify hugo-translator can post telemetry to the API.

This simulates what hugo-translator would do when posting telemetry events.

NOTE: This script requires the telemetry API server to be running at localhost:8765.
Run this script directly: python test_hugo_translator_integration.py
"""

import sys
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, r"C:\Users\prora\AppData\Roaming\Python\Python313\site-packages")

try:
    import requests
except ImportError:
    print("[ERROR] requests module not found. Installing...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "requests"])
    import requests

# Telemetry API endpoint (should match hugo-translator's .env)
API_URL = "http://localhost:8765"


# Guard against import-time execution
if __name__ != "__main__":
    # File is being imported (e.g., by pytest collection), not executed directly
    # Skip all test execution to prevent connection attempts at import time
    import sys as _sys
    _sys.exit(0)

print("=" * 70)
print("HUGO-TRANSLATOR TELEMETRY INTEGRATION TEST")
print("=" * 70)
print()

# Test 1: Verify API is reachable
print("[Test 1] Verify Telemetry API is running")
try:
    response = requests.get(f"{API_URL}/health", timeout=5)
    response.raise_for_status()
    health = response.json()
    print(f"  [OK] API is healthy: {health['status']}")
    print(f"  [OK] Version: {health['version']}")
except Exception as e:
    print(f"  [FAIL] Cannot reach telemetry API: {e}")
    sys.exit(1)

print()

# Test 2: Check current metrics (before posting)
print("[Test 2] Check current metrics")
try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()
    print(f"  [OK] Total runs: {metrics['total_runs']}")
    print(f"  [OK] Agents: {json.dumps(metrics['agents'], indent=4)}")

    # Check if hugo-translator already has data
    if "hugo-translator" in metrics['agents']:
        print(f"  [INFO] hugo-translator already has {metrics['agents']['hugo-translator']} runs")
    else:
        print("  [INFO] No hugo-translator runs yet")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 3: POST a test event as hugo-translator
print("[Test 3] POST test event as hugo-translator")
event = {
    "event_id": str(uuid.uuid4()),
    "run_id": "test-hugo-translator-001",
    "start_time": datetime.now(timezone.utc).isoformat(),
    "agent_name": "hugo-translator",
    "job_type": "translate_file",
    "status": "success",
    "items_discovered": 50,  # 50 segments
    "items_succeeded": 48,   # 48 translated successfully
    "items_failed": 2,       # 2 failed
    "duration_ms": 15000,    # 15 seconds
    "product": "slides",
    "platform": ".NET",
    "host": "local-dev"
}

try:
    response = requests.post(f"{API_URL}/api/v1/runs", json=event, timeout=5)
    response.raise_for_status()
    result = response.json()
    print(f"  [OK] Status: {result['status']}")
    print(f"  [OK] Event ID: {result['event_id']}")
    print(f"  [OK] Run ID: {result['run_id']}")
except Exception as e:
    print(f"  [FAIL] {e}")
    print(f"  [DEBUG] Response: {response.text if 'response' in locals() else 'N/A'}")
    sys.exit(1)

print()

# Test 4: Verify hugo-translator appears in metrics
print("[Test 4] Verify hugo-translator appears in metrics")
try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()

    if "hugo-translator" not in metrics['agents']:
        print(f"  [FAIL] hugo-translator not in agents list")
        print(f"  [DEBUG] Current agents: {metrics['agents']}")
        sys.exit(1)

    count = metrics['agents']['hugo-translator']
    print(f"  [OK] hugo-translator has {count} runs")
    print(f"  [OK] Total runs: {metrics['total_runs']}")
    print(f"  [OK] All agents: {json.dumps(metrics['agents'], indent=4)}")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()

# Test 5: POST another event (test idempotency)
print("[Test 5] POST duplicate event (test idempotency)")
try:
    response = requests.post(f"{API_URL}/api/v1/runs", json=event, timeout=5)
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

# Test 6: Verify metrics unchanged after duplicate
print("[Test 6] Verify metrics unchanged after duplicate")
try:
    response = requests.get(f"{API_URL}/metrics", timeout=5)
    response.raise_for_status()
    metrics = response.json()

    new_count = metrics['agents']['hugo-translator']
    if new_count != count:
        print(f"  [FAIL] Count changed after duplicate: {count} -> {new_count}")
        sys.exit(1)

    print(f"  [OK] Count still {count} (duplicate didn't add new run)")
except Exception as e:
    print(f"  [FAIL] {e}")
    sys.exit(1)

print()
print("=" * 70)
print("[SUCCESS] hugo-translator telemetry integration verified!")
print("=" * 70)
print()
print("Summary:")
print("  - hugo-translator can successfully POST to telemetry API")
print("  - Events are created and tracked correctly")
print("  - Idempotency working (duplicates rejected)")
print("  - Metrics updated correctly")
print()
print("Configuration verified:")
print(f"  METRICS_API_URL=http://localhost:8765 ✓")
print()
print("hugo-translator should now post real events when running translations!")
print("=" * 70)
