"""
Measure telemetry system performance.
"""

import sqlite3
import sys
import time
from pathlib import Path
from statistics import median, quantiles

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry import TelemetryClient, TelemetryConfig

def measure_write_latency(num_writes=100):
    """Measure write operation latency."""
    print(f"
Measuring write latency ({num_writes} writes)...")

    config = TelemetryConfig.from_env()
    client = TelemetryClient(config)
    latencies = []

    for i in range(num_writes):
        start = time.time()

        with client.track_run(
            agent_name="perf_test",
            job_type="latency_test",
            trigger_type="benchmark"
        ) as run_ctx:
            run_ctx.update_metrics(items_discovered=10)

        end = time.time()
        latencies.append((end - start) * 1000)  # Convert to ms

    # Calculate percentiles
    p50 = median(latencies)
    p95, p99 = quantiles(latencies, n=100)[94], quantiles(latencies, n=100)[98]

    print(f"  p50: {p50:.2f}ms")
    print(f"  p95: {p95:.2f}ms")
    print(f"  p99: {p99:.2f}ms")

    # Check thresholds
    if p95 < 100:
        print(f"  ✅ Write latency acceptable (p95 < 100ms)")
    else:
        print(f"  ⚠️  Write latency high (p95 = {p95:.2f}ms)")

    return {"p50": p50, "p95": p95, "p99": p99}

def measure_query_latency():
    """Measure query operation latency."""
    print(f"
Measuring query latency...")

    config = TelemetryConfig.from_env()
    conn = sqlite3.connect(str(config.database_path))
    cursor = conn.cursor()

    queries = [
        ("COUNT(*)", "SELECT COUNT(*) FROM agent_runs"),
        ("Recent runs", "SELECT * FROM agent_runs ORDER BY start_time DESC LIMIT 10"),
        ("Aggregation", "SELECT agent_name, COUNT(*), SUM(items_discovered) FROM agent_runs GROUP BY agent_name"),
        ("JOIN", "SELECT ar.run_id, COUNT(re.event_id) FROM agent_runs ar LEFT JOIN run_events re ON ar.run_id = re.run_id GROUP BY ar.run_id LIMIT 10"),
    ]

    results = {}

    for name, query in queries:
        latencies = []
        for _ in range(10):  # Run each query 10 times
            start = time.time()
            cursor.execute(query)
            cursor.fetchall()
            end = time.time()
            latencies.append((end - start) * 1000)

        p50 = median(latencies)
        print(f"  {name}: {p50:.2f}ms")
        results[name] = p50

    conn.close()

    if all(lat < 200 for lat in results.values()):
        print(f"  ✅ Query latency acceptable (all < 200ms)")
    else:
        print(f"  ⚠️  Some queries slow")

    return results

def measure_database_size():
    """Measure database size and growth."""
    print(f"
Measuring database size...")

    config = TelemetryConfig.from_env()
    db_path = config.database_path

    # Database file size
    db_size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"  Database size: {db_size_mb:.2f} MB")

    # Count records
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM agent_runs")
    run_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM run_events")
    event_count = cursor.fetchone()[0]

    print(f"  Records: {run_count} runs, {event_count} events")

    # Calculate size per record
    if run_count > 0:
        bytes_per_run = (db_size_mb * 1024 * 1024) / run_count
        print(f"  Size per run: {bytes_per_run:.0f} bytes")

    conn.close()

    if db_size_mb < 100:
        print(f"  ✅ Database size reasonable (< 100 MB)")
    else:
        print(f"  ⚠️  Database getting large ({db_size_mb:.2f} MB)")

    return {"size_mb": db_size_mb, "runs": run_count, "events": event_count}

def measure_throughput():
    """Measure write throughput."""
    print(f"
Measuring write throughput...")

    config = TelemetryConfig.from_env()
    client = TelemetryClient(config)

    num_writes = 100
    start_time = time.time()

    for i in range(num_writes):
        with client.track_run(
            agent_name="throughput_test",
            job_type="throughput_test",
            trigger_type="benchmark"
        ) as run_ctx:
            run_ctx.update_metrics(items_discovered=5)

    end_time = time.time()
    elapsed = end_time - start_time
    throughput = num_writes / elapsed

    print(f"  Completed {num_writes} writes in {elapsed:.2f}s")
    print(f"  Throughput: {throughput:.2f} writes/sec")

    if throughput > 20:
        print(f"  ✅ Throughput acceptable (> 20 writes/sec)")
    else:
        print(f"  ⚠️  Throughput low ({throughput:.2f} writes/sec)")

    return {"throughput": throughput, "elapsed": elapsed, "writes": num_writes}

def main():
    """Run all performance measurements."""
    print("=" * 70)
    print("Telemetry Performance Validation")
    print("=" * 70)

    write_perf = measure_write_latency()
    query_perf = measure_query_latency()
    db_stats = measure_database_size()
    throughput_stats = measure_throughput()

    print("
" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"Write p50: {write_perf['p50']:.2f}ms")
    print(f"Write p95: {write_perf['p95']:.2f}ms")
    print(f"Write p99: {write_perf['p99']:.2f}ms")
    print(f"Query avg: {sum(query_perf.values())/len(query_perf):.2f}ms")
    print(f"Throughput: {throughput_stats['throughput']:.2f} writes/sec")
    print(f"DB size: {db_stats['size_mb']:.2f} MB ({db_stats['runs']} runs)")

    # Overall assessment
    write_ok = write_perf['p95'] < 100
    query_ok = all(lat < 200 for lat in query_perf.values())
    size_ok = db_stats['size_mb'] < 100
    throughput_ok = throughput_stats['throughput'] > 20

    print("
" + "=" * 70)
    print("Performance Assessment")
    print("=" * 70)
    print(f"Write latency (p95 < 100ms): {'PASS' if write_ok else 'FAIL'}")
    print(f"Query latency (all < 200ms): {'PASS' if query_ok else 'FAIL'}")
    print(f"Database size (< 100 MB): {'PASS' if size_ok else 'FAIL'}")
    print(f"Throughput (> 20 writes/sec): {'PASS' if throughput_ok else 'FAIL'}")

    if write_ok and query_ok and size_ok and throughput_ok:
        print("
✅ ALL PERFORMANCE CHECKS PASSED")
        return True
    else:
        print("
⚠️  Some performance issues detected")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
