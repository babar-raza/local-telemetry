"""
Telemetry Platform - Database Writer

Writes telemetry data to SQLite database with retry logic for lock contention.
"""

import sqlite3
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from .models import RunRecord

logger = logging.getLogger(__name__)


class DatabaseWriter:
    """
    Writes telemetry data to SQLite database.

    Features:
    - Retry logic for SQLite lock contention (3 retries with exponential backoff)
    - Synchronous writes for run summaries (start/end)
    - WAL mode for concurrent access
    - No writes to run_events table (NDJSON only per TEL-03 design)

    Concurrency Strategy:
    - Run summaries: 1 INSERT at start, 1 UPDATE at end (low frequency)
    - Events: Written to NDJSON only (avoids contention)
    - Retry on lock: 100ms, 200ms, 400ms delays
    """

    def __init__(self, database_path: Path, max_retries: int = 3):
        """
        Initialize database writer.

        Args:
            database_path: Path to SQLite database file
            max_retries: Maximum retry attempts for locked database (default: 3)
        """
        self.database_path = Path(database_path)
        self.max_retries = max_retries
        self.retry_delays = [0.1, 0.2, 0.4]  # 100ms, 200ms, 400ms

    def check_integrity(self, quick: bool = True) -> tuple[bool, str]:
        """
        Check database integrity.

        Args:
            quick: If True, use PRAGMA quick_check (faster, less thorough).
                   If False, use PRAGMA integrity_check (slower, comprehensive).

        Returns:
            Tuple of (is_healthy: bool, message: str)
        """
        try:
            if not self.database_path.exists():
                return False, "Database file does not exist"

            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()

            check_type = "quick_check" if quick else "integrity_check"
            cursor.execute(f"PRAGMA {check_type}")
            result = cursor.fetchone()[0]
            conn.close()

            if result == "ok":
                return True, f"[OK] Database integrity check passed ({check_type})"
            else:
                return False, f"[FAIL] Database integrity issue: {result}"

        except sqlite3.DatabaseError as e:
            return False, f"[FAIL] Database corrupted: {e}"
        except Exception as e:
            return False, f"[FAIL] Integrity check error: {e}"

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get database connection with WAL mode and corruption prevention settings.

        Creates the database directory if it doesn't exist before connecting.
        Configures SQLite pragmas to prevent corruption:
        - WAL mode for concurrent access
        - busy_timeout to wait for locks instead of failing immediately
        - synchronous=NORMAL for durability without excessive fsync
        - wal_autocheckpoint for regular checkpointing

        Returns:
            sqlite3.Connection: Database connection
        """
        # Ensure database directory exists before connecting
        db_dir = self.database_path.parent
        if not db_dir.exists():
            db_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created database directory: {db_dir}")

        conn = sqlite3.connect(self.database_path)

        # Corruption prevention settings
        conn.execute("PRAGMA busy_timeout=5000")  # Wait 5s for locks
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")  # Durability without excessive fsync
        conn.execute("PRAGMA wal_autocheckpoint=1000")  # Checkpoint every 1000 pages

        return conn

    def _execute_with_retry(
        self, operation: str, params: tuple, fetch: bool = False
    ) -> tuple[bool, Optional[Any], str]:
        """
        Execute database operation with retry logic.

        Args:
            operation: SQL statement
            params: Parameters for SQL statement
            fetch: Whether to fetch results

        Returns:
            Tuple of (success: bool, result: Any, message: str)
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                conn = self._get_connection()
                cursor = conn.cursor()

                cursor.execute(operation, params)

                result = None
                if fetch:
                    result = cursor.fetchone()

                conn.commit()
                conn.close()

                return True, result, "[OK] Database write successful"

            except sqlite3.OperationalError as e:
                last_error = e
                error_msg = str(e).lower()

                # Check if it's a lock error
                if "locked" in error_msg or "busy" in error_msg:
                    if attempt < self.max_retries - 1:
                        # Retry with exponential backoff
                        delay = self.retry_delays[attempt]
                        time.sleep(delay)
                        continue
                    else:
                        # Max retries reached
                        return (
                            False,
                            None,
                            f"[WARN] Database locked after {self.max_retries} retries",
                        )
                else:
                    # Non-lock error, don't retry
                    return False, None, f"[FAIL] Database error: {e}"

            except Exception as e:
                return False, None, f"[FAIL] Unexpected database error: {e}"

        # Should not reach here, but just in case
        return False, None, f"[FAIL] Database operation failed: {last_error}"

    def insert_run(self, record: RunRecord) -> tuple[bool, str]:
        """
        Insert a new run record into the database.

        Args:
            record: RunRecord to insert

        Returns:
            Tuple of (success: bool, message: str)
        """
        sql = """
            INSERT INTO agent_runs (
                run_id, schema_version, agent_name, agent_owner, job_type,
                trigger_type, start_time, end_time, status,
                items_discovered, items_succeeded, items_failed,
                duration_ms, input_summary, output_summary, error_summary,
                metrics_json, insight_id, product, platform, product_family, subdomain,
                git_repo, git_branch, git_run_tag, host,
                api_posted, api_posted_at, api_retry_count
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """

        params = (
            record.run_id,
            record.schema_version,
            record.agent_name,
            record.agent_owner,
            record.job_type,
            record.trigger_type,
            record.start_time,
            record.end_time,
            record.status,
            record.items_discovered,
            record.items_succeeded,
            record.items_failed,
            record.duration_ms,
            record.input_summary,
            record.output_summary,
            record.error_summary,
            record.metrics_json,
            record.insight_id,
            record.product,
            record.platform,
            record.product_family,
            record.subdomain,
            record.git_repo,
            record.git_branch,
            record.git_run_tag,
            record.host,
            record.api_posted,
            record.api_posted_at,
            record.api_retry_count,
        )

        success, _, message = self._execute_with_retry(sql, params)
        return success, message

    def update_run(self, record: RunRecord) -> tuple[bool, str]:
        """
        Update an existing run record in the database.

        Args:
            record: RunRecord with updated values

        Returns:
            Tuple of (success: bool, message: str)
        """
        sql = """
            UPDATE agent_runs SET
                end_time = ?,
                status = ?,
                items_discovered = ?,
                items_succeeded = ?,
                items_failed = ?,
                duration_ms = ?,
                input_summary = ?,
                output_summary = ?,
                error_summary = ?,
                metrics_json = ?,
                insight_id = ?,
                product = ?,
                platform = ?,
                product_family = ?,
                subdomain = ?,
                git_repo = ?,
                git_branch = ?,
                git_run_tag = ?,
                host = ?,
                api_posted = ?,
                api_posted_at = ?,
                api_retry_count = ?,
                updated_at = datetime('now')
            WHERE run_id = ?
        """

        params = (
            record.end_time,
            record.status,
            record.items_discovered,
            record.items_succeeded,
            record.items_failed,
            record.duration_ms,
            record.input_summary,
            record.output_summary,
            record.error_summary,
            record.metrics_json,
            record.insight_id,
            record.product,
            record.platform,
            record.product_family,
            record.subdomain,
            record.git_repo,
            record.git_branch,
            record.git_run_tag,
            record.host,
            record.api_posted,
            record.api_posted_at,
            record.api_retry_count,
            record.run_id,
        )

        success, _, message = self._execute_with_retry(sql, params)
        return success, message

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """
        Retrieve a run record by run_id.

        Args:
            run_id: Run ID to retrieve

        Returns:
            RunRecord if found, None otherwise
        """
        sql = "SELECT * FROM agent_runs WHERE run_id = ?"

        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row  # Enable column access by name
            cursor = conn.cursor()

            cursor.execute(sql, (run_id,))
            row = cursor.fetchone()

            conn.close()

            if row:
                # Convert row to dictionary
                data = dict(row)
                return RunRecord.from_dict(data)

            return None

        except Exception:
            return None

    def mark_api_posted(self, run_id: str, posted_at: str) -> tuple[bool, str]:
        """
        Mark a run as successfully posted to API.

        Args:
            run_id: Run ID to update
            posted_at: ISO8601 timestamp of API post

        Returns:
            Tuple of (success: bool, message: str)
        """
        sql = """
            UPDATE agent_runs
            SET api_posted = 1, api_posted_at = ?
            WHERE run_id = ?
        """

        success, _, message = self._execute_with_retry(sql, (posted_at, run_id))
        return success, message

    def increment_api_retry_count(self, run_id: str) -> tuple[bool, str]:
        """
        Increment the API retry count for a run.

        Args:
            run_id: Run ID to update

        Returns:
            Tuple of (success: bool, message: str)
        """
        sql = """
            UPDATE agent_runs
            SET api_retry_count = api_retry_count + 1
            WHERE run_id = ?
        """

        success, _, message = self._execute_with_retry(sql, (run_id,))
        return success, message

    def get_pending_api_posts(self, limit: int = 100) -> list[RunRecord]:
        """
        Get runs that haven't been posted to API yet.

        Args:
            limit: Maximum number of runs to retrieve

        Returns:
            List of RunRecord objects
        """
        sql = """
            SELECT * FROM agent_runs
            WHERE api_posted = 0 AND status != 'running'
            ORDER BY start_time DESC
            LIMIT ?
        """

        try:
            conn = self._get_connection()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(sql, (limit,))
            rows = cursor.fetchall()

            conn.close()

            records = []
            for row in rows:
                data = dict(row)
                records.append(RunRecord.from_dict(data))

            return records

        except Exception:
            return []

    def get_run_stats(self) -> Dict[str, Any]:
        """
        Get statistics about runs in the database.

        Returns:
            Dictionary with statistics
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Total runs
            cursor.execute("SELECT COUNT(*) FROM agent_runs")
            total_runs = cursor.fetchone()[0]

            # Runs by status
            cursor.execute(
                """
                SELECT status, COUNT(*) as count
                FROM agent_runs
                GROUP BY status
            """
            )
            status_counts = {row[0]: row[1] for row in cursor.fetchall()}

            # Pending API posts
            cursor.execute(
                """
                SELECT COUNT(*) FROM agent_runs
                WHERE api_posted = 0 AND status != 'running'
            """
            )
            pending_api = cursor.fetchone()[0]

            conn.close()

            return {
                "total_runs": total_runs,
                "status_counts": status_counts,
                "pending_api_posts": pending_api,
            }

        except Exception as e:
            return {"error": str(e)}
