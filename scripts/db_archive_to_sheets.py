#!/usr/bin/env python3
"""
Database Archival to Google Sheets

Archives old telemetry data to Google Sheets as aggregated summaries,
then deletes the archived records to reduce database size.

Features:
    - Configurable retention period (--days, default: 7)
    - Configurable aggregation grouping (--group-by)
    - Dry-run mode for safe preview
    - Batch posting with retry logic
    - Only deletes after successful push
    - VACUUM to reclaim disk space

Usage:
    # Preview with default settings
    python scripts/db_archive_to_sheets.py --dry-run

    # Archive data older than 14 days, grouped by agent
    python scripts/db_archive_to_sheets.py --days 14 --group-by date,agent

    # Group by subdomain
    python scripts/db_archive_to_sheets.py --group-by date,subdomain

    # Group by product
    python scripts/db_archive_to_sheets.py --group-by date,product
"""

import os
import sys
import json
import sqlite3
import argparse
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

try:
    from telemetry.status import normalize_status
except ImportError:
    def normalize_status(s):
        return s

# =============================================================================
# Configuration
# =============================================================================

# Database path resolution (same as other scripts)
TELEMETRY_DB_PATH = os.getenv(
    "TELEMETRY_DB_PATH",
    os.getenv("AGENT_METRICS_DIR", "D:/agent-metrics") + "/db/telemetry.sqlite"
)

# Google Sheets API
SHEETS_API_URL = os.getenv("GOOGLE_SHEETS_API_URL") or os.getenv("SHEETS_API_URL")
SHEETS_API_TOKEN = (
    os.getenv("GOOGLE_SHEETS_API_TOKEN")
    or os.getenv("SHEETS_API_TOKEN")
    or os.getenv("METRICS_API_TOKEN")
)

# Archive defaults (can be overridden by CLI)
DEFAULT_DAYS = int(os.getenv("ARCHIVE_DAYS", "7"))
DEFAULT_GROUP_BY = os.getenv("ARCHIVE_GROUP_BY", "date,agent,job_type")
DEFAULT_BATCH_SIZE = int(os.getenv("ARCHIVE_BATCH_SIZE", "100"))
DEFAULT_DRY_RUN = os.getenv("ARCHIVE_DRY_RUN", "false").lower() in ("true", "1", "yes")

# Column mapping for group-by options
# Note: Some older schema versions use 'subdomain' column, newer use 'website_section'
GROUP_COLUMNS = {
    'date': 'date(created_at)',
    'agent': 'agent_name',
    'job_type': 'job_type',
    'subdomain': 'COALESCE(website_section, subdomain)',  # Handle both column names
    'product': 'product',
    'website': 'website',
}

VALID_GROUP_OPTIONS = list(GROUP_COLUMNS.keys())


def get_available_columns(cursor) -> set:
    """Get available columns in agent_runs table."""
    cursor.execute("PRAGMA table_info(agent_runs)")
    columns = cursor.fetchall()
    return {col[1] for col in columns}

# Valid terminal statuses for archival
ARCHIVABLE_STATUSES = ('success', 'failure', 'partial', 'timeout', 'cancelled')


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class AggregatedSummary:
    """Aggregated telemetry summary for archival."""
    # Grouping keys (dynamic based on --group-by)
    group_keys: Dict[str, str]

    # Counts
    total_count: int
    success_count: int
    failure_count: int
    other_count: int  # partial + timeout + cancelled

    # Metrics
    avg_duration_ms: float
    total_discovered: int
    total_succeeded: int
    total_failed: int
    total_skipped: int

    # Event IDs for deletion tracking
    event_ids: List[str]

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.success_count / self.total_count) * 100


# =============================================================================
# SQL Query Builder
# =============================================================================

