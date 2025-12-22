#!/usr/bin/env python
"""
Migration Script: Schema v3 to v4 - Add Git Commit Tracking

This migration adds git commit tracking fields to support linking
telemetry runs to their resulting git commits.

SCHEMA VERSION: 3 -> 4

Changes:
- Add git_commit_hash column (TEXT, nullable) - The commit SHA
- Add git_commit_source column (TEXT, nullable, CHECK constraint) - 'manual', 'llm', 'ci'
- Add git_commit_author column (TEXT, nullable) - Commit author
- Add git_commit_timestamp column (TEXT, nullable) - When commit was made
- Create idx_runs_commit index for fast commit-based queries
- Update schema_migrations table to version 4

Usage:
    python scripts/migrate_v3_to_v4.py [database_path]

Example:
    python scripts/migrate_v3_to_v4.py D:/agent-metrics/db/telemetry.sqlite

    # With explicit test database
    python scripts/migrate_v3_to_v4.py --db D:/agent-metrics/db/telemetry.test.sqlite

Rollback:
    SQLite doesn't support DROP COLUMN easily. To rollback:
    1. Restore from pre-migration backup (created automatically)
    2. Backups are stored in the same directory with .pre_v4_backup suffix
"""

import sqlite3
import shutil
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
    backup_path = db_path.parent / f"{db_path.stem}.pre_v4_backup.{timestamp}.sqlite"

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


def get_existing_columns(cursor) -> set[str]:
    """Get set of existing column names in agent_runs table."""
    cursor.execute("PRAGMA table_info(agent_runs)")
    return {row[1] for row in cursor.fetchall()}


def migrate_v3_to_v4(db_path: str, skip_backup: bool = False) -> tuple[bool, list[str]]:
    """
    Migrate database from schema v3 to v4.

    Adds git commit tracking fields:
    - git_commit_hash
    - git_commit_source
    - git_commit_author
    - git_commit_timestamp

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

        if current_version >= 4:
            messages.append("[SKIP] Database is already at v4 or higher")
            conn.close()
            return True, messages

        # Step 5: Get existing columns
        existing_columns = get_existing_columns(cursor)
        messages.append(f"[INFO] Existing columns: {len(existing_columns)}")

        # Step 6: Add new columns (if they don't exist)
        new_columns = [
            ("git_commit_hash", "TEXT"),
            ("git_commit_source", "TEXT CHECK(git_commit_source IN ('manual', 'llm', 'ci', NULL))"),
            ("git_commit_author", "TEXT"),
            ("git_commit_timestamp", "TEXT"),
        ]

        for col_name, col_type in new_columns:
            if col_name in existing_columns:
                messages.append(f"[SKIP] Column {col_name} already exists")
            else:
                try:
                    cursor.execute(f"ALTER TABLE agent_runs ADD COLUMN {col_name} {col_type}")
                    messages.append(f"[OK] Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    messages.append(f"[FAIL] Failed to add column {col_name}: {e}")
                    conn.close()
                    return False, messages

        # Step 7: Create index on git_commit_hash
        messages.append("[INFO] Creating index on git_commit_hash...")
        try:
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_runs_commit
                ON agent_runs(git_commit_hash)
            """)
            messages.append("[OK] Created idx_runs_commit index")
        except sqlite3.OperationalError as e:
            messages.append(f"[WARN] Index creation warning: {e}")

        # Step 8: Update schema version
        messages.append("[INFO] Updating schema version to 4...")
        try:
            cursor.execute("""
                INSERT INTO schema_migrations (version, description, applied_at)
                VALUES (4, 'Added git commit tracking fields (hash, source, author, timestamp)', datetime('now'))
            """)
            messages.append("[OK] Updated schema version to 4")
        except sqlite3.IntegrityError:
            messages.append("[SKIP] Schema version 4 already recorded")

        # Step 9: Commit changes
        conn.commit()
        messages.append("[OK] Changes committed")

        # Step 10: Verify migration
        messages.append("[INFO] Verifying migration...")

        # Verify columns
        final_columns = get_existing_columns(cursor)
        for col_name, _ in new_columns:
            if col_name in final_columns:
                messages.append(f"[OK] Verified column: {col_name}")
            else:
                messages.append(f"[FAIL] Missing column after migration: {col_name}")
                conn.close()
                return False, messages

        # Verify index
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_runs_commit'
        """)
        if cursor.fetchone():
            messages.append("[OK] Verified index: idx_runs_commit")
        else:
            messages.append("[WARN] Index idx_runs_commit not found")

        # Verify schema version
        final_version = get_schema_version(cursor)
        messages.append(f"[OK] Final schema version: {final_version}")

        conn.close()

        # Step 11: Post-migration integrity check
        is_healthy, msg = check_database_integrity(db_path)
        if is_healthy:
            messages.append("[OK] Post-migration integrity check passed")
        else:
            messages.append(f"[WARN] Post-migration integrity issue: {msg}")

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
    print("MIGRATION: Schema v3 to v4 - Add Git Commit Tracking")
    print("=" * 70)
    print(f"Target database: {db_path}")
    print(f"Skip backup: {skip_backup}")
    print("-" * 70)

    # Run migration
    success, messages = migrate_v3_to_v4(db_path, skip_backup=skip_backup)

    # Print messages
    for message in messages:
        print(message)

    # Print summary
    print("-" * 70)
    if success:
        print("[SUCCESS] Migration completed successfully")
        print("\nNew columns added:")
        print("  - git_commit_hash: The 40-character git commit SHA")
        print("  - git_commit_source: How commit was created ('manual', 'llm', 'ci')")
        print("  - git_commit_author: Git author string")
        print("  - git_commit_timestamp: ISO8601 timestamp of commit")
        print("\nUsage:")
        print("  from telemetry import TelemetryClient")
        print("  client = TelemetryClient.from_env()")
        print("  client.associate_commit(run_id, commit_hash, 'llm')")
        return 0
    else:
        print("[FAILED] Migration failed")
        print("\nIf needed, restore from backup:")
        print(f"  Look for .pre_v4_backup.*.sqlite files in {Path(db_path).parent}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
