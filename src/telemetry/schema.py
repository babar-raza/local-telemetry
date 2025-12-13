"""
Telemetry Platform - Database Schema

Defines SQLite schema for multi-agent telemetry storage.
Includes tables for agent runs, events, commits, and migrations.

SCHEMA VERSION 2 CHANGES:
- Added insight_id column for SEO Intelligence integration
- Enhanced metrics_json documentation for flexible metadata storage
- Added idx_runs_insight index for efficient insight-based queries

SCHEMA VERSION 3 CHANGES:
- Added product_family column for business context (Aspose product family: slides, words, cells, etc.)
- Added subdomain column for business context (site subdomain: products, docs, etc.)
"""

import sqlite3
from pathlib import Path
from typing import Tuple

# Schema version for migrations
# v2: Added insight_id column for SEO Intelligence integration
# v3: Added product_family and subdomain columns for business context tracking
SCHEMA_VERSION = 3

# Table definitions
TABLES = {
    "agent_runs": """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id TEXT PRIMARY KEY,
    schema_version INTEGER DEFAULT 3,
    agent_name TEXT NOT NULL,
    agent_owner TEXT,
    job_type TEXT,
    trigger_type TEXT CHECK(trigger_type IN ('cli', 'web', 'scheduler', 'mcp', 'manual')),
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
    product_family TEXT,
    subdomain TEXT,
    git_repo TEXT,
    git_branch TEXT,
    git_run_tag TEXT,
    host TEXT,
    api_posted INTEGER DEFAULT 0,
    api_posted_at TEXT,
    api_retry_count INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
)
""",
    "run_events": """
CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES agent_runs(run_id),
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    payload_json TEXT
)
""",
    "commits": """
CREATE TABLE IF NOT EXISTS commits (
    commit_hash TEXT PRIMARY KEY,
    run_id TEXT REFERENCES agent_runs(run_id),
    agent_name TEXT,
    repo TEXT,
    branch TEXT,
    commit_date TEXT,
    author TEXT,
    message TEXT,
    files_changed INTEGER,
    insertions INTEGER,
    deletions INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
)
""",
    "schema_migrations": """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now')),
    description TEXT
)
""",
}

# Index definitions
INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name)",
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_runs_start ON agent_runs(start_time)",
    "CREATE INDEX IF NOT EXISTS idx_runs_api_posted ON agent_runs(api_posted)",
    "CREATE INDEX IF NOT EXISTS idx_runs_insight ON agent_runs(insight_id)",  # New: For SEO Intelligence queries
    "CREATE INDEX IF NOT EXISTS idx_events_run ON run_events(run_id)",
    "CREATE INDEX IF NOT EXISTS idx_commits_run ON commits(run_id)",
]