def build_aggregation_query(group_by: List[str], days: int, available_columns: set = None) -> str:
    """
    Build dynamic SQL aggregation query based on grouping options.

    Args:
        group_by: List of grouping dimensions (e.g., ['date', 'agent', 'job_type'])
        days: Archive records older than this many days
        available_columns: Set of available column names (for schema compatibility)

    Returns:
        SQL query string
    """
    if available_columns is None:
        available_columns = set()

    # Build SELECT columns for grouping
    select_cols = []
    for g in group_by:
        col = GROUP_COLUMNS[g]
        select_cols.append(f"{col} AS {g}")

    # Build GROUP BY columns
    group_cols = [GROUP_COLUMNS[g] for g in group_by]

    # Status placeholders
    status_placeholders = ",".join([f"'{s}'" for s in ARCHIVABLE_STATUSES])

    # Handle optional items_skipped column (not in older schema versions)
    items_skipped_sql = "SUM(COALESCE(items_skipped, 0))" if 'items_skipped' in available_columns else "0"

    # Handle event_id column (might be run_id in older schemas)
    event_id_col = 'event_id' if 'event_id' in available_columns else 'run_id'

    query = f"""
    SELECT
        {', '.join(select_cols)},
        COUNT(*) AS total_count,
        SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
        SUM(CASE WHEN status = 'failure' THEN 1 ELSE 0 END) AS failure_count,
        SUM(CASE WHEN status IN ('partial', 'timeout', 'cancelled') THEN 1 ELSE 0 END) AS other_count,
        AVG(COALESCE(duration_ms, 0)) AS avg_duration_ms,
        SUM(COALESCE(items_discovered, 0)) AS total_discovered,
        SUM(COALESCE(items_succeeded, 0)) AS total_succeeded,
        SUM(COALESCE(items_failed, 0)) AS total_failed,
        {items_skipped_sql} AS total_skipped,
        GROUP_CONCAT({event_id_col}) AS event_ids
    FROM agent_runs
    WHERE created_at < datetime('now', '-{days} days')
      AND status IN ({status_placeholders})
    GROUP BY {', '.join(group_cols)}
    ORDER BY {group_cols[0]} ASC
    """

    return query


def count_archivable_records(cursor, days: int) -> int:
    """Count total records that would be archived."""
    status_placeholders = ",".join([f"'{s}'" for s in ARCHIVABLE_STATUSES])
    cursor.execute(f"""
        SELECT COUNT(*) FROM agent_runs
        WHERE created_at < datetime('now', '-{days} days')
          AND status IN ({status_placeholders})
    """)
    return cursor.fetchone()[0]


# =============================================================================
# Google Sheets API
# =============================================================================

def summary_to_sheets_payload(summary: AggregatedSummary, group_by: List[str]) -> Dict:
    """
    Convert aggregated summary to Google Sheets API payload format.

    Args:
        summary: The aggregated summary
        group_by: List of grouping dimensions used

    Returns:
        Dictionary matching Google Sheets API schema
    """
    # Build item_name from group keys
    item_name_parts = [f"{k}={v}" for k, v in summary.group_keys.items() if v]
    item_name = "archive_" + "_".join(item_name_parts) if item_name_parts else "archive_summary"

    # Extended metrics as JSON
    extended_metrics = {
        'archived_at': datetime.now(timezone.utc).isoformat(),
        'group_by': ','.join(group_by),
        'success_rate_pct': round(summary.success_rate, 2),
        'avg_duration_ms': round(summary.avg_duration_ms, 2),
        'failure_count': summary.failure_count,
        'other_count': summary.other_count,
        'total_discovered': summary.total_discovered,
        'total_succeeded': summary.total_succeeded,
        'total_failed': summary.total_failed,
        'total_skipped': summary.total_skipped,
        'record_count': summary.total_count,
    }

    # Add group keys to extended metrics
    for k, v in summary.group_keys.items():
        extended_metrics[f'group_{k}'] = v

    payload = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'agent_name': summary.group_keys.get('agent', 'archived'),
        'job_type': 'aggregated_daily_archive',
        'product': summary.group_keys.get('product', 'archive'),
        'platform': 'daily_summary',
        'website': summary.group_keys.get('website', 'NA'),
        'website_section': summary.group_keys.get('subdomain', 'NA'),
        'item_name': item_name,
        'items_discovered': summary.total_count,  # Total runs as "discovered"
        'items_succeeded': summary.success_count,
        'items_failed': summary.failure_count,
        'items_skipped': summary.other_count,
        'duration_ms': int(summary.avg_duration_ms * summary.total_count),
        'error_summary': json.dumps(extended_metrics),
        'run_count': summary.total_count,
    }

    return payload


