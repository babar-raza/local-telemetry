"""
Telemetry Platform - API Client

Posts telemetry data to Google Sheets API with exponential backoff retry.
"""

import time
from typing import Dict, Any, Optional

try:
    import httpx
except ImportError:
    httpx = None  # Will be handled gracefully

from .models import APIPayload


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
        api_url: Optional[str],
        api_token: Optional[str],
        api_enabled: bool = True,
        max_retries: int = 3,
        timeout: float = 10.0,
    ):
        """
        Initialize API client.

        Args:
            api_url: Google Apps Script API URL
            api_token: API authentication token
            api_enabled: Whether API posting is enabled
            max_retries: Maximum retry attempts (default: 3)
            timeout: Request timeout in seconds (default: 10.0)
        """
        self.api_url = api_url
        self.api_token = api_token
        self.api_enabled = api_enabled
        self.max_retries = max_retries
        self.timeout = timeout
        self.retry_delays = [1.0, 2.0, 4.0]  # 1s, 2s, 4s

    def is_configured(self) -> bool:
        """
        Check if API client is properly configured.

        Returns:
            bool: True if URL and token are set
        """
        return bool(self.api_url and self.api_token)

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
                    elif response.status_code in (401, 403):
                        # Authentication error - don't retry
                        return (
                            False,
                            f"[FAIL] API authentication failed: {response.status_code}",
                        )
                    else:
                        # Server error - retry
                        last_error = f"HTTP {response.status_code}"

                        if attempt < self.max_retries - 1:
                            delay = self.retry_delays[attempt]
                            time.sleep(delay)
                            continue
                        else:
                            return (
                                False,
                                f"[FAIL] API post failed after {self.max_retries} attempts: {last_error}",
                            )

            except httpx.TimeoutException:
                last_error = "Request timeout"

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    time.sleep(delay)
                    continue
                else:
                    return (
                        False,
                        f"[FAIL] API timeout after {self.max_retries} attempts",
                    )

            except httpx.RequestError as e:
                last_error = str(e)

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    time.sleep(delay)
                    continue
                else:
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
                    elif response.status_code in (401, 403):
                        # Authentication error - don't retry
                        return (
                            False,
                            f"[FAIL] API authentication failed: {response.status_code}",
                        )
                    else:
                        # Server error - retry
                        last_error = f"HTTP {response.status_code}"

                        if attempt < self.max_retries - 1:
                            delay = self.retry_delays[attempt]
                            await self._async_sleep(delay)
                            continue
                        else:
                            return (
                                False,
                                f"[FAIL] API post failed after {self.max_retries} attempts: {last_error}",
                            )

            except httpx.TimeoutException:
                last_error = "Request timeout"

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    await self._async_sleep(delay)
                    continue
                else:
                    return (
                        False,
                        f"[FAIL] API timeout after {self.max_retries} attempts",
                    )

            except httpx.RequestError as e:
                last_error = str(e)

                if attempt < self.max_retries - 1:
                    delay = self.retry_delays[attempt]
                    await self._async_sleep(delay)
                    continue
                else:
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
