"""
Migration Script: Add insight_id Column to agent_runs Table

This migration adds the insight_id column to support SEO Intelligence integration.
The insight_id links action runs to their originating insights.

SCHEMA VERSION: 1 -> 2

Changes:
- Add insight_id column as nullable TEXT
- Create idx_runs_insight index for fast insight-based queries
- Update schema_migrations table to version 2

Usage:
    python scripts/migrate_add_insight_id.py [database_path]

Example:
    python scripts/migrate_add_insight_id.py D:/agent-metrics/db/telemetry.sqlite
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


def migrate_add_insight_id(db_path: str) -> tuple[bool, list[str]]:
    """
    Add insight_id column to agent_runs table.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Tuple of (success: bool, messages: list[str])
    """
    messages = []

    try:
        # Check if database exists
        if not Path(db_path).exists():
            return False, [f"[FAIL] Database file not found: {db_path}"]

        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check current schema version
        try:
            cursor.execute("SELECT MAX(version) FROM schema_migrations")
            current_version = cursor.fetchone()[0] or 0
            messages.append(f"[INFO] Current schema version: {current_version}")
        except sqlite3.OperationalError:
            current_version = 0
            messages.append("[INFO] No schema_migrations table found (version 0)")

        # Check if insight_id column already exists
        cursor.execute("PRAGMA table_info(agent_runs)")
        columns = [row[1] for row in cursor.fetchall()]

        if "insight_id" in columns:
            messages.append("[SKIP] insight_id column already exists")
            conn.close()
            return True, messages

        # Step 1: Add insight_id column
        messages.append("[INFO] Adding insight_id column to agent_runs table...")
        cursor.execute("""
            ALTER TABLE agent_runs
            ADD COLUMN insight_id TEXT
        """)
        messages.append("[OK] Added insight_id column")

        # Step 2: Create index on insight_id
        messages.append("[INFO] Creating index on insight_id...")
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_runs_insight
            ON agent_runs(insight_id)
        """)
        messages.append("[OK] Created idx_runs_insight index")

        # Step 3: Update schema version
        if current_version < 2:
            messages.append("[INFO] Updating schema version to 2...")
            cursor.execute("""
                INSERT INTO schema_migrations (version, description, applied_at)
                VALUES (2, 'Added insight_id column for SEO Intelligence integration', datetime('now'))
            """)
            messages.append("[OK] Updated schema version to 2")

        # Commit changes
        conn.commit()

        # Verify migration
        cursor.execute("PRAGMA table_info(agent_runs)")
        columns_after = [row[1] for row in cursor.fetchall()]

        if "insight_id" in columns_after:
            messages.append("[OK] Migration successful - insight_id column verified")
        else:
            messages.append("[FAIL] Migration failed - insight_id column not found after migration")
            conn.close()
            return False, messages

        # Check index was created
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_runs_insight'
        """)
        index_exists = cursor.fetchone() is not None

        if index_exists:
            messages.append("[OK] idx_runs_insight index verified")
        else:
            messages.append("[WARN] idx_runs_insight index not found")

        # Get final schema version
        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        final_version = cursor.fetchone()[0] or 0
        messages.append(f"[OK] Final schema version: {final_version}")

        conn.close()

        return True, messages

    except sqlite3.Error as e:
        messages.append(f"[FAIL] Database error: {e}")
        return False, messages
    except Exception as e:
        messages.append(f"[FAIL] Unexpected error: {e}")
        return False, messages


def main():
    """Main entry point."""
    # Get database path from command line or use default
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Default path
        db_path = "D:/agent-metrics/db/telemetry.sqlite"

    print(f"Migration: Add insight_id column to agent_runs")
    print(f"Target database: {db_path}")
    print("-" * 60)

    # Run migration
    success, messages = migrate_add_insight_id(db_path)

    # Print messages
    for message in messages:
        print(message)

    # Print summary
    print("-" * 60)
    if success:
        print("[SUCCESS] Migration completed successfully")
        return 0
    else:
        print("[FAILED] Migration failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
