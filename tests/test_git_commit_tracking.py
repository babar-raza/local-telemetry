"""
Tests for Git Commit Tracking (Schema v6)

Tests cover:
- Schema v4 fields exist in database
- RunRecord accepts git commit fields
- APIPayload includes git commit fields
- DatabaseWriter.associate_commit() method
- Input validation for commit_source and commit_hash
- TelemetryClient.associate_commit() method
"""

import sys
import sqlite3
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.database import DatabaseWriter
from telemetry.models import RunRecord, APIPayload, get_iso8601_timestamp
from telemetry.schema import create_schema, verify_schema, SCHEMA_VERSION


class TestSchemaV6Fields:
    """Test schema has git commit tracking fields."""

    def test_schema_version_is_4(self):
        """Test that SCHEMA_VERSION is 6."""
        assert SCHEMA_VERSION == 6

    def test_schema_has_git_commit_columns(self, tmp_path):
        """Test that schema creates git commit columns."""
        db_path = tmp_path / "test.sqlite"
        success, messages = create_schema(str(db_path))

        assert success is True

        # Check columns exist
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(agent_runs)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "git_commit_hash" in columns
        assert "git_commit_source" in columns
        assert "git_commit_author" in columns
        assert "git_commit_timestamp" in columns

    def test_schema_has_commit_index(self, tmp_path):
        """Test that schema creates idx_runs_commit index."""
        db_path = tmp_path / "test.sqlite"
        success, messages = create_schema(str(db_path))

        assert success is True

        # Check index exists
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_runs_commit'"
        )
        result = cursor.fetchone()
        conn.close()

        assert result is not None, "idx_runs_commit index should exist"

    def test_verify_schema_includes_commit_index(self, tmp_path):
        """Test that verify_schema checks for idx_runs_commit."""
        db_path = tmp_path / "test.sqlite"
        create_schema(str(db_path))

        success, messages = verify_schema(str(db_path))

        assert success is True
        assert any("idx_runs_commit" in msg for msg in messages)


