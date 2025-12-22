#!/usr/bin/env python3
"""
Database Migration: Schema v5 → v6

Adds event_id column with UUID values for idempotency.

Changes:
- Add event_id TEXT NOT NULL UNIQUE column
- Add idx_runs_event_id index
- Backfill event_id with UUID for existing rows
- Update schema_version to 6

Usage:
    python scripts/migrate_v5_to_v6.py
    python scripts/migrate_v5_to_v6.py --db-path /path/to/telemetry.sqlite
    python scripts/migrate_v5_to_v6.py --dry-run  # Preview without applying
"""

import os
import sys
import uuid
import sqlite3
import argparse
from pathlib import Path
from datetime import datetime

def check_schema_version(conn: sqlite3.Connection) -> int:
    """
    Check current schema version.

    Args:
        conn: Database connection

    Returns:
        int: Current schema version (0 if not found)
    """
    cursor = conn.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='schema_migrations'
    """)

    if not cursor.fetchone():
        # No schema_migrations table - assume v5 (or older)
        print("[INFO] No schema_migrations table found. Assuming schema v5.")
        return 5

    cursor = conn.execute("""
        SELECT version FROM schema_migrations
        ORDER BY applied_at DESC
        LIMIT 1
    """)

    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        return 5


def check_event_id_exists(conn: sqlite3.Connection) -> bool:
    """
    Check if event_id column exists.

    Args:
        conn: Database connection

    Returns:
        bool: True if event_id column exists
    """
    cursor = conn.execute("PRAGMA table_info(agent_runs)")
    columns = [row[1] for row in cursor.fetchall()]
    return "event_id" in columns


def migrate_v5_to_v6(db_path: str, dry_run: bool = False):
    """
    Migrate database from schema v5 to v6.

    Args:
        db_path: Path to SQLite database
        dry_run: If True, preview changes without applying
    """
    print("=" * 70)
    print("DATABASE MIGRATION: Schema v5 → v6")
    print("=" * 70)
    print(f"Database: {db_path}")
    print(f"Dry run: {dry_run}")
    print()

    if not Path(db_path).exists():
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    # Connect to database
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    try:
        # Check current version
        current_version = check_schema_version(conn)
        print(f"Current schema version: {current_version}")

        if current_version >= 6:
            print("[OK] Database already at v6 or higher. No migration needed.")
            return

        if current_version < 5:
            print(f"[ERROR] Database is at v{current_version}. This script only migrates v5 → v6.")
            print("Please migrate to v5 first.")
            sys.exit(1)

        # Check if event_id already exists
        if check_event_id_exists(conn):
            print("[OK] event_id column already exists. Skipping.")
            return

        # Count existing rows
        cursor = conn.execute("SELECT COUNT(*) FROM agent_runs")
        total_rows = cursor.fetchone()[0]
        print(f"Total rows to migrate: {total_rows}")
        print()

        if dry_run:
            print("[DRY RUN] Would perform the following changes:")
            print("  1. Add event_id column to agent_runs table")
            print("  2. Backfill event_id with UUID for all existing rows")
            print("  3. Create UNIQUE constraint on event_id")
            print("  4. Create idx_runs_event_id index")
            print("  5. Update schema version to 6")
            print()
            print("Run without --dry-run to apply changes.")
            return

        # Step 1: Add event_id column (nullable first)
        print("Step 1: Adding event_id column...")
        conn.execute("""
            ALTER TABLE agent_runs
            ADD COLUMN event_id TEXT
        """)
        conn.commit()
        print("[OK] Column added")

        # Step 2: Backfill event_id with UUID
        print("Step 2: Backfilling event_id with UUIDs...")
        cursor = conn.execute("SELECT id FROM agent_runs WHERE event_id IS NULL")
        rows = cursor.fetchall()

        for i, row in enumerate(rows, 1):
            event_id = str(uuid.uuid4())
            conn.execute("""
                UPDATE agent_runs
                SET event_id = ?
                WHERE id = ?
            """, (event_id, row[0]))

            if i % 1000 == 0:
                conn.commit()
                print(f"  Progress: {i}/{total_rows} rows")

        conn.commit()
        print(f"[OK] Backfilled {total_rows} rows")

        # Step 3: Create UNIQUE index on event_id
        print("Step 3: Creating UNIQUE index on event_id...")
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_event_id
            ON agent_runs(event_id)
        """)
        conn.commit()
        print("[OK] Index created")

        # Step 4: Create or update schema_migrations table
        print("Step 4: Updating schema version...")

        # Create schema_migrations table if it doesn't exist
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version INTEGER NOT NULL,
                description TEXT,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Insert v6 migration record
        conn.execute("""
            INSERT INTO schema_migrations (version, description)
            VALUES (6, 'Add event_id column for idempotency')
        """)

        conn.commit()
        print("[OK] Schema version updated to 6")

        print()
        print("=" * 70)
        print("[SUCCESS] Migration completed successfully!")
        print("=" * 70)
        print(f"Migrated {total_rows} rows")
        print("Schema version: 5 → 6")
        print()
        print("Next steps:")
        print("1. Start the telemetry API service")
        print("2. Migrate applications to use HTTP API client")
        print("=" * 70)

    except Exception as e:
        print()
        print("=" * 70)
        print(f"[ERROR] Migration failed: {e}")
        print("=" * 70)
        print("The database has been left in an inconsistent state.")
        print("Please restore from backup or contact support.")
        sys.exit(1)

    finally:
        conn.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate telemetry database from schema v5 to v6"
    )
    parser.add_argument(
        "--db-path",
        default=os.getenv("TELEMETRY_DB_PATH", "D:/agent-metrics/db/telemetry.sqlite"),
        help="Path to SQLite database (default: $TELEMETRY_DB_PATH or D:/agent-metrics/db/telemetry.sqlite)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without applying"
    )

    args = parser.parse_args()

    migrate_v5_to_v6(args.db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