def create_schema(db_path: str) -> Tuple[bool, list[str]]:
    """
    Create the telemetry database schema.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Tuple of (success: bool, messages: list[str])
    """
    messages = []

    try:
        # Ensure parent directory exists
        db_file = Path(db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Enable WAL mode for concurrent access
        cursor.execute("PRAGMA journal_mode=WAL")
        wal_mode = cursor.fetchone()[0]
        messages.append(f"[OK] Set journal mode: {wal_mode}")

        # Create tables
        for table_name, table_sql in TABLES.items():
            cursor.execute(table_sql)
            messages.append(f"[OK] Created table: {table_name}")

        # Create indexes
        for index_sql in INDEXES:
            cursor.execute(index_sql)
            # Extract index name from SQL for logging
            index_name = index_sql.split()[5]  # "CREATE INDEX IF NOT EXISTS <name>"
            messages.append(f"[OK] Created index: {index_name}")

        # Record initial schema version
        cursor.execute(
            """
            INSERT OR IGNORE INTO schema_migrations (version, description)
            VALUES (?, ?)
            """,
            (SCHEMA_VERSION, "Schema v3: Added product_family and subdomain columns"),
        )
        if cursor.rowcount > 0:
            messages.append(f"[OK] Recorded schema version: {SCHEMA_VERSION}")
        else:
            messages.append(
                f"[OK] Schema version {SCHEMA_VERSION} already recorded"
            )

        # Commit changes
        conn.commit()
        conn.close()

        return True, messages

    except sqlite3.Error as e:
        messages.append(f"[FAIL] Database error: {e}")
        return False, messages
    except Exception as e:
        messages.append(f"[FAIL] Unexpected error: {e}")
        return False, messages


def get_schema_version(db_path: str) -> int:
    """
    Get the current schema version from the database.

    Args:
        db_path: Path to SQLite database file

    Returns:
        int: Current schema version, or 0 if not found
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT MAX(version) FROM schema_migrations"
        )
        result = cursor.fetchone()
        conn.close()

        return result[0] if result and result[0] is not None else 0

    except sqlite3.Error:
        return 0


def verify_schema(db_path: str) -> Tuple[bool, list[str]]:
    """
    Verify that the database schema is correctly created.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Tuple of (success: bool, messages: list[str])
    """
    messages = []
    all_ok = True

    try:
        if not Path(db_path).exists():
            return False, ["[FAIL] Database file does not exist"]

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check tables exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        existing_tables = {row[0] for row in cursor.fetchall()}

        expected_tables = set(TABLES.keys())
        for table in expected_tables:
            if table in existing_tables:
                messages.append(f"[OK] Table exists: {table}")
            else:
                messages.append(f"[FAIL] Table missing: {table}")
                all_ok = False

        # Check indexes exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        existing_indexes = {row[0] for row in cursor.fetchall()}

        expected_indexes = {
            "idx_runs_agent",
            "idx_runs_status",
            "idx_runs_start",
            "idx_runs_api_posted",
            "idx_runs_insight",  # New index
            "idx_events_run",
            "idx_commits_run",
        }

        for index in expected_indexes:
            if index in existing_indexes:
                messages.append(f"[OK] Index exists: {index}")
            else:
                messages.append(f"[FAIL] Index missing: {index}")
                all_ok = False

        # Check WAL mode
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        if journal_mode.lower() == "wal":
            messages.append(f"[OK] Journal mode: {journal_mode}")
        else:
            messages.append(
                f"[FAIL] Journal mode is {journal_mode}, expected WAL"
            )
            all_ok = False

        # Check schema version
        version = get_schema_version(db_path)
        if version == SCHEMA_VERSION:
            messages.append(f"[OK] Schema version: {version}")
        else:
            messages.append(
                f"[FAIL] Schema version is {version}, expected {SCHEMA_VERSION}"
            )
            all_ok = False

        conn.close()

        return all_ok, messages

    except sqlite3.Error as e:
        messages.append(f"[FAIL] Database error: {e}")
        return False, messages
    except Exception as e:
        messages.append(f"[FAIL] Unexpected error: {e}")
        return False, messages


def export_schema_sql(output_path: str) -> Tuple[bool, str]:
    """
    Export the schema as a SQL file.

    Args:
        output_path: Path where SQL file should be written

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        sql_content = f"""-- Telemetry Platform Database Schema
-- Version: {SCHEMA_VERSION}
-- Generated: Auto-generated from schema.py

-- Enable WAL mode for concurrent access
PRAGMA journal_mode=WAL;

-- Tables
"""

        for table_name, table_sql in TABLES.items():
            sql_content += f"\n-- Table: {table_name}\n"
            sql_content += table_sql.strip() + ";\n"

        sql_content += "\n-- Indexes\n"
        for index_sql in INDEXES:
            sql_content += index_sql + ";\n"

        sql_content += f"""
-- Record schema version
INSERT OR IGNORE INTO schema_migrations (version, description)
VALUES ({SCHEMA_VERSION}, 'Schema v3: Added product_family and subdomain columns');
"""

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(sql_content)

        return True, f"[OK] Exported schema to {output_path}"

    except (OSError, IOError) as e:
        return False, f"[FAIL] Error exporting schema: {e}"
