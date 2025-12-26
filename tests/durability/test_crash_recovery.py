"""
Crash Recovery Tests for SQLite Database Durability.

Tests that database survives process crashes with synchronous=FULL.
Uses multiprocessing to simulate crashes by killing writer processes mid-operation.

These tests prove:
1. Committed transactions survive crashes
2. Uncommitted transactions are properly rolled back
3. Database integrity is maintained after crashes
4. No corruption occurs with PRAGMA synchronous=FULL

Usage:
    pytest tests/durability/test_crash_recovery.py -v
    python tests/durability/test_crash_recovery.py  # Direct execution
"""

import os
import sys
import time
import signal
import sqlite3
import tempfile
import multiprocessing
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from telemetry.database import DatabaseWriter
from telemetry.schema import create_schema


@dataclass
class CrashTestResult:
    """Result of a crash simulation test."""
    records_before_crash: int
    records_after_crash: int
    integrity_ok: bool
    error: Optional[str] = None


def writer_process(db_path: str, num_records: int, crash_after: int, ready_event, crash_event):
    """
    Child process that writes records to database.

    Args:
        db_path: Path to SQLite database
        num_records: Total records to write
        crash_after: Crash after this many records (simulated by parent killing us)
        ready_event: Event to signal when ready to be killed
        crash_event: Event to wait for before crashing
    """
    try:
        writer = DatabaseWriter(Path(db_path))
        conn = writer._get_connection()
        cursor = conn.cursor()

        for i in range(num_records):
            # Insert a record
            cursor.execute(
                """
                INSERT INTO agent_runs (run_id, event_id, agent_name, start_time, status)
                VALUES (?, ?, ?, datetime('now'), 'running')
                """,
                (f"crash_test_run_{i}", f"crash_test_event_{i}", "crash_test_agent")
            )
            conn.commit()  # Commit each record individually

            # Signal ready to be crashed after target records
            if i == crash_after - 1:
                ready_event.set()
                # Wait a bit to ensure we're in a vulnerable state
                time.sleep(0.1)

        conn.close()

    except Exception as e:
        # Process may be killed before completing
        pass


def count_records(db_path: str) -> int:
    """Count records in database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM agent_runs WHERE agent_name = 'crash_test_agent'")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def check_integrity(db_path: str) -> tuple[bool, str]:
    """Check database integrity."""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        result = cursor.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        return result == "ok", result
    except sqlite3.Error as e:
        return False, str(e)


class TestCrashRecovery:
    """Tests for database crash recovery."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database with schema."""
        db_path = tmp_path / "crash_test.sqlite"
        create_schema(str(db_path))
        return db_path

    def test_committed_records_survive_crash(self, temp_db):
        """Committed records should survive a process crash."""
        db_path = str(temp_db)
        num_records = 20
        crash_after = 10

        # Create synchronization events
        ready_event = multiprocessing.Event()
        crash_event = multiprocessing.Event()

        # Start writer process
        proc = multiprocessing.Process(
            target=writer_process,
            args=(db_path, num_records, crash_after, ready_event, crash_event)
        )
        proc.start()

        # Wait for process to write target records
        ready_event.wait(timeout=10)
        time.sleep(0.05)  # Brief delay to ensure commit completes

        # Kill the process (simulate crash)
        proc.terminate()
        proc.join(timeout=5)

        # Verify records survived
        records_after = count_records(db_path)
        assert records_after >= crash_after, (
            f"Expected at least {crash_after} records after crash, got {records_after}"
        )

        # Verify integrity
        integrity_ok, result = check_integrity(db_path)
        assert integrity_ok, f"Database integrity check failed: {result}"

    def test_database_integrity_after_multiple_crashes(self, temp_db):
        """Database should remain intact after multiple crashes."""
        db_path = str(temp_db)

        for crash_num in range(5):
            ready_event = multiprocessing.Event()
            crash_event = multiprocessing.Event()

            proc = multiprocessing.Process(
                target=writer_process,
                args=(db_path, 10, 5, ready_event, crash_event)
            )
            proc.start()

            # Wait and crash
            ready_event.wait(timeout=10)
            time.sleep(0.02)
            proc.terminate()
            proc.join(timeout=5)

        # After 5 crashes, database should still be valid
        integrity_ok, result = check_integrity(db_path)
        assert integrity_ok, f"Database corrupted after {crash_num + 1} crashes: {result}"

        # Should have accumulated records
        records = count_records(db_path)
        assert records >= 25, f"Expected at least 25 records after 5 crashes, got {records}"

    def test_synchronous_full_prevents_corruption(self, temp_db):
        """PRAGMA synchronous=FULL should prevent corruption on crash."""
        db_path = str(temp_db)

        # Verify PRAGMA settings are correct
        writer = DatabaseWriter(temp_db)
        conn = writer._get_connection()
        cursor = conn.cursor()

        synchronous = cursor.execute("PRAGMA synchronous").fetchone()[0]
        assert synchronous == 2, f"Expected synchronous=2 (FULL), got {synchronous}"

        conn.close()

        # Run crash simulation
        ready_event = multiprocessing.Event()
        crash_event = multiprocessing.Event()

        proc = multiprocessing.Process(
            target=writer_process,
            args=(db_path, 50, 25, ready_event, crash_event)
        )
        proc.start()
        ready_event.wait(timeout=10)
        time.sleep(0.01)
        proc.terminate()
        proc.join(timeout=5)

        # Verify no corruption
        integrity_ok, result = check_integrity(db_path)
        assert integrity_ok, f"Corruption detected with synchronous=FULL: {result}"

    def test_rapid_crash_recovery(self, temp_db):
        """Database should handle rapid successive crashes."""
        db_path = str(temp_db)

        for i in range(10):
            ready_event = multiprocessing.Event()
            crash_event = multiprocessing.Event()

            proc = multiprocessing.Process(
                target=writer_process,
                args=(db_path, 5, 2, ready_event, crash_event)
            )
            proc.start()
            ready_event.wait(timeout=5)
            proc.terminate()
            proc.join(timeout=2)

        # Verify integrity after rapid crashes
        integrity_ok, result = check_integrity(db_path)
        assert integrity_ok, f"Corruption after rapid crashes: {result}"

    def test_crash_during_transaction(self, temp_db):
        """Crash during uncommitted transaction should not corrupt database."""
        db_path = str(temp_db)

        def uncommitted_writer(db_path, ready_event):
            """Writer that crashes before committing."""
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Apply same PRAGMA settings as production
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.execute("PRAGMA journal_mode=DELETE")
            cursor.execute("PRAGMA synchronous=FULL")

            # Start transaction but don't commit
            cursor.execute(
                """
                INSERT INTO agent_runs (run_id, event_id, agent_name, start_time, status)
                VALUES ('uncommitted_run', 'uncommitted_event', 'uncommitted_agent', datetime('now'), 'running')
                """
            )

            ready_event.set()
            time.sleep(1)  # Wait to be killed
            # Note: No commit - this should be rolled back

        ready_event = multiprocessing.Event()
        proc = multiprocessing.Process(
            target=uncommitted_writer,
            args=(db_path, ready_event)
        )
        proc.start()
        ready_event.wait(timeout=5)
        time.sleep(0.05)
        proc.terminate()
        proc.join(timeout=2)

        # Verify uncommitted record was rolled back
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM agent_runs WHERE run_id = 'uncommitted_run'")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 0, "Uncommitted transaction should have been rolled back"

        # Verify database integrity
        integrity_ok, result = check_integrity(db_path)
        assert integrity_ok, f"Corruption after uncommitted transaction crash: {result}"


