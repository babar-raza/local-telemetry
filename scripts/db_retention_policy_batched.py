#!/usr/bin/env python3
"""
Database retention policy with batched deletions - delete records older than N days.

This script implements a time-based retention policy using batched DELETE operations
to handle large datasets reliably. It deletes records in chunks and commits after
each batch to avoid SQLite transaction limitations.

Usage:
    # Preview what would be deleted (safe, no changes)
    python scripts/db_retention_policy_batched.py /data/telemetry.sqlite --days 14 --dry-run

    # Actually delete old records in batches
    python scripts/db_retention_policy_batched.py /data/telemetry.sqlite --days 14

Features:
    - Batched deletion (configurable batch size, default: 100,000)
    - Configurable retention period (default: 30 days)
    - Dry-run mode to preview before deleting
    - Progress tracking with ETA
    - VACUUM to reclaim disk space
    - Detailed logging of deleted records and freed space
"""

import sqlite3
import sys
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import time


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


def cleanup_batched(
    db_path: str,
    retention_days: int = 30,
    batch_size: int = 100000,
    dry_run: bool = False,
) -> dict:
    """Delete records older than retention_days using batched deletes.

    Args:
        db_path: Path to SQLite database file
        retention_days: Number of days to keep (default: 30)
        batch_size: Number of records to delete per batch (default: 100,000)
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
        print(f"Batch size: {batch_size:,} records per batch")
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
            print(f"[DRY RUN] Estimated batches: {(count_to_delete + batch_size - 1) // batch_size:,}")
            print(f"[DRY RUN] Run without --dry-run to actually delete")
            return {"deleted": 0, "would_delete": count_to_delete, "dry_run": True}

        # Batched deletion
        print(f"Deleting {count_to_delete:,} records in batches of {batch_size:,}...")
        print()

        total_deleted = 0
        batch_num = 0
        start_time = datetime.now()
        estimated_batches = (count_to_delete + batch_size - 1) // batch_size

        while True:
            batch_start = time.time()
            batch_num += 1

            # Delete one batch
            cursor.execute(
                """
                DELETE FROM agent_runs
                WHERE event_id IN (
                    SELECT event_id FROM agent_runs
                    WHERE created_at < ?
                    LIMIT ?
                )
            """,
                (cutoff_str, batch_size),
            )

            deleted_in_batch = cursor.rowcount
            if deleted_in_batch == 0:
                break

            conn.commit()
            total_deleted += deleted_in_batch

            # Calculate progress and ETA
            batch_time = time.time() - batch_start
            elapsed = (datetime.now() - start_time).total_seconds()
            avg_time_per_batch = elapsed / batch_num
            batches_remaining = estimated_batches - batch_num
            eta_seconds = avg_time_per_batch * batches_remaining

            progress_pct = (total_deleted / count_to_delete) * 100

            print(
                f"Batch {batch_num}/{estimated_batches}: "
                f"Deleted {deleted_in_batch:,} records in {batch_time:.1f}s | "
                f"Total: {total_deleted:,}/{count_to_delete:,} ({progress_pct:.1f}%) | "
                f"ETA: {eta_seconds/60:.1f}m"
            )

            # Safety check - if we've deleted more than expected, something is wrong
            if total_deleted > count_to_delete * 1.1:  # 10% tolerance
                print("WARNING: Deleted more records than expected, stopping")
                break

        delete_time = (datetime.now() - start_time).total_seconds()
        print()
        print(f"Deleted {total_deleted:,} records in {delete_time/60:.1f} minutes ({batch_num} batches)")
        print()

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
        print(f"VACUUM completed in {vacuum_time/60:.1f} minutes")
        print(f"Deleted {total_deleted:,} records")
        print(f"Freed {freed_mb:.1f} MB disk space")
        print(f"New DB size: {db_size_after / (1024 * 1024):.1f} MB")

        return {
            "deleted": total_deleted,
            "freed_mb": freed_mb,
            "delete_time": delete_time,
            "vacuum_time": vacuum_time,
            "batches": batch_num,
        }

    except sqlite3.Error as e:
        print(f"ERROR: SQLite error: {e}")
        conn.rollback()
        return {"error": str(e)}
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        conn.rollback()
        return {"error": str(e)}
    finally:
        conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Database retention policy with batched deletions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview what would be deleted (safe)
    python %(prog)s /data/telemetry.sqlite --days 14 --dry-run

    # Delete records older than 14 days
    python %(prog)s /data/telemetry.sqlite --days 14

    # Delete with custom batch size
    python %(prog)s /data/telemetry.sqlite --days 14 --batch-size 50000
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
        "--batch-size",
        type=int,
        default=100000,
        help="Records per batch (default: 100,000)",
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

    if args.batch_size < 1000:
        print("ERROR: Batch size must be at least 1,000")
        sys.exit(1)

    result = cleanup_batched(args.db_path, args.days, args.batch_size, args.dry_run)

    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
