#!/usr/bin/env python3
"""Utility functions and API client for the Telemetry Dashboard."""

import os
import requests
import json
from typing import Dict, List, Optional, Any


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
        status: Optional[str] = None,
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
    return status in ["running", "success", "failed", "partial", "timeout", "cancelled"]


def validate_json(json_str: str) -> tuple[bool, str]:
    """Validate JSON string."""
    try:
        json.loads(json_str)
        return True, ""
    except json.JSONDecodeError as e:
        return False, str(e)
