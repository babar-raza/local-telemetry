#!/usr/bin/env python3
"""
SQLite backup helper for Docker container.

This script uses Python's sqlite3.backup() API which gracefully handles
database locks and active transactions.

Usage:
    python sqlite_backup_helper.py <source_db> <backup_db>
"""

import sqlite3
import sys
from pathlib import Path


def backup_database(source_path: str, backup_path: str) -> bool:
    """
    Backup SQLite database using Python backup API.

    This API handles locks gracefully and works even with active connections.

    Args:
        source_path: Path to source database
        backup_path: Path to backup database

    Returns:
        True if backup succeeded, False otherwise
    """
    try:
        # Connect to source and backup databases
        source_conn = sqlite3.connect(source_path)
        backup_conn = sqlite3.connect(backup_path)

        # Perform backup (copies all pages from source to backup)
        # This method handles locks gracefully
        source_conn.backup(backup_conn)

        # Close connections
        backup_conn.close()
        source_conn.close()

        # Verify backup was created
        if not Path(backup_path).exists():
            print(f"ERROR: Backup file not created: {backup_path}", file=sys.stderr)
            return False

        # Get backup size
        backup_size = Path(backup_path).stat().st_size
        print(f"OK: Backup created ({backup_size} bytes)")

        return True

    except sqlite3.Error as e:
        print(f"ERROR: SQLite error: {e}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) != 3:
        print("Usage: python sqlite_backup_helper.py <source_db> <backup_db>", file=sys.stderr)
        sys.exit(2)

    source_db = sys.argv[1]
    backup_db = sys.argv[2]

    # Verify source exists
    if not Path(source_db).exists():
        print(f"ERROR: Source database not found: {source_db}", file=sys.stderr)
        sys.exit(2)

    # Perform backup
    success = backup_database(source_db, backup_db)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
