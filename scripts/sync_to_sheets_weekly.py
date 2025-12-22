#!/usr/bin/env python3
"""
Weekly Google Sheets Sync Script

Aggregates telemetry data from last 7 days and posts to Google Sheets API.
Designed to run weekly via Windows Task Scheduler or cron.

References:
  - plans/weekly-sheets-integration-plan.md
  - plans/agentic-metrics-logging-integration-guide.md
"""

import os
import sys
import json
import sqlite3
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("[ERROR] requests module required. Install with: pip install requests")
    sys.exit(1)

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

# Configuration
TELEMETRY_DB_PATH = os.getenv(
    "TELEMETRY_DB_PATH",
    "D:/agent-metrics/db/telemetry.sqlite"
)
SHEETS_API_URL = os.getenv("SHEETS_API_URL")  # Required
SHEETS_API_TOKEN = os.getenv("SHEETS_API_TOKEN")  # Required
BATCH_SIZE = int(os.getenv("SHEETS_BATCH_SIZE", "5"))
DAYS_BACK = int(os.getenv("SHEETS_SYNC_DAYS", "7"))


def query_runs_for_sync(db_path: str, days_back: int = 7) -> List[Dict]:
    """
    Query runs that need syncing to Google Sheets.

    Criteria:
    - status IN ('success', 'failure', 'partial')
    - api_posted = 0 (not yet synced to Google Sheets)
    - start_time within last {days_back} days

    Returns:
        List of run dictionaries
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()

    cursor.execute("""
        SELECT *
        FROM agent_runs
        WHERE status IN ('success', 'failure', 'partial')
          AND (api_posted = 0 OR api_posted IS NULL)
          AND start_time >= ?
        ORDER BY start_time ASC
    """, (cutoff_date,))

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def aggregate_runs(runs: List[Dict]) -> List[Dict]:
    """
    Group runs by (agent, website, section, product, platform)
    and sum metrics.

    Returns:
        List of aggregated event dicts matching Google Sheets schema
    """
    # Group by composite key
    groups = defaultdict(lambda: {
        'items_discovered': 0,
        'items_succeeded': 0,
        'items_failed': 0,
        'items_skipped': 0,
        'duration_ms': 0,
        'run_count': 0,
        'error_count': 0,
        'errors': [],
        'run_ids': []
    })

    for run in runs:
        key = (
            run.get('agent_name', 'NA'),
            run.get('website', 'NA'),
            run.get('website_section', 'NA'),
            run.get('product', 'NA'),
            run.get('platform', 'NA')
        )

        group = groups[key]
        group['items_discovered'] += run.get('items_discovered', 0)
        group['items_succeeded'] += run.get('items_succeeded', 0)
        group['items_failed'] += run.get('items_failed', 0)
        group['items_skipped'] += run.get('items_skipped', 0)
        group['duration_ms'] += run.get('duration_ms', 0)
        group['run_count'] += 1

        if run.get('status') in ('failure', 'partial'):
            group['error_count'] += 1
            if run.get('error_summary'):
                group['errors'].append(run['error_summary'])

        group['run_ids'].append(run['run_id'])

    # Convert to list of events
    events = []
    for key, group in groups.items():
        agent_name, website, website_section, product, platform = key

        # Get latest timestamp from this group (for reporting)
        timestamp = datetime.now(timezone.utc).isoformat()

        event = {
            'timestamp': timestamp,  # ISO 8601 with timezone
            'agent_name': agent_name,
            'job_type': 'aggregated_weekly',
            'product': product,
            'platform': platform,
            'website': website,
            'website_section': website_section,
            'item_name': 'runs',
            'items_discovered': group['items_discovered'],
            'items_failed': group['items_failed'],
            'items_succeeded': group['items_succeeded'],
            'items_skipped': group['items_skipped'],
            'run_count': group['run_count'],
            'error_count': group['error_count'],
            'duration_ms': group['duration_ms'],
            'error_summary': '; '.join(group['errors'][:5])  # First 5 errors
        }

        events.append(event)

    return events


def validate_event(event: Dict) -> Tuple[bool, str]:
    """
    Validate event matches Google Sheets requirements.

    Returns:
        (is_valid, error_message)
    """
    # Check required fields
    required = ['timestamp', 'agent_name', 'product', 'platform',
                'website', 'website_section', 'item_name',
                'items_discovered', 'items_failed', 'items_succeeded']

    for field in required:
        if field not in event:
            return False, f"Missing required field: {field}"

    # Validate invariant
    discovered = event['items_discovered']
    succeeded = event['items_succeeded']
    failed = event['items_failed']
    skipped = event.get('items_skipped', 0)

    if skipped > 0:
        expected = succeeded + failed + skipped
    else:
        expected = succeeded + failed

    if discovered != expected:
        # Auto-fix
        event['items_discovered'] = expected

    # Validate timestamp format (ISO 8601 with timezone)
    try:
        dt = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        # Ensure timezone aware
        if dt.tzinfo is None:
            return False, f"Timestamp missing timezone: {event['timestamp']}"
    except Exception as e:
        return False, f"Invalid timestamp format: {e}"

    return True, ""


def post_to_sheets_api(
    events: List[Dict],
    api_url: str,
    api_token: str,
    batch_size: int = 5
) -> Tuple[int, int, List[str]]:
    """
    Post aggregated events to Google Sheets API.

    Features:
    - Batch posting (5 events per request by default)
    - Retry with exponential backoff (3 attempts)
    - Error logging

    Returns:
        (successful_count, failed_count, error_messages)
    """
    successful = 0
    failed = 0
    errors = []

    for i in range(0, len(events), batch_size):
        batch = events[i:i + batch_size]

        # Retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    f"{api_url}?token={api_token}",
                    json={'events': batch},
                    timeout=30
                )
                response.raise_for_status()

                result = response.json()
                if result.get('ok'):
                    successful += len(batch)
                    print(f"Batch {i//batch_size + 1}: Posted {len(batch)} events")
                    break
                else:
                    error_msg = result.get('error', 'Unknown error')
                    errors.append(f"Batch {i//batch_size + 1}: {error_msg}")
                    failed += len(batch)
                    break

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"Retry {attempt + 1}/{max_retries} after {wait_time}s...")
                    import time
                    time.sleep(wait_time)
                else:
                    error_msg = f"Batch {i//batch_size + 1} failed after {max_retries} attempts: {e}"
                    errors.append(error_msg)
                    failed += len(batch)

    return successful, failed, errors


def mark_as_posted(db_path: str, run_ids: List[str]):
    """Update api_posted flag for successfully synced runs."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    placeholders = ','.join(['?'] * len(run_ids))
    cursor.execute(f"""
        UPDATE agent_runs
        SET api_posted = 1,
            api_posted_at = ?
        WHERE run_id IN ({placeholders})
    """, [datetime.now(timezone.utc).isoformat()] + run_ids)

    conn.commit()
    updated = cursor.rowcount
    conn.close()

    return updated


