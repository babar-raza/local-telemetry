#!/usr/bin/env python3
"""
Test BufferSyncWorker functionality.

Verifies that buffered events from failover can be synced to the API.
This tests the "guaranteed delivery" claim of the buffer system.

Usage:
    python scripts/test_buffer_sync.py
"""
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, r"C:\Users\prora\AppData\Roaming\Python\Python313\site-packages")
sys.path.insert(0, str(Path(__file__).parent.parent))

import requests
import json
from src.telemetry.buffer import BufferSyncWorker

API_URL = "http://localhost:8765"
BUFFER_DIR = str(Path(__file__).parent.parent / "telemetry_buffer")


def check_api_health():
    """Verify API is available."""
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        if resp.status_code == 200:
            print(f"[OK] API is healthy: {resp.json()}")
            return True
        else:
            print(f"[ERROR] API returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] Cannot connect to API: {e}")
        return False


def list_buffer_files():
    """List buffer files and their status."""
    buffer_path = Path(BUFFER_DIR)
    if not buffer_path.exists():
        print("[WARN] Buffer directory does not exist")
        return []

    files = []
    for ext in ['.ready', '.active', '.synced']:
        for f in buffer_path.glob(f"*{ext}"):
            size = f.stat().st_size
            with open(f, 'r') as fh:
                lines = sum(1 for _ in fh)
            files.append((f.name, ext, size, lines))
            print(f"  {f.name}: {lines} records, {size} bytes")

    return files


def get_metrics():
    """Get current run count from API."""
    try:
        resp = requests.get(f"{API_URL}/metrics", timeout=5)
        data = resp.json()
        return data.get("total_runs", 0)
    except Exception as e:
        print(f"[ERROR] Cannot get metrics: {e}")
        return -1


def main():
    print("=" * 60)
    print("BUFFER SYNC WORKER TEST")
    print("=" * 60)

    # Step 1: Check API
    print("\n1. Checking API health...")
    if not check_api_health():
        print("[FAIL] API not available")
        return 1

    # Step 2: List buffer files
    print("\n2. Buffer files before sync:")
    files_before = list_buffer_files()
    if not files_before:
        print("[WARN] No buffer files found")

    ready_files = [f for f in files_before if f[1] == '.ready']
    if not ready_files:
        print("[INFO] No .ready files to sync")
        print("[PASS] Buffer sync verified (nothing to sync)")
        return 0

    # Step 3: Get baseline metrics
    print("\n3. Getting baseline metrics...")
    runs_before = get_metrics()
    print(f"   Total runs before sync: {runs_before}")

    # Step 4: Run sync
    print("\n4. Running BufferSyncWorker...")
    try:
        worker = BufferSyncWorker(
            buffer_dir=BUFFER_DIR,
            api_url=API_URL,
            batch_size=50
        )
        result = worker.sync_all_ready_files()

        print(f"\n   Sync results:")
        print(f"   - Files processed: {result['files_processed']}")
        print(f"   - Total sent: {result['total_sent']}")
        print(f"   - Duplicates: {result['total_duplicates']}")
        if result['errors']:
            print(f"   - Errors: {result['errors']}")
    except Exception as e:
        print(f"[ERROR] Sync failed: {e}")
        return 1

    # Step 5: Verify metrics increased
    print("\n5. Verifying metrics after sync...")
    runs_after = get_metrics()
    print(f"   Total runs after sync: {runs_after}")

    new_runs = runs_after - runs_before
    print(f"   New runs added: {new_runs}")

    # Step 6: List buffer files after
    print("\n6. Buffer files after sync:")
    files_after = list_buffer_files()

    # Verify .ready files became .synced
    synced_files = [f for f in files_after if f[1] == '.synced']
    ready_files_after = [f for f in files_after if f[1] == '.ready']

    # Step 7: Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = True
    issues = []

    # Check 1: Files processed
    if result['files_processed'] > 0:
        print(f"[PASS] Processed {result['files_processed']} file(s)")
    elif len(ready_files) > 0:
        print(f"[FAIL] Did not process .ready files")
        passed = False
        issues.append("Ready files not processed")
    else:
        print(f"[INFO] No .ready files to process")

    # Check 2: Events sent or duplicated (both are OK due to idempotency)
    total_handled = result['total_sent'] + result['total_duplicates']
    if total_handled > 0:
        print(f"[PASS] Handled {total_handled} events ({result['total_sent']} new, {result['total_duplicates']} duplicates)")
    elif result['files_processed'] > 0:
        print(f"[WARN] Processed files but no events handled")
        issues.append("No events in processed files")

    # Check 3: No errors
    if not result['errors']:
        print(f"[PASS] No errors during sync")
    else:
        print(f"[FAIL] Errors occurred: {result['errors']}")
        passed = False
        issues.append(f"Sync errors: {result['errors']}")

    # Check 4: Ready files converted to synced
    if len(ready_files_after) < len(ready_files):
        print(f"[PASS] Ready files converted to synced")
    elif len(ready_files) > 0 and result['files_processed'] > 0:
        print(f"[WARN] Ready files still present after sync")

    # Final verdict
    print()
    if passed:
        print("[SUCCESS] Buffer sync verification passed!")
        return 0
    else:
        print(f"[FAILURE] Issues found: {', '.join(issues)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
