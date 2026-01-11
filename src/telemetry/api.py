"""
Telemetry Platform - API Client

Posts telemetry data to Google Sheets API with exponential backoff retry.
"""

import os
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:
    httpx = None  # Will be handled gracefully

from .models import APIPayload


def should_retry(response=None, exception=None):
    """
    Determine if a request should be retried based on response or exception.

    Smart retry logic:
    - 4xx client errors (400-499) → DON'T retry (won't be fixed)
    - 5xx server errors (500-599) → DO retry (might be transient)
    - Connection/timeout errors → DO retry (network issues)

    Args:
        response: HTTP response object (if available)
        exception: Exception object (if raised)

    Returns:
        bool: True if request should be retried, False otherwise
    """
    if exception and httpx:
        # Retry connection errors and timeouts (network issues)
        if isinstance(exception, (httpx.ConnectError, httpx.TimeoutException)):
            return True
        # Retry general request errors (might be transient)
        if isinstance(exception, httpx.RequestError):
            return True
        # Don't retry other exceptions
        return False

    if response:
        # Don't retry 4xx client errors (bad request, won't be fixed)
        if 400 <= response.status_code < 500:
            return False
        # Retry 5xx server errors (might be transient)
        if 500 <= response.status_code < 600:
            return True

    return False


class APIClient:
    """
    Client for posting telemetry data to Google Sheets API.

    Features:
    - Exponential backoff retry (3 attempts)
    - Fire-and-forget behavior (failures don't crash)
    - Synchronous wrapper for non-async agents
    - Respects METRICS_API_ENABLED flag

    Retry delays: 1s, 2s, 4s
    """

    def __init__(
        self,
        google_sheets_api_url: Optional[str],
        api_token: Optional[str],
        google_sheets_api_enabled: bool = False,
        max_retries: int = 3,
        timeout: float = 10.0,
    ):
        """
        Initialize Google Sheets API client.

        Args:
            google_sheets_api_url: Google Sheets/Apps Script API URL
            api_token: API authentication token
            google_sheets_api_enabled: Whether Google Sheets export is enabled
            max_retries: Maximum retry attempts (default: 3)
            timeout: Request timeout in seconds (default: 10.0)
        """
        self.api_url = google_sheets_api_url
        self.api_token = api_token
        self.api_enabled = google_sheets_api_enabled
        self.max_retries = max_retries
        self.timeout = timeout
        # Generate exponential backoff delays dynamically
        self.retry_delays = [2**i for i in range(max_retries)]  # 1s, 2s, 4s, 8s...

    def is_configured(self) -> bool:
        """
        Check if API client is properly configured.
        
        Token is optional when connecting to auth-disabled servers.

        Returns:
            bool: True if URL is set and token requirements are met
        """
        if not self.api_url:
            return False

        # Token required only if auth is enabled
        auth_required_str = os.getenv("METRICS_API_AUTH_REQUIRED", "false").lower()
        auth_required = auth_required_str in ("true", "1", "yes", "on")

        if auth_required and not self.api_token:
            return False

        return True

    def post_run_sync(self, payload: APIPayload) -> tuple[bool, str]:
        """
        Post run data to API (synchronous).

        This is a fire-and-forget operation - failures are logged but don't crash.

        Args:
            payload: APIPayload to post

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Check if API is enabled
        if not self.api_enabled:
            return False, "[SKIP] API posting disabled (METRICS_API_ENABLED=false)"

        # Check if configured
        if not self.is_configured():
            return (
                False,
                "[SKIP] API not configured (missing URL or token)",
            )

        # Check if httpx is available
        if httpx is None:
            return (
                False,
                "[SKIP] httpx not installed (run: pip install httpx)",
            )

        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        payload_dict = payload.to_dict()

        # Retry with exponential backoff
        last_error = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        self.api_url,
                        json=payload_dict,
                        headers=headers,
                    )

                    # Check response status
                    if response.status_code == 200:
                        return True, f"[OK] Posted to API (attempt {attempt + 1})"
                    else:
                        # Use smart retry logic
                        last_error = f"HTTP {response.status_code}"

                        if should_retry(response=response):
                            # Retryable error (5xx server error)
                            if attempt < self.max_retries - 1:
                                delay = self.retry_delays[attempt]
                                logger.warning(
                                    f"API error {response.status_code} (retryable), "
                                    f"attempt {attempt + 1}/{self.max_retries}, "
                                    f"retrying in {delay}s"
                                )
                                time.sleep(delay)
                                continue
                            else:
                                logger.error(
                                    f"API error {response.status_code} failed after {self.max_retries} attempts"
                                )
                                return (
                                    False,
                                    f"[FAIL] API post failed after {self.max_retries} attempts: {last_error}",
                                )
                        else:
                            # Non-retryable error (4xx client error)
                            logger.warning(
                                f"API error {response.status_code} (client error, not retrying)"
                            )
                            return (
                                False,
                                f"[FAIL] API client error {response.status_code} (not retried)",
                            )

            except httpx.TimeoutException as e:
                last_error = "Request timeout"

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(
                        f"API timeout (retryable), attempt {attempt + 1}/{self.max_retries}, "
                        f"retrying in {delay}s"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"API timeout after {self.max_retries} attempts")
                    return (
                        False,
                        f"[FAIL] API timeout after {self.max_retries} attempts",
                    )

            except httpx.RequestError as e:
                last_error = str(e)

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(
                        f"API request error (retryable), attempt {attempt + 1}/{self.max_retries}, "
                        f"retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(f"API request error after {self.max_retries} attempts: {e}")
                    return (
                        False,
                        f"[FAIL] API request error: {e}",
                    )

            except Exception as e:
                # Unexpected error - don't retry
                return False, f"[FAIL] Unexpected API error: {e}"

        # Should not reach here, but just in case
        return (
            False,
            f"[FAIL] API post failed: {last_error}",
        )

    async def post_run_async(self, payload: APIPayload) -> tuple[bool, str]:
        """
        Post run data to API (asynchronous).

        This is a fire-and-forget operation - failures are logged but don't crash.

        Args:
            payload: APIPayload to post

        Returns:
            Tuple of (success: bool, message: str)
        """
        # Check if API is enabled
        if not self.api_enabled:
            return False, "[SKIP] API posting disabled (METRICS_API_ENABLED=false)"

        # Check if configured
        if not self.is_configured():
            return (
                False,
                "[SKIP] API not configured (missing URL or token)",
            )

        # Check if httpx is available
        if httpx is None:
            return (
                False,
                "[SKIP] httpx not installed (run: pip install httpx)",
            )

        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        payload_dict = payload.to_dict()

        # Retry with exponential backoff
        last_error = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.api_url,
                        json=payload_dict,
                        headers=headers,
                    )

                    # Check response status
                    if response.status_code == 200:
                        return True, f"[OK] Posted to API (attempt {attempt + 1})"
                    else:
                        # Use smart retry logic
                        last_error = f"HTTP {response.status_code}"

                        if should_retry(response=response):
                            # Retryable error (5xx server error)
                            if attempt < self.max_retries - 1:
                                delay = self.retry_delays[attempt]
                                logger.warning(
                                    f"API error {response.status_code} (retryable), "
                                    f"attempt {attempt + 1}/{self.max_retries}, "
                                    f"retrying in {delay}s"
                                )
                                await self._async_sleep(delay)
                                continue
                            else:
                                logger.error(
                                    f"API error {response.status_code} failed after {self.max_retries} attempts"
                                )
                                return (
                                    False,
                                    f"[FAIL] API post failed after {self.max_retries} attempts: {last_error}",
                                )
                        else:
                            # Non-retryable error (4xx client error)
                            logger.warning(
                                f"API error {response.status_code} (client error, not retrying)"
                            )
                            return (
                                False,
                                f"[FAIL] API client error {response.status_code} (not retried)",
                            )

            except httpx.TimeoutException as e:
                last_error = "Request timeout"

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(
                        f"API timeout (retryable), attempt {attempt + 1}/{self.max_retries}, "
                        f"retrying in {delay}s"
                    )
                    await self._async_sleep(delay)
                    continue
                else:
                    logger.error(f"API timeout after {self.max_retries} attempts")
                    return (
                        False,
                        f"[FAIL] API timeout after {self.max_retries} attempts",
                    )

            except httpx.RequestError as e:
                last_error = str(e)

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    logger.warning(
                        f"API request error (retryable), attempt {attempt + 1}/{self.max_retries}, "
                        f"retrying in {delay}s: {e}"
                    )
                    await self._async_sleep(delay)
                    continue
                else:
                    logger.error(f"API request error after {self.max_retries} attempts: {e}")
                    return (
                        False,
                        f"[FAIL] API request error: {e}",
                    )

            except Exception as e:
                # Unexpected error - don't retry
                return False, f"[FAIL] Unexpected API error: {e}"

        # Should not reach here, but just in case
        return (
            False,
            f"[FAIL] API post failed: {last_error}",
        )

    async def _async_sleep(self, seconds: float):
        """
        Async sleep helper.

        Args:
            seconds: Seconds to sleep
        """
        import asyncio

        await asyncio.sleep(seconds)

    def test_connection(self) -> tuple[bool, str]:
        """
        Test API connection with a minimal request.

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not self.is_configured():
            return False, "[FAIL] API not configured"

        if httpx is None:
            return False, "[FAIL] httpx not installed"

        try:
            with httpx.Client(timeout=5.0) as client:
                # Simple GET request to check connectivity
                response = client.get(self.api_url)

                if response.status_code in (200, 405):  # 405 = Method Not Allowed is OK
                    return True, "[OK] API endpoint reachable"
                else:
                    return (
                        False,
                        f"[FAIL] API returned status {response.status_code}",
                    )

        except Exception as e:
            return False, f"[FAIL] API connection test failed: {e}"
