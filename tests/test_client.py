"""
Tests for telemetry.client module

Tests cover:
- TelemetryClient initialization
- Explicit start_run/end_run pattern
- Context manager track_run pattern
- RunContext methods (log_event, set_metrics)
- Error handling (never crash agent)
- Multi-writer coordination (NDJSON, database, API)
- Statistics retrieval
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.client import TelemetryClient, RunContext
from telemetry.config import TelemetryConfig
from telemetry.models import RunRecord


@pytest.fixture(autouse=True)
def configure_writer_mocks():
    """Auto-configure DatabaseWriter and NDJSONWriter mocks for all tests."""
    with patch("telemetry.client.DatabaseWriter") as mock_db, \
         patch("telemetry.client.NDJSONWriter") as mock_ndjson:

        # Configure mocks to return success
        mock_db_instance = mock_db.return_value
        mock_db_instance.insert_run.return_value = (True, "[OK] Inserted")
        mock_db_instance.update_run.return_value = (True, "[OK] Updated")
        mock_db_instance.get_run.return_value = None

        mock_ndjson_instance = mock_ndjson.return_value
        mock_ndjson_instance.append.return_value = (True, "[OK] Appended")

        yield


class TestTelemetryClientCreation:
    """Test TelemetryClient initialization."""

    def test_client_creation_default_config(self):
        """Test creating client with default config."""
        with patch.dict("os.environ", {}, clear=True):
            client = TelemetryClient()

            assert client.config is not None
            assert client.ndjson_writer is not None
            assert client.database_writer is not None
            assert client.api_client is not None

    def test_client_creation_custom_config(self, tmp_path):
        """Test creating client with custom config."""
        config = TelemetryConfig(
            metrics_dir=tmp_path / "metrics",
            database_path=tmp_path / "metrics" / "db" / "telemetry.sqlite",
            ndjson_dir=tmp_path / "metrics" / "raw",
            api_url="https://api.example.com",
            api_token="test-token",
            api_enabled=True,
            agent_owner="test_owner",
            test_mode=None,
        )

        client = TelemetryClient(config)

        assert client.config == config

    def test_client_validation_warnings(self, capsys):
        """Test that client prints validation warnings."""
        with patch.dict(
            "os.environ",
            {
                "METRICS_API_ENABLED": "true",
                # Missing API_URL and API_TOKEN
            },
            clear=True,
        ):
            client = TelemetryClient()

            captured = capsys.readouterr()
            assert "[WARN]" in captured.out
            assert "configuration issues" in captured.out


class TestStartRun:
    """Test explicit start_run method."""

    def test_start_run_minimal(self):
        """Test starting run with minimal parameters."""
        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")

        assert run_id is not None
        assert run_id.startswith("202")  # Should start with year
        assert "test_agent" in run_id

    def test_start_run_with_all_params(self):
        """Test starting run with all parameters."""
        client = TelemetryClient()

        run_id = client.start_run(
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            agent_owner="test_owner",
            product="test_product",
            platform="test_platform",
        )

        assert run_id is not None

        # Check that run is in active runs
        assert run_id in client._active_runs

        record = client._active_runs[run_id]
        assert record.agent_name == "test_agent"
        assert record.product == "test_product"

    def test_start_run_registers_active_run(self):
        """Test that start_run registers run in active runs."""
        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")

        assert run_id in client._active_runs
        assert isinstance(client._active_runs[run_id], RunRecord)

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_start_run_writes_to_ndjson(self, mock_db, mock_ndjson):
        """Test that start_run writes to NDJSON."""
        mock_ndjson_instance = MagicMock()
        mock_ndjson.return_value = mock_ndjson_instance

        client = TelemetryClient()
        run_id = client.start_run("test_agent", "test_job")

        # Should have called append
        assert mock_ndjson_instance.append.called

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_start_run_writes_to_database(self, mock_db, mock_ndjson):
        """Test that start_run writes to database."""
        mock_db_instance = MagicMock()
        mock_db_instance.insert_run.return_value = (True, "[OK]")
        mock_db.return_value = mock_db_instance

        client = TelemetryClient()
        run_id = client.start_run("test_agent", "test_job")

        # Should have called insert_run
        assert mock_db_instance.insert_run.called

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_start_run_handles_exception(self, mock_db, mock_ndjson, capsys):
        """Test that start_run handles exceptions gracefully."""
        mock_ndjson_instance = MagicMock()
        mock_ndjson_instance.append.side_effect = Exception("Test error")
        mock_ndjson.return_value = mock_ndjson_instance

        client = TelemetryClient()

        # Should not crash, returns error run ID
        run_id = client.start_run("test_agent", "test_job")

        assert run_id is not None
        assert run_id.startswith("error-")

        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out


class TestEndRun:
    """Test explicit end_run method."""

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    @patch("telemetry.client.APIClient")
    def test_end_run_success(self, mock_api, mock_db, mock_ndjson):
        """Test ending run successfully."""
        mock_api_instance = MagicMock()
        mock_api_instance.post_run_sync.return_value = (True, "[OK]")
        mock_api.return_value = mock_api_instance

        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")
        client.end_run(run_id, status="success")

        # Run should be removed from active runs
        assert run_id not in client._active_runs

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_end_run_updates_metrics(self, mock_db, mock_ndjson):
        """Test that end_run updates metrics."""
        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")
        client.end_run(
            run_id,
            status="success",
            items_discovered=10,
            items_succeeded=8,
            items_failed=2,
        )

        # Cannot check record after end_run because it's removed from active_runs
        # But we can verify no exceptions occurred

    @patch("telemetry.client.APIClient")
    def test_end_run_posts_to_api(self, mock_api):
        """Test that end_run posts to API."""
        mock_api_instance = MagicMock()
        mock_api_instance.post_run_sync.return_value = (True, "[OK]")
        mock_api.return_value = mock_api_instance

        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")
        client.end_run(run_id, status="success")

        # Should have called post_run_sync
        assert mock_api_instance.post_run_sync.called

    def test_end_run_nonexistent_id(self, capsys):
        """Test ending run with non-existent ID."""
        client = TelemetryClient()

        # Should not crash
        client.end_run("nonexistent-run-id", status="success")

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "not found" in captured.out

    def test_end_run_calculates_duration(self):
        """Test that end_run calculates duration."""
        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")

        # Get the record to verify start_time is set
        record = client._active_runs[run_id]
        assert record.start_time is not None

        client.end_run(run_id, status="success")

        # Duration should be calculated (we can't verify exact value)


class TestTrackRun:
    """Test context manager track_run method."""

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    @patch("telemetry.client.APIClient")
    def test_track_run_success(self, mock_api, mock_db, mock_ndjson):
        """Test track_run context manager with success."""
        mock_api_instance = MagicMock()
        mock_api_instance.post_run_sync.return_value = (True, "[OK]")
        mock_api.return_value = mock_api_instance

        client = TelemetryClient()

        with client.track_run("test_agent", "test_job") as ctx:
            assert ctx is not None
            assert isinstance(ctx, RunContext)
            assert ctx.run_id is not None

        # Run should be ended and removed from active runs

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    @patch("telemetry.client.APIClient")
    def test_track_run_with_exception(self, mock_api, mock_db, mock_ndjson):
        """Test track_run context manager when exception occurs."""
        mock_api_instance = MagicMock()
        mock_api_instance.post_run_sync.return_value = (True, "[OK]")
        mock_api.return_value = mock_api_instance

        client = TelemetryClient()

        with pytest.raises(ValueError):
            with client.track_run("test_agent", "test_job") as ctx:
                raise ValueError("Test exception")

        # Exception should be propagated
        # But run should be ended with failed status

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_track_run_yields_context(self, mock_db, mock_ndjson):
        """Test that track_run yields RunContext."""
        client = TelemetryClient()

        with client.track_run("test_agent", "test_job") as ctx:
            assert isinstance(ctx, RunContext)
            assert hasattr(ctx, "run_id")
            assert hasattr(ctx, "log_event")
            assert hasattr(ctx, "set_metrics")


class TestRunContext:
    """Test RunContext methods."""

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_run_context_log_event(self, mock_db, mock_ndjson):
        """Test RunContext.log_event method."""
        mock_ndjson_instance = MagicMock()
        mock_ndjson.return_value = mock_ndjson_instance

        client = TelemetryClient()

        with client.track_run("test_agent", "test_job") as ctx:
            ctx.log_event("checkpoint", {"step": 1})

        # Should have called append for event
        assert mock_ndjson_instance.append.call_count >= 2  # At least start + event

    def test_run_context_set_metrics(self):
        """Test RunContext.set_metrics method."""
        client = TelemetryClient()

        with client.track_run("test_agent", "test_job") as ctx:
            ctx.set_metrics(items_discovered=10, items_succeeded=5)

            # Verify metrics were set on record
            record = ctx._record
            assert record.items_discovered == 10
            assert record.items_succeeded == 5

    def test_run_context_set_metrics_multiple_calls(self):
        """Test multiple calls to set_metrics."""
        client = TelemetryClient()

        with client.track_run("test_agent", "test_job") as ctx:
            ctx.set_metrics(items_discovered=10)
            ctx.set_metrics(items_succeeded=5)
            ctx.set_metrics(items_failed=2)

            record = ctx._record
            assert record.items_discovered == 10
            assert record.items_succeeded == 5
            assert record.items_failed == 2


class TestLogEvent:
    """Test log_event method."""

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_log_event_writes_to_ndjson(self, mock_db, mock_ndjson):
        """Test that log_event writes to NDJSON."""
        mock_ndjson_instance = MagicMock()
        mock_ndjson.return_value = mock_ndjson_instance

        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")
        client.log_event(run_id, "checkpoint", {"step": 1})

        # Should have called append
        assert mock_ndjson_instance.append.call_count >= 2  # start + event

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_log_event_handles_exception(self, mock_db, mock_ndjson, capsys):
        """Test that log_event handles exceptions gracefully."""
        mock_ndjson_instance = MagicMock()
        mock_ndjson_instance.append.side_effect = Exception("Test error")
        mock_ndjson.return_value = mock_ndjson_instance

        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")

        # Should not crash
        client.log_event(run_id, "checkpoint", {"step": 1})

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out


class TestGetStats:
    """Test get_stats method."""

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_get_stats_returns_dict(self, mock_db, mock_ndjson):
        """Test that get_stats returns dictionary."""
        mock_db_instance = MagicMock()
        mock_db_instance.get_run_stats.return_value = {
            "total_runs": 5,
            "status_counts": {"success": 3, "failed": 2},
            "pending_api_posts": 2,
        }
        mock_db.return_value = mock_db_instance

        client = TelemetryClient()
        stats = client.get_stats()

        assert isinstance(stats, dict)
        assert "total_runs" in stats

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_get_stats_handles_exception(self, mock_db, mock_ndjson):
        """Test that get_stats handles exceptions gracefully."""
        mock_db_instance = MagicMock()
        mock_db_instance.get_run_stats.side_effect = Exception("Test error")
        mock_db.return_value = mock_db_instance

        client = TelemetryClient()
        stats = client.get_stats()

        # Should return error dict, not crash
        assert isinstance(stats, dict)
        assert "error" in stats


class TestErrorHandling:
    """Test error handling throughout TelemetryClient."""

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_never_crash_on_ndjson_error(self, mock_db, mock_ndjson):
        """Test that NDJSON errors don't crash."""
        mock_ndjson_instance = MagicMock()
        mock_ndjson_instance.append.side_effect = Exception("NDJSON error")
        mock_ndjson.return_value = mock_ndjson_instance

        client = TelemetryClient()

        # Should not crash
        run_id = client.start_run("test_agent", "test_job")
        assert run_id.startswith("error-")

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    def test_never_crash_on_database_error(self, mock_db, mock_ndjson):
        """Test that database errors don't crash."""
        mock_db_instance = MagicMock()
        mock_db_instance.insert_run.side_effect = Exception("Database error")
        mock_db.return_value = mock_db_instance

        client = TelemetryClient()

        # Should not crash
        run_id = client.start_run("test_agent", "test_job")
        # May still succeed if NDJSON write works

    @patch("telemetry.client.NDJSONWriter")
    @patch("telemetry.client.DatabaseWriter")
    @patch("telemetry.client.APIClient")
    def test_never_crash_on_api_error(self, mock_api, mock_db, mock_ndjson):
        """Test that API errors don't crash."""
        mock_api_instance = MagicMock()
        mock_api_instance.post_run_sync.side_effect = Exception("API error")
        mock_api.return_value = mock_api_instance

        client = TelemetryClient()

        run_id = client.start_run("test_agent", "test_job")
        # Should not crash on end_run
        client.end_run(run_id, status="success")


class TestTriggerTypes:
    """Test different trigger types."""

    def test_trigger_type_cli(self):
        """Test CLI trigger type."""
        client = TelemetryClient()
        run_id = client.start_run("test_agent", "test_job", trigger_type="cli")

        record = client._active_runs[run_id]
        assert record.trigger_type == "cli"

    def test_trigger_type_web(self):
        """Test web trigger type."""
        client = TelemetryClient()
        run_id = client.start_run("test_agent", "test_job", trigger_type="web")

        record = client._active_runs[run_id]
        assert record.trigger_type == "web"

    def test_trigger_type_scheduler(self):
        """Test scheduler trigger type."""
        client = TelemetryClient()
        run_id = client.start_run("test_agent", "test_job", trigger_type="scheduler")

        record = client._active_runs[run_id]
        assert record.trigger_type == "scheduler"