def main():
    """Main sync routine."""
    print("=" * 70)
    print("WEEKLY GOOGLE SHEETS SYNC")
    print("=" * 70)
    print(f"Start time: {datetime.now().isoformat()}")
    print(f"Database: {TELEMETRY_DB_PATH}")
    print(f"Days back: {DAYS_BACK}")
    print()

    # Validate configuration
    if not SHEETS_API_URL:
        print("ERROR: SHEETS_API_URL environment variable not set")
        sys.exit(1)

    if not SHEETS_API_TOKEN:
        print("ERROR: SHEETS_API_TOKEN environment variable not set")
        sys.exit(1)

    # Step 1: Query runs
    print("Step 1: Querying runs from database...")
    runs = query_runs_for_sync(TELEMETRY_DB_PATH, DAYS_BACK)
    print(f"  Found {len(runs)} runs to sync")

    if not runs:
        print("  No runs to sync. Exiting.")
        return

    # Step 2: Aggregate
    print("\nStep 2: Aggregating by (agent, website, section, product, platform)...")
    events = aggregate_runs(runs)
    print(f"  Aggregated to {len(events)} events")
    if len(runs) > 0:
        print(f"  Reduction: {len(runs)} runs -> {len(events)} events ({len(events)*100//len(runs)}%)")

    # Step 3: Validate
    print("\nStep 3: Validating events...")
    for i, event in enumerate(events):
        valid, error = validate_event(event)
        if not valid:
            print(f"  WARNING: Event {i+1} validation issue: {error}")

    # Step 4: Post to Google Sheets
    print("\nStep 4: Posting to Google Sheets API...")
    successful, failed, errors = post_to_sheets_api(
        events,
        SHEETS_API_URL,
        SHEETS_API_TOKEN,
        BATCH_SIZE
    )

    print(f"\nResults:")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")

    if errors:
        print(f"\nErrors:")
        for error in errors:
            print(f"  - {error}")

    # Step 5: Mark as posted
    if successful > 0:
        print("\nStep 5: Marking runs as posted...")
        all_run_ids = [run['run_id'] for run in runs]
        updated = mark_as_posted(TELEMETRY_DB_PATH, all_run_ids)
        print(f"  Updated {updated} runs")

    print("\n" + "=" * 70)
    if failed == 0:
        print("SUCCESS - All events posted to Google Sheets")
    else:
        print(f"PARTIAL SUCCESS - {successful} posted, {failed} failed")
    print("=" * 70)

    # Exit code
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
