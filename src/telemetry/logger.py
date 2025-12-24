"""Structured logging for telemetry service."""
import logging
import json
import time
from typing import Any, Dict, Optional
from contextlib import contextmanager
import os

# Configure log level from environment (default: INFO)
LOG_LEVEL = os.getenv("TELEMETRY_LOG_LEVEL", "INFO").upper()

# Create logger
logger = logging.getLogger("telemetry_api")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

# JSON formatter for structured logging
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data)

# Console handler with JSON formatting
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)


def log_request(endpoint: str, method: str, **kwargs):
    """Log API request with structured data."""
    logger.info(f"{method} {endpoint}", extra={
        "extra_fields": {
            "endpoint": endpoint,
            "method": method,
            **kwargs
        }
    })


def log_query(query_params: Dict[str, Any], result_count: int, duration_ms: float):
    """Log query endpoint with performance metrics."""
    logger.info("Query executed", extra={
        "extra_fields": {
            "endpoint": "/api/v1/runs",
            "query_params": query_params,
            "result_count": result_count,
            "duration_ms": round(duration_ms, 2),
            "is_slow": duration_ms > 1000,  # Flag slow queries (>1s)
        }
    })


def log_update(event_id: str, fields_updated: list, duration_ms: float, success: bool):
    """Log PATCH update with audit trail."""
    logger.info("Run updated" if success else "Update failed", extra={
        "extra_fields": {
            "endpoint": "/api/v1/runs/{event_id}",
            "event_id": event_id,
            "fields_updated": fields_updated,
            "duration_ms": round(duration_ms, 2),
            "success": success,
        }
    })


def log_error(endpoint: str, error_type: str, error_message: str, **context):
    """Log error with context."""
    logger.error(f"Error in {endpoint}: {error_message}", extra={
        "extra_fields": {
            "endpoint": endpoint,
            "error_type": error_type,
            "error_message": error_message[:500],  # Truncate long errors
            **context
        }
    })


@contextmanager
def track_duration():
    """Context manager to track operation duration."""
    start_time = time.time()
    try:
        yield lambda: (time.time() - start_time) * 1000  # Return duration in ms
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        raise
