"""
Integration test for production database PRAGMA settings.

Tests the actual production database (read-only) to verify PRAGMA settings
are correctly applied and persisted.

Usage:
    pytest tests/integration/test_production_pragma.py -v
"""

import sys
import sqlite3
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from telemetry.database import DatabaseWriter
from telemetry import TelemetryClient
from telemetry.config import TelemetryConfig


def test_production_database_exists():
    """Verify production database file exists."""
    config = TelemetryConfig.from_env()
    db_path = config.database_path

    assert db_path.exists(), f"Production database not found at {db_path}"
    assert db_path.stat().st_size > 0, "Production database is empty"


def test_production_pragma_settings_via_database_writer():
    """Test PRAGMA settings via DatabaseWriter with production database."""
    config = TelemetryConfig.from_env()
    db_path = config.database_path

    if not db_path.exists():
        pytest.skip(f"Production database not found at {db_path}")

    # Use DatabaseWriter to get connection (applies our PRAGMA settings)
    writer = DatabaseWriter(db_path)
    conn = writer._get_connection()
    cursor = conn.cursor()

    try:
        # Verify all PRAGMA settings
        busy_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()[0]
        assert busy_timeout == 30000, f"busy_timeout is {busy_timeout}, expected 30000"

        journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "delete", f"journal_mode is {journal_mode}, expected DELETE"

        synchronous = cursor.execute("PRAGMA synchronous").fetchone()[0]
        assert synchronous == 2, f"synchronous is {synchronous}, expected 2 (FULL)"

        wal_autocheckpoint = cursor.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
        assert wal_autocheckpoint == 100, f"wal_autocheckpoint is {wal_autocheckpoint}, expected 100"

    finally:
        conn.close()


def test_production_pragma_settings_via_telemetry_client():
    """Test PRAGMA settings via TelemetryClient with production database."""
    config = TelemetryConfig.from_env()
    db_path = config.database_path

    if not db_path.exists():
        pytest.skip(f"Production database not found at {db_path}")

    # Use TelemetryClient (which uses DatabaseWriter internally)
    try:
        client = TelemetryClient()
        conn = client.database_writer._get_connection()
        cursor = conn.cursor()

        try:
            # Verify all PRAGMA settings
            busy_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()[0]
            assert busy_timeout == 30000, f"busy_timeout is {busy_timeout}, expected 30000"

            journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()[0]
            assert journal_mode.lower() == "delete", f"journal_mode is {journal_mode}, expected DELETE"

            synchronous = cursor.execute("PRAGMA synchronous").fetchone()[0]
            assert synchronous == 2, f"synchronous is {synchronous}, expected 2 (FULL)"

            wal_autocheckpoint = cursor.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
            assert wal_autocheckpoint == 100, f"wal_autocheckpoint is {wal_autocheckpoint}, expected 100"

        finally:
            conn.close()

    except Exception as e:
        pytest.fail(f"TelemetryClient initialization failed: {e}")


def test_production_database_integrity():
    """Verify production database integrity (read-only check)."""
    config = TelemetryConfig.from_env()
    db_path = config.database_path

    if not db_path.exists():
        pytest.skip(f"Production database not found at {db_path}")

    # Connect and run integrity check (read-only)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()

    try:
        result = cursor.execute("PRAGMA integrity_check").fetchone()[0]
        assert result == "ok", f"Database integrity check failed: {result}"
    finally:
        conn.close()


def test_production_database_statistics():
    """Gather statistics from production database (read-only)."""
    config = TelemetryConfig.from_env()
    db_path = config.database_path

    if not db_path.exists():
        pytest.skip(f"Production database not found at {db_path}")

    # Connect read-only
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()

    try:
        # Get table count
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()

        assert len(tables) > 0, "No tables found in production database"

        # Get row count from main table (if exists)
        if any(t[0] == 'runs' for t in tables):
            row_count = cursor.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            print(f"\nProduction database statistics:")
            print(f"  Tables: {len(tables)}")
            print(f"  Runs: {row_count}")
            print(f"  Size: {db_path.stat().st_size / 1024 / 1024:.2f} MB")

    finally:
        conn.close()


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])
