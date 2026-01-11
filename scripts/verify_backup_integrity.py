#!/usr/bin/env python3
r"""
Verify backup integrity for Docker telemetry database backups.

Standalone script that can be called from PowerShell with proper exit codes.
Reuses proven integrity check logic from backup_database.py.

Usage:
    python verify_backup_integrity.py --backup-path D:\agent-metrics\docker-backups\20260102_150000\telemetry.sqlite

Exit codes:
    0: Backup verified successfully
    1: Backup verification failed
    2: File not found
"""

import sqlite3
import sys
import argparse
from pathlib import Path


def check_database_integrity(db_path: Path) -> tuple[bool, str, dict]:
    """
    Verify SQLite database integrity and gather statistics.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Tuple of (is_healthy: bool, message: str, stats: dict)
        stats contains: run_count, schema_version, file_size_mb
    """
    stats = {}

    # Check file exists
    if not db_path.exists():
        return False, "Database file does not exist", stats

    try:
        # Get file size
        stats['file_size_mb'] = round(db_path.stat().st_size / (1024 * 1024), 2)

        # Connect to database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # PRAGMA integrity_check (comprehensive check)
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]

        if result != "ok":
            conn.close()
            return False, f"Integrity issue: {result}", stats

        # Get run count
        try:
            cursor.execute("SELECT COUNT(*) FROM agent_runs")
            stats['run_count'] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            stats['run_count'] = 0

        # Get schema version
        try:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY applied_at DESC LIMIT 1")
            result = cursor.fetchone()
            stats['schema_version'] = result[0] if result else "unknown"
        except sqlite3.OperationalError:
            stats['schema_version'] = "unknown"

        # Get event count
        try:
            cursor.execute("SELECT COUNT(*) FROM run_events")
            stats['event_count'] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            stats['event_count'] = 0

        conn.close()

        message = f"OK: {stats['run_count']} runs, {stats['event_count']} events, schema v{stats['schema_version']}, {stats['file_size_mb']} MB"
        return True, message, stats

    except sqlite3.DatabaseError as e:
        return False, f"Database corrupted: {e}", stats
    except Exception as e:
        return False, f"Verification error: {e}", stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify SQLite backup integrity for Docker telemetry database"
    )
    parser.add_argument(
        "--backup-path",
        required=True,
        help="Path to backup SQLite file to verify"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress output (only exit code)"
    )

    args = parser.parse_args()

    backup_path = Path(args.backup_path)

    # Verify backup
    success, message, stats = check_database_integrity(backup_path)

    if not args.quiet:
        if success:
            print(f"[OK] {message}")
            if stats:
                print(f"     File: {backup_path}")
                print(f"     Size: {stats.get('file_size_mb', 0)} MB")
                print(f"     Runs: {stats.get('run_count', 0)}")
                print(f"     Events: {stats.get('event_count', 0)}")
                print(f"     Schema: v{stats.get('schema_version', 'unknown')}")
        else:
            print(f"[FAIL] {message}", file=sys.stderr)
            print(f"       File: {backup_path}", file=sys.stderr)

    # Exit with appropriate code
    if not backup_path.exists():
        sys.exit(2)  # File not found
    elif success:
        sys.exit(0)  # Success
    else:
        sys.exit(1)  # Verification failed


if __name__ == "__main__":
    main()
