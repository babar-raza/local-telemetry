#!/usr/bin/env python3
"""Utility functions and API client for the Telemetry Dashboard."""

import os
import requests
import json
from typing import Dict, List, Optional, Any

from telemetry.status import CANONICAL_STATUSES, normalize_status


# ============================================================================
# API Client
# ============================================================================

class TelemetryAPIClient:
    """Client for interacting with the Telemetry FastAPI service."""

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or os.environ.get("TELEMETRY_API_URL", "http://localhost:8765")

    def health_check(self) -> bool:
        """Check if API is reachable."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            return response.status_code == 200
        except Exception:
            return False

    def get_runs(
        self,
        agent_name: Optional[str] = None,
        status: Optional[List[str]] = None,
        job_type: Optional[str] = None,
        run_id_contains: Optional[str] = None,
        parent_run_id: Optional[str] = None,
        exclude_job_type: Optional[str] = None,
        created_before: Optional[str] = None,
        created_after: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Query runs with filters."""
        params = {
            "limit": limit,
            "offset": offset
        }
        if agent_name:
            params["agent_name"] = agent_name
        if status:
            params["status"] = status
        if job_type:
            params["job_type"] = job_type
        if run_id_contains:
            params["run_id_contains"] = run_id_contains
        if parent_run_id:
            params["parent_run_id"] = parent_run_id
        if exclude_job_type:
            params["exclude_job_type"] = exclude_job_type
        if created_before:
            params["created_before"] = created_before
        if created_after:
            params["created_after"] = created_after

        response = requests.get(f"{self.base_url}/api/v1/runs", params=params)
        response.raise_for_status()
        return response.json()

    def update_run(self, event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update run via PATCH endpoint."""
        # Remove None values (don't update fields not changed)
        payload = {k: v for k, v in updates.items() if v is not None}

        response = requests.patch(
            f"{self.base_url}/api/v1/runs/{event_id}",
            json=payload
        )
        response.raise_for_status()
        return response.json()

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata including distinct agent names and job types."""
        response = requests.get(f"{self.base_url}/api/v1/metadata")
        response.raise_for_status()
        return response.json()


# ============================================================================
# Utility Functions
# ============================================================================

def format_duration(duration_ms: Optional[int]) -> str:
    """Format duration_ms as human-readable string."""
    if duration_ms is None:
        return "N/A"
    seconds = duration_ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds/60:.1f}m"
    else:
        return f"{seconds/3600:.1f}h"


def truncate_text(text: Optional[str], max_length: int = 50) -> str:
    """Truncate text to max_length with ellipsis."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def validate_status(status: str) -> bool:
    """Validate status enum."""
    return normalize_status(status) in CANONICAL_STATUSES


def validate_json(json_str: str) -> tuple[bool, str]:
    """Validate JSON string."""
    try:
        json.loads(json_str)
        return True, ""
    except json.JSONDecodeError as e:
        return False, str(e)


def safe_get(record: Dict, key: str, default: Any = None) -> Any:
    """Safely get value from dict with null/missing handling."""
    value = record.get(key, default)
    return value if value is not None else default


def validate_record(record: Dict) -> tuple[bool, List[str]]:
    """Validate record has minimum required fields."""
    errors = []
    required = ["event_id", "run_id", "agent_name", "status"]
    for field in required:
        if not record.get(field):
            errors.append(f"Missing required field: {field}")
    return len(errors) == 0, errors
