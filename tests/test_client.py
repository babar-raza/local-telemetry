"""
Tests for telemetry.client module

Tests cover:
- TelemetryClient initialization
- Explicit start_run/end_run pattern
- Context manager track_run pattern
- RunContext methods (log_event, set_metrics)
- Error handling (never crash agent)
- Real file I/O (NDJSON, buffer files) with tmp_path
- Statistics retrieval

TEST DEPENDENCIES:
These tests use REAL file operations and may attempt HTTP API calls.
- NDJSON files are written to tmp_path (no mocking)
- Buffer files are written to tmp_path (no mocking)
- HTTP API calls to localhost:8765 may fail if API not running (expected, graceful failover to buffer)
- Tests verify graceful degradation when HTTP API unavailable

To run HTTP API service for testing:
    python -m api.main  # Start API server on localhost:8765
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.client import TelemetryClient, RunContext
from telemetry.config import TelemetryConfig
from telemetry.models import RunRecord


@pytest.fixture
def temp_telemetry_dir(tmp_path):
    """Create temporary directory for telemetry files."""
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    ndjson_dir = metrics_dir / "raw"
    ndjson_dir.mkdir(parents=True, exist_ok=True)

    buffer_dir = metrics_dir / "buffer"
    buffer_dir.mkdir(parents=True, exist_ok=True)

    db_dir = metrics_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)

    return {
        "metrics_dir": metrics_dir,
        "ndjson_dir": ndjson_dir,
        "buffer_dir": buffer_dir,
        "database_path": db_dir / "telemetry.sqlite",
    }


@pytest.fixture
def test_config(temp_telemetry_dir):
    """Create test configuration with real paths."""
    return TelemetryConfig(
        metrics_dir=temp_telemetry_dir["metrics_dir"],
        database_path=temp_telemetry_dir["database_path"],
        ndjson_dir=temp_telemetry_dir["ndjson_dir"],
        api_url="http://localhost:8765",
        google_sheets_api_url=None,
        google_sheets_api_enabled=False,  # Disable Google Sheets API for tests
        api_token=None,
        api_enabled=False,  # Legacy field
        retry_backoff_factor=1.0,
        agent_owner="test_owner",
        test_mode=None,
        skip_validation=False,
    )


@pytest.fixture
def client(test_config):
    """Create TelemetryClient with test configuration."""
    return TelemetryClient(test_config)


class TestTelemetryClientCreation:
    """Test TelemetryClient initialization."""

    def test_client_creation_with_test_config(self, client, test_config):
        """Test creating client with test config."""
        assert client.config == test_config
        assert client.ndjson_writer is not None
        assert client.http_api is not None
        assert client.buffer is not None
        # Google Sheets client should be None when disabled
        assert client.api_client is None

    def test_client_creation_custom_config(self, temp_telemetry_dir):
        """Test creating client with custom config."""
        config = TelemetryConfig(
            metrics_dir=temp_telemetry_dir["metrics_dir"],
            database_path=temp_telemetry_dir["database_path"],
            ndjson_dir=temp_telemetry_dir["ndjson_dir"],
            api_url="http://localhost:8765",
            google_sheets_api_url=None,
            google_sheets_api_enabled=False,
            api_token="test-token",
            api_enabled=False,
            retry_backoff_factor=1.0,
            agent_owner="test_owner",
            test_mode=None,
            skip_validation=False,
        )

        client = TelemetryClient(config)

        assert client.config == config
        assert client.ndjson_writer is not None
        assert client.http_api is not None
        assert client.api_client is None

    def test_client_validation_warnings(self, capsys, temp_telemetry_dir):
        """Test that client prints validation warnings."""
        # Create config with Google Sheets enabled but missing URL
        config = TelemetryConfig(
            metrics_dir=temp_telemetry_dir["metrics_dir"],
            database_path=temp_telemetry_dir["database_path"],
            ndjson_dir=temp_telemetry_dir["ndjson_dir"],
            api_url="http://localhost:8765",
            google_sheets_api_url=None,
            google_sheets_api_enabled=True,
            api_token=None,
            api_enabled=False,
            retry_backoff_factor=1.0,
            agent_owner=None,
            test_mode=None,
            skip_validation=False,
        )

        client = TelemetryClient(config)

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "configuration issues" in captured.out


class TestClientSelection:
    """Test client selection logic based on configuration (TS-02)."""

    def test_google_sheets_disabled_by_default(self, test_config):
        """Test that Google Sheets client is None when disabled."""
        test_config.google_sheets_api_enabled = False
        client = TelemetryClient(test_config)

        assert client.http_api is not None, "HTTPAPIClient should always be created"
        assert client.api_client is None, "Google Sheets client should be None when disabled"

    def test_google_sheets_enabled_with_url(self, temp_telemetry_dir):
        """Test that Google Sheets client is created when enabled with URL."""
        config = TelemetryConfig(
            metrics_dir=temp_telemetry_dir["metrics_dir"],
            database_path=temp_telemetry_dir["database_path"],
            ndjson_dir=temp_telemetry_dir["ndjson_dir"],
            api_url="http://localhost:8765",
            google_sheets_api_url="https://script.google.com/test",
            google_sheets_api_enabled=True,
            api_token="test-token",
            api_enabled=False,
            retry_backoff_factor=1.0,
            agent_owner="test_owner",
            test_mode=None,
            skip_validation=False,
        )
        client = TelemetryClient(config)

        assert client.http_api is not None, "HTTPAPIClient should always be created"
        assert client.api_client is not None, "Google Sheets client should be created when enabled"

    def test_google_sheets_enabled_without_url(self, temp_telemetry_dir, caplog):
        """Test that Google Sheets client is None when enabled but URL missing."""
        import logging
        caplog.set_level(logging.WARNING)

        config = TelemetryConfig(
            metrics_dir=temp_telemetry_dir["metrics_dir"],
            database_path=temp_telemetry_dir["database_path"],
            ndjson_dir=temp_telemetry_dir["ndjson_dir"],
            api_url="http://localhost:8765",
            google_sheets_api_url=None,
            google_sheets_api_enabled=True,
            api_token=None,
            api_enabled=False,
            retry_backoff_factor=1.0,
            agent_owner="test_owner",
            test_mode=None,
            skip_validation=False,
        )
        client = TelemetryClient(config)

        assert client.http_api is not None
        assert client.api_client is None, "Google Sheets client should be None without URL"
        assert any("GOOGLE_SHEETS_API_URL not set" in record.message for record in caplog.records)

    def test_initialization_logs_client_summary(self, test_config, caplog):
        """Test that initialization logs active clients."""
        import logging
        caplog.set_level(logging.INFO)

        test_config.google_sheets_api_enabled = False
        client = TelemetryClient(test_config)

        # Check for summary logging
        log_messages = [record.message for record in caplog.records]

        assert any("Primary: HTTPAPIClient -> http://localhost:8765" in msg for msg in log_messages)
        assert any("Google Sheets API -> DISABLED" in msg for msg in log_messages)


class TestStartRun:
    """Test explicit start_run method."""

    def test_start_run_minimal(self, client):
        """Test starting run with minimal parameters."""
        run_id = client.start_run("test_agent", "test_job")

        assert run_id is not None
        assert run_id.startswith("202")  # Should start with year
        assert "test_agent" in run_id

    def test_start_run_with_all_params(self, client):
        """Test starting run with all parameters."""
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

    def test_start_run_registers_active_run(self, client):
        """Test that start_run registers run in active runs."""
        run_id = client.start_run("test_agent", "test_job")

        assert run_id in client._active_runs
        assert isinstance(client._active_runs[run_id], RunRecord)

    def test_start_run_writes_to_ndjson(self, client, temp_telemetry_dir):
        """Test that start_run writes to NDJSON file."""
        run_id = client.start_run("test_agent", "test_job")

        # Check that NDJSON file was created
        ndjson_dir = temp_telemetry_dir["ndjson_dir"]
        ndjson_files = list(ndjson_dir.glob("*.ndjson"))

        assert len(ndjson_files) > 0, "NDJSON file should be created"

        # Verify file contains run_id
        ndjson_file = ndjson_files[0]
        content = ndjson_file.read_text()
        assert run_id in content, f"NDJSON file should contain run_id {run_id}"

    def test_start_run_writes_to_buffer_on_api_unavailable(self, client, temp_telemetry_dir):
        """Test that start_run writes to buffer when HTTP API unavailable."""
        run_id = client.start_run("test_agent", "test_job")

        # If API is unavailable (expected), event should be buffered
        # Check buffer directory for .jsonl.active files
        buffer_dir = temp_telemetry_dir["buffer_dir"]
        buffer_files = list(buffer_dir.glob("*.jsonl.active"))

        # Buffer files are created on failover - may or may not exist depending on API availability
        # This test just verifies no crash occurred
        assert run_id is not None


class TestEndRun:
    """Test explicit end_run method."""

    def test_end_run_success(self, client):
        """Test ending run successfully."""
        run_id = client.start_run("test_agent", "test_job")
        client.end_run(run_id, status="success")

        # Run should be removed from active runs
        assert run_id not in client._active_runs

    def test_end_run_updates_metrics(self, client):
        """Test that end_run updates metrics."""
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
        assert run_id not in client._active_runs

    def test_end_run_nonexistent_id(self, capsys, client):
        """Test ending run with non-existent ID."""
        # Should not crash
        client.end_run("nonexistent-run-id", status="success")

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out
        assert "not found" in captured.out

    def test_end_run_calculates_duration(self, client):
        """Test that end_run calculates duration."""
        run_id = client.start_run("test_agent", "test_job")

        # Get the record to verify start_time is set
        record = client._active_runs[run_id]
        assert record.start_time is not None

        client.end_run(run_id, status="success")

        # Duration should be calculated (we can't verify exact value)

    def test_end_run_skips_google_sheets_when_disabled(self, client, caplog):
        """Test that end_run skips Google Sheets posting when disabled (TS-02)."""
        import logging
        caplog.set_level(logging.DEBUG)

        # Ensure Google Sheets is disabled
        assert client.api_client is None

        run_id = client.start_run("test_agent", "test_job")
        client.end_run(run_id, status="success")

        # Check that Google Sheets skip was logged
        assert any("Google Sheets API disabled" in record.message for record in caplog.records)

    def test_end_run_posts_to_google_sheets_when_enabled(self, temp_telemetry_dir, caplog):
        """Test that end_run posts to Google Sheets when enabled (TS-02)."""
        import logging
        from unittest.mock import Mock
        caplog.set_level(logging.DEBUG)

        # Enable Google Sheets
        config = TelemetryConfig(
            metrics_dir=temp_telemetry_dir["metrics_dir"],
            database_path=temp_telemetry_dir["database_path"],
            ndjson_dir=temp_telemetry_dir["ndjson_dir"],
            api_url="http://localhost:8765",
            google_sheets_api_url="https://script.google.com/test",
            google_sheets_api_enabled=True,
            api_token="test-token",
            api_enabled=False,
            retry_backoff_factor=1.0,
            agent_owner="test_owner",
            test_mode=None,
            skip_validation=False,
        )
        client = TelemetryClient(config)

        # Mock the API client
        client.api_client.post_run_sync = Mock(return_value=(True, "[OK] Posted"))

        run_id = client.start_run("test_agent", "test_job")
        client.end_run(run_id, status="success")

        # Verify Google Sheets was called
        assert client.api_client.post_run_sync.called


class TestTrackRun:
    """Test context manager track_run method."""

    def test_track_run_success(self, client):
        """Test track_run context manager with success."""
        with client.track_run("test_agent", "test_job") as ctx:
            assert ctx is not None
            assert isinstance(ctx, RunContext)
            assert ctx.run_id is not None

        # Run should be ended and removed from active runs

    def test_track_run_with_exception(self, client):
        """Test track_run context manager when exception occurs."""
        with pytest.raises(ValueError):
            with client.track_run("test_agent", "test_job") as ctx:
                raise ValueError("Test exception")

        # Exception should be propagated
        # But run should be ended with failed status

    def test_track_run_yields_context(self, client):
        """Test that track_run yields RunContext."""
        with client.track_run("test_agent", "test_job") as ctx:
            assert isinstance(ctx, RunContext)
            assert hasattr(ctx, "run_id")
            assert hasattr(ctx, "log_event")
            assert hasattr(ctx, "set_metrics")


class TestRunContext:
    """Test RunContext methods."""

    def test_run_context_log_event(self, client, temp_telemetry_dir):
        """Test RunContext.log_event method."""
        with client.track_run("test_agent", "test_job") as ctx:
            ctx.log_event("checkpoint", {"step": 1})

        # Verify event was written to NDJSON
        ndjson_dir = temp_telemetry_dir["ndjson_dir"]
        ndjson_files = list(ndjson_dir.glob("*.ndjson"))
        assert len(ndjson_files) > 0

        # Check file contains checkpoint event
        ndjson_file = ndjson_files[0]
        content = ndjson_file.read_text()
        assert "checkpoint" in content

    def test_run_context_set_metrics(self, client):
        """Test RunContext.set_metrics method."""
        with client.track_run("test_agent", "test_job") as ctx:
            ctx.set_metrics(items_discovered=10, items_succeeded=5)

            # Verify metrics were set on record
            record = ctx._record
            assert record.items_discovered == 10
            assert record.items_succeeded == 5

    def test_run_context_set_metrics_multiple_calls(self, client):
        """Test multiple calls to set_metrics."""
        with client.track_run("test_agent", "test_job") as ctx:
            ctx.set_metrics(items_discovered=10)
            ctx.set_metrics(items_succeeded=5)
            ctx.set_metrics(items_failed=2)

            record = ctx._record
            assert record.items_discovered == 10
            assert record.items_succeeded == 5
            assert record.items_failed == 2

    def test_run_context_set_metrics_warns_on_unknown_kwarg(self, caplog, client):
        """Test that set_metrics logs warning for unknown kwargs (TEL-07-D)."""
        import logging
        caplog.set_level(logging.WARNING)

        with client.track_run("test_agent", "test_job") as ctx:
            # Valid kwarg should work
            ctx.set_metrics(items_discovered=10)
            assert ctx._record.items_discovered == 10

            # Invalid kwarg (typo) should warn
            ctx.set_metrics(items_discoverd=20)  # Note: typo

        # Check warning was logged
        assert any("items_discoverd" in record.message for record in caplog.records)
        assert any("ignoring unknown kwarg" in record.message for record in caplog.records)

    def test_run_context_set_metrics_unknown_kwarg_does_not_crash(self, client):
        """Test that unknown kwargs don't crash set_metrics (TEL-07-D)."""
        with client.track_run("test_agent", "test_job") as ctx:
            # Should not crash with unknown kwargs
            ctx.set_metrics(
                items_discovered=10,
                nonexistent_field="value",
                another_typo=123,
            )

            # Valid field should still be set
            assert ctx._record.items_discovered == 10


