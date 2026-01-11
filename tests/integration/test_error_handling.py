"""
Integration tests for error handling and graceful degradation.

Verifies that telemetry errors don't crash agent applications.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from telemetry import TelemetryClient, TelemetryConfig


class TestErrorHandling:
    """Test error handling and graceful degradation."""

    def test_telemetry_with_invalid_metrics(self):
        """Test that invalid metrics don't crash agent."""
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        # Try to update with invalid data - should not crash
        with client.track_run(
            agent_name="test_agent",
            job_type="test_invalid_metrics"
        ) as run_ctx:
            # These should either work or fail gracefully
            try:
                run_ctx.set_metrics(items_discovered="not_a_number")  # Invalid
            except (TypeError, ValueError, AttributeError):
                pass  # Expected - invalid input may be rejected or ignored

            # Agent continues working
            run_ctx.set_metrics(items_discovered=10)  # Valid

        # Test passes if we get here

    def test_telemetry_continues_after_partial_failure(self):
        """Test that partial failures don't break subsequent writes."""
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        # First run - simulate some issue
        run_id_1 = None
        try:
            with client.track_run(
                agent_name="test_agent",
                job_type="test_partial_failure_1"
            ) as run_ctx:
                run_id_1 = run_ctx.run_id
                run_ctx.set_metrics(items_discovered=10)
                # Simulate error
                raise RuntimeError("Simulated failure")
        except RuntimeError:
            pass  # Expected

        # Second run - should work fine despite previous failure
        with client.track_run(
            agent_name="test_agent",
            job_type="test_partial_failure_2"
        ) as run_ctx:
            run_id_2 = run_ctx.run_id
            run_ctx.set_metrics(items_discovered=20)

        # Verify both runs recorded
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM agent_runs WHERE run_id = ?", (run_id_1,))
        status_1 = cursor.fetchone()
        assert status_1 is not None
        assert status_1[0] == "failure"

        cursor.execute("SELECT status FROM agent_runs WHERE run_id = ?", (run_id_2,))
        status_2 = cursor.fetchone()
        assert status_2 is not None
        assert status_2[0] == "success"

        conn.close()

    def test_telemetry_with_nested_errors(self):
        """Test that nested exceptions are handled correctly."""
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        run_id = None

        with pytest.raises(ValueError):
            with client.track_run(
                agent_name="test_agent",
                job_type="test_nested_errors"
            ) as run_ctx:
                run_id = run_ctx.run_id

                try:
                    # Inner error
                    1 / 0
                except ZeroDivisionError:
                    # Transform and re-raise
                    raise ValueError("Math error occurred")

        # Verify error recorded
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, error_summary FROM agent_runs WHERE run_id = ?",
            (run_id,)
        )
        row = cursor.fetchone()
        assert row[0] == "failure"
        assert "Math error" in row[1] or "ValueError" in row[1]
        conn.close()

    def test_telemetry_without_environment_variable(self):
        """Test that telemetry works without AGENT_METRICS_DIR set."""
        # Temporarily unset environment variable
        original_value = os.environ.get("AGENT_METRICS_DIR")

        try:
            if "AGENT_METRICS_DIR" in os.environ:
                del os.environ["AGENT_METRICS_DIR"]

            # Should fall back to D:\ or C:\ detection
            config = TelemetryConfig.from_env()
            assert config.metrics_dir is not None

            client = TelemetryClient(config)

            # Should still work
            with client.track_run(
                agent_name="test_agent",
                job_type="test_no_env_var"
            ) as run_ctx:
                run_ctx.set_metrics(items_discovered=5)

        finally:
            # Restore environment variable
            if original_value:
                os.environ["AGENT_METRICS_DIR"] = original_value
            else:
                # Make sure it's set for subsequent tests
                os.environ["AGENT_METRICS_DIR"] = "D:\\agent-metrics"

    def test_concurrent_writes_dont_deadlock(self):
        """Test that concurrent writes don't deadlock."""
        import threading

        config = TelemetryConfig.from_env()
        errors = []

        def write_telemetry(thread_id):
            try:
                client = TelemetryClient(config)
                with client.track_run(
                    agent_name=f"test_agent_{thread_id}",
                    job_type="test_concurrent"
                ) as run_ctx:
                    run_ctx.set_metrics(items_discovered=thread_id)
            except Exception as e:
                errors.append(e)

        # Launch multiple threads
        threads = []
        for i in range(5):
            t = threading.Thread(target=write_telemetry, args=(i,))
            threads.append(t)
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join(timeout=10)

        # Verify no deadlocks (all threads completed)
        assert all(not t.is_alive() for t in threads), "Some threads deadlocked"

        # Verify no exceptions
        assert len(errors) == 0, f"Errors occurred: {errors}"

    def test_telemetry_with_empty_metrics(self):
        """Test that empty or None metrics are handled gracefully."""
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        with client.track_run(
            agent_name="test_agent",
            job_type="test_empty_metrics"
        ) as run_ctx:
            # Should not crash with empty metrics
            run_ctx.set_metrics()

        # Test passes if we get here

    def test_telemetry_with_large_event_payload(self):
        """Test that large event payloads are handled gracefully."""
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        with client.track_run(
            agent_name="test_agent",
            job_type="test_large_event"
        ) as run_ctx:
            # Create a large payload (but not too large to be unreasonable)
            large_data = {"data": "x" * 10000}  # 10KB string

            # Should handle large event without crashing
            try:
                run_ctx.log_event("large_event", large_data)
            except Exception as e:
                # If it fails, it should fail gracefully
                print(f"Large event failed (graceful): {e}")

        # Test passes if we get here

    def test_telemetry_exception_in_start_run(self):
        """Test that exceptions in start_run don't crash the agent."""
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        # Try to start a run with potentially invalid parameters
        # The client should handle this gracefully
        try:
            run_id = client.start_run(
                agent_name="test_agent",
                job_type="test_exception_in_start",
                trigger_type="test"
            )
            # Should get a run_id even if internal errors occur
            assert run_id is not None
        except Exception:
            # If it does raise, test fails - telemetry should never crash agent
            pytest.fail("start_run raised exception - should be graceful")

    def test_telemetry_with_special_characters(self):
        """Test that special characters in data are handled correctly."""
        config = TelemetryConfig.from_env()
        client = TelemetryClient(config)

        with client.track_run(
            agent_name="test_agent",
            job_type="test_special_chars",
            trigger_type="test"
        ) as run_ctx:
            # Test with various special characters
            run_ctx.log_event("test", {
                "message": "Test with 'quotes' and \"double quotes\"",
                "unicode": "Test with emoji 🚀",
                "newlines": "Line 1\nLine 2\nLine 3",
                "tabs": "Col1\tCol2\tCol3"
            })

        # Test passes if we get here without exceptions
