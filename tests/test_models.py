"""
Tests for telemetry.models module

Tests cover:
- RunRecord creation and validation
- RunEvent creation and validation
- APIPayload creation and validation
- Helper functions (generate_run_id, get_iso8601_timestamp, calculate_duration_ms)
- Serialization/deserialization (to_dict, from_dict)
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.models import (
    RunRecord,
    RunEvent,
    APIPayload,
    generate_run_id,
    get_iso8601_timestamp,
    calculate_duration_ms,
    SCHEMA_VERSION,
)


class TestHelperFunctions:
    """Test helper functions."""

    def test_generate_run_id_format(self):
        """Test run ID format is correct."""
        agent_name = "test_agent"
        run_id = generate_run_id(agent_name)

        # Format: {YYYYMMDD}T{HHMMSS}Z-{agent_name}-{uuid8}
        parts = run_id.split("-")
        assert len(parts) >= 3
        assert parts[1] == agent_name
        assert len(parts[2]) == 8  # UUID short is 8 chars

        # Timestamp part should be parseable
        timestamp_part = parts[0]
        assert timestamp_part.endswith("Z")
        assert "T" in timestamp_part

    def test_generate_run_id_unique(self):
        """Test that generated run IDs are unique."""
        agent_name = "test_agent"
        ids = [generate_run_id(agent_name) for _ in range(100)]

        # All should be unique
        assert len(set(ids)) == 100

    def test_get_iso8601_timestamp_format(self):
        """Test ISO8601 timestamp format."""
        ts = get_iso8601_timestamp()

        # Should end with +00:00 (UTC)
        assert ts.endswith("+00:00")

        # Should be parseable
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None

    def test_calculate_duration_ms_valid(self):
        """Test duration calculation with valid timestamps."""
        start = "2025-12-10T10:00:00.000000+00:00"
        end = "2025-12-10T10:00:05.000000+00:00"

        duration = calculate_duration_ms(start, end)
        assert duration == 5000  # 5 seconds

    def test_calculate_duration_ms_subsecond(self):
        """Test duration calculation with subsecond precision."""
        start = "2025-12-10T10:00:00.000000+00:00"
        end = "2025-12-10T10:00:00.500000+00:00"

        duration = calculate_duration_ms(start, end)
        assert duration == 500  # 500 milliseconds

    def test_calculate_duration_ms_invalid_start(self):
        """Test duration calculation with invalid start time."""
        with pytest.raises(ValueError):
            calculate_duration_ms("invalid", "2025-12-10T10:00:05.000000+00:00")

    def test_calculate_duration_ms_invalid_end(self):
        """Test duration calculation with invalid end time."""
        with pytest.raises(ValueError):
            calculate_duration_ms("2025-12-10T10:00:00.000000+00:00", "invalid")

    def test_calculate_duration_ms_negative(self):
        """Test duration calculation when end is before start."""
        start = "2025-12-10T10:00:05.000000+00:00"
        end = "2025-12-10T10:00:00.000000+00:00"

        duration = calculate_duration_ms(start, end)
        assert duration == -5000  # Negative duration


class TestRunRecord:
    """Test RunRecord dataclass."""

    def test_run_record_creation_minimal(self):
        """Test creating RunRecord with minimal required fields."""
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        assert record.run_id == "test-run-123"
        assert record.agent_name == "test_agent"
        assert record.schema_version == 1

    def test_run_record_creation_full(self):
        """Test creating RunRecord with all fields."""
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

        assert record.items_discovered == 10
        assert record.items_succeeded == 8
        assert record.items_failed == 2

    def test_run_record_to_dict(self):
        """Test RunRecord to_dict serialization."""
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        data = record.to_dict()
        assert isinstance(data, dict)
        assert data["run_id"] == "test-run-123"
        assert data["schema_version"] == 1
        assert data["record_type"] == "run"

    def test_run_record_from_dict(self):
        """Test RunRecord from_dict deserialization."""
        data = {
            "run_id": "test-run-123",
            "schema_version": 1,
            "agent_name": "test_agent",
            "job_type": "test_job",
            "trigger_type": "cli",
            "start_time": get_iso8601_timestamp(),
            "status": "running",
            "record_type": "run",
        }

        record = RunRecord.from_dict(data)
        assert record.run_id == "test-run-123"
        assert record.agent_name == "test_agent"

    def test_run_record_roundtrip(self):
        """Test RunRecord serialization roundtrip."""
        original = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
            items_discovered=5,
        )

        data = original.to_dict()
        restored = RunRecord.from_dict(data)

        assert restored.run_id == original.run_id
        assert restored.items_discovered == original.items_discovered


class TestRunEvent:
    """Test RunEvent dataclass."""

    def test_run_event_creation_minimal(self):
        """Test creating RunEvent with minimal fields."""
        event = RunEvent(
            run_id="test-run-123",
            event_type="checkpoint",
            timestamp=get_iso8601_timestamp(),
        )

        assert event.run_id == "test-run-123"
        assert event.event_type == "checkpoint"
        assert event.payload_json is None

    def test_run_event_creation_with_payload(self):
        """Test creating RunEvent with payload."""
        payload = {"step": 1, "status": "ok"}
        event = RunEvent(
            run_id="test-run-123",
            event_type="checkpoint",
            timestamp=get_iso8601_timestamp(),
            payload_json=json.dumps(payload),
        )

        assert event.payload_json is not None
        restored_payload = json.loads(event.payload_json)
        assert restored_payload["step"] == 1

    def test_run_event_to_dict(self):
        """Test RunEvent to_dict serialization."""
        event = RunEvent(
            run_id="test-run-123",
            event_type="checkpoint",
            timestamp=get_iso8601_timestamp(),
        )

        data = event.to_dict()
        assert isinstance(data, dict)
        assert data["run_id"] == "test-run-123"
        assert data["record_type"] == "event"

    def test_run_event_from_dict(self):
        """Test RunEvent from_dict deserialization."""
        data = {
            "run_id": "test-run-123",
            "event_type": "checkpoint",
            "timestamp": get_iso8601_timestamp(),
            "payload_json": '{"step": 1}',
            "record_type": "event",
        }

        event = RunEvent.from_dict(data)
        assert event.run_id == "test-run-123"
        assert event.event_type == "checkpoint"


class TestAPIPayload:
    """Test APIPayload dataclass."""

    def test_api_payload_creation_minimal(self):
        """Test creating APIPayload with minimal fields."""
        payload = APIPayload(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        assert payload.run_id == "test-run-123"
        assert payload.agent_name == "test_agent"

    def test_api_payload_from_run_record(self):
        """Test creating APIPayload from RunRecord."""
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
            product="test_product",
        )

        payload = APIPayload.from_run_record(record)
        assert payload.run_id == record.run_id
        assert payload.agent_name == record.agent_name
        assert payload.items_discovered == 10

    def test_api_payload_to_dict(self):
        """Test APIPayload to_dict serialization."""
        payload = APIPayload(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        data = payload.to_dict()
        assert isinstance(data, dict)
        assert data["run_id"] == "test-run-123"

    def test_api_payload_to_dict_excludes_none(self):
        """Test that to_dict excludes None values."""
        payload = APIPayload(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
            end_time=None,  # Should be excluded
            error_summary=None,  # Should be excluded
        )

        data = payload.to_dict()
        assert "end_time" not in data
        assert "error_summary" not in data


class TestSchemaVersion:
    """Test schema version constant."""

    def test_schema_version_value(self):
        """Test that SCHEMA_VERSION is set correctly."""
        assert SCHEMA_VERSION == 1

    def test_schema_version_in_run_record(self):
        """Test that RunRecord uses SCHEMA_VERSION."""
        record = RunRecord(
            run_id="test-run-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="running",
        )

        assert record.schema_version == SCHEMA_VERSION
