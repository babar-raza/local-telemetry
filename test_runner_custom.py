"""
Simple test runner for custom run_id tests without pytest
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from telemetry.client import TelemetryClient
import logging

# Configure logging to see all messages
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(name)s - %(message)s')

def test_duplicate_custom_run_id():
    """Test calling start_run() twice with same custom run_id generates unique IDs."""
    print("\n=== Test: Duplicate Custom Run ID ===")

    client = TelemetryClient()
    custom_id = "my-custom-run-123"

    # First call - should succeed with custom ID
    run_id_1 = client.start_run("test_agent", "test_job", run_id=custom_id)
    print(f"First run_id: {run_id_1}")
    assert run_id_1 == custom_id, f"Expected {custom_id}, got {run_id_1}"

    # Second call with same custom ID - should generate unique ID
    run_id_2 = client.start_run("test_agent", "test_job", run_id=custom_id)
    print(f"Second run_id: {run_id_2}")

    # Verify IDs are different
    assert run_id_1 != run_id_2, f"IDs should be different: {run_id_1} vs {run_id_2}"

    # Verify second ID has duplicate suffix
    assert run_id_2.startswith(f"{custom_id}-duplicate-"), \
        f"Second ID should have duplicate suffix: {run_id_2}"

    # Verify both runs exist in active runs
    assert run_id_1 in client._active_runs, f"{run_id_1} not in active runs"
    assert run_id_2 in client._active_runs, f"{run_id_2} not in active runs"

    print("✓ Test passed: Duplicate custom run_id generates unique IDs")
    return True

def test_duplicate_in_active_runs():
    """Test that duplicate of active run in _active_runs registry is detected."""
    print("\n=== Test: Duplicate in Active Runs Registry ===")

    client = TelemetryClient()
    custom_id = "active-run-test"

    # Start first run
    run_id_1 = client.start_run("test_agent", "test_job", run_id=custom_id)
    print(f"First run_id: {run_id_1}")

    # Verify it's in active runs
    assert custom_id in client._active_runs, f"{custom_id} not in active runs"

    # Start second run with same ID
    run_id_2 = client.start_run("test_agent", "test_job", run_id=custom_id)
    print(f"Second run_id: {run_id_2}")

    # Verify duplicate was detected and new ID generated
    assert run_id_2 != custom_id, f"Should have generated new ID, got {run_id_2}"
    assert run_id_2.startswith(f"{custom_id}-duplicate-"), \
        f"Should have duplicate suffix: {run_id_2}"

    # Verify original run is still in active runs
    assert custom_id in client._active_runs, f"Original run should still be active"
    assert run_id_2 in client._active_runs, f"New run should be in active runs"

    print("✓ Test passed: Duplicate in active runs registry detected")
    return True

def test_concurrent_duplicates():
    """Test concurrent calls with same custom run_id."""
    print("\n=== Test: Concurrent Duplicate Custom Run IDs ===")

    client = TelemetryClient()
    custom_id = "concurrent-test-id"

    # Simulate concurrent calls
    run_ids = []
    for i in range(3):
        run_id = client.start_run("test_agent", "test_job", run_id=custom_id)
        run_ids.append(run_id)
        print(f"Run {i+1} ID: {run_id}")

    # Verify all IDs are unique
    assert len(run_ids) == len(set(run_ids)), "All IDs should be unique"

    # First should be original, rest should have duplicate suffix
    assert run_ids[0] == custom_id, f"First ID should be original: {run_ids[0]}"
    assert run_ids[1].startswith(f"{custom_id}-duplicate-"), \
        f"Second ID should have suffix: {run_ids[1]}"
    assert run_ids[2].startswith(f"{custom_id}-duplicate-"), \
        f"Third ID should have suffix: {run_ids[2]}"

    # Verify all runs exist
    for run_id in run_ids:
        assert run_id in client._active_runs, f"{run_id} not in active runs"

    print("✓ Test passed: Concurrent duplicate custom run_ids handled")
    return True

def test_no_duplicate_after_end():
    """Test that same custom run_id can be reused after end_run()."""
    print("\n=== Test: No Duplicate After end_run() ===")

    client = TelemetryClient()
    custom_id = "reusable-run-id"

    # First run
    run_id_1 = client.start_run("test_agent", "test_job", run_id=custom_id)
    print(f"First run_id: {run_id_1}")
    assert run_id_1 == custom_id, f"First ID should be custom_id: {run_id_1}"

    # End the run (removes from active_runs)
    client.end_run(run_id_1, status="success")

    # Verify removed from active runs
    assert custom_id not in client._active_runs, "Should be removed from active runs"

    # Start new run with same custom ID - should succeed
    run_id_2 = client.start_run("test_agent", "test_job", run_id=custom_id)
    print(f"Second run_id: {run_id_2}")
    assert run_id_2 == custom_id, f"Second ID should be custom_id: {run_id_2}"

    # No duplicate suffix should be added
    assert not run_id_2.startswith(f"{custom_id}-duplicate-"), \
        "Should not have duplicate suffix after end_run()"

    print("✓ Test passed: Custom run_id can be reused after end_run()")
    return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("Custom Run ID Duplicate Detection Tests (CRID-SR-01)")
    print("=" * 60)

    tests = [
        test_duplicate_custom_run_id,
        test_duplicate_in_active_runs,
        test_concurrent_duplicates,
        test_no_duplicate_after_end,
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except AssertionError as e:
            print(f"✗ Test failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ Test error: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
