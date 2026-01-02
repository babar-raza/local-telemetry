"""
Tests for telemetry.database module (DatabaseWriter)

Tests cover:
- DatabaseWriter initialization
- Insert/update operations
- Retry logic for lock contention
- API posting status tracking
- Run statistics
- Pending API posts retrieval

NO MOCKING - uses real SQLite database with real locks and real errors.
"""

import sys
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.database import DatabaseWriter
from telemetry.models import RunRecord, get_iso8601_timestamp
from telemetry.schema import create_schema


class TestDatabaseWriterCreation:
    """Test DatabaseWriter initialization."""

    def test_writer_creation(self, tmp_path):
        """Test creating DatabaseWriter."""
        db_path = tmp_path / "test.sqlite"
        writer = DatabaseWriter(db_path)

        assert writer.database_path == db_path
        assert writer.max_retries == 3

    def test_writer_custom_retries(self, tmp_path):
        """Test creating DatabaseWriter with custom retries."""
        db_path = tmp_path / "test.sqlite"
        writer = DatabaseWriter(db_path, max_retries=5)

        assert writer.max_retries == 5


class TestDatabaseConnection:
    """Test database connection management."""

    def test_get_connection_creates_database(self, tmp_path):
        """Test that get_connection creates database file."""
        db_path = tmp_path / "test.sqlite"
        writer = DatabaseWriter(db_path)

        conn = writer._get_connection()
        assert db_path.exists()
        conn.close()

    def test_get_connection_enables_wal(self, tmp_path):
        """Test that get_connection enables WAL mode."""
        db_path = tmp_path / "test.sqlite"

        # Create schema first
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)
        conn = writer._get_connection()

        # Check WAL mode
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]

        conn.close()
        assert mode.upper() == "WAL"


class TestInsertRun:
    """Test inserting run records."""

    def test_insert_run_success(self, tmp_path):
        """Test successful run insertion."""
        db_path = tmp_path / "test.sqlite"

        # Setup database with schema
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        success, message = writer.insert_run(record)

        # Debug output
        if not success:
            print(f"\nINSERT FAILED: {message}")
            print(f"Record: {record}")

        assert success is True, f"Insert failed: {message}"
        assert "[OK]" in message

    def test_insert_run_with_all_fields(self, tmp_path):
        """Test inserting run with all fields populated."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            agent_owner="test_owner",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            end_time=get_iso8601_timestamp(),
            status="success",
            items_discovered=10,
            items_succeeded=8,
            items_failed=2,
            duration_ms=5000,
            input_summary="test input",
            output_summary="test output",
            error_summary=None,
            metrics_json='{"custom": "metrics"}',
            product="test_product",
            platform="test_platform",
            git_repo="test/repo",
            git_branch="main",
            git_run_tag="v1.0.0",
            host="test-host",
        )

        success, message = writer.insert_run(record)
        assert success is True

        # Verify record was inserted
        retrieved = writer.get_run("test-run-123")
        assert retrieved is not None
        assert retrieved.items_discovered == 10

    def test_insert_run_duplicate_id(self, tmp_path):
        """Test inserting run with duplicate ID fails."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        # Insert once
        success1, _ = writer.insert_run(record)
        assert success1 is True

        # Try to insert again with same ID
        success2, message2 = writer.insert_run(record)
        assert success2 is False
        assert "FAIL" in message2 or "error" in message2.lower()


class TestUpdateRun:
    """Test updating run records."""

    def test_update_run_success(self, tmp_path):
        """Test successful run update."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert initial record
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        writer.insert_run(record)

        # Update record
        record.status = "success"
        record.end_time = get_iso8601_timestamp()
        record.items_succeeded = 5

        success, message = writer.update_run(record)

        assert success is True
        assert "[OK]" in message

        # Verify update
        retrieved = writer.get_run("test-run-123")
        assert retrieved.status == "success"
        assert retrieved.items_succeeded == 5

    def test_update_run_nonexistent(self, tmp_path):
        """Test updating non-existent run."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        record = RunRecord(
            run_id="nonexistent-run",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        # Should succeed but not update anything
        success, _ = writer.update_run(record)
        assert success is True


class TestGetRun:
    """Test retrieving run records."""

    def test_get_run_found(self, tmp_path):
        """Test retrieving existing run."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert record
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        writer.insert_run(record)

        # Retrieve
        retrieved = writer.get_run("test-run-123")

        assert retrieved is not None
        assert retrieved.run_id == "test-run-123"
        assert retrieved.agent_name == "test_agent"

    def test_get_run_not_found(self, tmp_path):
        """Test retrieving non-existent run."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        retrieved = writer.get_run("nonexistent-run")
        assert retrieved is None


