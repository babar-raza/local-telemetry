#!/usr/bin/env python3
"""
Database retention policy - delete records older than N days.

This script implements a time-based retention policy for the telemetry database.
It deletes records older than the specified retention period and reclaims disk
space using VACUUM.

Usage:
    # Preview what would be deleted (safe, no changes)
    python scripts/db_retention_policy.py /data/telemetry.sqlite --days 30 --dry-run

    # Actually delete old records
    python scripts/db_retention_policy.py /data/telemetry.sqlite --days 30

Features:
    - Configurable retention period (default: 30 days)
    - Dry-run mode to preview before deleting
    - VACUUM to reclaim disk space
    - Detailed logging of deleted records and freed space
"""

import sqlite3
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path


def get_db_stats(cursor) -> dict:
    """Get database statistics."""
    cursor.execute("SELECT COUNT(*) FROM agent_runs")
    total_rows = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM agent_runs")
    min_date, max_date = cursor.fetchone()

    return {
        "total_rows": total_rows,
        "oldest_record": min_date,
        "newest_record": max_date,
    }


def cleanup(db_path: str, retention_days: int = 30, dry_run: bool = False) -> dict:
    """Delete records older than retention_days.

    Args:
        db_path: Path to SQLite database file
        retention_days: Number of days to keep (default: 30)
        dry_run: If True, only preview what would be deleted

    Returns:
        Dictionary with deletion results
    """
    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: Database not found: {db_path}")
        return {"error": "Database not found"}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

        print(f"Retention policy: {retention_days} days")
        print(f"Cutoff date: {cutoff_str}")
        print()

        # Get current stats
        stats = get_db_stats(cursor)
        print(f"Current database stats:")
        print(f"  Total rows: {stats['total_rows']:,}")
        print(f"  Oldest record: {stats['oldest_record']}")
        print(f"  Newest record: {stats['newest_record']}")
        print()

        # Count records to delete
        cursor.execute(
            """
            SELECT COUNT(*) FROM agent_runs
            WHERE created_at < ?
        """,
            (cutoff_str,),
        )
        count_to_delete = cursor.fetchone()[0]

        # Get current DB size
        db_size_before = db.stat().st_size
        db_size_mb = db_size_before / (1024 * 1024)

        print(f"Records to delete: {count_to_delete:,}")
        print(f"Records to keep: {stats['total_rows'] - count_to_delete:,}")
        print(f"Current DB size: {db_size_mb:.1f} MB")
        print()

        if count_to_delete == 0:
            print("No records to delete.")
            return {"deleted": 0, "freed_mb": 0}

        if dry_run:
            print(f"[DRY RUN] Would delete {count_to_delete:,} records")
            print(f"[DRY RUN] Run without --dry-run to actually delete")
            return {"deleted": 0, "would_delete": count_to_delete, "dry_run": True}

        # Delete old records
        print(f"Deleting {count_to_delete:,} records...")
        start_time = datetime.now()

        cursor.execute(
            """
            DELETE FROM agent_runs
            WHERE created_at < ?
        """,
            (cutoff_str,),
        )
        deleted = cursor.rowcount
        conn.commit()

        delete_time = (datetime.now() - start_time).total_seconds()
        print(f"Deleted {deleted:,} records in {delete_time:.1f} seconds")

        # Vacuum to reclaim space
        print("Running VACUUM to reclaim disk space (this may take a while)...")
        vacuum_start = datetime.now()
        cursor.execute("VACUUM")
        conn.commit()
        vacuum_time = (datetime.now() - vacuum_start).total_seconds()

        # Calculate freed space
        db_size_after = db.stat().st_size
        freed_bytes = db_size_before - db_size_after
        freed_mb = freed_bytes / (1024 * 1024)

        print()
        print(f"VACUUM completed in {vacuum_time:.1f} seconds")
        print(f"Deleted {deleted:,} records")
        print(f"Freed {freed_mb:.1f} MB disk space")
        print(f"New DB size: {db_size_after / (1024 * 1024):.1f} MB")

        return {"deleted": deleted, "freed_mb": freed_mb, "vacuum_time": vacuum_time}

    except sqlite3.Error as e:
        print(f"ERROR: SQLite error: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Database retention policy - delete records older than N days",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview what would be deleted (safe)
    python %(prog)s /data/telemetry.sqlite --days 30 --dry-run

    # Delete records older than 30 days
    python %(prog)s /data/telemetry.sqlite --days 30

    # Delete records older than 90 days
    python %(prog)s /data/telemetry.sqlite --days 90
""",
    )
    parser.add_argument("db_path", help="Path to SQLite database")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Retention period in days (default: 30)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without deleting (safe mode)",
    )

    args = parser.parse_args()

    if args.days < 1:
        print("ERROR: Retention days must be at least 1")
        sys.exit(1)

    result = cleanup(args.db_path, args.days, args.dry_run)

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
