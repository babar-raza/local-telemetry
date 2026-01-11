"""
Telemetry Platform - Database Setup Script

Creates the SQLite database with telemetry schema.
Idempotent and safe to run multiple times.

Usage:
    python scripts/setup_database.py
    python scripts/setup_database.py --db-path /path/to/telemetry.sqlite

Exit codes:
    0 - Success
    1 - Failure
"""

import sys
import os
import argparse
from pathlib import Path

# Add src to path for importing telemetry package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry import schema


def get_database_path() -> Path:
    """
    Get the path to the telemetry database.

    Returns:
        Path: Database file path (D:\agent-metrics\db\telemetry.sqlite)
    """
    env_db_path = Path(os.getenv("TELEMETRY_DB_PATH", "")) if os.getenv("TELEMETRY_DB_PATH") else None
    if env_db_path:
        return env_db_path

    # Check for D: drive first
    d_drive_path = Path("D:\\agent-metrics\\db\\telemetry.sqlite")
    if d_drive_path.parent.parent.exists():
        return d_drive_path

    # Fallback to C: drive
    c_drive_path = Path("C:\\agent-metrics\\db\\telemetry.sqlite")
    if c_drive_path.parent.parent.exists():
        return c_drive_path

    # Use D: as default if neither exists yet
    return d_drive_path


def main() -> int:
    """
    Main entry point for database setup.

    Returns:
        int: Exit code (0 = success, 1 = failure)
    """
    parser = argparse.ArgumentParser(description="Telemetry database setup")
    parser.add_argument("--db-path", type=Path, help="Path to SQLite database")
    args = parser.parse_args()

    print("=" * 70)
    print("Telemetry Platform - Database Setup")
    print("=" * 70)
    print()

    # Step 1: Determine database path
    print("[1/4] Determining database location...")
    db_path = args.db_path or get_database_path()
    print(f"      Selected: {db_path}")
    print()

    # Step 2: Check prerequisites
    print("[2/4] Checking prerequisites...")
    if not db_path.parent.exists():
        print(f"      [FAIL] Directory does not exist: {db_path.parent}")
        print()
        print("      Please run scripts/setup_storage.py first (TEL-01)")
        return 1
    print(f"      [OK] Database directory exists: {db_path.parent}")
    print()

    # Step 3: Create schema
    print("[3/4] Creating database schema...")
    success, messages = schema.create_schema(str(db_path))

    for msg in messages:
        print(f"      {msg}")

    if not success:
        print()
        print("[FAIL] Could not create database schema")
        return 1
    print()

    # Step 4: Verify schema
    print("[4/4] Verifying schema...")
    success, messages = schema.verify_schema(str(db_path))

    for msg in messages:
        print(f"      {msg}")

    if not success:
        print()
        print("[FAIL] Schema verification failed")
        return 1
    print()

    # Export schema SQL
    print("[BONUS] Exporting schema.sql...")
    config_path = db_path.parent.parent / "config" / "schema.sql"
    success, message = schema.export_schema_sql(str(config_path))
    print(f"      {message}")
    print()

    # Success
    print("=" * 70)
    print(f"[SUCCESS] Telemetry database initialized at {db_path}")
    print(f"          Schema version: {schema.SCHEMA_VERSION}")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
