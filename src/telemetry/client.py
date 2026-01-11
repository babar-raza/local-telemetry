"""
Telemetry Platform - Main Client

TelemetryClient provides the public API for agent telemetry instrumentation.
"""

import json
import logging
import platform
import threading
from contextlib import contextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Database schema constraints
# See: docs/schema_constraints.md for full documentation
# Note: Database schema (TEXT) allows unlimited length, but we enforce
# a practical limit for file system compatibility and performance
MAX_RUN_ID_LENGTH = 255

from .config import TelemetryConfig
from .models import (
    RunRecord,
    RunEvent,
    APIPayload,
    generate_run_id,
    get_iso8601_timestamp,
    calculate_duration_ms,
)
from .local import NDJSONWriter
from .database import DatabaseWriter  # Kept for backward compatibility (reads only)
from .api import APIClient  # Google Sheets API (external)
from .http_client import HTTPAPIClient, APIUnavailableError, APIValidationError, APIError  # Telemetry HTTP API
from .buffer import BufferFile  # Local buffer for failover
from .git_detector import GitDetector  # GT-01: Automatic Git detection
from pathlib import Path
from .status import CANONICAL_STATUSES, normalize_status


class RunIDMetrics:
    """
    In-memory metrics for run_id tracking and validation.

    Tracks:
    - Custom vs generated run_id usage
    - Validation rejection reasons
    - Duplicate detection

    Thread-safe via threading.Lock for concurrent access.
    """

    def __init__(self):
        """Initialize metrics counters."""
        self._lock = threading.Lock()

        # Run ID source counters
        self.custom_accepted = 0      # Custom run_ids that passed validation
        self.generated = 0            # Auto-generated run_ids used

        # Validation rejection counters (by reason)
        self.rejected_empty = 0       # Rejected: empty or whitespace-only
        self.rejected_too_long = 0    # Rejected: > 255 characters
        self.rejected_invalid_chars = 0  # Rejected: path separators or null bytes

        # Duplicate detection
        self.duplicates_detected = 0  # Duplicate run_ids found in active registry

    def increment_custom_accepted(self):
        """Increment custom run_id accepted counter."""
        with self._lock:
            self.custom_accepted += 1

    def increment_generated(self):
        """Increment generated run_id counter."""
        with self._lock:
            self.generated += 1

    def increment_rejected_empty(self):
        """Increment empty/whitespace rejection counter."""
        with self._lock:
            self.rejected_empty += 1

    def increment_rejected_too_long(self):
        """Increment too-long rejection counter."""
        with self._lock:
            self.rejected_too_long += 1

    def increment_rejected_invalid_chars(self):
        """Increment invalid-chars rejection counter."""
        with self._lock:
            self.rejected_invalid_chars += 1

    def increment_duplicates(self):
        """Increment duplicate detection counter."""
        with self._lock:
            self.duplicates_detected += 1

    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get thread-safe snapshot of current metrics.

        Returns:
            Dictionary with all metrics in structured format
        """
        with self._lock:
            total_rejected = (
                self.rejected_empty +
                self.rejected_too_long +
                self.rejected_invalid_chars
            )
            total_runs = self.custom_accepted + self.generated

            # Calculate percentage (avoid division by zero)
            custom_percentage = 0.0
            if total_runs > 0:
                custom_percentage = round((self.custom_accepted / total_runs) * 100, 2)

            return {
                "run_id_metrics": {
                    "custom_accepted": self.custom_accepted,
                    "generated": self.generated,
                    "rejected": {
                        "empty": self.rejected_empty,
                        "too_long": self.rejected_too_long,
                        "invalid_chars": self.rejected_invalid_chars,
                        "total": total_rejected,
                    },
                    "duplicates_detected": self.duplicates_detected,
                    "total_runs": total_runs,
                    "custom_percentage": custom_percentage,
                },
                "timestamp": get_iso8601_timestamp(),
            }

    def to_json(self) -> str:
        """
        Get metrics snapshot as formatted JSON string.

        Returns:
            JSON string with metrics
        """
        return json.dumps(self.get_snapshot(), indent=2)

    def log_metrics(self):
        """Log current metrics to logger as structured JSON."""
        try:
            metrics_json = self.to_json()
            logger.info(f"Run ID Metrics:\n{metrics_json}")
        except Exception as e:
            logger.warning(f"Failed to log metrics: {e}")


class RunContext:
    """
    Context object yielded by track_run() context manager.

    Provides methods for logging events and updating metrics during a run.
    """

    def __init__(
        self,
        run_id: str,
        record: RunRecord,
        client: "TelemetryClient",
    ):
        """
        Initialize run context.

        Args:
            run_id: Unique run ID
            record: RunRecord for this run
            client: TelemetryClient instance
        """
        self.run_id = run_id
        self._record = record
        self._client = client

    def log_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None):
        """
        Log an event during the run.

        Args:
            event_type: Type of event (e.g., "checkpoint", "error", "info")
            payload: Optional dictionary with event data
        """
        self._client.log_event(self.run_id, event_type, payload)

    def set_metrics(self, **kwargs):
        """
        Update run metrics.

        Args:
            **kwargs: Metric values to update (e.g., items_discovered=10)

        Supported metrics:
            - items_discovered
            - items_succeeded
            - items_failed
            - input_summary
            - output_summary
            - error_summary
            - metrics_json (flexible JSON for ANY custom metrics)
            - insight_id (links action runs to originating insights)
            - product
            - platform
            - website (API spec: root domain e.g., "aspose.com")
            - website_section (API spec: subdomain e.g., "products", "docs")
            - item_name (API spec: specific page/entity e.g., "/slides/net/")
            - git_repo
            - git_branch
            - git_run_tag
        """
        # Update record attributes
        for key, value in kwargs.items():
            if hasattr(self._record, key):
                setattr(self._record, key, value)
            else:
                logger.warning(f"set_metrics() ignoring unknown kwarg: {key}")


class TelemetryClient:
    """
    Main telemetry client for agent instrumentation.

    Provides two usage patterns:
    1. Explicit start_run() / end_run()
    2. Context manager track_run()

    Architecture (MIG-008):
    - Primary: HTTP API POST (single-writer, zero corruption)
    - Failover: Local buffer files (guaranteed delivery)
    - Backup: NDJSON files (local resilience)
    - External: Google Sheets API (fire-and-forget)

    Features:
    - Zero corruption guarantee (single-writer via HTTP API)
    - Guaranteed delivery (buffer + sync worker)
    - At-least-once semantics (idempotent API)
    - Error handling: Never crashes the agent
    """

    def __init__(self, config: Optional[TelemetryConfig] = None):
        """
        Initialize telemetry client.

        Args:
            config: TelemetryConfig instance (defaults to from_env())
        """
        self.config = config or TelemetryConfig.from_env()

        # Validate configuration
        is_valid, errors = self.config.validate()
        if not is_valid:
            # Log validation errors but don't crash
            print("[WARN] Telemetry configuration issues:")
            for error in errors:
                print(f"  - {error}")

        # Initialize HTTP API client (primary write destination for local telemetry)
        api_url = self.config.api_url or "http://localhost:8765"
        self.http_api = HTTPAPIClient(api_url=api_url)
        logger.info(f"HTTP API client initialized: {api_url}")

        # Initialize local buffer (failover when API unavailable)
        buffer_dir = getattr(self.config, 'buffer_dir', None) or Path("./telemetry_buffer")
        self.buffer = BufferFile(buffer_dir=str(buffer_dir))
        logger.info(f"Buffer initialized: {buffer_dir}")

        # Initialize NDJSON writer (backup/audit trail)
        self.ndjson_writer = NDJSONWriter(self.config.ndjson_dir)

        # Initialize Google Sheets API client (external export) - only if enabled
        if self.config.google_sheets_api_enabled:
            if self.config.google_sheets_api_url:
                self.api_client = APIClient(
                    google_sheets_api_url=self.config.google_sheets_api_url,
                    api_token=self.config.api_token,
                    google_sheets_api_enabled=True,
                )
                logger.info(f"Google Sheets API client enabled: {self.config.google_sheets_api_url}")
            else:
                logger.warning(
                    "GOOGLE_SHEETS_API_ENABLED=true but GOOGLE_SHEETS_API_URL not set. "
                    "Google Sheets export will be disabled."
                )
                self.api_client = None
        else:
            logger.info("Google Sheets API client disabled (GOOGLE_SHEETS_API_ENABLED=false)")
            self.api_client = None

        # Keep database_writer for backward compatibility (reads only)
        # TODO: Remove after migration complete, replace with HTTP API reads
        try:
            self.database_writer = DatabaseWriter(self.config.database_path)
            logger.debug("Database writer initialized (read-only)")
        except Exception as e:
            logger.warning(f"Database writer initialization failed: {e}")
            self.database_writer = None

        # Run registry (for tracking active runs)
        self._active_runs: Dict[str, RunRecord] = {}

        # Run ID metrics (CRID-OB-01: observability for custom run_ids)
        self.run_id_metrics = RunIDMetrics()
        logger.debug("Run ID metrics initialized")

        # Git detector (GT-01: automatic git context detection)
        self.git_detector = GitDetector(auto_detect=True)
        logger.debug("Git detector initialized")

        # Log active clients summary
        logger.info("=" * 60)
        logger.info("Telemetry Client Initialized")
        logger.info("=" * 60)
        logger.info(f"Primary: HTTPAPIClient -> {api_url}")
        if self.api_client:
            logger.info(f"External: Google Sheets API -> {self.config.google_sheets_api_url}")
        else:
            logger.info("External: Google Sheets API -> DISABLED")
        logger.info(f"Failover: Local buffer -> {buffer_dir}")
        logger.info(f"Backup: NDJSON -> {self.config.ndjson_dir}")
        logger.info("=" * 60)


    def _write_run_to_api(self, record: RunRecord):
        """
        Write run to HTTP API with buffer failover (MIG-008).

        Strategy:
        1. Try POST to HTTP API
        2. If API unavailable, write to local buffer
        3. Buffer sync worker will retry later

        Args:
            record: RunRecord to write
        """
        # Convert record to dict (API format)
        event_dict = record.to_dict()

        # Ensure event_id exists (required for idempotency)
        if 'event_id' not in event_dict or not event_dict['event_id']:
            import uuid
            event_dict['event_id'] = str(uuid.uuid4())

        # Ensure timestamps exist (required by API)
        current_timestamp = get_iso8601_timestamp()
        if not event_dict.get('created_at'):
            event_dict['created_at'] = current_timestamp
        if not event_dict.get('updated_at'):
            event_dict['updated_at'] = current_timestamp

        try:
            # Primary: POST to HTTP API
            result = self.http_api.post_event(event_dict)
            logger.debug(
                f"Event written to API: {result['status']} "
                f"(event_id={event_dict['event_id']})"
            )

        except APIUnavailableError as e:
            # Failover: Write to local buffer
            logger.warning(f"API unavailable, buffering event: {e}")
            self.buffer.append(event_dict)
            logger.info(f"Event buffered locally: {event_dict['event_id']}")

        except Exception as e:
            # Unexpected error - still buffer the event
            logger.error(f"Unexpected API error, buffering event: {e}")
            self.buffer.append(event_dict)

        # Optional: Keep NDJSON backup (for audit trail)
        try:
            self.ndjson_writer.append(event_dict)
        except Exception as e:
            logger.warning(f"NDJSON write failed: {e}")

    def _update_run_to_api(self, record: RunRecord):
        """
        Update run in HTTP API with buffer failover (MIG-008).

        Used by end_run() to update status, end_time, duration, items, etc.
        Uses PATCH instead of POST to avoid creating duplicates.

        Strategy:
        1. Try PATCH to HTTP API
        2. If API unavailable, write to local buffer
        3. Buffer sync worker will retry later

        Args:
            record: RunRecord with updated fields
        """
        # Convert record to dict (API format)
        event_dict = record.to_dict()

        # Extract event_id (required for PATCH)
        event_id = event_dict.get('event_id')
        if not event_id:
            logger.error("Cannot update run without event_id")
            return

        # Build update payload (only fields that should be updated on end_run)
        update_data = {
            'status': event_dict.get('status'),
            'end_time': event_dict.get('end_time'),
            'duration_ms': event_dict.get('duration_ms'),
            'items_discovered': event_dict.get('items_discovered'),
            'items_succeeded': event_dict.get('items_succeeded'),
            'items_failed': event_dict.get('items_failed'),
            'input_summary': event_dict.get('input_summary'),
            'output_summary': event_dict.get('output_summary'),
            'error_summary': event_dict.get('error_summary'),
            'metrics_json': event_dict.get('metrics_json'),
        }

        # Remove None values (don't update fields that weren't set)
        update_data = {k: v for k, v in update_data.items() if v is not None}

        # Ensure updated_at timestamp
        update_data['updated_at'] = get_iso8601_timestamp()

        try:
            # Primary: PATCH to HTTP API
            result = self.http_api.patch_event(event_id, update_data)
            logger.debug(
                f"Event updated in API: {result.get('fields_updated', [])} "
                f"(event_id={event_id})"
            )

        except APIUnavailableError as e:
            # Failover: Write to local buffer (buffer will use POST with full event)
            logger.warning(f"API unavailable, buffering update: {e}")
            self.buffer.append(event_dict)
            logger.info(f"Update buffered locally: {event_id}")

        except Exception as e:
            # Unexpected error - still buffer the event
            logger.error(f"Unexpected API error, buffering update: {e}")
            self.buffer.append(event_dict)

        # Optional: Keep NDJSON backup (for audit trail)
        try:
            self.ndjson_writer.append(event_dict)
        except Exception as e:
            logger.warning(f"NDJSON write failed: {e}")

    def _validate_custom_run_id(self, run_id: str) -> tuple[bool, Optional[str]]:
        """
        Validate custom run_id format and track rejection reasons.

        Enforces application-level constraints beyond database schema:
        - Max length: 255 characters (MAX_RUN_ID_LENGTH)
        - No path separators (security: prevent directory traversal)
        - No null bytes (security: prevent string termination attacks)
        - Must not be empty or whitespace-only

        See: docs/schema_constraints.md for full constraint documentation

        Args:
            run_id: Custom run ID to validate

        Returns:
            Tuple of (is_valid: bool, rejection_reason: Optional[str])
            - (True, None) if valid
            - (False, reason) if invalid
        """
        if not run_id or not run_id.strip():
            try:
                self.run_id_metrics.increment_rejected_empty()
            except Exception:
                pass  # Never crash on metrics
            return False, "empty"

        if len(run_id) > MAX_RUN_ID_LENGTH:
            try:
                self.run_id_metrics.increment_rejected_too_long()
            except Exception:
                pass  # Never crash on metrics
            return False, "too_long"

        # Basic safety: no path separators or null bytes
        if '/' in run_id or '\\' in run_id or '\x00' in run_id:
            try:
                self.run_id_metrics.increment_rejected_invalid_chars()
            except Exception:
                pass  # Never crash on metrics
            return False, "invalid_chars"

        return True, None

    def start_run(
        self,
        agent_name: str,
        job_type: str,
        trigger_type: str = "cli",
        **kwargs,
    ) -> str:
        """
        Start a new telemetry run.

        Args:
            agent_name: Name of the agent
            job_type: Type of job being run
            trigger_type: How the run was triggered (cli, web, scheduler, mcp, manual)
            **kwargs: Additional fields (insight_id, product, platform, run_id, etc.)
                     If run_id is provided, it will be used instead of generating a new one.

        Returns:
            str: Unique run_id

        Example:
            run_id = client.start_run("my_agent", "process_files", trigger_type="cli")
            # Or with custom run_id:
            run_id = client.start_run("my_agent", "process_files", run_id="custom-id-123")
        """
        try:
            # Extract custom run_id if provided
            custom_run_id = kwargs.pop("run_id", None)

            # Validate and use custom run_id or generate new one
            if custom_run_id:
                is_valid, rejection_reason = self._validate_custom_run_id(custom_run_id)
                if not is_valid:
                    logger.warning(
                        f"Invalid custom run_id rejected (reason: {rejection_reason}): "
                        f"{custom_run_id[:50]}"
                    )
                    run_id = generate_run_id(agent_name)
                    # Track generated run_id (fallback after rejection)
                    try:
                        self.run_id_metrics.increment_generated()
                    except Exception:
                        pass  # Never crash on metrics
                else:
                    logger.info(f"Using consumer-provided run_id: {custom_run_id}")
                    run_id = custom_run_id
                    # Track custom run_id accepted
                    try:
                        self.run_id_metrics.increment_custom_accepted()
                    except Exception:
                        pass  # Never crash on metrics
            else:
                run_id = generate_run_id(agent_name)
                logger.debug(f"Generated run_id: {run_id}")
                # Track generated run_id
                try:
                    self.run_id_metrics.increment_generated()
                except Exception:
                    pass  # Never crash on metrics

            # Check for duplicate run_id in active runs registry
            if run_id in self._active_runs:
                logger.warning(f"Duplicate run_id detected: {run_id}")
                # Track duplicate detection
                try:
                    self.run_id_metrics.increment_duplicates()
                except Exception:
                    pass  # Never crash on metrics

                if custom_run_id:
                    # For custom run_ids: log error and generate new ID with suffix
                    logger.error(
                        f"Custom run_id '{custom_run_id}' is already active. "
                        f"Generating new unique ID to prevent database constraint violation."
                    )
                    # Create unique suffix with short UUID
                    import uuid
                    suffix = str(uuid.uuid4())[:8]
                    run_id = f"{custom_run_id}-duplicate-{suffix}"
                    logger.info(f"New run_id generated: {run_id}")
                else:
                    # For generated run_ids: regenerate with new UUID
                    logger.info(f"Regenerating run_id to avoid duplicate: {run_id}")
                    run_id = generate_run_id(agent_name)
                    logger.debug(f"Regenerated run_id: {run_id}")

            start_time = get_iso8601_timestamp()

            # GT-01: Auto-detect Git context (if not explicitly provided)
            git_context = {}
            try:
                detected = self.git_detector.get_git_context()
                # Only use auto-detected values if not explicitly provided
                for key in ["git_repo", "git_branch", "git_run_tag"]:
                    if key not in kwargs and key in detected:
                        git_context[key] = detected[key]
                        logger.debug(f"Auto-detected {key}: {detected[key]}")
            except Exception as e:
                # Never crash on git detection failure
                logger.debug(f"Git auto-detection failed: {e}")

            # Merge git_context into kwargs (explicit values take precedence)
            enriched_kwargs = {**git_context, **kwargs}

            # Create run record
            record = RunRecord(
                run_id=run_id,
                agent_name=agent_name,
                job_type=job_type,
                trigger_type=trigger_type,
                start_time=start_time,
                status="running",
                agent_owner=enriched_kwargs.get("agent_owner") or self.config.agent_owner,
                host=enriched_kwargs.get("host") or platform.node(),
                **{k: v for k, v in enriched_kwargs.items() if k not in ("agent_owner", "host")},
            )

            # Store in registry
            self._active_runs[run_id] = record

            # Write to HTTP API (with buffer failover)
            self._write_run_to_api(record)

            return run_id

        except Exception as e:
            # Never crash the agent
            print(f"[ERROR] Telemetry start_run failed: {e}")
            # Return a dummy ID so agent can continue (preserve custom ID if provided)
            error_id = custom_run_id if custom_run_id else generate_run_id(agent_name)
            return f"error-{error_id}"

    def end_run(
        self,
        run_id: str,
        status: str = "success",
        **kwargs,
    ):
        """
        End a telemetry run.

        Args:
            run_id: Run ID from start_run()
            status: Final status (success, failure, partial, timeout, cancelled)
            **kwargs: Updated metrics (items_discovered, items_succeeded, etc.)

        Example:
            client.end_run(run_id, status="success", items_succeeded=10)
        """
        try:
            # Get record from registry
            record = self._active_runs.get(run_id)

            if not record:
                print(f"[WARN] Run ID not found: {run_id}")
                return

            # Update record
            record.end_time = get_iso8601_timestamp()
            normalized_status = normalize_status(status)
            if normalized_status not in CANONICAL_STATUSES:
                logger.warning(f"Unknown status '{status}', defaulting to 'failure'")
                normalized_status = "failure"
            record.status = normalized_status

            # Calculate duration
            if record.start_time and record.end_time:
                try:
                    record.duration_ms = calculate_duration_ms(
                        record.start_time, record.end_time
                    )
                except Exception:
                    pass  # Duration calculation is optional

            # Update metrics from kwargs
            for key, value in kwargs.items():
                if hasattr(record, key):
                    setattr(record, key, value)

            # Update run in HTTP API using PATCH (with buffer failover)
            self._update_run_to_api(record)

            # Post to Google Sheets API (fire-and-forget, external export)
            if self.api_client is not None:
                try:
                    payload = APIPayload.from_run_record(record)
                    success, message = self.api_client.post_run_sync(payload)

                    if not success:
                        logger.debug(f"Google Sheets API post failed: {message}")
                    else:
                        logger.debug(f"Google Sheets API post succeeded: {message}")

                except Exception as e:
                    logger.debug(f"Google Sheets API post failed: {e}")
            else:
                logger.debug("Google Sheets API disabled, skipping external export")

            # Remove from registry
            if run_id in self._active_runs:
                del self._active_runs[run_id]

        except Exception as e:
            # Never crash the agent
            print(f"[ERROR] Telemetry end_run failed: {e}")

    def log_event(
        self,
        run_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """
        Log an event during a run.

        Per TEL-03 design: Events are written to NDJSON only, not to run_events table.
        This avoids SQLite lock contention on high-frequency event logging.

        Args:
            run_id: Run ID from start_run()
            event_type: Type of event
            payload: Optional event data

        Example:
            client.log_event(run_id, "checkpoint", {"step": 1, "status": "ok"})
        """
        try:
            # Create event
            event = RunEvent(
                run_id=run_id,
                event_type=event_type,
                timestamp=get_iso8601_timestamp(),
                payload_json=json.dumps(payload) if payload else None,
            )

            # Write to NDJSON only (no database write for events)
            self.ndjson_writer.append(event.to_dict())

        except Exception as e:
            # Never crash the agent
            print(f"[WARN] Telemetry log_event failed: {e}")

    @contextmanager
    def track_run(
        self,
        agent_name: str,
        job_type: str,
        trigger_type: str = "cli",
        **kwargs,
    ):
        """
        Context manager for tracking a run.

        Automatically handles start/end and exception handling.

        Args:
            agent_name: Name of the agent
            job_type: Type of job being run
            trigger_type: How the run was triggered
            **kwargs: Additional fields (insight_id, product, platform, etc.)

        Yields:
            RunContext: Context object for logging events and metrics

        Example:
            with client.track_run("my_agent", "process") as ctx:
                ctx.log_event("start", {"input": "data.csv"})
                # ... do work ...
                ctx.set_metrics(items_discovered=10, items_succeeded=10)
        """
        run_id = None
        record = None

        try:
            # Start run
            run_id = self.start_run(agent_name, job_type, trigger_type, **kwargs)
            record = self._active_runs.get(run_id)

            # Yield context
            ctx = RunContext(run_id, record, self)
            yield ctx

            # Success - end run with success status
            self.end_run(run_id, status="success")

        except Exception as e:
            # Exception during run - end with failure status
            if run_id:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self.end_run(
                    run_id,
                    status="failure",
                    error_summary=error_msg,
                )

            # Re-raise exception so agent can handle it
            raise

    def get_run_id_metrics(self) -> Dict[str, Any]:
        """
        Get run_id metrics snapshot (CRID-OB-01).

        Returns:
            Dictionary with run_id metrics in structured format

        Example:
            metrics = client.get_run_id_metrics()
            print(f"Custom IDs: {metrics['run_id_metrics']['custom_accepted']}")
            print(f"Generated IDs: {metrics['run_id_metrics']['generated']}")
            print(f"Total rejected: {metrics['run_id_metrics']['rejected']['total']}")
        """
        try:
            return self.run_id_metrics.get_snapshot()
        except Exception as e:
            logger.error(f"Failed to get run_id metrics: {e}")
            return {
                "error": f"Metrics unavailable: {e}",
                "timestamp": get_iso8601_timestamp()
            }

    def log_run_id_metrics(self):
        """
        Log run_id metrics to logger as structured JSON (CRID-OB-01).

        Useful for periodic metrics reporting or debugging.

        Example:
            client.log_run_id_metrics()
        """
        try:
            self.run_id_metrics.log_metrics()
        except Exception as e:
            logger.warning(f"Failed to log run_id metrics: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get telemetry statistics including run_id metrics.

        Returns:
            Dictionary with statistics

        Example:
            stats = client.get_stats()
            print(f"Total runs: {stats['total_runs']}")
            print(f"Custom IDs: {stats['run_id_metrics']['custom_accepted']}")
        """
        stats = {}

        try:
            # Try HTTP API first
            metrics = self.http_api.get_metrics()
            if metrics:
                stats = {
                    "total_runs": metrics.get('total_runs', 0),
                    "agents": metrics.get('agents', {}),
                    "recent_24h": metrics.get('recent_24h', 0),
                }
        except Exception as e:
            logger.debug(f"HTTP API get_metrics failed: {e}")

            # Fallback to database (if available)
            if self.database_writer:
                try:
                    stats = self.database_writer.get_run_stats()
                except Exception as e:
                    logger.error(f"Database get_stats failed: {e}")
                    stats = {"error": "Statistics unavailable"}

        # Add run_id metrics (CRID-OB-01)
        try:
            run_id_snapshot = self.run_id_metrics.get_snapshot()
            stats.update(run_id_snapshot)
        except Exception as e:
            logger.warning(f"Failed to add run_id metrics to stats: {e}")

        return stats

    def associate_commit(
        self,
        run_id: str,
        commit_hash: str,
        commit_source: str,
        commit_author: Optional[str] = None,
        commit_timestamp: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Associate a git commit with a completed telemetry run.

        Use this method after a commit is made to link it back to the
        agent run that produced the changes. This enables tracking which
        commits came from which agent runs.

        Args:
            run_id: The run ID to associate the commit with
            commit_hash: Git commit SHA (7-40 hex characters)
            commit_source: How the commit was created ('manual', 'llm', 'ci')
            commit_author: Optional git author string (e.g., "Name <email>")
            commit_timestamp: Optional ISO8601 timestamp of when commit was made

        Returns:
            Tuple of (success: bool, message: str)

        Example:
            # After completing a run and making a commit:
            run_id = client.start_run("hugo-translator", "translate")
            # ... do work, make changes ...
            client.end_run(run_id, status="success")

            # After git commit:
            import subprocess
            result = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True)
            commit_hash = result.stdout.strip()

            success, msg = client.associate_commit(
                run_id=run_id,
                commit_hash=commit_hash,
                commit_source="llm",
                commit_author="Claude Code <noreply@anthropic.com>"
            )
        """
        # Get event_id for this run_id
        if run_id not in self._active_runs:
            return False, f"[ERROR] Run ID not found: {run_id}"

        # _active_runs stores RunRecord objects, access event_id as attribute
        event_id = self._active_runs[run_id].event_id

        # Try HTTP API first
        if self.http_api:
            try:
                response = self.http_api.associate_commit(
                    event_id=event_id,
                    commit_hash=commit_hash,
                    commit_source=commit_source,
                    commit_author=commit_author,
                    commit_timestamp=commit_timestamp,
                )
                return True, f"Commit {commit_hash} associated via HTTP API"
            except APIValidationError as e:
                # Don't fallback for validation errors (data is bad)
                return False, f"[ERROR] Validation failed: {e}"
            except APIUnavailableError as e:
                # Fall through to database_writer if HTTP unavailable
                logger.warning(f"HTTP API unavailable, trying database fallback: {e}")
            except APIError as e:
                # Fall through to database_writer for other API errors
                logger.warning(f"HTTP API error, trying database fallback: {e}")
            except Exception as e:
                # Fall through for unexpected errors
                logger.warning(f"Unexpected HTTP error, trying database fallback: {e}")

        # Fallback to database_writer (backward compatibility)
        if self.database_writer:
            try:
                return self.database_writer.associate_commit(
                    run_id=run_id,
                    commit_hash=commit_hash,
                    commit_source=commit_source,
                    commit_author=commit_author,
                    commit_timestamp=commit_timestamp,
                )
            except Exception as e:
                # Never crash the agent
                return False, f"[ERROR] associate_commit failed: {e}"

        return False, "[ERROR] Commit association not available (no HTTP or database)"
