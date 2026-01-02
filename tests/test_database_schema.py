"""
Tests for database schema module.

Verifies that the telemetry database schema can be created correctly.
"""

import os
import sys
import tempfile
import sqlite3
from pathlib import Path

import pytest

# Add src to path for importing telemetry package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry import schema


@pytest.mark.fast
class TestSchemaConstants:
    """Test schema constant definitions."""

    def test_schema_version_defined(self):
        """Schema version should be defined as an integer."""
        assert isinstance(schema.SCHEMA_VERSION, int)
        assert schema.SCHEMA_VERSION >= 1

    def test_tables_defined(self):
        """All required tables should be defined."""
        assert "agent_runs" in schema.TABLES
        assert "run_events" in schema.TABLES
        assert "commits" in schema.TABLES
        assert "schema_migrations" in schema.TABLES

    def test_table_definitions_are_strings(self):
        """Table definitions should be SQL strings."""
        for table_name, table_sql in schema.TABLES.items():
            assert isinstance(table_sql, str)
            assert len(table_sql) > 0
            assert "CREATE TABLE" in table_sql

    def test_indexes_defined(self):
        """Indexes should be defined as a list."""
        assert isinstance(schema.INDEXES, list)
        assert len(schema.INDEXES) >= 6

    def test_index_definitions_are_strings(self):
        """Index definitions should be SQL strings."""
        for index_sql in schema.INDEXES:
            assert isinstance(index_sql, str)
            assert "CREATE INDEX" in index_sql


@pytest.mark.slow
@pytest.mark.requires_db
class TestCreateSchema:
    """Test schema creation function."""

    def test_creates_database_file(self, tmp_path):
        """Should create database file if it doesn't exist."""
        db_path = tmp_path / "test.db"

        success, messages = schema.create_schema(str(db_path))

        assert success
        assert db_path.exists()

    def test_creates_all_tables(self, tmp_path):
        """Should create all required tables."""
        db_path = tmp_path / "test.db"

        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "agent_runs" in tables
        assert "run_events" in tables
        assert "commits" in tables
        assert "schema_migrations" in tables

    def test_creates_all_indexes(self, tmp_path):
        """Should create all required indexes."""
        db_path = tmp_path / "test.db"

        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        indexes = {row[0] for row in cursor.fetchall()}
        conn.close()

        assert "idx_runs_agent" in indexes
        assert "idx_runs_status" in indexes
        assert "idx_runs_start" in indexes
        assert "idx_runs_api_posted" in indexes
        assert "idx_events_run" in indexes
        assert "idx_commits_run" in indexes

    def test_enables_delete_mode(self, tmp_path):
        """Should enable DELETE mode for Docker volume compatibility."""
        db_path = tmp_path / "test.db"

        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        conn.close()

        assert journal_mode.lower() == "delete"

    def test_records_schema_version(self, tmp_path):
        """Should record schema version in migrations table."""
        db_path = tmp_path / "test.db"

        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT version, description FROM schema_migrations")
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == schema.SCHEMA_VERSION
        assert "Initial schema" in result[1]

    def test_idempotent_execution(self, tmp_path):
        """Should be safe to run multiple times."""
        db_path = tmp_path / "test.db"

        # First run
        success1, messages1 = schema.create_schema(str(db_path))
        assert success1

        # Second run
        success2, messages2 = schema.create_schema(str(db_path))
        assert success2

        # Database should still be valid
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        conn.close()

        assert len(tables) >= 4

    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories if they don't exist."""
        db_path = tmp_path / "nested" / "path" / "test.db"

        success, messages = schema.create_schema(str(db_path))

        assert success
        assert db_path.exists()
        assert db_path.parent.exists()

    def test_returns_informative_messages(self, tmp_path):
        """Should return informative messages about creation."""
        db_path = tmp_path / "test.db"

        success, messages = schema.create_schema(str(db_path))

        assert success
        assert len(messages) > 0
        assert any("journal mode" in msg.lower() for msg in messages)
        assert any("table" in msg.lower() for msg in messages)
        assert any("index" in msg.lower() for msg in messages)


