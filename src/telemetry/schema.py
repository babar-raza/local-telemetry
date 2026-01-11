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

SCHEMA VERSION 4 CHANGES:
- Added git_commit_hash column for tracking commit SHA
- Added git_commit_source column for tracking how commit was created (manual, llm, ci)
- Added git_commit_author column for commit author
- Added git_commit_timestamp column for when commit was made
"""

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Tuple

# Schema version for migrations
# v2: Added insight_id column for SEO Intelligence integration
# v3: Added product_family and subdomain columns for business context tracking
# v4: Added git commit tracking fields (hash, source, author, timestamp)
# v5: Added website, website_section, item_name for API spec compliance
# v6: Added event_id with UNIQUE constraint for idempotency
SCHEMA_VERSION = 6

# Table definitions
TABLES = {
    "agent_runs": """
CREATE TABLE IF NOT EXISTS agent_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    schema_version INTEGER DEFAULT 6,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    start_time TEXT NOT NULL,
    end_time TEXT,
    agent_name TEXT NOT NULL,
    agent_owner TEXT,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    product TEXT,
    product_family TEXT,
    platform TEXT,
    subdomain TEXT,
    website TEXT,
    website_section TEXT,
    item_name TEXT,
    items_discovered INTEGER DEFAULT 0,
    items_succeeded INTEGER DEFAULT 0,
    items_failed INTEGER DEFAULT 0,
    items_skipped INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    input_summary TEXT,
    output_summary TEXT,
    source_ref TEXT,
    target_ref TEXT,
    error_summary TEXT,
    error_details TEXT,
    git_repo TEXT,
    git_branch TEXT,
    git_commit_hash TEXT,
    git_run_tag TEXT,
    git_commit_source TEXT,
    git_commit_author TEXT,
    git_commit_timestamp TEXT,
    host TEXT,
    environment TEXT,
    trigger_type TEXT,
    metrics_json TEXT,
    context_json TEXT,
    api_posted INTEGER DEFAULT 0,
    api_posted_at TEXT,
    api_retry_count INTEGER DEFAULT 0,
    insight_id TEXT,
    parent_run_id TEXT,
    CHECK (items_discovered >= 0),
    CHECK (items_succeeded >= 0),
    CHECK (items_failed >= 0),
    CHECK (items_skipped >= 0),
    CHECK (duration_ms >= 0),
    CHECK (api_retry_count >= 0),
    CHECK (status IN ('running', 'success', 'failure', 'partial', 'timeout', 'cancelled'))
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
    "CREATE INDEX IF NOT EXISTS idx_runs_event_id ON agent_runs(event_id)",
    "CREATE INDEX IF NOT EXISTS idx_runs_agent ON agent_runs(agent_name)",
    "CREATE INDEX IF NOT EXISTS idx_runs_status ON agent_runs(status)",
    "CREATE INDEX IF NOT EXISTS idx_runs_start ON agent_runs(start_time)",
    "CREATE INDEX IF NOT EXISTS idx_runs_created_desc ON agent_runs(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runs_agent_status_created ON agent_runs(agent_name, status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runs_agent_created ON agent_runs(agent_name, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_runs_job_type ON agent_runs(job_type)",
    "CREATE INDEX IF NOT EXISTS idx_runs_parent_run ON agent_runs(parent_run_id)",
    "CREATE INDEX IF NOT EXISTS idx_runs_api_posted ON agent_runs(api_posted)",
    "CREATE INDEX IF NOT EXISTS idx_runs_insight ON agent_runs(insight_id)",
    "CREATE INDEX IF NOT EXISTS idx_runs_commit ON agent_runs(git_commit_hash)",
    "CREATE INDEX IF NOT EXISTS idx_runs_website ON agent_runs(website)",
    "CREATE INDEX IF NOT EXISTS idx_runs_website_section ON agent_runs(website, website_section)",
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

        # Enable DELETE mode for Docker volume mount compatibility
        cursor.execute("PRAGMA journal_mode=DELETE")
        journal_mode = cursor.fetchone()[0]
        messages.append(f"[OK] Set journal mode: {journal_mode}")

        # Enforce FULL synchronous mode for durability
        cursor.execute("PRAGMA synchronous=FULL")
        sync_mode = cursor.fetchone()[0]
        messages.append(f"[OK] Set synchronous mode: {sync_mode}")

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
            (SCHEMA_VERSION, "Schema v6: Canonical telemetry schema"),
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
            "idx_runs_event_id",  # v6: Idempotency lookups
            "idx_runs_agent",
            "idx_runs_status",
            "idx_runs_start",
            "idx_runs_created_desc",
            "idx_runs_agent_status_created",
            "idx_runs_agent_created",
            "idx_runs_job_type",
            "idx_runs_parent_run",
            "idx_runs_api_posted",
            "idx_runs_insight",
            "idx_runs_commit",  # For commit-based lookups
            "idx_runs_website",  # For website-based queries
            "idx_runs_website_section",  # For section queries
            "idx_events_run",
            "idx_commits_run",
        }

        for index in expected_indexes:
            if index in existing_indexes:
                messages.append(f"[OK] Index exists: {index}")
            else:
                messages.append(f"[FAIL] Index missing: {index}")
                all_ok = False

        # Check DELETE mode
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        if journal_mode.lower() == "delete":
            messages.append(f"[OK] Journal mode: {journal_mode}")
        else:
            messages.append(
                f"[FAIL] Journal mode is {journal_mode}, expected DELETE"
            )
            all_ok = False

        # Check synchronous mode (2 = FULL)
        cursor.execute("PRAGMA synchronous")
        sync_mode = cursor.fetchone()[0]
        if sync_mode == 2:
            messages.append(f"[OK] Synchronous mode: {sync_mode}")
        else:
            messages.append(
                f"[FAIL] Synchronous mode is {sync_mode}, expected 2 (FULL)"
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


def ensure_schema(db_path: str, backup_on_drift: bool = True) -> Tuple[bool, list[str]]:
    """
    Ensure schema exists and self-heal drift when possible.

    Args:
        db_path: Path to SQLite database file
        backup_on_drift: If True, copy the database before applying drift fixes

    Returns:
        Tuple of (success: bool, messages: list[str])
    """
    messages: list[str] = []
    db_file = Path(db_path)

    if not db_file.exists():
        return create_schema(db_path)

    drift_detected = False

    # Columns that can be added via ALTER TABLE
    alter_columns = {
        "event_id": "event_id TEXT",
        "run_id": "run_id TEXT",
        "schema_version": f"schema_version INTEGER DEFAULT {SCHEMA_VERSION}",
        "created_at": "created_at TEXT DEFAULT (datetime('now'))",
        "updated_at": "updated_at TEXT DEFAULT (datetime('now'))",
        "start_time": "start_time TEXT",
        "end_time": "end_time TEXT",
        "agent_name": "agent_name TEXT",
        "agent_owner": "agent_owner TEXT",
        "job_type": "job_type TEXT",
        "status": "status TEXT",
        "product": "product TEXT",
        "product_family": "product_family TEXT",
        "platform": "platform TEXT",
        "subdomain": "subdomain TEXT",
        "website": "website TEXT",
        "website_section": "website_section TEXT",
        "item_name": "item_name TEXT",
        "items_discovered": "items_discovered INTEGER DEFAULT 0",
        "items_succeeded": "items_succeeded INTEGER DEFAULT 0",
        "items_failed": "items_failed INTEGER DEFAULT 0",
        "items_skipped": "items_skipped INTEGER DEFAULT 0",
        "duration_ms": "duration_ms INTEGER DEFAULT 0",
        "input_summary": "input_summary TEXT",
        "output_summary": "output_summary TEXT",
        "source_ref": "source_ref TEXT",
        "target_ref": "target_ref TEXT",
        "error_summary": "error_summary TEXT",
        "error_details": "error_details TEXT",
        "git_repo": "git_repo TEXT",
        "git_branch": "git_branch TEXT",
        "git_commit_hash": "git_commit_hash TEXT",
        "git_run_tag": "git_run_tag TEXT",
        "git_commit_source": "git_commit_source TEXT",
        "git_commit_author": "git_commit_author TEXT",
        "git_commit_timestamp": "git_commit_timestamp TEXT",
        "host": "host TEXT",
        "environment": "environment TEXT",
        "trigger_type": "trigger_type TEXT",
        "metrics_json": "metrics_json TEXT",
        "context_json": "context_json TEXT",
        "api_posted": "api_posted INTEGER DEFAULT 0",
        "api_posted_at": "api_posted_at TEXT",
        "api_retry_count": "api_retry_count INTEGER DEFAULT 0",
        "insight_id": "insight_id TEXT",
        "parent_run_id": "parent_run_id TEXT",
    }

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agent_runs'"
        )
        if not cursor.fetchone():
            messages.append("[WARN] agent_runs table missing; recreating schema")
            conn.close()
            return create_schema(db_path)

        cursor.execute("PRAGMA table_info(agent_runs)")
        existing_columns = {row[1] for row in cursor.fetchall()}

        missing_columns = [col for col in alter_columns if col not in existing_columns]
        if missing_columns:
            drift_detected = True

        if drift_detected and backup_on_drift:
            backup_path = db_file.with_suffix(
                f".backup_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.sqlite"
            )
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            backup_path.write_bytes(db_file.read_bytes())
            messages.append(f"[OK] Backup created: {backup_path}")

        for column in missing_columns:
            definition = alter_columns[column]
            cursor.execute(f"ALTER TABLE agent_runs ADD COLUMN {definition}")
            messages.append(f"[OK] Added column: {column}")

        # Backfill event_id and ensure unique index
        if "event_id" in missing_columns:
            cursor.execute("SELECT rowid FROM agent_runs WHERE event_id IS NULL")
            rows = cursor.fetchall()
            for row in rows:
                cursor.execute(
                    "UPDATE agent_runs SET event_id = ? WHERE rowid = ?",
                    (str(uuid.uuid4()), row[0]),
                )
            messages.append("[OK] Backfilled event_id values")

        # Ensure core tables exist
        for table_name, table_sql in TABLES.items():
            cursor.execute(table_sql)

        # Ensure indexes exist
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        )
        existing_indexes = {row[0] for row in cursor.fetchall()}
        for index_sql in INDEXES:
            index_name = index_sql.split()[5]
            if index_name not in existing_indexes:
                cursor.execute(index_sql)
                messages.append(f"[OK] Created index: {index_name}")

        # Ensure schema_migrations table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        if not cursor.fetchone():
            cursor.execute(TABLES["schema_migrations"])
            messages.append("[OK] Created table: schema_migrations")

        # Record schema version if needed
        cursor.execute("SELECT MAX(version) FROM schema_migrations")
        result = cursor.fetchone()
        current_version = result[0] if result and result[0] is not None else 0
        if current_version < SCHEMA_VERSION:
            cursor.execute(
                "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                (SCHEMA_VERSION, "Schema v6: Canonical telemetry schema"),
            )
            messages.append(f"[OK] Recorded schema version: {SCHEMA_VERSION}")

        conn.commit()
        conn.close()
        return True, messages

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

-- Enable DELETE mode for Docker volume compatibility
PRAGMA journal_mode=DELETE;
PRAGMA synchronous=FULL;

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
VALUES ({SCHEMA_VERSION}, 'Schema v6: Canonical telemetry schema');
"""

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(sql_content)

        return True, f"[OK] Exported schema to {output_path}"

    except (OSError, IOError) as e:
        return False, f"[FAIL] Error exporting schema: {e}"
