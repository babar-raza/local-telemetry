"""
Automatic backup script for D:\\agent-metrics\\db\\telemetry.sqlite
Creates backup in same folder with pattern telemetry.backup.YYYYMMDD_HHMMSS.sqlite
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

def create_backup():
    """Create database backup using SQLite backup API."""
    source_path = Path("D:/agent-metrics/db/telemetry.sqlite")
    if not source_path.exists():
        print(f"X Source database not found: {source_path}")
        return False

    # Generate backup filename in same directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = source_path.parent / f"telemetry.backup.{timestamp}.sqlite"

    print(f"Creating backup: {backup_path}")

    try:
        # Use SQLite backup API (hot backup - database remains accessible)
        source_conn = sqlite3.connect(str(source_path))
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

def main():
    print("=" * 70)
    print("Agent Metrics Database Backup")
    print("=" * 70)
    print()

    success = create_backup()

    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())