@pytest.mark.slow
@pytest.mark.requires_db
class TestGetSchemaVersion:
    """Test schema version retrieval."""

    def test_returns_zero_for_nonexistent_database(self, tmp_path):
        """Should return 0 for database that doesn't exist."""
        db_path = tmp_path / "nonexistent.db"

        version = schema.get_schema_version(str(db_path))

        assert version == 0

    def test_returns_correct_version(self, tmp_path):
        """Should return correct schema version from database."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        version = schema.get_schema_version(str(db_path))

        assert version == schema.SCHEMA_VERSION

    def test_returns_zero_for_empty_database(self, tmp_path):
        """Should return 0 for database without migrations table."""
        db_path = tmp_path / "empty.db"

        # Create empty database
        conn = sqlite3.connect(db_path)
        conn.close()

        version = schema.get_schema_version(str(db_path))

        assert version == 0


@pytest.mark.slow
@pytest.mark.requires_db
class TestVerifySchema:
    """Test schema verification function."""

    def test_fails_for_nonexistent_database(self, tmp_path):
        """Should fail if database doesn't exist."""
        db_path = tmp_path / "nonexistent.db"

        success, messages = schema.verify_schema(str(db_path))

        assert not success
        assert any("does not exist" in msg for msg in messages)

    def test_passes_for_valid_schema(self, tmp_path):
        """Should pass for correctly created schema."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        success, messages = schema.verify_schema(str(db_path))

        assert success
        assert all("[OK]" in msg or "[ok]" in msg.lower() for msg in messages)

    def test_checks_all_tables(self, tmp_path):
        """Should check for all required tables."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        success, messages = schema.verify_schema(str(db_path))

        assert success
        assert any("agent_runs" in msg for msg in messages)
        assert any("run_events" in msg for msg in messages)
        assert any("commits" in msg for msg in messages)
        assert any("schema_migrations" in msg for msg in messages)

    def test_checks_all_indexes(self, tmp_path):
        """Should check for all required indexes."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        success, messages = schema.verify_schema(str(db_path))

        assert success
        assert any("idx_runs_agent" in msg for msg in messages)
        assert any("idx_runs_status" in msg for msg in messages)
        assert any("idx_runs_start" in msg for msg in messages)

    def test_checks_delete_mode(self, tmp_path):
        """Should check that DELETE mode is enabled."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        success, messages = schema.verify_schema(str(db_path))

        assert success
        assert any("journal mode" in msg.lower() for msg in messages)

    def test_checks_schema_version(self, tmp_path):
        """Should check schema version matches expected."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        success, messages = schema.verify_schema(str(db_path))

        assert success
        assert any(f"version: {schema.SCHEMA_VERSION}" in msg.lower() for msg in messages)

    def test_fails_for_missing_table(self, tmp_path):
        """Should fail if a required table is missing."""
        db_path = tmp_path / "incomplete.db"

        # Create database with only some tables
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(schema.TABLES["agent_runs"])
        conn.commit()
        conn.close()

        success, messages = schema.verify_schema(str(db_path))

        assert not success


@pytest.mark.fast
class TestExportSchemaSql:
    """Test schema SQL export function."""

    def test_creates_sql_file(self, tmp_path):
        """Should create SQL file at specified path."""
        output_path = tmp_path / "schema.sql"

        success, message = schema.export_schema_sql(str(output_path))

        assert success
        assert output_path.exists()

    def test_sql_file_contains_tables(self, tmp_path):
        """SQL file should contain all table definitions."""
        output_path = tmp_path / "schema.sql"

        schema.export_schema_sql(str(output_path))

        content = output_path.read_text(encoding="utf-8")

        assert "CREATE TABLE" in content
        assert "agent_runs" in content
        assert "run_events" in content
        assert "commits" in content
        assert "schema_migrations" in content

    def test_sql_file_contains_indexes(self, tmp_path):
        """SQL file should contain all index definitions."""
        output_path = tmp_path / "schema.sql"

        schema.export_schema_sql(str(output_path))

        content = output_path.read_text(encoding="utf-8")

        assert "CREATE INDEX" in content
        assert "idx_runs_agent" in content
        assert "idx_runs_status" in content

    def test_sql_file_contains_version(self, tmp_path):
        """SQL file should contain schema version."""
        output_path = tmp_path / "schema.sql"

        schema.export_schema_sql(str(output_path))

        content = output_path.read_text(encoding="utf-8")

        assert f"Version: {schema.SCHEMA_VERSION}" in content

    def test_sql_file_contains_delete_pragma(self, tmp_path):
        """SQL file should enable DELETE mode."""
        output_path = tmp_path / "schema.sql"

        schema.export_schema_sql(str(output_path))

        content = output_path.read_text(encoding="utf-8")

        assert "PRAGMA journal_mode=DELETE" in content

    def test_creates_parent_directories(self, tmp_path):
        """Should create parent directories if needed."""
        output_path = tmp_path / "nested" / "path" / "schema.sql"

        success, message = schema.export_schema_sql(str(output_path))

        assert success
        assert output_path.exists()

    def test_sql_file_is_valid(self, tmp_path):
        """Exported SQL should be valid and executable."""
        sql_path = tmp_path / "schema.sql"
        db_path = tmp_path / "test_from_export.db"

        # Export schema
        schema.export_schema_sql(str(sql_path))

        # Read SQL
        sql_content = sql_path.read_text(encoding="utf-8")

        # Execute SQL to create database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.executescript(sql_content)
        conn.commit()

        # Verify tables were created
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        conn.close()

        assert "agent_runs" in tables
        assert "run_events" in tables
        assert "commits" in tables


@pytest.mark.slow
@pytest.mark.requires_db
class TestSchemaConstraints:
    """Test that schema constraints work correctly."""

    def test_agent_runs_primary_key(self, tmp_path):
        """run_id should be primary key in agent_runs."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Insert first row
        cursor.execute(
            "INSERT INTO agent_runs (run_id, agent_name, start_time) VALUES (?, ?, ?)",
            ("test_run_1", "test_agent", "2025-12-10T00:00:00Z"),
        )

        # Try to insert duplicate run_id - should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO agent_runs (run_id, agent_name, start_time) VALUES (?, ?, ?)",
                ("test_run_1", "test_agent", "2025-12-10T00:00:00Z"),
            )

        conn.close()

    def test_trigger_type_constraint(self, tmp_path):
        """trigger_type should only accept valid values."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Valid trigger types should work
        for trigger_type in ["cli", "web", "scheduler", "mcp", "manual"]:
            cursor.execute(
                "INSERT INTO agent_runs (run_id, agent_name, start_time, trigger_type) VALUES (?, ?, ?, ?)",
                (f"run_{trigger_type}", "test_agent", "2025-12-10T00:00:00Z", trigger_type),
            )

        # Invalid trigger type should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO agent_runs (run_id, agent_name, start_time, trigger_type) VALUES (?, ?, ?, ?)",
                ("run_invalid", "test_agent", "2025-12-10T00:00:00Z", "invalid_type"),
            )

        conn.close()

    def test_status_constraint(self, tmp_path):
        """status should only accept valid values."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Valid statuses should work
        for status in ["running", "success", "failed", "partial"]:
            cursor.execute(
                "INSERT INTO agent_runs (run_id, agent_name, start_time, status) VALUES (?, ?, ?, ?)",
                (f"run_{status}", "test_agent", "2025-12-10T00:00:00Z", status),
            )

        # Invalid status should fail
        with pytest.raises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO agent_runs (run_id, agent_name, start_time, status) VALUES (?, ?, ?, ?)",
                ("run_invalid", "test_agent", "2025-12-10T00:00:00Z", "invalid_status"),
            )

        conn.close()


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.requires_db
class TestIntegration:
    """Integration tests for full workflow."""

    def test_create_verify_export_workflow(self, tmp_path):
        """Test complete workflow: create, verify, export."""
        db_path = tmp_path / "telemetry.db"
        sql_path = tmp_path / "schema.sql"

        # Create schema
        success, messages = schema.create_schema(str(db_path))
        assert success

        # Verify schema
        success, messages = schema.verify_schema(str(db_path))
        assert success

        # Export schema
        success, message = schema.export_schema_sql(str(sql_path))
        assert success

        # All files should exist
        assert db_path.exists()
        assert sql_path.exists()

    def test_schema_supports_basic_operations(self, tmp_path):
        """Test that schema supports basic insert/select operations."""
        db_path = tmp_path / "test.db"
        schema.create_schema(str(db_path))

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Insert into agent_runs
        cursor.execute(
            """
            INSERT INTO agent_runs (run_id, agent_name, start_time, status)
            VALUES (?, ?, ?, ?)
            """,
            ("test_run_1", "test_agent", "2025-12-10T00:00:00Z", "success"),
        )

        # Insert into run_events
        cursor.execute(
            """
            INSERT INTO run_events (run_id, event_type, timestamp)
            VALUES (?, ?, ?)
            """,
            ("test_run_1", "checkpoint", "2025-12-10T00:01:00Z"),
        )

        # Insert into commits
        cursor.execute(
            """
            INSERT INTO commits (commit_hash, run_id, agent_name)
            VALUES (?, ?, ?)
            """,
            ("abc123", "test_run_1", "test_agent"),
        )

        conn.commit()

        # Query data
        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT COUNT(*) FROM run_events")
        assert cursor.fetchone()[0] == 1

        cursor.execute("SELECT COUNT(*) FROM commits")
        assert cursor.fetchone()[0] == 1

        conn.close()


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
