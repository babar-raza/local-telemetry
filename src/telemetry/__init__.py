"""
Telemetry Platform - Python Package

Multi-agent telemetry collection, storage, and reporting system.

Usage:
    from telemetry import TelemetryClient

    client = TelemetryClient()
    with client.track_run("my_agent", "process") as ctx:
        ctx.log_event("checkpoint", {"step": 1})
        ctx.set_metrics(items_discovered=10)
"""

__version__ = "0.1.0"
__author__ = "Telemetry Platform Team"

# Public API
from .client import TelemetryClient, RunContext
from .config import TelemetryConfig
from .models import RunRecord, RunEvent, APIPayload
from .schema import SCHEMA_VERSION

__all__ = [
    "TelemetryClient",
    "RunContext",
    "TelemetryConfig",
    "RunRecord",
    "RunEvent",
    "APIPayload",
    "SCHEMA_VERSION",
]