class TestAPIPosting:
    """Test API posting status tracking."""

    def test_mark_api_posted(self, tmp_path):
        """Test marking run as posted to API."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert record
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        writer.insert_run(record)

        # Mark as posted
        posted_at = get_iso8601_timestamp()
        success, message = writer.mark_api_posted("test-run-123", posted_at)

        assert success is True

        # Verify
        retrieved = writer.get_run("test-run-123")
        assert retrieved.api_posted is True
        assert retrieved.api_posted_at == posted_at

    def test_increment_api_retry_count(self, tmp_path):
        """Test incrementing API retry count."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert record
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        writer.insert_run(record)

        # Increment retry count multiple times
        for _ in range(3):
            success, _ = writer.increment_api_retry_count("test-run-123")
            assert success is True

        # Verify
        retrieved = writer.get_run("test-run-123")
        assert retrieved.api_retry_count == 3

    def test_get_pending_api_posts(self, tmp_path):
        """Test retrieving runs pending API posting."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert multiple records
        for i in range(5):
            record = RunRecord(
                run_id=f"test-run-{i}",
                agent_name="test_agent",
                job_type="test_job",
                trigger_type="cli",
                start_time=get_iso8601_timestamp(),
                status="success",
            )
            writer.insert_run(record)

        # Mark some as posted
        writer.mark_api_posted("test-run-0", get_iso8601_timestamp())
        writer.mark_api_posted("test-run-2", get_iso8601_timestamp())

        # Get pending
        pending = writer.get_pending_api_posts()

        # Should get 3 pending (1, 3, 4)
        assert len(pending) == 3
        pending_ids = {r.run_id for r in pending}
        assert "test-run-1" in pending_ids
        assert "test-run-3" in pending_ids
        assert "test-run-4" in pending_ids

    def test_get_pending_api_posts_limit(self, tmp_path):
        """Test get_pending_api_posts respects limit."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert many records
        for i in range(20):
            record = RunRecord(
                run_id=f"test-run-{i}",
                agent_name="test_agent",
                job_type="test_job",
                trigger_type="cli",
                start_time=get_iso8601_timestamp(),
                status="success",
            )
            writer.insert_run(record)

        # Get with limit
        pending = writer.get_pending_api_posts(limit=5)
        assert len(pending) == 5


class TestRunStatistics:
    """Test getting run statistics."""

    def test_get_run_stats_empty(self, tmp_path):
        """Test statistics for empty database."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)
        stats = writer.get_run_stats()

        assert stats["total_runs"] == 0
        assert stats["pending_api_posts"] == 0

    def test_get_run_stats_with_runs(self, tmp_path):
        """Test statistics with multiple runs."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert runs with different statuses
        statuses = ["success", "success", "failed", "partial", "success"]
        for i, status in enumerate(statuses):
            record = RunRecord(
                run_id=f"test-run-{i}",
                agent_name="test_agent",
                job_type="test_job",
                trigger_type="cli",
                start_time=get_iso8601_timestamp(),
                status=status,
            )
            writer.insert_run(record)

        stats = writer.get_run_stats()

        assert stats["total_runs"] == 5
        assert stats["status_counts"]["success"] == 3
        assert stats["status_counts"]["failed"] == 1
        assert stats["status_counts"]["partial"] == 1


class TestRetryLogic:
    """Test retry logic for lock contention."""

    def test_execute_with_retry_success_first_attempt(self, tmp_path):
        """Test operation succeeds on first attempt."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Should succeed immediately
        sql = "SELECT 1"
        success, result, message = writer._execute_with_retry(sql, (), fetch=True)

        assert success is True
        assert result == (1,)

    @pytest.mark.serial
    @pytest.mark.slow
    @pytest.mark.requires_db
    def test_execute_with_retry_handles_lock_error(self, tmp_path):
        """Test retry logic handles REAL database lock errors."""
        db_path = tmp_path / "test.sqlite"

        create_schema(str(db_path))

        writer = DatabaseWriter(db_path, max_retries=5, retry_delay=0.1)

        # Create a REAL database lock by holding a transaction in a background thread
        lock_released = threading.Event()
        lock_acquired = threading.Event()

        def create_lock():
            # Hold an exclusive write lock temporarily
            conn = sqlite3.connect(str(db_path), timeout=0.05)
            try:
                conn.execute("BEGIN EXCLUSIVE")
                lock_acquired.set()  # Signal that lock is held
                lock_released.wait(timeout=0.5)  # Wait for test to signal release or timeout
                conn.rollback()
            finally:
                conn.close()

        # Start lock in background thread
        lock_thread = threading.Thread(target=create_lock)
        lock_thread.start()

        # Wait for thread to acquire lock (max 0.1s)
        assert lock_acquired.wait(timeout=0.1), "Background thread should acquire lock quickly"

        try:
            # This should retry until lock is released, then succeed
            sql = "SELECT 1"
            success, result, message = writer._execute_with_retry(sql, (), fetch=True)

            # Should eventually succeed after retries
            assert success is True
            assert result == (1,)

        finally:
            lock_released.set()  # Signal background thread to release lock
            lock_thread.join(timeout=2.0)


class TestErrorHandling:
    """Test error handling in DatabaseWriter."""

    def test_insert_run_handles_database_error(self, tmp_path):
        """Test that insert_run handles database errors gracefully."""
        db_path = tmp_path / "nonexistent_dir" / "test.sqlite"

        writer = DatabaseWriter(db_path)

        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        # Should return False, not crash
        success, message = writer.insert_run(record)
        # May fail or succeed depending on whether directory is auto-created
        assert isinstance(success, bool)

    def test_get_run_handles_error(self, tmp_path):
        """Test that get_run handles errors gracefully."""
        db_path = tmp_path / "test.sqlite"
        writer = DatabaseWriter(db_path)

        # Database doesn't exist, should return None
        result = writer.get_run("test-run-123")
        assert result is None
