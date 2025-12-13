#!/usr/bin/env python
"""
Database Backup Script

Creates daily backups of the telemetry database with rotation.

Usage:
    python scripts/backup_database.py [--keep N]

Options:
    --keep N    Number of backups to keep (default: 7)

Schedule this script to run daily via:
- Windows Task Scheduler
- cron (Linux/Mac)
- systemd timer
"""

import sqlite3
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime

# Fix encoding on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def check_database_integrity(db_path: Path) -> tuple[bool, str]:
    """Check if database is healthy before backup."""
    if not db_path.exists():
        return False, "Database file does not exist"

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check")
        result = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            return True, "ok"
        else:
            return False, f"integrity issue: {result}"

    except sqlite3.DatabaseError as e:
        return False, f"corrupted: {e}"
    except Exception as e:
        return False, f"error: {e}"


def create_backup(db_path: Path, backup_dir: Path) -> tuple[bool, str, Path | None]:
    """
    Create a backup of the database.

    Uses SQLite's backup API for a consistent backup even while
    the database is being written to.

    Returns:
        Tuple of (success: bool, message: str, backup_path: Path | None)
    """
    if not db_path.exists():
        return False, "Database file does not exist", None

    # Check integrity first
    is_healthy, msg = check_database_integrity(db_path)
    if not is_healthy:
        return False, f"Cannot backup corrupted database: {msg}", None

    # Create backup directory if needed
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate backup filename with date
    date_str = datetime.now().strftime("%Y%m%d")
    backup_name = f"telemetry.backup.{date_str}.sqlite"
    backup_path = backup_dir / backup_name

    # If today's backup already exists, add time component
    if backup_path.exists():
        time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"telemetry.backup.{time_str}.sqlite"
        backup_path = backup_dir / backup_name

    try:
        # Use SQLite backup API for consistent backup
        source_conn = sqlite3.connect(str(db_path))
        dest_conn = sqlite3.connect(str(backup_path))

        source_conn.backup(dest_conn)

        source_conn.close()
        dest_conn.close()

        # Verify backup
        is_healthy, msg = check_database_integrity(backup_path)
        if not is_healthy:
            backup_path.unlink()
            return False, f"Backup verification failed: {msg}", None

        backup_size = backup_path.stat().st_size / 1024 / 1024
        return True, f"Created backup: {backup_name} ({backup_size:.2f} MB)", backup_path

    except Exception as e:
        if backup_path.exists():
            backup_path.unlink()
        return False, f"Backup failed: {e}", None


def rotate_backups(backup_dir: Path, keep: int = 7) -> list[Path]:
    """
    Remove old backups, keeping only the most recent N.

    Args:
        backup_dir: Directory containing backups
        keep: Number of backups to keep

    Returns:
        List of deleted backup paths
    """
    backups = sorted(
        backup_dir.glob("telemetry.backup.*.sqlite"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,  # Newest first
    )

    deleted = []
    for backup in backups[keep:]:
        backup.unlink()
        deleted.append(backup)

    return deleted


def main():
    """Main entry point."""
    # Parse args
    keep = 7
    for i, arg in enumerate(sys.argv):
        if arg == "--keep" and i + 1 < len(sys.argv):
            try:
                keep = int(sys.argv[i + 1])
            except ValueError:
                print(f"Invalid --keep value: {sys.argv[i + 1]}")
                sys.exit(1)

    # Get paths from environment or defaults
    metrics_dir = Path(os.getenv("AGENT_METRICS_DIR", "D:/agent-metrics"))
    db_path = metrics_dir / "db" / "telemetry.sqlite"
    backup_dir = metrics_dir / "backups"

    print("=" * 60)
    print("DATABASE BACKUP")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"Backup dir: {backup_dir}")
    print(f"Keep backups: {keep}")

    # Step 1: Check database health
    print("\n1. Checking database integrity...")
    is_healthy, msg = check_database_integrity(db_path)
    if is_healthy:
        print(f"   Database is healthy")
    else:
        print(f"   WARNING: {msg}")
        print("   Run recover_database.py to fix the database first")
        sys.exit(1)

    # Step 2: Create backup
    print("\n2. Creating backup...")
    success, msg, backup_path = create_backup(db_path, backup_dir)
    print(f"   {msg}")

    if not success:
        sys.exit(1)

    # Step 3: Rotate old backups
    print(f"\n3. Rotating backups (keeping {keep})...")
    deleted = rotate_backups(backup_dir, keep)
    if deleted:
        for d in deleted:
            print(f"   Deleted: {d.name}")
    else:
        print("   No old backups to delete")

    # Step 4: Summary
    print("\n4. Current backups:")
    backups = sorted(backup_dir.glob("telemetry.backup.*.sqlite"))
    for b in backups:
        size_mb = b.stat().st_size / 1024 / 1024
        mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"   {b.name}: {size_mb:.2f} MB ({mtime})")

    print("\n" + "=" * 60)
    print("BACKUP COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
