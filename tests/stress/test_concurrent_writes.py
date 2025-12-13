"""
Stress test for concurrent telemetry writes.
"""

import sqlite3
import threading
import time
from datetime import datetime, timezone

from telemetry import TelemetryClient, TelemetryConfig


def worker_write_telemetry(worker_id, num_runs, results):
    """Worker thread that writes telemetry."""
    try:
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        for i in range(num_runs):
            with client.track_run(
                agent_name=f"concurrent_test_worker_{worker_id}",
                job_type=f"concurrent_test_run_{i}",
                trigger_type="manual"
            ) as run_ctx:
                run_ctx.set_metrics(
                    items_discovered=10,
                    items_succeeded=9,
                    items_failed=1
                )
                time.sleep(0.01)  # Simulate work

        results[worker_id] = {"success": True, "runs": num_runs}

    except Exception as e:
        results[worker_id] = {"success": False, "error": str(e)}


def test_concurrent_writes():
    """Test concurrent writes from multiple threads."""

    NUM_WORKERS = 10
    RUNS_PER_WORKER = 5
    EXPECTED_TOTAL = NUM_WORKERS * RUNS_PER_WORKER

    print("Starting concurrent write test:")
    print(f"  Workers: {NUM_WORKERS}")
    print(f"  Runs per worker: {RUNS_PER_WORKER}")
    print(f"  Expected total runs: {EXPECTED_TOTAL}")

    # Clean up previous test data
    config = TelemetryConfig.from_env()
    conn = sqlite3.connect(str(config.database_path))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM agent_runs WHERE agent_name LIKE 'concurrent_test%'")
    conn.commit()
    conn.close()

    # Start workers
    threads = []
    results = {}
    start_time = time.time()

    for i in range(NUM_WORKERS):
        t = threading.Thread(
            target=worker_write_telemetry,
            args=(i, RUNS_PER_WORKER, results)
        )
        threads.append(t)
        t.start()

    # Wait for all workers
    for t in threads:
        t.join(timeout=60)

    end_time = time.time()
    duration = end_time - start_time

    # Check results
    print(f"\nAll workers completed in {duration:.2f}s")

    # Verify all workers succeeded
    failures = [w for w, r in results.items() if not r.get("success")]
    if failures:
        print(f"Workers failed: {failures}")
        for worker_id in failures:
            print(f"  Worker {worker_id}: {results[worker_id].get('error')}")
        return False

    print("All workers succeeded")

    # Verify data written
    conn = sqlite3.connect(str(config.database_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM agent_runs WHERE agent_name LIKE 'concurrent_test%'")
    actual_count = cursor.fetchone()[0]

    if actual_count == EXPECTED_TOTAL:
        print(f"All {EXPECTED_TOTAL} runs recorded (no data loss)")
    else:
        print(f"Data loss: expected {EXPECTED_TOTAL}, got {actual_count}")
        conn.close()
        return False

    # Check for integrity
    cursor.execute("""
        SELECT COUNT(*) FROM agent_runs
        WHERE agent_name LIKE 'concurrent_test%'
        AND (run_id IS NULL OR start_time IS NULL)
    """)
    corrupt_count = cursor.fetchone()[0]

    if corrupt_count == 0:
        print("No corrupted records")
    else:
        print(f"Found {corrupt_count} corrupted records")
        conn.close()
        return False

    # Performance metrics
    writes_per_second = EXPECTED_TOTAL / duration
    print(f"\nPerformance: {writes_per_second:.1f} writes/second")

    conn.close()

    print("\nCONCURRENT WRITE TEST PASSED")
    return True


if __name__ == "__main__":
    import sys
    success = test_concurrent_writes()
    sys.exit(0 if success else 1)