class TestRunRecordGitCommitFields:
    """Test RunRecord dataclass with git commit fields."""

    def test_run_record_has_git_commit_fields(self):
        """Test RunRecord has git commit field attributes."""
        record = RunRecord(
            run_id="test-123",
            agent_name="test",
            job_type="test",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        assert hasattr(record, "git_commit_hash")
        assert hasattr(record, "git_commit_source")
        assert hasattr(record, "git_commit_author")
        assert hasattr(record, "git_commit_timestamp")

    def test_run_record_with_git_commit_values(self):
        """Test RunRecord accepts git commit values."""
        record = RunRecord(
            run_id="test-123",
            agent_name="test",
            job_type="test",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
            git_commit_hash="abc1234567890abcdef",
            git_commit_source="llm",
            git_commit_author="Claude <claude@anthropic.com>",
            git_commit_timestamp="2025-12-15T12:00:00+00:00",
        )

        assert record.git_commit_hash == "abc1234567890abcdef"
        assert record.git_commit_source == "llm"
        assert record.git_commit_author == "Claude <claude@anthropic.com>"
        assert record.git_commit_timestamp == "2025-12-15T12:00:00+00:00"

    def test_run_record_to_dict_includes_git_commit(self):
        """Test RunRecord.to_dict() includes git commit fields."""
        record = RunRecord(
            run_id="test-123",
            agent_name="test",
            job_type="test",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
            git_commit_hash="abc123",
            git_commit_source="manual",
        )

        data = record.to_dict()

        assert "git_commit_hash" in data
        assert "git_commit_source" in data
        assert data["git_commit_hash"] == "abc123"
        assert data["git_commit_source"] == "manual"

    def test_run_record_from_dict_with_git_commit(self):
        """Test RunRecord.from_dict() handles git commit fields."""
        data = {
            "run_id": "test-123",
            "agent_name": "test",
            "job_type": "test",
            "trigger_type": "cli",
            "start_time": "2025-12-15T12:00:00+00:00",
            "status": "success",
            "git_commit_hash": "abc123",
            "git_commit_source": "ci",
            "git_commit_author": "CI Bot",
            "git_commit_timestamp": "2025-12-15T13:00:00+00:00",
        }

        record = RunRecord.from_dict(data)

        assert record.git_commit_hash == "abc123"
        assert record.git_commit_source == "ci"
        assert record.git_commit_author == "CI Bot"


class TestAPIPayloadGitCommitFields:
    """Test APIPayload includes git commit fields."""

    def test_api_payload_has_git_commit_fields(self):
        """Test APIPayload has git commit field attributes."""
        payload = APIPayload(
            run_id="test-123",
            agent_name="test",
            status="success",
        )

        assert hasattr(payload, "git_commit_hash")
        assert hasattr(payload, "git_commit_source")
        assert hasattr(payload, "git_commit_author")
        assert hasattr(payload, "git_commit_timestamp")

    def test_api_payload_from_run_record_with_git_commit(self):
        """Test APIPayload.from_run_record() includes git commit fields."""
        record = RunRecord(
            run_id="test-123",
            agent_name="test",
            job_type="test",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
            git_commit_hash="abc123def456",
            git_commit_source="llm",
            git_commit_author="Claude",
            git_commit_timestamp="2025-12-15T12:00:00+00:00",
        )

        payload = APIPayload.from_run_record(record)

        assert payload.git_commit_hash == "abc123def456"
        assert payload.git_commit_source == "llm"
        assert payload.git_commit_author == "Claude"
        assert payload.git_commit_timestamp == "2025-12-15T12:00:00+00:00"


class TestDatabaseWriterAssociateCommit:
    """Test DatabaseWriter.associate_commit() method."""

    def test_associate_commit_success(self, tmp_path):
        """Test successful commit association."""
        db_path = tmp_path / "test.sqlite"
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert a run
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )
        writer.insert_run(record)

        # Associate commit
        success, message = writer.associate_commit(
            run_id="test-run-123",
            commit_hash="a1b2c3d4e5f6789012345678901234567890abcd",
            commit_source="llm",
            commit_author="Claude <noreply@anthropic.com>",
            commit_timestamp="2025-12-15T12:30:00+00:00",
        )

        assert success is True
        assert "[OK]" in message

        # Verify fields were updated
        updated = writer.get_run("test-run-123")
        assert updated.git_commit_hash == "a1b2c3d4e5f6789012345678901234567890abcd"
        assert updated.git_commit_source == "llm"
        assert updated.git_commit_author == "Claude <noreply@anthropic.com>"
        assert updated.git_commit_timestamp == "2025-12-15T12:30:00+00:00"

    def test_associate_commit_minimal_fields(self, tmp_path):
        """Test commit association with only required fields."""
        db_path = tmp_path / "test.sqlite"
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert a run
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )
        writer.insert_run(record)

        # Associate commit with only required fields
        success, message = writer.associate_commit(
            run_id="test-run-123",
            commit_hash="abc1234",
            commit_source="manual",
        )

        assert success is True

        updated = writer.get_run("test-run-123")
        assert updated.git_commit_hash == "abc1234"
        assert updated.git_commit_source == "manual"
        assert updated.git_commit_author is None
        assert updated.git_commit_timestamp is None

    def test_associate_commit_invalid_source(self, tmp_path):
        """Test commit association with invalid source is rejected."""
        db_path = tmp_path / "test.sqlite"
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert a run
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )
        writer.insert_run(record)

        # Try invalid commit_source
        success, message = writer.associate_commit(
            run_id="test-run-123",
            commit_hash="abc123",
            commit_source="invalid_source",
        )

        assert success is False
        assert "Invalid commit_source" in message

    def test_associate_commit_invalid_hash_format(self, tmp_path):
        """Test commit association with invalid hash format is rejected."""
        db_path = tmp_path / "test.sqlite"
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Insert a run
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )
        writer.insert_run(record)

        # Try invalid commit_hash (not hex)
        success, message = writer.associate_commit(
            run_id="test-run-123",
            commit_hash="not-a-valid-hex-hash!",
            commit_source="manual",
        )

        assert success is False
        assert "Invalid commit_hash" in message

    def test_associate_commit_missing_run(self, tmp_path):
        """Test commit association with non-existent run is rejected."""
        db_path = tmp_path / "test.sqlite"
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        # Try to associate commit to non-existent run
        success, message = writer.associate_commit(
            run_id="nonexistent-run-id",
            commit_hash="abc1234567",
            commit_source="llm",
        )

        assert success is False
        assert "Run not found" in message

    def test_associate_commit_all_valid_sources(self, tmp_path):
        """Test all valid commit_source values work."""
        db_path = tmp_path / "test.sqlite"
        create_schema(str(db_path))

        writer = DatabaseWriter(db_path)

        valid_sources = ["manual", "llm", "ci"]

        for i, source in enumerate(valid_sources):
            # Insert a run
            run_id = f"test-run-{i}"
            record = RunRecord(
                run_id=run_id,
                agent_name="test_agent",
                job_type="test_job",
                trigger_type="cli",
                start_time=get_iso8601_timestamp(),
                status="success",
            )
            writer.insert_run(record)

            # Associate commit with valid source
            success, message = writer.associate_commit(
                run_id=run_id,
                commit_hash=f"abc{i}234567",
                commit_source=source,
            )

            assert success is True, f"Failed for source '{source}': {message}"

            updated = writer.get_run(run_id)
            assert updated.git_commit_source == source


