"""
Cleanup Helper for Stale Telemetry Runs

This module provides utilities for cleaning up stale telemetry records that remain
in "running" state due to agent crashes or forceful termination.

Usage:
    from telemetry.helpers.cleanup_stale_runs import cleanup_stale_runs

    # Clean up on application startup
    cleanup_stale_runs(
        api_url="http://localhost:8765",
        agent_name="hugo-translator",
        stale_threshold_hours=1
    )
"""

import requests
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def cleanup_stale_runs(
    api_url: str,
    agent_name: str,
    stale_threshold_hours: int = 1,
    status_to_check: str = "running",
    cleanup_status: str = "cancelled",
    auth_token: Optional[str] = None,
    timeout: int = 30
) -> Dict[str, Any]:
    """
    Clean up stale telemetry runs that have been in 'running' state for too long.

    This function queries the telemetry API for runs matching the specified criteria,
    identifies those older than the stale threshold, and marks them as cancelled.

    Args:
        api_url: Base URL of the telemetry API (e.g., "http://localhost:8765")
        agent_name: Name of the agent to clean up (e.g., "hugo-translator")
        stale_threshold_hours: Hours before a run is considered stale (default: 1)
        status_to_check: Status to search for (default: "running")
        cleanup_status: Status to set for stale runs (default: "cancelled")
        auth_token: Optional bearer token for authenticated requests
        timeout: Request timeout in seconds (default: 30)

    Returns:
        Dict containing cleanup statistics:
        {
            "found": int,           # Number of stale runs found
            "cleaned": int,         # Number successfully cleaned up
            "failed": int,          # Number that failed to clean
            "errors": List[str],    # Error messages if any
            "stale_runs": List[Dict]  # Details of stale runs found
        }

    Example:
        >>> result = cleanup_stale_runs(
        ...     api_url="http://localhost:8765",
        ...     agent_name="hugo-translator",
        ...     stale_threshold_hours=1
        ... )
        >>> print(f"Cleaned up {result['cleaned']} stale runs")
    """
    result = {
        "found": 0,
        "cleaned": 0,
        "failed": 0,
        "errors": [],
        "stale_runs": []
    }

    # Calculate stale threshold timestamp
    stale_threshold = datetime.now(timezone.utc) - timedelta(hours=stale_threshold_hours)
    created_before = stale_threshold.isoformat()

    logger.info(
        f"Searching for stale {status_to_check} runs "
        f"(agent={agent_name}, threshold={stale_threshold_hours}h)"
    )

    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    # Step 1: Query for stale runs
    try:
        query_url = f"{api_url}/api/v1/runs"
        params = {
            "agent_name": agent_name,
            "status": status_to_check,
            "created_before": created_before,
            "limit": 1000  # Adjust if needed
        }

        logger.debug(f"Querying: {query_url} with params={params}")
        response = requests.get(
            query_url,
            params=params,
            headers=headers if auth_token else None,
            timeout=timeout
        )
        response.raise_for_status()

        stale_runs = response.json()
        result["found"] = len(stale_runs)
        result["stale_runs"] = stale_runs

        logger.info(f"Found {result['found']} stale runs to clean up")

        if result["found"] == 0:
            logger.info("No stale runs found - cleanup complete")
            return result

    except requests.RequestException as e:
        error_msg = f"Failed to query stale runs: {str(e)}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        return result

    # Step 2: Clean up each stale run
    for run in stale_runs:
        event_id = run.get("event_id")
        run_id = run.get("run_id")
        created_at = run.get("created_at")

        if not event_id:
            result["failed"] += 1
            result["errors"].append(f"Run missing event_id: {run_id}")
            continue

        try:
            # Prepare update payload
            update_url = f"{api_url}/api/v1/runs/{event_id}"
            update_data = {
                "status": cleanup_status,
                "end_time": datetime.now(timezone.utc).isoformat(),
                "error_summary": f"Stale run cleaned up on startup (created at {created_at})",
                "output_summary": f"Process did not complete - marked as {cleanup_status} on restart"
            }

            logger.debug(f"Updating run {event_id} ({run_id}) to {cleanup_status}")
            response = requests.patch(
                update_url,
                json=update_data,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()

            result["cleaned"] += 1
            logger.info(f"✓ Cleaned up stale run: {run_id} (event_id={event_id})")

        except requests.RequestException as e:
            result["failed"] += 1
            error_msg = f"Failed to update run {event_id}: {str(e)}"
            logger.error(error_msg)
            result["errors"].append(error_msg)

    # Summary logging
    logger.info(
        f"Cleanup complete: {result['cleaned']} cleaned, "
        f"{result['failed']} failed, {result['found']} total"
    )

    return result


def cleanup_on_startup(
    api_url: str = "http://localhost:8765",
    agent_name: Optional[str] = None,
    stale_threshold_hours: int = 1,
    auth_token: Optional[str] = None
) -> bool:
    """
    Convenience function for cleaning up stale runs on application startup.

    This is a simplified wrapper around cleanup_stale_runs() that:
    - Logs results clearly
    - Returns a simple success/failure boolean
    - Handles missing agent_name gracefully

    Args:
        api_url: Base URL of the telemetry API
        agent_name: Name of the agent (if None, must be set by caller)
        stale_threshold_hours: Hours before a run is considered stale
        auth_token: Optional bearer token for authenticated requests

    Returns:
        bool: True if cleanup succeeded without errors, False otherwise

    Example:
        >>> import logging
        >>> logging.basicConfig(level=logging.INFO)
        >>> success = cleanup_on_startup(
        ...     agent_name="hugo-translator",
        ...     stale_threshold_hours=2
        ... )
        >>> if not success:
        ...     print("Warning: Some stale runs could not be cleaned up")
    """
    if not agent_name:
        logger.error("agent_name is required for cleanup")
        return False

    logger.info("=" * 60)
    logger.info("Starting stale run cleanup")
    logger.info(f"Agent: {agent_name}")
    logger.info(f"API URL: {api_url}")
    logger.info(f"Stale threshold: {stale_threshold_hours} hours")
    logger.info("=" * 60)

    try:
        result = cleanup_stale_runs(
            api_url=api_url,
            agent_name=agent_name,
            stale_threshold_hours=stale_threshold_hours,
            auth_token=auth_token
        )

        # Log detailed results
        if result["errors"]:
            logger.warning(f"Cleanup completed with {len(result['errors'])} errors:")
            for error in result["errors"]:
                logger.warning(f"  - {error}")

        # Return success if no failures
        success = result["failed"] == 0
        if success:
            logger.info("✓ Stale run cleanup completed successfully")
        else:
            logger.warning(f"⚠ Cleanup completed with {result['failed']} failures")

        return success

    except Exception as e:
        logger.error(f"Cleanup failed with unexpected error: {e}", exc_info=True)
        return False


# CLI usage example
if __name__ == "__main__":
    import argparse
    import sys

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Clean up stale telemetry runs"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8765",
        help="Telemetry API URL (default: http://localhost:8765)"
    )
    parser.add_argument(
        "--agent-name",
        required=True,
        help="Agent name to clean up (e.g., hugo-translator)"
    )
    parser.add_argument(
        "--stale-threshold-hours",
        type=int,
        default=1,
        help="Hours before a run is considered stale (default: 1)"
    )
    parser.add_argument(
        "--auth-token",
        help="Bearer token for authenticated requests (optional)"
    )

    args = parser.parse_args()

    # Run cleanup
    success = cleanup_on_startup(
        api_url=args.api_url,
        agent_name=args.agent_name,
        stale_threshold_hours=args.stale_threshold_hours,
        auth_token=args.auth_token
    )

    # Exit with appropriate code
    sys.exit(0 if success else 1)