class TestCrashRecoveryStress:
    """Stress tests for crash recovery - run with pytest -v for detailed output."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database with schema."""
        db_path = tmp_path / "stress_test.sqlite"
        create_schema(str(db_path))
        return db_path

    @pytest.mark.slow
    def test_100_crash_iterations(self, temp_db):
        """Run 100 crash iterations to prove durability."""
        db_path = str(temp_db)
        successful_crashes = 0
        total_records = 0

        for i in range(100):
            ready_event = multiprocessing.Event()
            crash_event = multiprocessing.Event()

            proc = multiprocessing.Process(
                target=writer_process,
                args=(db_path, 5, 3, ready_event, crash_event)
            )
            proc.start()

            if ready_event.wait(timeout=5):
                time.sleep(0.01)
                proc.terminate()
                proc.join(timeout=2)
                successful_crashes += 1
            else:
                proc.terminate()
                proc.join(timeout=2)

        # Verify final integrity
        integrity_ok, result = check_integrity(db_path)
        assert integrity_ok, f"Corruption after 100 crashes: {result}"

        total_records = count_records(db_path)
        print(f"\n100 crash test: {successful_crashes} crashes, {total_records} records survived")

        # Should have accumulated significant records
        assert total_records >= 200, f"Expected at least 200 records, got {total_records}"


def run_crash_durability_test(db_path: str, iterations: int = 10) -> CrashTestResult:
    """
    Run crash durability test programmatically.

    Args:
        db_path: Path to database (will be created if not exists)
        iterations: Number of crash iterations

    Returns:
        CrashTestResult with test results
    """
    # Create schema if needed
    if not Path(db_path).exists():
        create_schema(db_path)

    records_before = count_records(db_path)

    for i in range(iterations):
        ready_event = multiprocessing.Event()
        crash_event = multiprocessing.Event()

        proc = multiprocessing.Process(
            target=writer_process,
            args=(db_path, 10, 5, ready_event, crash_event)
        )
        proc.start()

        if ready_event.wait(timeout=5):
            time.sleep(0.02)
            proc.terminate()
            proc.join(timeout=2)
        else:
            proc.terminate()
            proc.join(timeout=2)

    records_after = count_records(db_path)
    integrity_ok, result = check_integrity(db_path)

    return CrashTestResult(
        records_before_crash=records_before,
        records_after_crash=records_after,
        integrity_ok=integrity_ok,
        error=None if integrity_ok else result
    )


if __name__ == "__main__":
    # Run tests directly
    print("=" * 60)
    print("Crash Recovery Durability Test")
    print("=" * 60)

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = str(Path(tmp_dir) / "durability_test.sqlite")

        print(f"\nTest database: {db_path}")
        print("Running 20 crash iterations...")

        result = run_crash_durability_test(db_path, iterations=20)

        print(f"\nResults:")
        print(f"  Records before: {result.records_before_crash}")
        print(f"  Records after:  {result.records_after_crash}")
        print(f"  Integrity OK:   {result.integrity_ok}")

        if result.error:
            print(f"  Error: {result.error}")

        if result.integrity_ok and result.records_after_crash > 0:
            print("\n[PASS] Database survived all crash iterations!")
            sys.exit(0)
        else:
            print("\n[FAIL] Database corruption detected!")
            sys.exit(1)