class TestTelemetryClientAssociateCommit:
    """Test TelemetryClient.associate_commit() method."""

    def test_client_has_associate_commit_method(self):
        """Test TelemetryClient has associate_commit method."""
        from telemetry.client import TelemetryClient

        assert hasattr(TelemetryClient, "associate_commit")

    def test_client_associate_commit_signature(self):
        """Test TelemetryClient.associate_commit has correct signature."""
        import inspect
        from telemetry.client import TelemetryClient

        sig = inspect.signature(TelemetryClient.associate_commit)
        params = list(sig.parameters.keys())

        assert "self" in params
        assert "run_id" in params
        assert "commit_hash" in params
        assert "commit_source" in params
        assert "commit_author" in params
        assert "commit_timestamp" in params

    def test_client_associate_commit_integration(self, tmp_path):
        """Test full client integration with associate_commit."""
        from telemetry.client import TelemetryClient
        from telemetry.config import TelemetryConfig

        # Setup
        db_path = tmp_path / "test.sqlite"
        ndjson_dir = tmp_path / "ndjson"
        ndjson_dir.mkdir()
        create_schema(str(db_path))

        config = TelemetryConfig(
            metrics_dir=tmp_path,
            database_path=db_path,
            ndjson_dir=ndjson_dir,
            api_url="http://localhost/test",
            api_token="test-token",
            api_enabled=False,
            agent_owner="test",
            test_mode=True,
        )

        client = TelemetryClient(config)

        # Create a run
        run_id = client.start_run("test-agent", "test-job", trigger_type="cli")
        client.end_run(run_id, status="success")

        # Associate commit
        success, message = client.associate_commit(
            run_id=run_id,
            commit_hash="fedcba9876543210",
            commit_source="llm",
            commit_author="Test Author",
            commit_timestamp="2025-12-15T14:00:00+00:00",
        )

        assert success is True

        # Verify via database
        record = client.database_writer.get_run(run_id)
        assert record.git_commit_hash == "fedcba9876543210"
        assert record.git_commit_source == "llm"


class TestMigrationV3ToV4:
    """Test v3 to v4 migration script."""

    def test_migration_script_exists(self):
        """Test migration script file exists."""
        script_path = Path(__file__).parent.parent / "scripts" / "migrate_v3_to_v4.py"
        assert script_path.exists(), "migrate_v3_to_v4.py should exist"

    def test_migration_function_importable(self):
        """Test migration function can be imported."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from migrate_v3_to_v4 import migrate_v3_to_v4

        assert callable(migrate_v3_to_v4)

    def test_migration_adds_columns(self, tmp_path):
        """Test migration adds git commit columns to v3 database."""
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from migrate_v3_to_v4 import migrate_v3_to_v4

        # Create a v3 database
        db_path = tmp_path / "v3.sqlite"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create minimal v3 schema (without git commit fields)
        cursor.execute(
            """
            CREATE TABLE agent_runs (
                run_id TEXT PRIMARY KEY,
                schema_version INTEGER DEFAULT 3,
                agent_name TEXT NOT NULL,
                start_time TEXT NOT NULL,
                status TEXT,
                product_family TEXT,
                subdomain TEXT
            )
        """
        )
        cursor.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT,
                description TEXT
            )
        """
        )
        cursor.execute(
            "INSERT INTO schema_migrations (version, description) VALUES (3, 'v3')"
        )
        conn.commit()
        conn.close()

        # Run migration
        success, messages = migrate_v3_to_v4(str(db_path), skip_backup=True)

        assert success is True

        # Verify columns added
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(agent_runs)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "git_commit_hash" in columns
        assert "git_commit_source" in columns
        assert "git_commit_author" in columns
        assert "git_commit_timestamp" in columns
