"""
Telemetry Platform - Main Client

TelemetryClient provides the public API for agent telemetry instrumentation.
"""

import json
import logging
import platform
from contextlib import contextmanager
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

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
from .http_client import HTTPAPIClient, APIUnavailableError  # Telemetry HTTP API
from .buffer import BufferFile  # Local buffer for failover
from pathlib import Path


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

        # Initialize HTTP API client (primary write destination)
        api_url = self.config.api_url or "http://localhost:8765"
        self.http_api = HTTPAPIClient(api_url=api_url)
        logger.info(f"HTTP API client initialized: {api_url}")

        # Initialize local buffer (failover when API unavailable)
        buffer_dir = getattr(self.config, 'buffer_dir', None) or Path("./telemetry_buffer")
        self.buffer = BufferFile(buffer_dir=str(buffer_dir))
        logger.info(f"Buffer initialized: {buffer_dir}")

        # Initialize NDJSON writer (backup/audit trail)
        self.ndjson_writer = NDJSONWriter(self.config.ndjson_dir)

        # Initialize Google Sheets API client (external export)
        self.api_client = APIClient(
            api_url=self.config.api_url,
            api_token=self.config.api_token,
            api_enabled=self.config.api_enabled,
        )

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
            **kwargs: Additional fields (insight_id, product, platform, etc.) (agent_owner, product, platform, insight_id, etc.)

        Returns:
            str: Unique run_id

        Example:
            run_id = client.start_run("my_agent", "process_files", trigger_type="cli")
        """
        try:
            # Generate run ID
            run_id = generate_run_id(agent_name)
            start_time = get_iso8601_timestamp()

            # Create run record
            record = RunRecord(
                run_id=run_id,
                agent_name=agent_name,
                job_type=job_type,
                trigger_type=trigger_type,
                start_time=start_time,
                status="running",
                agent_owner=kwargs.get("agent_owner") or self.config.agent_owner,
                host=kwargs.get("host") or platform.node(),
                **{k: v for k, v in kwargs.items() if k not in ("agent_owner", "host")},
            )

            # Store in registry
            self._active_runs[run_id] = record

            # Write to HTTP API (with buffer failover)
            self._write_run_to_api(record)

            return run_id

        except Exception as e:
            # Never crash the agent
            print(f"[ERROR] Telemetry start_run failed: {e}")
            # Return a dummy ID so agent can continue
            return "error-" + generate_run_id(agent_name)

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
            status: Final status (success, failed, partial)
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
            record.status = status

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

            # Write to HTTP API (with buffer failover)
            self._write_run_to_api(record)

            # Post to Google Sheets API (fire-and-forget, external export)
            try:
                payload = APIPayload.from_run_record(record)
                success, message = self.api_client.post_run_sync(payload)

                if not success:
                    logger.debug(f"Google Sheets API post failed: {message}")

            except Exception as e:
                logger.debug(f"Google Sheets API post failed: {e}")

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
            # Exception during run - end with failed status
            if run_id:
                error_msg = f"{type(e).__name__}: {str(e)}"
                self.end_run(
                    run_id,
                    status="failed",
                    error_summary=error_msg,
                )

            # Re-raise exception so agent can handle it
            raise

    def get_stats(self) -> Dict[str, Any]:
        """
        Get telemetry statistics.

        Returns:
            Dictionary with statistics

        Example:
            stats = client.get_stats()
            print(f"Total runs: {stats['total_runs']}")
        """
        try:
            # Try HTTP API first
            metrics = self.http_api.get_metrics()
            if metrics:
                return {
                    "total_runs": metrics.get('total_runs', 0),
                    "agents": metrics.get('agents', {}),
                    "recent_24h": metrics.get('recent_24h', 0),
                }
        except Exception as e:
            logger.debug(f"HTTP API get_metrics failed: {e}")

        # Fallback to database (if available)
        if self.database_writer:
            try:
                return self.database_writer.get_run_stats()
            except Exception as e:
                logger.error(f"Database get_stats failed: {e}")

        return {"error": "Statistics unavailable"}

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
        # TODO MIG-008: Add HTTP API endpoint for commit association
        # For now, use database_writer if available
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
        else:
            return False, "[ERROR] Commit association not available (database unavailable)"