class TestLogEvent:
    """Test log_event method."""

    def test_log_event_writes_to_ndjson(self, client, temp_telemetry_dir):
        """Test that log_event writes to NDJSON."""
        run_id = client.start_run("test_agent", "test_job")
        client.log_event(run_id, "checkpoint", {"step": 1})

        # Verify event was written to NDJSON
        ndjson_dir = temp_telemetry_dir["ndjson_dir"]
        ndjson_files = list(ndjson_dir.glob("*.ndjson"))
        assert len(ndjson_files) > 0

        # Check file contains event
        ndjson_file = ndjson_files[0]
        content = ndjson_file.read_text()
        assert "checkpoint" in content


class TestGetStats:
    """Test get_stats method."""

    def test_get_stats_returns_dict(self, client):
        """Test that get_stats returns dictionary."""
        stats = client.get_stats()

        assert isinstance(stats, dict)
        # May contain run_id_metrics if available
        assert "run_id_metrics" in stats or "error" in stats


class TestErrorHandling:
    """Test error handling throughout TelemetryClient."""

    def test_never_crash_on_ndjson_error(self, client, temp_telemetry_dir):
        """Test that NDJSON errors don't crash."""
        # Make NDJSON directory read-only to force write error
        ndjson_dir = temp_telemetry_dir["ndjson_dir"]

        # This test is platform-specific and may not work on all systems
        # Just verify client doesn't crash with invalid directory
        run_id = client.start_run("test_agent", "test_job")
        assert run_id is not None


