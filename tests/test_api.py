"""
Tests for telemetry.api module

Tests cover:
- APIClient initialization
- Configuration checking
- Synchronous API posting to Google Sheets API
- Asynchronous API posting
- Exponential backoff retry logic
- Error handling
- Connection testing

NO MOCKING POLICY EXCEPTION:
This file tests APIClient which posts to EXTERNAL Google Sheets API (not our service).
We CANNOT make real HTTP calls to Google Sheets in tests, so httpx mocking is REQUIRED.

This is an ACCEPTABLE exception to the NO MOCKING policy because:
1. External API (Google Apps Script) - not under our control
2. Requires authentication credentials not available in test environment
3. Would cause side effects (writing to real spreadsheet)
4. HTTP mocking is the industry-standard approach for external API testing

All other test files use REAL file operations and REAL internal HTTP API calls.
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.api import APIClient
from telemetry.models import APIPayload, get_iso8601_timestamp


class TestAPIClientCreation:
    """Test APIClient initialization."""

    def test_client_creation_minimal(self):
        """Test creating APIClient with minimal config."""
        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
        )

        assert client.api_url == "https://api.example.com"
        assert client.api_token == "test-token"
        assert client.api_enabled is True
        assert client.max_retries == 3

    def test_client_creation_custom_params(self):
        """Test creating APIClient with custom parameters."""
        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
            api_enabled=False,
            max_retries=5,
            timeout=20.0,
        )

        assert client.api_enabled is False
        assert client.max_retries == 5
        assert client.timeout == 20.0

    def test_client_creation_none_values(self):
        """Test creating APIClient with None values."""
        client = APIClient(
            api_url=None,
            api_token=None,
        )

        assert client.api_url is None
        assert client.api_token is None


class TestAPIConfiguration:
    """Test API configuration methods."""

    def test_is_configured_true(self):
        """Test is_configured returns True when URL and token are set."""
        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
        )

        assert client.is_configured() is True

    def test_is_configured_missing_url(self):
        """Test is_configured returns False when URL is missing."""
        client = APIClient(
            api_url=None,
            api_token="test-token",
        )

        assert client.is_configured() is False

    def test_is_configured_missing_token(self):
        """Test is_configured returns False when token is missing."""
        client = APIClient(
            api_url="https://api.example.com",
            api_token=None,
        )

        assert client.is_configured() is False

    def test_is_configured_empty_strings(self):
        """Test is_configured returns False for empty strings."""
        client = APIClient(
            api_url="",
            api_token="",
        )

        assert client.is_configured() is False


class TestSyncAPIPosting:
    """Test synchronous API posting."""

    def test_post_run_sync_disabled(self):
        """Test posting when API is disabled."""
        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
            api_enabled=False,
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

        assert success is False
        assert "disabled" in message.lower()

    def test_post_run_sync_not_configured(self):
        """Test posting when API is not configured."""
        client = APIClient(
            api_url=None,
            api_token=None,
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

        assert success is False
        assert "not configured" in message.lower()

    @patch("telemetry.api.httpx")
    def test_post_run_sync_success(self, mock_httpx):
        """Test successful API post."""
        # Mock httpx response
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
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

        assert success is True
        assert "[OK]" in message

    @patch("telemetry.api.httpx")
    def test_post_run_sync_auth_error(self, mock_httpx):
        """Test API post with authentication error."""
        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
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

        assert success is False
        assert "authentication failed" in message.lower()

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_post_run_sync_retry_on_server_error(self, mock_sleep, mock_httpx):
        """Test retry logic on server error."""
        # First 2 attempts fail with 500, third succeeds with 200
        mock_response_500 = MagicMock()
        mock_response_500.status_code = 500

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.side_effect = [
            mock_response_500,
            mock_response_500,
            mock_response_200,
        ]

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
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

        # Should have slept twice (after first 2 failures)
        assert mock_sleep.call_count == 2

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_post_run_sync_max_retries_exceeded(self, mock_sleep, mock_httpx):
        """Test failure after max retries exceeded."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
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

        assert success is False
        assert "failed after 3 attempts" in message.lower()

    @patch("telemetry.api.httpx")
    def test_post_run_sync_timeout(self, mock_httpx):
        """Test handling of timeout error."""
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.side_effect = mock_httpx.TimeoutException()

        mock_httpx.Client.return_value = mock_client
        mock_httpx.TimeoutException = Exception  # Mock the exception class

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
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

        assert success is False
        assert "timeout" in message.lower()

    @patch("telemetry.api.httpx")
    def test_post_run_sync_request_error(self, mock_httpx):
        """Test handling of request error."""
        # Create proper exception classes
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
            api_url="https://api.example.com",
            api_token="test-token",
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

        assert success is False
        assert "request error" in message.lower()

    def test_post_run_sync_httpx_not_installed(self):
        """Test behavior when httpx is not installed."""
        with patch("telemetry.api.httpx", None):
            client = APIClient(
                api_url="https://api.example.com",
                api_token="test-token",
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

            assert success is False
            assert "httpx not installed" in message.lower()


class TestAsyncAPIPosting:
    """Test asynchronous API posting."""

    @pytest.mark.asyncio
    async def test_post_run_async_disabled(self):
        """Test async posting when API is disabled."""
        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
            api_enabled=False,
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = await client.post_run_async(payload)

        assert success is False
        assert "disabled" in message.lower()

    @pytest.mark.asyncio
    @patch("telemetry.api.httpx")
    async def test_post_run_async_success(self, mock_httpx):
        """Test successful async API post."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_response)

        mock_httpx.AsyncClient.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
        )

        payload = APIPayload(
            run_id="test-123",
            agent_name="test_agent",
            job_type="test_job",
            trigger_type="cli",
            start_time=get_iso8601_timestamp(),
            status="success",
        )

        success, message = await client.post_run_async(payload)

        assert success is True
        assert "[OK]" in message


class TestConnectionTesting:
    """Test API connection testing."""

    def test_test_connection_not_configured(self):
        """Test connection test when not configured."""
        client = APIClient(
            api_url=None,
            api_token=None,
        )

        success, message = client.test_connection()

        assert success is False
        assert "not configured" in message.lower()

    def test_test_connection_httpx_not_installed(self):
        """Test connection test when httpx is not installed."""
        with patch("telemetry.api.httpx", None):
            client = APIClient(
                api_url="https://api.example.com",
                api_token="test-token",
            )

            success, message = client.test_connection()

            assert success is False
            assert "httpx not installed" in message.lower()

    @patch("telemetry.api.httpx")
    def test_test_connection_success(self, mock_httpx):
        """Test successful connection test."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
        )

        success, message = client.test_connection()

        assert success is True
        assert "[OK]" in message

    @patch("telemetry.api.httpx")
    def test_test_connection_method_not_allowed(self, mock_httpx):
        """Test connection test with 405 Method Not Allowed (should still pass)."""
        mock_response = MagicMock()
        mock_response.status_code = 405  # Method Not Allowed is OK for GET

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.get.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
        )

        success, message = client.test_connection()

        assert success is True
        assert "[OK]" in message


class TestRetryDelays:
    """Test retry delay configuration."""

    def test_retry_delays_default(self):
        """Test default retry delays."""
        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
        )

        assert client.retry_delays == [1.0, 2.0, 4.0]

    @patch("telemetry.api.httpx")
    @patch("telemetry.api.time.sleep")
    def test_retry_delays_used(self, mock_sleep, mock_httpx):
        """Test that retry delays are used correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=None)
        mock_client.post.return_value = mock_response

        mock_httpx.Client.return_value = mock_client

        client = APIClient(
            api_url="https://api.example.com",
            api_token="test-token",
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
