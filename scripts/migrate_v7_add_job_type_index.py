#!/usr/bin/env python3
"""
Migration v7: Add job_type index to agent_runs table.

This migration adds an index on the job_type column to improve performance
of DISTINCT queries used by the /api/v1/metadata endpoint.

Usage:
    python scripts/migrate_v7_add_job_type_index.py /path/to/telemetry.db

Features:
    - Creates backup before any changes
    - Idempotent (safe to run multiple times)
    - Verifies index creation
    - Estimates time for large datasets
"""

import sqlite3
import sys
import shutil
from pathlib import Path
from datetime import datetime


def migrate(db_path: str) -> bool:
    """Add job_type index to agent_runs table.

    Args:
        db_path: Path to SQLite database file

    Returns:
        True if successful, False otherwise
    """
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: Database not found: {db_path}")
        return False

    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = db.parent / f"{db.stem}.backup-v7-{timestamp}{db.suffix}"
    print(f"Creating backup: {backup}")
    shutil.copy(db, backup)
    print(f"Backup created: {backup.stat().st_size / (1024*1024):.1f} MB")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if index already exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_runs_job_type'
        """)
        if cursor.fetchone():
            print("Index idx_runs_job_type already exists. Skipping.")
            conn.close()
            return True

        # Get row count for progress estimate
        cursor.execute("SELECT COUNT(*) FROM agent_runs")
        row_count = cursor.fetchone()[0]
        print(f"Table has {row_count:,} rows")

        if row_count > 1_000_000:
            est_minutes = row_count / 2_000_000  # ~2M rows per minute estimate
            print(f"Estimated time: {est_minutes:.1f} minutes")

        print("Creating index idx_runs_job_type on agent_runs(job_type)...")

        # Create index
        start_time = datetime.now()
        cursor.execute("CREATE INDEX idx_runs_job_type ON agent_runs(job_type)")
        conn.commit()
        elapsed = (datetime.now() - start_time).total_seconds()

        print(f"Index created in {elapsed:.1f} seconds")

        # Verify index exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_runs_job_type'
        """)
        if cursor.fetchone():
            print("Migration v7 completed successfully")

            # Show new database size
            new_size = Path(db_path).stat().st_size / (1024*1024)
            print(f"Database size: {new_size:.1f} MB")
            return True
        else:
            print("ERROR: Index creation failed - index not found after CREATE")
            return False

    except sqlite3.Error as e:
        print(f"ERROR: SQLite error: {e}")
        return False
    finally:
        conn.close()


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <database_path>")
        print()
        print("Add job_type index to agent_runs table for faster DISTINCT queries.")
        print()
        print("Example:")
        print(f"  {sys.argv[0]} /data/telemetry.sqlite")
        sys.exit(1)

    db_path = sys.argv[1]
    success = migrate(db_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