def post_to_sheets_api(
    summaries: List[AggregatedSummary],
    group_by: List[str],
    api_url: str,
    api_token: str,
    batch_size: int = 100,
    verbose: bool = False
) -> Tuple[List[AggregatedSummary], List[AggregatedSummary], List[str]]:
    """
    Post aggregated summaries to Google Sheets API.

    Args:
        summaries: List of summaries to post
        group_by: Grouping dimensions used
        api_url: Google Sheets API URL
        api_token: API authentication token
        batch_size: Number of summaries per API call
        verbose: Enable verbose logging

    Returns:
        Tuple of (successful_summaries, failed_summaries, error_messages)
    """
    successful = []
    failed = []
    errors = []

    for i in range(0, len(summaries), batch_size):
        batch = summaries[i:i + batch_size]
        batch_num = i // batch_size + 1

        # Convert to payloads
        payloads = [summary_to_sheets_payload(s, group_by) for s in batch]

        # Retry logic
        max_retries = 3
        success = False

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{api_url}?token={api_token}",
                    json={'events': payloads},
                    timeout=30
                )
                response.raise_for_status()

                result = response.json()
                if result.get('ok'):
                    successful.extend(batch)
                    if verbose:
                        print(f"  Batch {batch_num}: Posted {len(batch)} summaries")
                    success = True
                    break
                else:
                    error_msg = result.get('error', 'Unknown error')
                    errors.append(f"Batch {batch_num}: {error_msg}")
                    failed.extend(batch)
                    break

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    if verbose:
                        print(f"  Retry {attempt + 1}/{max_retries} after {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    error_msg = f"Batch {batch_num} failed after {max_retries} attempts: {e}"
                    errors.append(error_msg)
                    failed.extend(batch)

        if not success and not errors:
            failed.extend(batch)

    return successful, failed, errors


# =============================================================================
# Database Operations
# =============================================================================

def get_db_stats(cursor, days: int) -> Dict:
    """Get database statistics."""
    cursor.execute("SELECT COUNT(*) FROM agent_runs")
    total_rows = cursor.fetchone()[0]

    cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM agent_runs")
    min_date, max_date = cursor.fetchone()

    archivable = count_archivable_records(cursor, days)

    return {
        "total_rows": total_rows,
        "oldest_record": min_date,
        "newest_record": max_date,
        "archivable_records": archivable,
    }


def query_aggregated_summaries(
    cursor,
    group_by: List[str],
    days: int,
    verbose: bool = False,
    available_columns: set = None
) -> List[AggregatedSummary]:
    """
    Query and aggregate records for archival.

    Args:
        cursor: Database cursor
        group_by: Grouping dimensions
        days: Archive records older than this many days
        verbose: Enable verbose logging
        available_columns: Set of available column names

    Returns:
        List of AggregatedSummary objects
    """
    if available_columns is None:
        available_columns = get_available_columns(cursor)

    query = build_aggregation_query(group_by, days, available_columns)

    if verbose:
        print(f"  SQL Query:\n{query}")

    cursor.execute(query)
    rows = cursor.fetchall()

    summaries = []
    for row in rows:
        # Extract group keys from row (first N columns are group dimensions)
        group_keys = {}
        for i, g in enumerate(group_by):
            group_keys[g] = row[i]

        # Parse event_ids
        event_ids_str = row[-1]  # Last column is GROUP_CONCAT(event_id)
        event_ids = event_ids_str.split(',') if event_ids_str else []

        summary = AggregatedSummary(
            group_keys=group_keys,
            total_count=row[len(group_by)],
            success_count=row[len(group_by) + 1],
            failure_count=row[len(group_by) + 2],
            other_count=row[len(group_by) + 3],
            avg_duration_ms=row[len(group_by) + 4] or 0,
            total_discovered=row[len(group_by) + 5] or 0,
            total_succeeded=row[len(group_by) + 6] or 0,
            total_failed=row[len(group_by) + 7] or 0,
            total_skipped=row[len(group_by) + 8] or 0,
            event_ids=event_ids,
        )
        summaries.append(summary)

    return summaries


def delete_archived_records(conn, event_ids: List[str], verbose: bool = False, id_column: str = 'event_id') -> int:
    """
    Delete records by event_id or run_id.

    Args:
        conn: Database connection
        event_ids: List of event/run IDs to delete
        verbose: Enable verbose logging
        id_column: Column name to use for deletion ('event_id' or 'run_id')

    Returns:
        Number of records deleted
    """
    if not event_ids:
        return 0

    cursor = conn.cursor()

    # Delete in batches to avoid huge IN clauses
    batch_size = 500
    total_deleted = 0

    for i in range(0, len(event_ids), batch_size):
        batch = event_ids[i:i + batch_size]
        placeholders = ','.join(['?'] * len(batch))

        cursor.execute(f"""
            DELETE FROM agent_runs
            WHERE {id_column} IN ({placeholders})
        """, batch)

        total_deleted += cursor.rowcount

        if verbose and (i + batch_size) % 5000 == 0:
            print(f"    Deleted {total_deleted} records so far...")

    conn.commit()
    return total_deleted


# =============================================================================
# Main Archive Function
# =============================================================================

def archive_to_sheets(
    db_path: str,
    days: int = 7,
    group_by: List[str] = None,
    batch_size: int = 100,
    dry_run: bool = False,
    skip_vacuum: bool = False,
    verbose: bool = False
) -> Dict:
    """
    Archive old records to Google Sheets and delete them.

    Args:
        db_path: Path to SQLite database
        days: Archive records older than this many days
        group_by: Grouping dimensions (default: ['date', 'agent', 'job_type'])
        batch_size: Number of summaries per API call
        dry_run: If True, preview without making changes
        skip_vacuum: If True, skip VACUUM after deletion
        verbose: Enable verbose logging

    Returns:
        Dictionary with results
    """
    if group_by is None:
        group_by = ['date', 'agent', 'job_type']

    # Validate group_by options
    for g in group_by:
        if g not in VALID_GROUP_OPTIONS:
            print(f"ERROR: Invalid group-by option '{g}'. Valid options: {VALID_GROUP_OPTIONS}")
            return {"error": f"Invalid group-by option: {g}"}

    db = Path(db_path)
    if not db.exists():
        print(f"ERROR: Database not found: {db_path}")
        return {"error": "Database not found"}

    # Check API configuration (unless dry-run)
    if not dry_run:
        if not HAS_REQUESTS:
            print("ERROR: requests module required. Install with: pip install requests")
            return {"error": "requests module not installed"}

        if not SHEETS_API_URL:
            print("ERROR: GOOGLE_SHEETS_API_URL not set")
            return {"error": "API URL not configured"}

        if not SHEETS_API_TOKEN:
            print("ERROR: GOOGLE_SHEETS_API_TOKEN not set")
            return {"error": "API token not configured"}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Detect available columns for schema compatibility
        available_columns = get_available_columns(cursor)
        id_column = 'event_id' if 'event_id' in available_columns else 'run_id'

        # Get initial stats
        db_size_before = db.stat().st_size
        stats = get_db_stats(cursor, days)

        print("=" * 70)
        print("DATABASE ARCHIVAL TO GOOGLE SHEETS")
        print("=" * 70)
        print(f"Database: {db_path}")
        print(f"Archive threshold: {days} days")
        print(f"Group by: {', '.join(group_by)}")
        print(f"Dry run: {dry_run}")
        print()

        print("Current database stats:")
        print(f"  Total rows: {stats['total_rows']:,}")
        print(f"  Oldest record: {stats['oldest_record']}")
        print(f"  Newest record: {stats['newest_record']}")
        print(f"  Records to archive: {stats['archivable_records']:,}")
        print(f"  Database size: {db_size_before / (1024 * 1024):.1f} MB")
        print()

        if stats['archivable_records'] == 0:
            print("No records to archive.")
            return {"archived": 0, "deleted": 0, "summaries": 0}

        # Query aggregated summaries
        print(f"Step 1: Aggregating records by ({', '.join(group_by)})...")
        summaries = query_aggregated_summaries(cursor, group_by, days, verbose, available_columns)

        total_event_ids = sum(len(s.event_ids) for s in summaries)
        print(f"  Created {len(summaries):,} aggregated summaries")
        print(f"  Covering {total_event_ids:,} individual records")
        print()

        # Preview some summaries
        if verbose and summaries:
            print("  Sample summaries:")
            for s in summaries[:3]:
                keys = ", ".join(f"{k}={v}" for k, v in s.group_keys.items())
                print(f"    [{keys}]: {s.total_count} runs, {s.success_rate:.1f}% success")
            if len(summaries) > 3:
                print(f"    ... and {len(summaries) - 3} more")
            print()

        if dry_run:
            print("[DRY RUN] Would post to Google Sheets and delete records")
            print(f"[DRY RUN] Summaries to post: {len(summaries):,}")
            print(f"[DRY RUN] Records to delete: {total_event_ids:,}")
            return {
                "dry_run": True,
                "summaries": len(summaries),
                "would_archive": total_event_ids,
            }

        # Post to Google Sheets
        print(f"Step 2: Posting to Google Sheets API...")
        successful, failed, errors = post_to_sheets_api(
            summaries, group_by, SHEETS_API_URL, SHEETS_API_TOKEN,
            batch_size, verbose
        )

        print(f"  Successful: {len(successful):,} summaries")
        print(f"  Failed: {len(failed):,} summaries")

        if errors:
            print(f"\nErrors:")
            for error in errors[:5]:
                print(f"  - {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more errors")
        print()

        if not successful:
            print("ERROR: No summaries were successfully posted. Aborting deletion.")
            return {
                "error": "API posting failed",
                "summaries_attempted": len(summaries),
                "errors": errors,
            }

        # Collect event_ids from successful summaries only
        event_ids_to_delete = []
        for s in successful:
            event_ids_to_delete.extend(s.event_ids)

        # Delete archived records
        print(f"Step 3: Deleting {len(event_ids_to_delete):,} archived records...")
        deleted = delete_archived_records(conn, event_ids_to_delete, verbose, id_column)
        print(f"  Deleted {deleted:,} records")
        print()

        # VACUUM
        if not skip_vacuum:
            print("Step 4: Running VACUUM to reclaim disk space...")
            vacuum_start = datetime.now()
            cursor.execute("VACUUM")
            conn.commit()
            vacuum_time = (datetime.now() - vacuum_start).total_seconds()

            db_size_after = db.stat().st_size
            freed_bytes = db_size_before - db_size_after
            freed_mb = freed_bytes / (1024 * 1024)

            print(f"  VACUUM completed in {vacuum_time:.1f} seconds")
            print(f"  Freed {freed_mb:.1f} MB disk space")
            print(f"  New database size: {db_size_after / (1024 * 1024):.1f} MB")
        else:
            print("Step 4: Skipping VACUUM (--skip-vacuum)")
            freed_mb = 0

        print()
        print("=" * 70)
        print("SUMMARY")
        print("=" * 70)
        print(f"  Summaries posted: {len(successful):,}")
        print(f"  Records archived: {len(event_ids_to_delete):,}")
        print(f"  Records deleted: {deleted:,}")
        if not skip_vacuum:
            print(f"  Disk space freed: {freed_mb:.1f} MB")

        if failed:
            print(f"\n  WARNING: {len(failed)} summaries failed to post")
            print(f"  Re-run the script to retry failed records")

        return {
            "summaries_posted": len(successful),
            "summaries_failed": len(failed),
            "records_archived": len(event_ids_to_delete),
            "records_deleted": deleted,
            "freed_mb": freed_mb if not skip_vacuum else 0,
        }

    except sqlite3.Error as e:
        print(f"ERROR: SQLite error: {e}")
        return {"error": str(e)}
    finally:
        conn.close()


# =============================================================================
# CLI
# =============================================================================

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Archive old telemetry data to Google Sheets and delete from database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Preview with default settings (7 days, group by date+agent+job_type)
    python %(prog)s --dry-run

    # Archive data older than 14 days
    python %(prog)s --days 14

    # Group by subdomain instead of agent
    python %(prog)s --group-by date,subdomain

    # Group by product
    python %(prog)s --group-by date,product

    # Full granularity
    python %(prog)s --group-by date,agent,job_type,subdomain,product

Valid group-by options: date, agent, job_type, subdomain, product, website

Environment variables:
    GOOGLE_SHEETS_API_URL     API endpoint (required unless --dry-run)
    GOOGLE_SHEETS_API_TOKEN   API token (required unless --dry-run)
    TELEMETRY_DB_PATH         Database path (optional)
    ARCHIVE_DAYS              Default days threshold
    ARCHIVE_GROUP_BY          Default grouping
"""
    )

    parser.add_argument(
        "db_path",
        nargs="?",
        default=TELEMETRY_DB_PATH,
        help=f"Path to SQLite database (default: {TELEMETRY_DB_PATH})"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Archive records older than N days (default: {DEFAULT_DAYS})"
    )
    parser.add_argument(
        "--group-by",
        type=str,
        default=DEFAULT_GROUP_BY,
        help=f"Comma-separated grouping dimensions (default: {DEFAULT_GROUP_BY})"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Summaries per API call (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=DEFAULT_DRY_RUN,
        help="Preview without making changes"
    )
    parser.add_argument(
        "--skip-vacuum",
        action="store_true",
        help="Skip VACUUM after deletion (faster, but no immediate space reclaim)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output"
    )

    args = parser.parse_args()

    # Validate days
    if args.days < 1:
        print("ERROR: Days must be at least 1")
        sys.exit(1)

    # Parse group-by
    group_by = [g.strip() for g in args.group_by.split(',') if g.strip()]
    if not group_by:
        print("ERROR: At least one group-by dimension required")
        sys.exit(1)

    result = archive_to_sheets(
        db_path=args.db_path,
        days=args.days,
        group_by=group_by,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        skip_vacuum=args.skip_vacuum,
        verbose=args.verbose,
    )

    if "error" in result:
        sys.exit(2)
    elif result.get("summaries_failed", 0) > 0:
        sys.exit(1)  # Partial success
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
