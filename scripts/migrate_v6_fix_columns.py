#!/usr/bin/env python
"""
Migration Script: Fix Missing Git Commit Columns (v6)

This migration adds missing git commit tracking columns to the agent_runs table.
These columns are defined in schema v6 but may be absent in databases upgraded
from earlier versions.

SCHEMA FIX: Adds columns that should exist in v6

Columns to add (if missing):
- git_commit_source TEXT - How commit was created ('manual', 'llm', 'ci')
- git_commit_author TEXT - Git author string (e.g., "Name <email>")
- git_commit_timestamp TEXT - ISO8601 timestamp of when commit was made

Note: git_commit_hash was added in v4 migration and should already exist.

Usage:
    python scripts/migrate_v6_fix_columns.py [database_path]

Example:
    python scripts/migrate_v6_fix_columns.py D:/agent-metrics/db/telemetry.sqlite

    # With explicit database path
    python scripts/migrate_v6_fix_columns.py --db ./telemetry.db

    # Skip backup (for testing only)
    python scripts/migrate_v6_fix_columns.py --skip-backup

Rollback:
    SQLite doesn't support DROP COLUMN easily. To rollback:
    1. Restore from pre-migration backup (created automatically)
    2. Backups are stored in the same directory with .pre_v6_fix_backup suffix
"""

import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime


def check_database_integrity(db_path: Path) -> tuple[bool, str]:
    """Check if database is healthy before migration."""
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


def create_pre_migration_backup(db_path: Path) -> tuple[bool, str, Path | None]:
    """
    Create a backup before migration.

    Returns:
        Tuple of (success: bool, message: str, backup_path: Path | None)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"{db_path.stem}.pre_v6_fix_backup.{timestamp}.sqlite"

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
        return True, f"Created backup: {backup_path.name} ({backup_size:.2f} MB)", backup_path

    except Exception as e:
        if backup_path.exists():
            backup_path.unlink()
        return False, f"Backup failed: {e}", None


def get_schema_version(cursor) -> int:
    """Get current schema version from database."""
    try:
        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        result = cursor.fetchone()[0]
        return result if result is not None else 0
    except sqlite3.OperationalError:
        return 0


def get_existing_columns(cursor, table_name: str = "agent_runs") -> set[str]:
    """Get set of existing column names in specified table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def migrate_v6_fix_columns(db_path: str, skip_backup: bool = False) -> tuple[bool, list[str]]:
    """
    Add missing git commit columns to agent_runs table.

    This migration is idempotent - safe to run multiple times.

    Args:
        db_path: Path to SQLite database file
        skip_backup: If True, skip creating backup (for testing)

    Returns:
        Tuple of (success: bool, messages: list[str])
    """
    messages = []
    db_path = Path(db_path)

    try:
        # Step 1: Check database exists
        if not db_path.exists():
            return False, [f"[FAIL] Database file not found: {db_path}"]
        messages.append(f"[INFO] Target database: {db_path}")

        # Step 2: Check integrity
        is_healthy, msg = check_database_integrity(db_path)
        if not is_healthy:
            return False, [f"[FAIL] Database integrity check failed: {msg}"]
        messages.append("[OK] Database integrity check passed")

        # Step 3: Create backup (unless skipped)
        if not skip_backup:
            success, msg, backup_path = create_pre_migration_backup(db_path)
            if not success:
                return False, messages + [f"[FAIL] {msg}"]
            messages.append(f"[OK] {msg}")
        else:
            messages.append("[SKIP] Backup skipped (test mode)")

        # Step 4: Connect and check current version
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        current_version = get_schema_version(cursor)
        messages.append(f"[INFO] Current schema version: {current_version}")

        # Step 5: Get existing columns
        existing_columns = get_existing_columns(cursor)
        messages.append(f"[INFO] Existing columns in agent_runs: {len(existing_columns)}")

        # Step 6: Define columns to add (if missing)
        # Note: git_commit_hash should already exist from v4, but we check anyway
        columns_to_add = [
            ("git_commit_source", "TEXT"),
            ("git_commit_author", "TEXT"),
            ("git_commit_timestamp", "TEXT"),
        ]

        # Track what we actually added
        columns_added = []
        columns_skipped = []

        for col_name, col_type in columns_to_add:
            if col_name in existing_columns:
                messages.append(f"[SKIP] Column '{col_name}' already exists")
                columns_skipped.append(col_name)
            else:
                try:
                    cursor.execute(f"ALTER TABLE agent_runs ADD COLUMN {col_name} {col_type}")
                    messages.append(f"[OK] Added column: {col_name} ({col_type})")
                    columns_added.append(col_name)
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e).lower():
                        messages.append(f"[SKIP] Column '{col_name}' already exists (detected during ALTER)")
                        columns_skipped.append(col_name)
                    else:
                        messages.append(f"[FAIL] Failed to add column '{col_name}': {e}")
                        conn.close()
                        return False, messages

        # Step 7: Commit changes
        conn.commit()
        messages.append("[OK] Changes committed")

        # Step 8: Verify migration with PRAGMA table_info
        messages.append("[INFO] Verifying migration with PRAGMA table_info...")

        final_columns = get_existing_columns(cursor)
        all_verified = True

        for col_name, _ in columns_to_add:
            if col_name in final_columns:
                messages.append(f"[OK] Verified column exists: {col_name}")
            else:
                messages.append(f"[FAIL] Column missing after migration: {col_name}")
                all_verified = False

        if not all_verified:
            conn.close()
            return False, messages

        # Step 9: Verify git_commit_hash also exists (sanity check)
        if "git_commit_hash" in final_columns:
            messages.append("[OK] Verified git_commit_hash column exists (from v4)")
        else:
            messages.append("[WARN] git_commit_hash column is missing (expected from v4 migration)")

        conn.close()

        # Step 10: Post-migration integrity check
        is_healthy, msg = check_database_integrity(db_path)
        if is_healthy:
            messages.append("[OK] Post-migration integrity check passed")
        else:
            messages.append(f"[WARN] Post-migration integrity issue: {msg}")

        # Step 11: Summary
        messages.append("-" * 50)
        messages.append("[SUMMARY]")
        messages.append(f"  Columns added: {len(columns_added)}")
        if columns_added:
            for col in columns_added:
                messages.append(f"    - {col}")
        messages.append(f"  Columns skipped (already existed): {len(columns_skipped)}")
        if columns_skipped:
            for col in columns_skipped:
                messages.append(f"    - {col}")

        return True, messages

    except sqlite3.Error as e:
        messages.append(f"[FAIL] Database error: {e}")
        return False, messages
    except Exception as e:
        messages.append(f"[FAIL] Unexpected error: {e}")
        return False, messages


