#!/usr/bin/env python
"""
Database Recovery Script

Recovers the telemetry database from NDJSON backup files when corruption is detected.

Usage:
    python scripts/recover_database.py [--check-only] [--force]

Options:
    --check-only    Only check integrity, don't recover
    --force         Force recovery even if database appears healthy
"""

import json
import sqlite3
import shutil
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Fix encoding on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")


def check_database_integrity(db_path: Path) -> tuple[bool, str]:
    """Check if database is healthy."""
    if not db_path.exists():
        return False, "Database file does not exist"

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check")
        result = cursor.fetchone()[0]
        conn.close()

        if result == "ok":
            return True, "Database integrity check passed"
        else:
            return False, f"Database integrity issue: {result}"

    except sqlite3.DatabaseError as e:
        return False, f"Database corrupted: {e}"
    except Exception as e:
        return False, f"Integrity check error: {e}"


def backup_corrupted_database(db_path: Path) -> Optional[Path]:
    """Backup the corrupted database before recovery."""
    if not db_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"telemetry.corrupted.{timestamp}.sqlite"

    shutil.move(str(db_path), str(backup_path))
    print(f"  Backed up corrupted database to: {backup_path.name}")

    return backup_path


def create_database_schema(db_path: Path) -> None:
    """Create a fresh database with the telemetry schema."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Corruption prevention settings
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA wal_autocheckpoint=1000")

    # Create agent_runs table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agent_runs (
        run_id TEXT PRIMARY KEY,
        schema_version INTEGER DEFAULT 2,
        agent_name TEXT NOT NULL,
        agent_owner TEXT,
        job_type TEXT,
        trigger_type TEXT,
        start_time TEXT NOT NULL,
        end_time TEXT,
        status TEXT CHECK(status IN ('running', 'success', 'failed', 'partial')),
        items_discovered INTEGER DEFAULT 0,
        items_succeeded INTEGER DEFAULT 0,
        items_failed INTEGER DEFAULT 0,
        duration_ms INTEGER,
        input_summary TEXT,
        output_summary TEXT,
        error_summary TEXT,
        metrics_json TEXT,
        insight_id TEXT,
        product TEXT,
        platform TEXT,
        git_repo TEXT,
        git_branch TEXT,
        git_run_tag TEXT,
        host TEXT,
        api_posted INTEGER DEFAULT 0,
        api_posted_at TEXT,
        api_retry_count INTEGER DEFAULT 0,
        custom_metadata TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_runs(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_start ON agent_runs(start_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_api_posted ON agent_runs(api_posted)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_runs_insight ON agent_runs(insight_id)")

    # Create run_events table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS run_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
        event_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        payload_json TEXT
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id)")

    # Create schema_migrations table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT DEFAULT (datetime('now')),
        description TEXT
    )
    """)
    cursor.execute(
        "INSERT INTO schema_migrations (version, description) VALUES (2, 'Schema v2: Added insight_id')"
    )

    conn.commit()
    conn.close()


