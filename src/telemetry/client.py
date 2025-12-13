"""
Telemetry Platform - Main Client

TelemetryClient provides the public API for agent telemetry instrumentation.
"""

import json
import platform
from contextlib import contextmanager
from typing import Optional, Dict, Any

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
from .database import DatabaseWriter
from .api import APIClient


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
            - git_repo
            - git_branch
            - git_run_tag
        """
        # Update record attributes
        for key, value in kwargs.items():
            if hasattr(self._record, key):
                setattr(self._record, key, value)


class TelemetryClient:
    """
    Main telemetry client for agent instrumentation.

    Provides two usage patterns:
    1. Explicit start_run() / end_run()
    2. Context manager track_run()

    Features:
    - Dual-write: NDJSON (local resilience) + SQLite (structured queries)
    - API posting: Fire-and-forget to Google Sheets
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

        # Initialize writers
        self.ndjson_writer = NDJSONWriter(self.config.ndjson_dir)
        self.database_writer = DatabaseWriter(self.config.database_path)
        self.api_client = APIClient(
            api_url=self.config.api_url,
            api_token=self.config.api_token,
            api_enabled=self.config.api_enabled,
        )

        # Run registry (for tracking active runs)
        self._active_runs: Dict[str, RunRecord] = {}

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

            # Write to NDJSON (local resilience)
            self.ndjson_writer.append(record.to_dict())

            # Write to SQLite (structured queries)
            success, message = self.database_writer.insert_run(record)
            if not success:
                print(f"[WARN] Database insert failed: {message}")

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

            # Write to NDJSON
            self.ndjson_writer.append(record.to_dict())

            # Update in SQLite
            success, message = self.database_writer.update_run(record)
            if not success:
                print(f"[WARN] Database update failed: {message}")

            # Post to API (fire-and-forget)
            try:
                payload = APIPayload.from_run_record(record)
                success, message = self.api_client.post_run_sync(payload)

                if success:
                    # Mark as posted in database
                    posted_at = get_iso8601_timestamp()
                    self.database_writer.mark_api_posted(run_id, posted_at)
                else:
                    # Increment retry count
                    self.database_writer.increment_api_retry_count(run_id)

            except Exception as e:
                print(f"[WARN] API post failed: {e}")

            # Remove from registry
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
            return self.database_writer.get_run_stats()
        except Exception as e:
            return {"error": str(e)}
