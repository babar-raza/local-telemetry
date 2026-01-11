"""
Tests for smart retry logic in telemetry.api module

Tests verify:
- 4xx errors (404, 400) → NO retry (1 attempt only)
- 5xx errors (503, 500) → YES retry (up to max_retries)
- Timeout errors → YES retry (up to max_retries)
- Connection errors → YES retry (up to max_retries)
- Max retries respected
- Backoff delays applied correctly
- Logging shows retry decisions

This file follows NO MOCKING policy exception for external Google Sheets API.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import logging

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.api import APIClient, should_retry
from telemetry.models import APIPayload, get_iso8601_timestamp


class TestShouldRetryHelper:
    """Test the should_retry() helper function."""

    def test_should_retry_404_response(self):
        """404 client error should NOT retry."""
        mock_response = MagicMock()
        mock_response.status_code = 404

        assert should_retry(response=mock_response) is False

    def test_should_retry_400_response(self):
        """400 client error should NOT retry."""
        mock_response = MagicMock()
        mock_response.status_code = 400

        assert should_retry(response=mock_response) is False

    def test_should_retry_422_response(self):
        """422 client error should NOT retry."""
        mock_response = MagicMock()
        mock_response.status_code = 422

        assert should_retry(response=mock_response) is False

    def test_should_retry_401_response(self):
        """401 auth error should NOT retry."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        assert should_retry(response=mock_response) is False

    def test_should_retry_503_response(self):
        """503 server error should retry."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        assert should_retry(response=mock_response) is True

    def test_should_retry_500_response(self):
        """500 server error should retry."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        assert should_retry(response=mock_response) is True

    def test_should_retry_502_response(self):
        """502 bad gateway should retry."""
        mock_response = MagicMock()
        mock_response.status_code = 502

        assert should_retry(response=mock_response) is True

    @patch("telemetry.api.httpx")
    def test_should_retry_timeout_exception(self, mock_httpx):
        """Timeout exception should retry."""
        # Create proper exception class
        class MockTimeoutException(Exception):
            pass

        mock_httpx.TimeoutException = MockTimeoutException
        mock_httpx.ConnectError = type('ConnectError', (Exception,), {})
        mock_httpx.RequestError = type('RequestError', (Exception,), {})
        exception = MockTimeoutException()

        assert should_retry(exception=exception) is True

    @patch("telemetry.api.httpx")
    def test_should_retry_connect_error(self, mock_httpx):
        """Connection error should retry."""
        mock_httpx.ConnectError = Exception
        exception = mock_httpx.ConnectError()

        assert should_retry(exception=exception) is True

    @patch("telemetry.api.httpx")
    def test_should_retry_request_error(self, mock_httpx):
        """General request error should retry."""
        # Create proper exception classes
        class MockRequestError(Exception):
            pass

        mock_httpx.RequestError = MockRequestError
        mock_httpx.TimeoutException = type('TimeoutException', (Exception,), {})
        mock_httpx.ConnectError = type('ConnectError', (Exception,), {})
        exception = MockRequestError()

        assert should_retry(exception=exception) is True

    def test_should_retry_other_exception(self):
        """Other exceptions should NOT retry."""
        exception = ValueError("Something went wrong")

        assert should_retry(exception=exception) is False


class TestNoRetryOn4xxErrors:
    """Test that 4xx client errors do NOT trigger retries."""

    @patch("telemetry.api.httpx")
    def test_no_retry_on_404(self, mock_httpx):
        """404 Not Found should NOT retry (1 attempt only)."""
        # Mock 404 response
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail immediately
        assert success is False
        assert "404" in message
        assert "not retried" in message

        # Should only call post() once (no retries)
        assert mock_client.post.call_count == 1

    @patch("telemetry.api.httpx")
    def test_no_retry_on_400(self, mock_httpx):
        """400 Bad Request should NOT retry."""
        mock_response = MagicMock()
        mock_response.status_code = 400

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail immediately
        assert success is False
        assert "400" in message
        assert "not retried" in message

        # Should only call post() once (no retries)
        assert mock_client.post.call_count == 1

    @patch("telemetry.api.httpx")
    def test_no_retry_on_422(self, mock_httpx):
        """422 Unprocessable Entity should NOT retry."""
        mock_response = MagicMock()
        mock_response.status_code = 422

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail immediately
        assert success is False
        assert "422" in message

        # Should only call post() once (no retries)
        assert mock_client.post.call_count == 1


