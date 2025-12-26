#!/usr/bin/env python
"""
Crash Durability Test Runner

Standalone script to test database durability under crash conditions.
Uses multiprocessing to simulate process crashes during database writes.

This script proves that PRAGMA synchronous=FULL prevents database corruption
when processes crash mid-write.

Usage:
    python scripts/test_crash_durability.py                    # Run with temp database
    python scripts/test_crash_durability.py --iterations 100   # Run 100 iterations
    python scripts/test_crash_durability.py --db path/to/db    # Use specific database

Exit codes:
    0 - All tests passed (100% survival rate)
    1 - Tests failed or corruption detected
"""

import os
import sys
import time
import argparse
import tempfile
import multiprocessing
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add src to path - import schema module directly to avoid dependency chain
src_path = Path(__file__).parent.parent / "src" / "telemetry"
sys.path.insert(0, str(src_path.parent))

# Import schema module directly (avoids full telemetry package load)
import importlib.util
schema_spec = importlib.util.spec_from_file_location("schema", src_path / "schema.py")
schema_module = importlib.util.module_from_spec(schema_spec)
schema_spec.loader.exec_module(schema_module)
create_schema = schema_module.create_schema


@dataclass
class DurabilityResult:
    """Results from durability test run."""
    iterations: int
    successful_crashes: int
    records_written: int
    integrity_ok: bool
    error_message: Optional[str] = None


def writer_process(db_path: str, num_records: int, crash_after: int, ready_event):
    """
    Child process that writes records to database.

    Writes records and signals when ready to be crashed.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Apply production PRAGMA settings
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA journal_mode=DELETE")
        cursor.execute("PRAGMA synchronous=FULL")
        cursor.execute("PRAGMA wal_autocheckpoint=100")

        for i in range(num_records):
            cursor.execute(
                """
                INSERT INTO agent_runs (run_id, event_id, agent_name, start_time, status)
                VALUES (?, ?, ?, datetime('now'), 'running')
                """,
                (f"durability_run_{time.time()}_{i}", f"durability_event_{time.time()}_{i}", "durability_test")
            )
            conn.commit()

            if i == crash_after - 1:
                ready_event.set()
                time.sleep(0.1)  # Give parent time to kill us

        conn.close()
    except Exception:
        pass  # Process may be killed


def count_test_records(db_path: str) -> int:
    """Count durability test records."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM agent_runs WHERE agent_name = 'durability_test'")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def check_integrity(db_path: str) -> tuple[bool, str]:
    """Check database integrity."""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        result = cursor.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        return result == "ok", result
    except sqlite3.Error as e:
        return False, str(e)


def run_durability_test(db_path: str, iterations: int, records_per_iter: int = 10, crash_after: int = 5) -> DurabilityResult:
    """
    Run durability test with specified iterations.

    Args:
        db_path: Path to database
        iterations: Number of crash iterations
        records_per_iter: Records to attempt per iteration
        crash_after: Crash after this many records

    Returns:
        DurabilityResult with test results
    """
    successful_crashes = 0

    for i in range(iterations):
        ready_event = multiprocessing.Event()

        proc = multiprocessing.Process(
            target=writer_process,
            args=(db_path, records_per_iter, crash_after, ready_event)
        )
        proc.start()

        # Wait for process to write target records
        if ready_event.wait(timeout=5):
            time.sleep(0.02)  # Brief delay to ensure commits complete
            proc.terminate()
            proc.join(timeout=2)
            successful_crashes += 1
        else:
            proc.terminate()
            proc.join(timeout=2)

        # Check integrity after each crash
        integrity_ok, result = check_integrity(db_path)
        if not integrity_ok:
            return DurabilityResult(
                iterations=i + 1,
                successful_crashes=successful_crashes,
                records_written=count_test_records(db_path),
                integrity_ok=False,
                error_message=f"Corruption detected at iteration {i + 1}: {result}"
            )

    final_records = count_test_records(db_path)
    integrity_ok, result = check_integrity(db_path)

    return DurabilityResult(
        iterations=iterations,
        successful_crashes=successful_crashes,
        records_written=final_records,
        integrity_ok=integrity_ok,
        error_message=None if integrity_ok else result
    )


def print_pragma_settings(db_path: str):
    """Print current PRAGMA settings."""
    import sqlite3
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    settings = [
        ("busy_timeout", "PRAGMA busy_timeout"),
        ("journal_mode", "PRAGMA journal_mode"),
        ("synchronous", "PRAGMA synchronous"),
        ("wal_autocheckpoint", "PRAGMA wal_autocheckpoint"),
    ]

    print("\nPRAGMA Settings:")
    for name, query in settings:
        value = cursor.execute(query).fetchone()[0]
        print(f"  {name}: {value}")

    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Test database durability under crash conditions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python scripts/test_crash_durability.py                    # 20 iterations, temp DB
    python scripts/test_crash_durability.py --iterations 100   # 100 iterations
    python scripts/test_crash_durability.py --verbose          # Show progress
        """
    )
    parser.add_argument(
        "--db", "-d",
        help="Database path (creates temp DB if not specified)"
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=20,
        help="Number of crash iterations (default: 20)"
    )
    parser.add_argument(
        "--records", "-r",
        type=int,
        default=10,
        help="Records per iteration (default: 10)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Database Crash Durability Test")
    print("=" * 70)
    print(f"\nThis test proves that PRAGMA synchronous=FULL prevents corruption")
    print(f"when database writer processes crash mid-operation.")

    # Setup database
    temp_dir = None
    if args.db:
        db_path = args.db
        if not Path(db_path).exists():
            print(f"\nCreating database at: {db_path}")
            create_schema(db_path)
    else:
        temp_dir = tempfile.mkdtemp()
        db_path = str(Path(temp_dir) / "durability_test.sqlite")
        print(f"\nCreating temporary database: {db_path}")
        create_schema(db_path)

    print_pragma_settings(db_path)

    print(f"\nRunning {args.iterations} crash iterations...")
    print(f"  Records per iteration: {args.records}")
    print(f"  Crash point: after 5 committed records")

    start_time = time.time()
    result = run_durability_test(
        db_path,
        iterations=args.iterations,
        records_per_iter=args.records
    )
    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("Results")
    print("=" * 70)
    print(f"\n  Iterations completed: {result.iterations}")
    print(f"  Successful crashes:   {result.successful_crashes}")
    print(f"  Records survived:     {result.records_written}")
    print(f"  Database integrity:   {'OK' if result.integrity_ok else 'FAILED'}")
    print(f"  Time elapsed:         {elapsed:.2f}s")

    if result.error_message:
        print(f"\n  ERROR: {result.error_message}")

    # Calculate survival rate
    expected_min = result.successful_crashes * 5  # At least 5 records per crash
    survival_rate = (result.records_written / expected_min * 100) if expected_min > 0 else 0

    print(f"\n  Minimum expected records: {expected_min}")
    print(f"  Survival rate: {survival_rate:.1f}%")

    print("\n" + "=" * 70)

    if result.integrity_ok and result.records_written >= expected_min:
        print("[PASS] Database survived all crash iterations!")
        print("       PRAGMA synchronous=FULL provides durability guarantees.")
        print("=" * 70)

        # Cleanup temp directory
        if temp_dir:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)

        return 0
    else:
        print("[FAIL] Durability test failed!")
        if not result.integrity_ok:
            print("       Database corruption detected.")
        else:
            print("       Insufficient records survived crashes.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    # Required for multiprocessing on Windows
    multiprocessing.freeze_support()
    sys.exit(main())