def main():
    """Main entry point."""
    # Parse command line arguments
    db_path = None
    skip_backup = False

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--db" and i + 1 < len(sys.argv):
            db_path = sys.argv[i + 1]
            i += 2
        elif arg == "--skip-backup":
            skip_backup = True
            i += 1
        elif arg in ("--help", "-h"):
            print(__doc__)
            return 0
        elif not arg.startswith("-"):
            db_path = arg
            i += 1
        else:
            i += 1

    # Default path from environment or standard location
    if db_path is None:
        metrics_dir = os.getenv("AGENT_METRICS_DIR", "D:/agent-metrics")
        db_path = os.path.join(metrics_dir, "db", "telemetry.sqlite")

    print("=" * 70)
    print("MIGRATION: Fix Missing Git Commit Columns (v6)")
    print("=" * 70)
    print(f"Target database: {db_path}")
    print(f"Skip backup: {skip_backup}")
    print("-" * 70)

    # Run migration
    success, messages = migrate_v6_fix_columns(db_path, skip_backup=skip_backup)

    # Print messages
    for message in messages:
        print(message)

    # Print final result
    print("-" * 70)
    if success:
        print("[SUCCESS] Migration completed successfully")
        print()
        print("The following columns are now available in agent_runs:")
        print("  - git_commit_source: How commit was created ('manual', 'llm', 'ci')")
        print("  - git_commit_author: Git author string (e.g., 'Name <email>')")
        print("  - git_commit_timestamp: ISO8601 timestamp of commit")
        print()
        print("These columns support the /api/v1/runs/{event_id}/associate-commit endpoint.")
        print()
        print("ROLLBACK INSTRUCTIONS:")
        print("  If you need to undo this migration, restore from backup:")
        print(f"  1. Find .pre_v6_fix_backup.*.sqlite files in {Path(db_path).parent}")
        print("  2. Stop the telemetry service")
        print("  3. Replace the database file with the backup")
        print("  4. Restart the telemetry service")
        return 0
    else:
        print("[FAILED] Migration failed")
        print()
        print("RECOVERY INSTRUCTIONS:")
        print("  If a backup was created, restore from it:")
        print(f"  Look for .pre_v6_fix_backup.*.sqlite files in {Path(db_path).parent}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
