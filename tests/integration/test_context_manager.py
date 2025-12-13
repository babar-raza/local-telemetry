"""
Integration tests for telemetry context manager usage pattern.

Tests verify that the recommended `with client.track_run()` pattern
works correctly for success cases, failures, and edge cases.
"""

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from telemetry import TelemetryClient, TelemetryConfig


@pytest.fixture
def telemetry_client():
    """Create a TelemetryClient with real config."""
    config = TelemetryConfig.from_env()
    return TelemetryClient(config)


def read_sqlite_record(run_id: str) -> dict:
    """Read a record from SQLite by run_id."""
    config = TelemetryConfig.from_env()
    conn = sqlite3.connect(str(config.database_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM agent_runs WHERE run_id = ?", (run_id,))
    row = cursor.fetchone()

    conn.close()

    return dict(row) if row else None


def read_sqlite_events(run_id: str) -> list:
    """Read events from SQLite for a specific run_id."""
    config = TelemetryConfig.from_env()
    conn = sqlite3.connect(str(config.database_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM run_events WHERE run_id = ? ORDER BY timestamp",
        (run_id,)
    )
    rows = cursor.fetchall()

    conn.close()

    return [dict(row) for row in rows]


class TestContextManager:
    """Test context manager usage pattern."""

    def test_context_manager_basic(self, telemetry_client):
        """Test basic context manager usage."""
        run_id = None

        # Use context manager
        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_context_basic"
        ) as run_ctx:
            run_id = run_ctx.run_id
            # Context manager should auto-start the run
            assert run_id is not None

        # After exiting, run should be ended with success
        record = read_sqlite_record(run_id)
        assert record is not None
        assert record['status'] == "success"
        assert record['end_time'] is not None

    def test_context_manager_with_metrics(self, telemetry_client):
        """Test context manager with metrics updates."""
        run_id = None

        # Use context manager with metrics
        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_context_metrics"
        ) as run_ctx:
            run_id = run_ctx.run_id

            # Update metrics via context
            run_ctx.set_metrics(
                items_discovered=100,
                items_succeeded=95,
                items_failed=5
            )

        # Verify metrics written
        record = read_sqlite_record(run_id)
        assert record['items_discovered'] == 100
        assert record['items_succeeded'] == 95
        assert record['items_failed'] == 5

    def test_context_manager_with_events(self, telemetry_client):
        """Test context manager with event logging."""
        run_id = None

        # Use context manager with events
        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_context_events"
        ) as run_ctx:
            run_id = run_ctx.run_id

            # Log events via context
            run_ctx.log_event("start", {"action": "Started processing"})
            run_ctx.log_event("progress", {"step": 50})
            run_ctx.log_event("complete", {"action": "Finished processing"})

        # Events are written to NDJSON only, not to run_events table per TEL-03 design
        # So we just verify the run completed successfully
        record = read_sqlite_record(run_id)
        assert record is not None
        assert record['status'] == "success"

    def test_context_manager_exception_handling(self, telemetry_client):
        """Test that exceptions are caught and status set to failed."""
        run_id = None

        # Use context manager with exception
        with pytest.raises(ValueError):
            with telemetry_client.track_run(
                agent_name="test_agent",
                job_type="test_context_exception"
            ) as run_ctx:
                run_id = run_ctx.run_id

                # Simulate work
                run_ctx.set_metrics(items_discovered=10)

                # Raise exception
                raise ValueError("Simulated error for testing")

        # Verify run ended with failure status
        record = read_sqlite_record(run_id)
        assert record is not None
        assert record['status'] == "failed"
        assert record['error_summary'] is not None
        assert "Simulated error" in record['error_summary']

    def test_context_manager_returns_valid_context(self, telemetry_client):
        """Test that context manager returns valid RunContext."""
        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_context_api"
        ) as run_ctx:
            # Verify context has required attributes
            assert hasattr(run_ctx, 'run_id')
            assert run_ctx.run_id is not None

            # Verify context has required methods
            assert hasattr(run_ctx, 'set_metrics')
            assert hasattr(run_ctx, 'log_event')
            assert callable(run_ctx.set_metrics)
            assert callable(run_ctx.log_event)

    def test_context_manager_with_custom_metrics_json(self, telemetry_client):
        """Test context manager with custom metrics JSON."""
        run_id = None

        custom_metrics = {
            "token_count": 1500,
            "api_calls": 3,
            "cache_hits": 12
        }

        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_context_custom_metrics"
        ) as run_ctx:
            run_id = run_ctx.run_id

            # Update with custom metrics
            run_ctx.set_metrics(
                metrics_json=json.dumps(custom_metrics)
            )

        # Verify custom metrics written
        record = read_sqlite_record(run_id)
        assert record['metrics_json'] is not None

        stored_metrics = json.loads(record['metrics_json'])
        assert stored_metrics['token_count'] == 1500
        assert stored_metrics['api_calls'] == 3
        assert stored_metrics['cache_hits'] == 12

    def test_context_manager_with_insight_relation(self, telemetry_client):
        """Test context manager with insight_id relation."""
        insight_id = f"insight_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        run_id = None

        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_context_relation",
            insight_id=insight_id
        ) as run_ctx:
            run_id = run_ctx.run_id

        # Verify insight_id stored
        record = read_sqlite_record(run_id)
        assert record['insight_id'] == insight_id

    def test_multiple_context_managers_sequential(self, telemetry_client):
        """Test multiple sequential context managers don't interfere."""
        run_ids = []

        # First run
        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_multi_1"
        ) as run_ctx:
            run_ids.append(run_ctx.run_id)

        # Second run
        with telemetry_client.track_run(
            agent_name="test_agent",
            job_type="test_multi_2"
        ) as run_ctx:
            run_ids.append(run_ctx.run_id)

        # Verify both runs completed successfully
        assert len(run_ids) == 2
        assert run_ids[0] != run_ids[1]

        for run_id in run_ids:
            record = read_sqlite_record(run_id)
            assert record is not None
            assert record['status'] == "success"

    def test_context_manager_nested_exception(self, telemetry_client):
        """Test context manager handles nested exceptions gracefully."""
        run_id = None

        with pytest.raises(RuntimeError):
            with telemetry_client.track_run(
                agent_name="test_agent",
                job_type="test_nested_exception"
            ) as run_ctx:
                run_id = run_ctx.run_id

                # Simulate nested work that fails
                try:
                    raise ValueError("Inner error")
                except ValueError as e:
                    # Re-raise as different exception
                    raise RuntimeError(f"Outer error: {e}")

        # Verify run failed with outer exception
        record = read_sqlite_record(run_id)
        assert record['status'] == "failed"
        assert "Outer error" in record['error_summary']