def import_from_ndjson(db_path: Path, ndjson_dir: Path) -> tuple[int, int]:
    """Import runs from NDJSON files into the database."""
    ndjson_files = sorted(ndjson_dir.glob("*.ndjson"))
    if not ndjson_files:
        print(f"  No NDJSON files found in {ndjson_dir}")
        return 0, 0

    print(f"  Found {len(ndjson_files)} NDJSON files")

    # Collect all runs (latest record per run_id wins)
    runs = {}
    for ndjson_file in ndjson_files:
        with open(ndjson_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    run_id = record.get("run_id")
                    if run_id:
                        runs[run_id] = record
                except json.JSONDecodeError:
                    continue

    print(f"  Found {len(runs)} unique runs in NDJSON files")

    # Insert into database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    inserted = 0
    errors = 0

    for run_id, record in runs.items():
        try:
            cursor.execute(
                """
                INSERT OR REPLACE INTO agent_runs (
                    run_id, schema_version, agent_name, agent_owner, job_type,
                    trigger_type, start_time, end_time, status,
                    items_discovered, items_succeeded, items_failed,
                    duration_ms, input_summary, output_summary, error_summary,
                    metrics_json, insight_id, product, platform, git_repo, git_branch,
                    git_run_tag, host, api_posted, api_posted_at, api_retry_count, custom_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.get("run_id"),
                    record.get("schema_version", 2),
                    record.get("agent_name"),
                    record.get("agent_owner"),
                    record.get("job_type"),
                    record.get("trigger_type"),
                    record.get("start_time"),
                    record.get("end_time"),
                    record.get("status"),
                    record.get("items_discovered", 0),
                    record.get("items_succeeded", 0),
                    record.get("items_failed", 0),
                    record.get("duration_ms"),
                    record.get("input_summary"),
                    record.get("output_summary"),
                    record.get("error_summary"),
                    json.dumps(record.get("metrics")) if record.get("metrics") else None,
                    record.get("insight_id"),
                    record.get("product"),
                    record.get("platform"),
                    record.get("git_repo"),
                    record.get("git_branch"),
                    record.get("git_run_tag"),
                    record.get("host"),
                    record.get("api_posted", 0),
                    record.get("api_posted_at"),
                    record.get("api_retry_count", 0),
                    json.dumps(record.get("custom_metadata"))
                    if record.get("custom_metadata")
                    else None,
                ),
            )
            inserted += 1
        except Exception:
            errors += 1

    conn.commit()
    conn.close()

    return inserted, errors


def recover_database(
    db_path: Path,
    ndjson_dir: Path,
    force: bool = False,
) -> tuple[bool, str]:
    """
    Recover the database from NDJSON files.

    Args:
        db_path: Path to the database file
        ndjson_dir: Path to the NDJSON backup directory
        force: Force recovery even if database is healthy

    Returns:
        Tuple of (success: bool, message: str)
    """
    print("=" * 60)
    print("DATABASE RECOVERY")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"NDJSON dir: {ndjson_dir}")

    # Step 1: Check integrity
    print("\n1. Checking database integrity...")
    is_healthy, msg = check_database_integrity(db_path)
    print(f"   {msg}")

    if is_healthy and not force:
        return True, "Database is healthy, no recovery needed"

    if is_healthy and force:
        print("   Force flag set, proceeding with recovery anyway")

    # Step 2: Backup corrupted database
    print("\n2. Backing up existing database...")
    backup_corrupted_database(db_path)

    # Step 3: Create new database
    print("\n3. Creating new database with schema...")
    create_database_schema(db_path)
    print("   Schema created successfully")

    # Step 4: Import from NDJSON
    print("\n4. Importing data from NDJSON files...")
    inserted, errors = import_from_ndjson(db_path, ndjson_dir)
    print(f"   Imported {inserted} runs, {errors} errors")

    # Step 5: Verify
    print("\n5. Verifying recovered database...")
    is_healthy, msg = check_database_integrity(db_path)
    print(f"   {msg}")

    if not is_healthy:
        return False, f"Recovery verification failed: {msg}"

    # Get stats
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM agent_runs")
    total_runs = cursor.fetchone()[0]
    conn.close()

    print(f"\n   Total runs in recovered database: {total_runs}")

    print("\n" + "=" * 60)
    print("RECOVERY COMPLETE")
    print("=" * 60)

    return True, f"Recovery successful: {inserted} runs restored"


def main():
    """Main entry point."""
    # Parse args
    check_only = "--check-only" in sys.argv
    force = "--force" in sys.argv

    # Get paths from environment or defaults
    metrics_dir = Path(os.getenv("AGENT_METRICS_DIR", "D:/agent-metrics"))
    db_path = metrics_dir / "db" / "telemetry.sqlite"
    ndjson_dir = metrics_dir / "raw"

    if check_only:
        print("Checking database integrity...")
        is_healthy, msg = check_database_integrity(db_path)
        print(msg)
        sys.exit(0 if is_healthy else 1)

    success, msg = recover_database(db_path, ndjson_dir, force=force)
    print(f"\nResult: {msg}")
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
