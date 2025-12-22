"""
Schema Migration v4 -> v5: Add website fields

Adds three new columns to support API spec compliance:
- website: Root domain (e.g., "aspose.com")
- website_section: Subdomain/section (e.g., "products", "docs", "main")
- item_name: Specific page/entity (e.g., "/slides/net/")

Usage:
    python scripts/migrate_v5.py

Environment Variables:
    TELEMETRY_DATABASE_PATH: Path to telemetry.sqlite (default: D:\agent-metrics\db\telemetry.sqlite)
"""

import os
import sqlite3
import sys
from pathlib import Path


def migrate_v5(database_path: Path) -> bool:
    """
    Apply v5 schema migration to add website fields.

    Args:
        database_path: Path to telemetry.sqlite database

    Returns:
        bool: True if migration succeeded, False otherwise
    """
    if not database_path.exists():
        print(f"[ERROR] Database not found: {database_path}")
        return False

    print(f"[INFO] Migrating database: {database_path}")
    print(f"[INFO] Database size: {database_path.stat().st_size / (1024*1024):.2f} MB")

    try:
        # Open connection with timeout to avoid lock issues
        conn = sqlite3.connect(database_path, timeout=10.0)
        cursor = conn.cursor()

        # Check current schema
        cursor.execute("PRAGMA table_info(agent_runs)")
        columns = {row[1] for row in cursor.fetchall()}
        print(f"[INFO] Current columns: {len(columns)}")

        # Add website column
        if 'website' not in columns:
            cursor.execute('ALTER TABLE agent_runs ADD COLUMN website TEXT')
            print('[OK] Added website column')
        else:
            print('[OK] website column already exists')

        # Add website_section column
        if 'website_section' not in columns:
            cursor.execute('ALTER TABLE agent_runs ADD COLUMN website_section TEXT')
            print('[OK] Added website_section column')
        else:
            print('[OK] website_section column already exists')

        # Add item_name column
        if 'item_name' not in columns:
            cursor.execute('ALTER TABLE agent_runs ADD COLUMN item_name TEXT')
            print('[OK] Added item_name column')
        else:
            print('[OK] item_name column already exists')

        # Create indexes for query performance
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_runs_website ON agent_runs(website)')
        print('[OK] Created index on website')

        cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_runs_website_section ON agent_runs(website, website_section)')
        print('[OK] Created index on website + website_section')

        # Verify migration
        cursor.execute('''
            SELECT
                COUNT(*) as total_runs,
                COUNT(website) as runs_with_website,
                COUNT(website_section) as runs_with_website_section,
                COUNT(item_name) as runs_with_item_name
            FROM agent_runs
        ''')
        row = cursor.fetchone()

        print('\n[OK] v5 Migration Complete:')
        print(f'  Total runs: {row[0]:,}')
        print(f'  Runs with website: {row[1]:,}')
        print(f'  Runs with website_section: {row[2]:,}')
        print(f'  Runs with item_name: {row[3]:,}')

        # Commit changes
        conn.commit()
        conn.close()

        print('\n[SUCCESS] Migration completed successfully')
        return True

    except sqlite3.DatabaseError as e:
        print(f"[ERROR] Database error: {e}")
        print("[HELP] Database may be corrupted. Try:")
        print("  1. Check database integrity: sqlite3 <path> 'PRAGMA integrity_check;'")
        print("  2. Restore from backup if available")
        return False

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main entry point for migration script."""
    # Get database path from environment or use default
    db_path_str = os.getenv('TELEMETRY_DATABASE_PATH', r'D:\agent-metrics\db\telemetry.sqlite')
    db_path = Path(db_path_str)

    print("=" * 60)
    print("Schema Migration v4 -> v5: Add Website Fields")
    print("=" * 60)

    # Run migration
    success = migrate_v5(db_path)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
