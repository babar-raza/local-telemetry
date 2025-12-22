#!/usr/bin/env python3
"""
MIG-008: Refactor TelemetryClient to use HTTP API

This script updates client.py to use HTTPAPIClient + BufferFile
instead of direct DatabaseWriter writes.
"""

import re
from pathlib import Path

def refactor_client():
    """Refactor client.py to use HTTP API."""

    client_path = Path(__file__).parent.parent / "src" / "telemetry" / "client.py"
    backup_path = client_path.with_suffix(".py.backup_mig008")

    print(f"Reading: {client_path}")

    with open(client_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Backup original
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Backup created: {backup_path}")

    # 1. Update imports
    old_imports = """from .config import TelemetryConfig
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
from .api import APIClient"""

    new_imports = """from .config import TelemetryConfig
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
from pathlib import Path"""

    content = content.replace(old_imports, new_imports)

    # 2. Update docstring
    old_docstring = """    Provides two usage patterns:
    1. Explicit start_run() / end_run()
    2. Context manager track_run()

    Features:
    - Dual-write: NDJSON (local resilience) + SQLite (structured queries)
    - API posting: Fire-and-forget to Google Sheets
    - Error handling: Never crashes the agent
    """

    new_docstring = """    Provides two usage patterns:
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

    content = content.replace(old_docstring, new_docstring)

    # 3. Update __init__ method
    old_init_writers = """        # Initialize writers
        self.ndjson_writer = NDJSONWriter(self.config.ndjson_dir)
        self.database_writer = DatabaseWriter(self.config.database_path)
        self.api_client = APIClient(
            api_url=self.config.api_url,
            api_token=self.config.api_token,
            api_enabled=self.config.api_enabled,
        )

        # Run registry (for tracking active runs)
        self._active_runs: Dict[str, RunRecord] = {}"""

    new_init_writers = """        # Initialize HTTP API client (primary write destination)
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
        self._active_runs: Dict[str, RunRecord] = {}"""

    content = content.replace(old_init_writers, new_init_writers)

    # 4. Add _write_run_to_api method before start_run
    write_api_method = '''
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
        if 'event_id' not in event_dict:
            import uuid
            event_dict['event_id'] = str(uuid.uuid4())

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

'''

    # Insert before start_run method
    content = re.sub(
        r'(    def start_run\()',
        write_api_method + r'\1',
        content,
        count=1
    )

    # 5. Replace database writes in start_run
    old_start_write = """            # Store in registry
            self._active_runs[run_id] = record

            # Write to NDJSON (local resilience)
            self.ndjson_writer.append(record.to_dict())

            # Write to SQLite (structured queries)
            success, message = self.database_writer.insert_run(record)
            if not success:
                print(f"[WARN] Database insert failed: {message}")

            return run_id"""

    new_start_write = """            # Store in registry
            self._active_runs[run_id] = record

            # Write to HTTP API (with buffer failover)
            self._write_run_to_api(record)

            return run_id"""

    content = content.replace(old_start_write, new_start_write)

    # 6. Replace database writes in end_run
    old_end_write = """            # Update metrics from kwargs
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
            del self._active_runs[run_id]"""

    new_end_write = """            # Update metrics from kwargs
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
                del self._active_runs[run_id]"""

    content = content.replace(old_end_write, new_end_write)

    # 7. Update get_stats to use HTTP API
    old_get_stats = """    def get_stats(self) -> Dict[str, Any]:
        \"\"\"
        Get telemetry statistics.

        Returns:
            Dictionary with statistics

        Example:
            stats = client.get_stats()
            print(f"Total runs: {stats['total_runs']}")
        \"\"\"
        try:
            return self.database_writer.get_run_stats()
        except Exception as e:
            return {"error": str(e)}"""

    new_get_stats = """    def get_stats(self) -> Dict[str, Any]:
        \"\"\"
        Get telemetry statistics.

        Returns:
            Dictionary with statistics

        Example:
            stats = client.get_stats()
            print(f"Total runs: {stats['total_runs']}")
        \"\"\"
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

        return {"error": "Statistics unavailable"}"""

    content = content.replace(old_get_stats, new_get_stats)

    # 8. Update associate_commit
    old_associate = """        try:
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
"""

    new_associate = """        # TODO MIG-008: Add HTTP API endpoint for commit association
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
"""

    content = content.replace(old_associate, new_associate)

    # Write refactored file
    with open(client_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f"✅ Refactored: {client_path}")
    print(f"✅ Backup: {backup_path}")
    print()
    print("Changes applied:")
    print("  - Added HTTPAPIClient and BufferFile imports")
    print("  - Updated __init__ to use HTTP API + buffer")
    print("  - Added _write_run_to_api() method")
    print("  - Updated start_run() to use HTTP API")
    print("  - Updated end_run() to use HTTP API")
    print("  - Updated get_stats() to use HTTP API")
    print("  - Updated associate_commit() with TODO")
    print()
    print("Next steps:")
    print("  1. Test with: python -c 'from telemetry.client import TelemetryClient; print(\"OK\")'")
    print("  2. Run integration tests")
    print("  3. Update config to include buffer_dir")

if __name__ == "__main__":
    refactor_client()