class TestRetryOn5xxErrors:
    """Test that 5xx server errors DO trigger retries."""

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_retry_on_503(self, mock_sleep, mock_httpx):
        """503 Service Unavailable should retry up to max_retries."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail after all retries
        assert success is False
        assert "failed after 3 attempts" in message

        # Should call post() max_retries times (3)
        assert mock_client.post.call_count == 3

        # Should sleep max_retries-1 times (2)
        assert mock_sleep.call_count == 2

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_retry_on_500(self, mock_sleep, mock_httpx):
        """500 Internal Server Error should retry."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail after all retries
        assert success is False

        # Should call post() max_retries times (3)
        assert mock_client.post.call_count == 3

        # Should sleep max_retries-1 times (2)
        assert mock_sleep.call_count == 2

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_eventual_success_after_retries(self, mock_sleep, mock_httpx):
        """503, 503, 200 should succeed on third attempt."""
        # First 2 attempts fail with 503, third succeeds with 200
        mock_response_503 = MagicMock()
        mock_response_503.status_code = 503

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.side_effect = [
            mock_response_503,
            mock_response_503,
            mock_response_200,
        ]

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should succeed on third attempt
        assert success is True
        assert "attempt 3" in message.lower()

        # Should call post() 3 times
        assert mock_client.post.call_count == 3

        # Should sleep 2 times (after first 2 failures)
        assert mock_sleep.call_count == 2


class TestRetryOnNetworkErrors:
    """Test that network errors (timeout, connection) DO trigger retries."""

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_retry_on_timeout(self, mock_sleep, mock_httpx):
        """Timeout exception should retry."""
        mock_httpx.TimeoutException = Exception
        mock_httpx.RequestError = Exception

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.side_effect = mock_httpx.TimeoutException()

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail after all retries
        assert success is False
        assert "timeout" in message.lower()

        # Should call post() max_retries times (3)
        assert mock_client.post.call_count == 3

        # Should sleep max_retries-1 times (2)
        assert mock_sleep.call_count == 2

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_retry_on_connection_error(self, mock_sleep, mock_httpx):
        """Connection error should retry."""
        class MockRequestError(Exception):
            pass

        class MockTimeoutException(Exception):
            pass

        mock_httpx.RequestError = MockRequestError
        mock_httpx.TimeoutException = MockTimeoutException

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.side_effect = MockRequestError("Connection failed")

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail after all retries
        assert success is False
        assert "request error" in message.lower()

        # Should call post() max_retries times (3)
        assert mock_client.post.call_count == 3

        # Should sleep max_retries-1 times (2)
        assert mock_sleep.call_count == 2


class TestMaxRetriesRespected:
    """Test that max_retries configuration is respected."""

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_max_retries_custom_value(self, mock_sleep, mock_httpx):
        """Custom max_retries should be respected."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        # Set max_retries to 5
        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=5,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail after 5 attempts
        assert success is False
        assert "failed after 5 attempts" in message

        # Should call post() 5 times
        assert mock_client.post.call_count == 5

        # Should sleep 4 times
        assert mock_sleep.call_count == 4

    @patch("telemetry.api.httpx")
    def test_max_retries_one(self, mock_httpx):
        """max_retries=1 should only try once."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=1,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = client.post_run_sync(payload)

        # Should fail after 1 attempt
        assert success is False
        assert "failed after 1 attempt" in message

        # Should only call post() once
        assert mock_client.post.call_count == 1


class TestBackoffDelays:
    """Test that exponential backoff delays are applied correctly."""

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_backoff_delays_sequence(self, mock_sleep, mock_httpx):
        """Verify backoff delays: 1s, 2s, 4s."""
        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        client.post_run_sync(payload)

        # Should sleep with delays: 1.0, 2.0
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)


class TestLogging:
    """Test that logging shows retry decisions."""

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_logging_shows_retry_decision_503(self, mock_sleep, mock_httpx, caplog):
        """Verify logging shows retry attempt for 503."""
        caplog.set_level(logging.WARNING)

        mock_response = MagicMock()
        mock_response.status_code = 503

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        client.post_run_sync(payload)

        # Check that log contains retry information
        log_text = caplog.text.lower()
        assert "503" in log_text
        assert "retryable" in log_text or "retry" in log_text

    @patch("telemetry.api.httpx")
    def test_logging_shows_no_retry_decision_404(self, mock_httpx, caplog):
        """Verify logging shows NO retry for 404."""
        caplog.set_level(logging.WARNING)

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            google_sheets_api_url="https://api.example.com",
            api_token="test-token",
            google_sheets_api_enabled=True,
            max_retries=3,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        client.post_run_sync(payload)

        # Check that log contains "not retrying" information
        log_text = caplog.text.lower()
        assert "404" in log_text
        assert "not retrying" in log_text or "client error" in log_text
