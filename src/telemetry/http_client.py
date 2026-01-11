"""
HTTP API Client for posting telemetry events to the centralized telemetry API service.

This client replaces direct database writes with HTTP POSTs to the API service,
which enforces the single-writer pattern and prevents database corruption.
"""

import requests
import logging
from typing import Dict, Any, List, Optional
import time

logger = logging.getLogger(__name__)


class HTTPAPIClient:
    """
    Client for posting telemetry events to HTTP API service.

    The API service enforces single-writer pattern and handles all database writes.
    This client provides:
    - Single event POST
    - Batch event POST
    - Health checks
    - Error handling and retries
    """

    def __init__(
        self,
        api_url: str,
        timeout: int = 10,
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize HTTP API client.

        Args:
            api_url: Base URL of telemetry API (e.g., http://localhost:8765)
            timeout: Request timeout in seconds (default: 10)
            max_retries: Maximum retry attempts for transient errors (default: 3)
            retry_delay: Delay between retries in seconds (default: 1.0)
        """
        self.api_url = api_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        logger.info(f"HTTPAPIClient initialized: {self.api_url}")

    def post_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST single telemetry event to API.

        Args:
            event: Event dictionary (must include event_id, run_id, etc.)

        Returns:
            API response dict with keys: status, event_id, run_id
            status can be: 'created', 'duplicate', 'error'

        Raises:
            APIUnavailableError: API is down or unreachable
            APIValidationError: Event validation failed (400 Bad Request)
            APIError: Other API errors
        """
        endpoint = f"{self.api_url}/api/v1/runs"

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    endpoint,
                    json=event,
                    timeout=self.timeout
                )

                # Handle success (201, 200)
                if response.status_code in (200, 201):
                    result = response.json()

                    if result['status'] == 'duplicate':
                        logger.debug(
                            f"Event {event.get('event_id', 'N/A')} already exists (idempotent)"
                        )
                    else:
                        logger.info(
                            f"Event {event.get('event_id', 'N/A')} created successfully"
                        )

                    return result

                # Handle validation errors (400)
                elif response.status_code == 400:
                    error_text = response.text
                    logger.error(f"Event validation failed: {error_text}")
                    raise APIValidationError(f"Invalid event: {error_text}")

                # Handle other errors
                else:
                    response.raise_for_status()

            except requests.exceptions.ConnectionError as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"API unavailable after {self.max_retries} attempts: {e}")
                    raise APIUnavailableError(
                        f"Cannot reach telemetry API at {endpoint}"
                    ) from e

            except requests.exceptions.Timeout as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Timeout (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"API timeout after {self.max_retries} attempts: {e}")
                    raise APIUnavailableError(
                        f"Telemetry API timeout: {endpoint}"
                    ) from e

            except requests.exceptions.HTTPError as e:
                logger.error(
                    f"API HTTP error {e.response.status_code}: {e.response.text}"
                )
                raise APIError(f"API error: {e}") from e

            except Exception as e:
                logger.error(f"Unexpected error posting event: {e}")
                raise APIError(f"Unexpected API error: {e}") from e

        # Should not reach here
        raise APIUnavailableError(f"Failed to post event after {self.max_retries} attempts")

    def patch_event(self, event_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        PATCH existing telemetry event to update fields.

        Used by end_run() to update status, end_time, duration, items, etc.

        Args:
            event_id: Unique event ID to update
            update_data: Dictionary with fields to update (status, end_time, etc.)

        Returns:
            API response dict with keys: event_id, updated, fields_updated

        Raises:
            APIUnavailableError: API is down or unreachable
            APIValidationError: Update validation failed (400 Bad Request)
            APIError: Other API errors (404 Not Found, 500 Server Error)
        """
        endpoint = f"{self.api_url}/api/v1/runs/{event_id}"

        for attempt in range(self.max_retries):
            try:
                response = self.session.patch(
                    endpoint,
                    json=update_data,
                    timeout=self.timeout
                )

                # Handle success (200)
                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"Event {event_id} updated successfully: {result.get('fields_updated', [])}"
                    )
                    return result

                # Handle not found (404)
                elif response.status_code == 404:
                    error_text = response.text
                    logger.error(f"Event not found: {event_id}")
                    raise APIValidationError(f"Event not found: {event_id}")

                # Handle validation errors (400)
                elif response.status_code == 400:
                    error_text = response.text
                    logger.error(f"Update validation failed: {error_text}")
                    raise APIValidationError(f"Invalid update: {error_text}")

                # Handle other errors
                else:
                    response.raise_for_status()

            except requests.exceptions.ConnectionError as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"API unavailable after {self.max_retries} attempts: {e}")
                    raise APIUnavailableError(
                        f"Cannot reach telemetry API at {endpoint}"
                    ) from e

            except requests.exceptions.Timeout as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Timeout (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"API timeout after {self.max_retries} attempts: {e}")
                    raise APIUnavailableError(
                        f"Telemetry API timeout: {endpoint}"
                    ) from e

            except requests.exceptions.HTTPError as e:
                logger.error(
                    f"API HTTP error {e.response.status_code}: {e.response.text}"
                )
                raise APIError(f"API error: {e}") from e

            except Exception as e:
                logger.error(f"Unexpected error updating event: {e}")
                raise APIError(f"Unexpected API error: {e}") from e

        # Should not reach here
        raise APIUnavailableError(f"Failed to update event after {self.max_retries} attempts")

    def post_batch(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        POST batch of telemetry events to API.

        Args:
            events: List of event dictionaries

        Returns:
            API response dict with keys:
            - inserted: Number of new events inserted
            - duplicates: Number of duplicate events (idempotent)
            - errors: List of error details
            - total: Total events in batch

        Raises:
            APIUnavailableError: API is down or unreachable
            APIError: API errors
        """
        endpoint = f"{self.api_url}/api/v1/runs/batch"

        if not events:
            logger.warning("Empty batch, nothing to POST")
            return {"inserted": 0, "duplicates": 0, "errors": [], "total": 0}

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    endpoint,
                    json=events,
                    timeout=self.timeout * 2  # Longer timeout for batch
                )

                # Handle success
                if response.status_code in (200, 201):
                    result = response.json()

                    logger.info(
                        f"Batch POST: {result['inserted']} inserted, "
                        f"{result['duplicates']} duplicates, "
                        f"{len(result['errors'])} errors"
                    )

                    # Log errors if any
                    if result['errors']:
                        for error in result['errors']:
                            logger.warning(f"Batch error: {error}")

                    return result

                # Handle errors
                else:
                    response.raise_for_status()

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Batch API error (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"Batch API unavailable after {self.max_retries} attempts: {e}")
                    raise APIUnavailableError(
                        f"Cannot reach batch API at {endpoint}"
                    ) from e

            except requests.exceptions.HTTPError as e:
                logger.error(f"Batch API HTTP error: {e.response.text}")
                raise APIError(f"Batch API error: {e}") from e

            except Exception as e:
                logger.error(f"Unexpected error posting batch: {e}")
                raise APIError(f"Unexpected batch API error: {e}") from e

        # Should not reach here
        raise APIUnavailableError(
            f"Failed to post batch after {self.max_retries} attempts"
        )

    def check_health(self) -> bool:
        """
        Check if API is healthy and reachable.

        Returns:
            True if API is healthy, False otherwise
        """
        try:
            response = self.session.get(
                f"{self.api_url}/health",
                timeout=5
            )
            response.raise_for_status()
            health = response.json()
            is_healthy = health.get('status') == 'ok'

            if is_healthy:
                logger.debug("API health check: OK")
            else:
                logger.warning(f"API health check failed: {health}")

            return is_healthy

        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    def get_metrics(self) -> Optional[Dict[str, Any]]:
        """
        Get current telemetry metrics from API.

        Returns:
            Metrics dict with keys: total_runs, agents, recent_24h, performance
            None if API is unavailable
        """
        try:
            response = self.session.get(
                f"{self.api_url}/metrics",
                timeout=5
            )
            response.raise_for_status()
            metrics = response.json()
            logger.debug(f"Retrieved metrics: {metrics.get('total_runs', 0)} total runs")
            return metrics

        except Exception as e:
            logger.debug(f"Failed to get metrics: {e}")
            return None

    def associate_commit(
        self,
        event_id: str,
        commit_hash: str,
        commit_source: str,
        commit_author: Optional[str] = None,
        commit_timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Associate a git commit with a telemetry run via HTTP API.

        Args:
            event_id: Event ID of the run
            commit_hash: Git commit SHA (7-40 hex characters)
            commit_source: How commit was created ('manual', 'llm', 'ci')
            commit_author: Optional author string (e.g., "Name <email>")
            commit_timestamp: Optional ISO8601 timestamp

        Returns:
            Response dict with status, event_id, run_id, commit_hash

        Raises:
            APIValidationError: Invalid commit data (400/422)
            APIUnavailableError: API unreachable
            APIError: Server error (404/500)
        """
        endpoint = f"{self.api_url}/api/v1/runs/{event_id}/associate-commit"

        payload = {
            "commit_hash": commit_hash,
            "commit_source": commit_source,
        }

        if commit_author:
            payload["commit_author"] = commit_author
        if commit_timestamp:
            payload["commit_timestamp"] = commit_timestamp

        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    endpoint,
                    json=payload,
                    timeout=self.timeout
                )

                # Handle success (200)
                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"Commit {commit_hash} associated with {event_id}"
                    )
                    return result

                # Handle not found (404)
                elif response.status_code == 404:
                    logger.error(f"Run not found: {event_id}")
                    raise APIValidationError(f"Run not found: {event_id}")

                # Handle validation errors (422)
                elif response.status_code == 422:
                    error_text = response.text
                    logger.error(f"Validation failed: {error_text}")
                    raise APIValidationError(f"Invalid commit data: {error_text}")

                # Handle other errors
                else:
                    response.raise_for_status()

            except requests.exceptions.ConnectionError as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Connection error (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"API unavailable after {self.max_retries} attempts: {e}")
                    raise APIUnavailableError(
                        f"Cannot reach telemetry API at {endpoint}"
                    ) from e

            except requests.exceptions.Timeout as e:
                if attempt < self.max_retries - 1:
                    logger.warning(
                        f"Timeout (attempt {attempt + 1}/{self.max_retries}): {e}"
                    )
                    time.sleep(self.retry_delay)
                    continue
                else:
                    logger.error(f"API timeout after {self.max_retries} attempts: {e}")
                    raise APIUnavailableError(
                        f"Telemetry API timeout: {endpoint}"
                    ) from e

            except requests.exceptions.HTTPError as e:
                logger.error(
                    f"API HTTP error {e.response.status_code}: {e.response.text}"
                )
                raise APIError(f"API error: {e}") from e

            except Exception as e:
                logger.error(f"Unexpected error associating commit: {e}")
                raise APIError(f"Unexpected API error: {e}") from e

        # Should not reach here
        raise APIUnavailableError(f"Failed to associate commit after {self.max_retries} attempts")

    def close(self):
        """Close the HTTP session."""
        self.session.close()
        logger.debug("HTTP session closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False


class APIUnavailableError(Exception):
    """
    API is down or unreachable.

    This error indicates the event should be buffered locally for later retry.
    """
    pass


class APIValidationError(Exception):
    """
    Event validation failed (400 Bad Request).

    This error indicates the event data is invalid and should not be retried.
    """
    pass


class APIError(Exception):
    """
    General API error (5xx or unexpected errors).

    This error may be transient and could be retried.
    """
    pass
