"""
Integration tests for basic telemetry write operations.

Tests verify that TelemetryClient can write to both NDJSON and SQLite,
and that data is consistent between both stores.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

from telemetry import TelemetryClient, TelemetryConfig


@pytest.fixture
def telemetry_client():
    """Create a TelemetryClient with real config."""
    config = TelemetryConfig.from_env()
    return TelemetryClient(config)


def get_ndjson_file_path() -> Path:
    """Get today's NDJSON file path."""
    config = TelemetryConfig.from_env()
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return config.ndjson_dir / f"events_{today}.ndjson"


def read_ndjson_records(run_id: str) -> list:
    """Read NDJSON records for a specific run_id."""
    ndjson_path = get_ndjson_file_path()

    if not ndjson_path.exists():
        return []

    records = []
    with open(ndjson_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                record = json.loads(line)
                if record.get('run_id') == run_id:
                    records.append(record)

    return records


def read_sqlite_record(run_id: str) -> dict:
    """Read a record from SQLite by run_id."""
    config = TelemetryConfig.from_env()
    conn = sqlite3.connect(str(config.database_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()

    conn.close()

    if row:
        return dict(row)
    return None


class TestBasicWrite:
    """Test basic telemetry write operations."""

    def test_basic_ndjson_write(self, telemetry_client):
        """Test that telemetry is written to NDJSON file."""
        # Start and end run
        run_id = telemetry_client.start_run(
            agent_name="test_agent",
            job_type="test_ndjson",
            trigger_type="test"
        )

        telemetry_client.end_run(run_id, status="success")

        # Verify NDJSON file exists
        ndjson_path = get_ndjson_file_path()
        assert ndjson_path.exists(), f"NDJSON file not found: {ndjson_path}"

        # Read NDJSON records
        records = read_ndjson_records(run_id)
        assert len(records) > 0, f"No NDJSON records found for run_id: {run_id}"

        # Verify record content
        record = records[0]  # Get the first record (should be start_run)
        assert record['run_id'] == run_id
        assert record['agent_name'] == "test_agent"
        assert record['job_type'] == "test_ndjson"
        assert 'start_time' in record

    def test_basic_sqlite_write(self, telemetry_client):
        """Test that telemetry is written to SQLite database."""
        # Start and end run
        run_id = telemetry_client.start_run(
            agent_name="test_agent",
            job_type="test_sqlite",
            trigger_type="test"
        )

        telemetry_client.end_run(run_id, status="success")

        # Verify SQLite record exists
        record = read_sqlite_record(run_id)
        assert record is not None, f"No SQLite record found for run_id: {run_id}"

        # Verify record content
        assert record['run_id'] == run_id
        assert record['agent_name'] == "test_agent"
        assert record['job_type'] == "test_sqlite"
        assert record['status'] == "success"
        assert record['start_time'] is not None
        assert record['end_time'] is not None

    def test_dual_write_consistency(self, telemetry_client):
        """Test that data is consistent between NDJSON and SQLite."""
        # Start run
        run_id = telemetry_client.start_run(
            agent_name="test_agent",
            job_type="test_consistency",
            trigger_type="test"
        )

        # End run with metrics
        telemetry_client.end_run(
            run_id,
            status="success",
            items_discovered=10,
            items_succeeded=8,
            items_failed=2
        )

        # Read from both stores
        ndjson_records = read_ndjson_records(run_id)
        sqlite_record = read_sqlite_record(run_id)

        # Verify both exist
        assert len(ndjson_records) > 0, "No NDJSON records"
        assert sqlite_record is not None, "No SQLite record"

        # Find the end_run record in NDJSON (last one)
        end_record = ndjson_records[-1]

        # Verify consistency
        assert end_record['run_id'] == sqlite_record['run_id']
        assert end_record['agent_name'] == sqlite_record['agent_name']
        assert end_record['job_type'] == sqlite_record['job_type']
        assert end_record['status'] == sqlite_record['status']

        # Verify metrics
        assert end_record.get('items_discovered') == sqlite_record['items_discovered'] == 10
        assert end_record.get('items_succeeded') == sqlite_record['items_succeeded'] == 8
        assert end_record.get('items_failed') == sqlite_record['items_failed'] == 2

    def test_write_with_metadata(self, telemetry_client):
        """Test writing telemetry with additional metadata."""
        # Start run with metadata
        run_id = telemetry_client.start_run(
            agent_name="test_agent",
            job_type="test_metadata",
            trigger_type="test",
            agent_owner="test_user",
            session_id="test_session_123"
        )

        telemetry_client.end_run(run_id, status="success")

        # Verify metadata in SQLite
        record = read_sqlite_record(run_id)
        assert record['agent_owner'] == "test_user"
        assert record['session_id'] == "test_session_123"

    def test_write_with_custom_metrics(self, telemetry_client):
        """Test writing custom metrics as JSON."""
        # Start run
        run_id = telemetry_client.start_run(
            agent_name="test_agent",
            job_type="test_custom_metrics",
            trigger_type="test"
        )

        # Add custom metrics
        custom_metrics = {
            "cache_hits": 42,
            "cache_misses": 3,
            "avg_latency_ms": 125.5
        }

        telemetry_client.end_run(
            run_id,
            status="success",
            metrics_json=json.dumps(custom_metrics)
        )

        # Verify custom metrics in SQLite
        record = read_sqlite_record(run_id)
        assert record['metrics_json'] is not None

        stored_metrics = json.loads(record['metrics_json'])
        assert stored_metrics['cache_hits'] == 42
        assert stored_metrics['cache_misses'] == 3
        assert stored_metrics['avg_latency_ms'] == 125.5
