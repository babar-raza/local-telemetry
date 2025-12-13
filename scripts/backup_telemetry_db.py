"""
Telemetry database backup script.
"""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for telemetry imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from telemetry import TelemetryConfig

def create_backup():
    """Create database backup using SQLite backup API."""
    config = TelemetryConfig.from_env()

    # Create backup directory
    backup_dir = config.metrics_dir / "backups"
    backup_dir.mkdir(exist_ok=True)

    # Generate backup filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"telemetry_backup_{timestamp}.sqlite"

    print(f"Creating backup: {backup_path}")

    try:
        # Use SQLite backup API (hot backup - database remains accessible)
        source_conn = sqlite3.connect(str(config.database_path))
        backup_conn = sqlite3.connect(str(backup_path))

        source_conn.backup(backup_conn)

        source_conn.close()
        backup_conn.close()

        # Verify backup
        verify_conn = sqlite3.connect(str(backup_path))
        cursor = verify_conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        verify_conn.close()

        if result != "ok":
            print(f"X Backup verification failed: {result}")
            backup_path.unlink()
            return False

        backup_size_mb = backup_path.stat().st_size / (1024 * 1024)
        print(f"OK Backup created successfully ({backup_size_mb:.2f} MB)")

        return True

    except Exception as e:
        print(f"X Backup failed: {e}")
        if backup_path.exists():
            backup_path.unlink()
        return False

def apply_retention_policy(keep_days=7):
    """Remove old backups beyond retention period."""
    config = TelemetryConfig.from_env()
    backup_dir = config.metrics_dir / "backups"

    if not backup_dir.exists():
        return

    cutoff_date = datetime.now() - timedelta(days=keep_days)
    print(f"\nApplying retention policy (keep last {keep_days} days)...")

    backups = sorted(backup_dir.glob("telemetry_backup_*.sqlite"))

    if len(backups) <= 1:
        print("  Keeping all backups (only 1 or 0 exist)")
        return

    deleted = 0
    for backup in backups[:-1]:  # Keep at least the last one
        backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
        if backup_time < cutoff_date:
            print(f"  Deleting old backup: {backup.name}")
            backup.unlink()
            deleted += 1

    if deleted == 0:
        print("  No old backups to delete")
    else:
        print(f"  Deleted {deleted} old backup(s)")

def restore_backup(backup_path: str):
    """Restore from backup."""
    config = TelemetryConfig.from_env()

    backup_file = Path(backup_path)
    if not backup_file.exists():
        print(f"X Backup file not found: {backup_path}")
        return False

    print(f"! WARNING: This will replace the current database!")
    print(f"  Current: {config.database_path}")
    print(f"  Backup: {backup_file}")
    response = input("Continue? (yes/no): ")

    if response.lower() != "yes":
        print("Restore cancelled")
        return False

    try:
        # Backup current database first
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safety_backup = config.database_path.parent / f"telemetry_before_restore_{timestamp}.sqlite"

        shutil.copy2(str(config.database_path), str(safety_backup))
        print(f"OK Created safety backup: {safety_backup}")

        # Restore from backup
        shutil.copy2(str(backup_file), str(config.database_path))
        print(f"OK Database restored from backup")

        # Verify
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            print(f"OK Restore verified successfully")
            return True
        else:
            print(f"X Restore verification failed")
            # Restore safety backup
            shutil.copy2(str(safety_backup), str(config.database_path))
            print(f"! Rolled back to safety backup")
            return False

    except Exception as e:
        print(f"X Restore failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Telemetry database backup tool")
    parser.add_argument("--restore", help="Restore from backup file")
    parser.add_argument("--keep-days", type=int, default=7, help="Retention period in days")
    args = parser.parse_args()

    print("=" * 70)
    print("Telemetry Database Backup")
    print("=" * 70)
    print()

    if args.restore:
        success = restore_backup(args.restore)
    else:
        success = create_backup()
        if success:
            apply_retention_policy(args.keep_days)

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
