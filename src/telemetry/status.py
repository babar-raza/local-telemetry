"""
Status normalization utilities for telemetry runs.
"""

from typing import Iterable, List, Optional


CANONICAL_STATUSES = [
    "running",
    "success",
    "failure",
    "partial",
    "timeout",
    "cancelled",
]

STATUS_ALIASES = {
    "failed": "failure",
    "completed": "success",
    "succeeded": "success",
    "canceled": "cancelled",
}


def normalize_status(value: Optional[str]) -> Optional[str]:
    """Normalize a status value to canonical form."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    normalized = value.strip().lower()
    if normalized in CANONICAL_STATUSES:
        return normalized
    return STATUS_ALIASES.get(normalized, normalized)


def normalize_status_list(values: Optional[Iterable[str]]) -> List[str]:
    """Normalize a list of status values to canonical form."""
    if not values:
        return []
    return [normalize_status(value) for value in values if value is not None]


def is_valid_status(value: Optional[str]) -> bool:
    """Return True if the status is canonical or an alias."""
    if value is None:
        return False
    normalized = normalize_status(value)
    return normalized in CANONICAL_STATUSES