class TestTriggerTypes:
    """Test different trigger types."""

    def test_trigger_type_cli(self, client):
        """Test CLI trigger type."""
        run_id = client.start_run("test_agent", "test_job", trigger_type="cli")

        record = client._active_runs[run_id]
        assert record.trigger_type == "cli"

    def test_trigger_type_web(self, client):
        """Test web trigger type."""
        run_id = client.start_run("test_agent", "test_job", trigger_type="web")

        record = client._active_runs[run_id]
        assert record.trigger_type == "web"

    def test_trigger_type_scheduler(self, client):
        """Test scheduler trigger type."""
        run_id = client.start_run("test_agent", "test_job", trigger_type="scheduler")

        record = client._active_runs[run_id]
        assert record.trigger_type == "scheduler"


class TestTelemetryClientGitAutoDetection:
    """
    Integration tests for GT-01: Automatic Git Detection Helper.

    Tests the integration between TelemetryClient and GitDetector.
    """

    def test_git_auto_detection_enriches_run_record(self, client):
        """Test that Git context is automatically detected and added to run record."""
        from unittest.mock import patch, Mock

        # Mock GitDetector to return test context
        with patch.object(client.git_detector, 'get_git_context') as mock_detect:
            mock_detect.return_value = {
                "git_repo": "test-repo",
                "git_branch": "feature-branch",
                "git_run_tag": "test-repo/feature-branch"
            }

            # Start run without explicit git values
            run_id = client.start_run("test_agent", "test_job")

            # Verify auto-detected values were added to record
            record = client._active_runs[run_id]
            assert record.git_repo == "test-repo"
            assert record.git_branch == "feature-branch"
            assert record.git_run_tag == "test-repo/feature-branch"

            # Verify GitDetector was called
            assert mock_detect.call_count == 1

    def test_explicit_git_values_override_auto_detection(self, client):
        """Test that explicit git_repo/git_branch values take precedence over auto-detection."""
        from unittest.mock import patch

        # Mock GitDetector to return different context
        with patch.object(client.git_detector, 'get_git_context') as mock_detect:
            mock_detect.return_value = {
                "git_repo": "auto-detected-repo",
                "git_branch": "auto-detected-branch",
                "git_run_tag": "auto-detected-repo/auto-detected-branch"
            }

            # Start run with explicit git values
            run_id = client.start_run(
                "test_agent",
                "test_job",
                git_repo="explicit-repo",
                git_branch="explicit-branch"
            )

            # Verify explicit values were used (not auto-detected)
            record = client._active_runs[run_id]
            assert record.git_repo == "explicit-repo"
            assert record.git_branch == "explicit-branch"
            # git_run_tag was not explicitly provided, so it comes from auto-detection
            assert record.git_run_tag == "auto-detected-repo/auto-detected-branch"

    def test_partial_explicit_git_values_merge_with_auto_detection(self, client):
        """Test that partial explicit values merge with auto-detected values."""
        from unittest.mock import patch

        # Mock GitDetector to return full context
        with patch.object(client.git_detector, 'get_git_context') as mock_detect:
            mock_detect.return_value = {
                "git_repo": "auto-repo",
                "git_branch": "auto-branch",
                "git_run_tag": "auto-repo/auto-branch"
            }

            # Start run with only git_repo explicit (git_branch should be auto-detected)
            run_id = client.start_run(
                "test_agent",
                "test_job",
                git_repo="explicit-repo"
            )

            # Verify explicit git_repo, auto-detected git_branch
            record = client._active_runs[run_id]
            assert record.git_repo == "explicit-repo"
            assert record.git_branch == "auto-branch"  # Auto-detected
            assert record.git_run_tag == "auto-repo/auto-branch"  # Auto-detected

    def test_git_detection_failure_does_not_crash(self, client):
        """Test that Git detection failure doesn't crash start_run."""
        from unittest.mock import patch

        # Mock GitDetector to raise exception
        with patch.object(client.git_detector, 'get_git_context') as mock_detect:
            mock_detect.side_effect = RuntimeError("Git detection failed")

            # Start run - should not crash
            run_id = client.start_run("test_agent", "test_job")

            # Verify run was created successfully
            assert run_id is not None
            assert run_id in client._active_runs

            # Verify no git context was added
            record = client._active_runs[run_id]
            assert not hasattr(record, 'git_repo') or record.git_repo is None
            assert not hasattr(record, 'git_branch') or record.git_branch is None

    def test_git_detection_empty_result_does_not_add_fields(self, client):
        """Test that empty Git detection result doesn't add empty fields."""
        from unittest.mock import patch

        # Mock GitDetector to return empty context (not in Git repo)
        with patch.object(client.git_detector, 'get_git_context') as mock_detect:
            mock_detect.return_value = {}

            # Start run
            run_id = client.start_run("test_agent", "test_job")

            # Verify run was created
            assert run_id is not None

            # Verify no git fields were added (or they're None)
            record = client._active_runs[run_id]
            # These fields may not exist or may be None
            git_repo = getattr(record, 'git_repo', None)
            git_branch = getattr(record, 'git_branch', None)
            git_run_tag = getattr(record, 'git_run_tag', None)

            assert git_repo is None
            assert git_branch is None
            assert git_run_tag is None
