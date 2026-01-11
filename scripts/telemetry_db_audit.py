#!/usr/bin/env python3
"""
Telemetry DB Audit Script
Performs read-only analysis of the SQLite telemetry database
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime

def get_db_path():
    """Get database path from environment or default"""
    return os.getenv("TELEMETRY_DB_PATH", "./data/telemetry.sqlite")

def get_db_size(db_path):
    """Get database file size in bytes"""
    if db_path.exists():
        return db_path.stat().st_size
    return 0

def analyze_schema(conn):
    """Analyze database schema"""
    cursor = conn.cursor()

    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]

    schema_info = {}
    total_rows = 0

    for table in tables:
        # Get row count
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        row_count = cursor.fetchone()[0]
        total_rows += row_count

        # Get column info
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()

        # Estimate size (rough approximation)
        cursor.execute(f"SELECT * FROM {table} LIMIT 1")
        sample = cursor.fetchone()
        if sample:
            avg_row_size = len(str(sample).encode('utf-8'))
            estimated_size = row_count * avg_row_size
        else:
            estimated_size = 0

        schema_info[table] = {
            'row_count': row_count,
            'columns': len(columns),
            'estimated_size_bytes': estimated_size,
            'column_details': [{'name': col[1], 'type': col[2]} for col in columns]
        }

    return schema_info, total_rows

def analyze_indexes(conn):
    """Analyze database indexes"""
    cursor = conn.cursor()

    cursor.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")
    indexes = cursor.fetchall()

    index_info = {}
    for name, table in indexes:
        index_info[name] = {'table': table}

    return index_info

def analyze_data_distribution(conn, schema_info):
    """Analyze data distribution patterns"""
    cursor = conn.cursor()

    distribution = {}

    # Check if agent_runs table exists
    if 'agent_runs' in schema_info:
        # Volume by agent
        cursor.execute("""
            SELECT agent_name, COUNT(*) as count
            FROM agent_runs
            GROUP BY agent_name
            ORDER BY count DESC
            LIMIT 10
        """)
        distribution['top_agents'] = cursor.fetchall()

        # Volume by status
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM agent_runs
            GROUP BY status
        """)
        distribution['status_distribution'] = cursor.fetchall()

        # Volume by day (if start_time exists)
        try:
            cursor.execute("""
                SELECT DATE(start_time) as day, COUNT(*) as count
                FROM agent_runs
                WHERE start_time IS NOT NULL
                GROUP BY DATE(start_time)
                ORDER BY day DESC
                LIMIT 30
            """)
            distribution['daily_volume'] = cursor.fetchall()
        except sqlite3.OperationalError:
            distribution['daily_volume'] = []

    # Check if run_events table exists
    if 'run_events' in schema_info:
        # Event types
        cursor.execute("""
            SELECT event_type, COUNT(*) as count
            FROM run_events
            GROUP BY event_type
            ORDER BY count DESC
            LIMIT 10
        """)
        distribution['top_event_types'] = cursor.fetchall()

        # Largest payloads (if payload column exists)
        try:
            cursor.execute("""
                SELECT LENGTH(payload) as size, event_type
                FROM run_events
                WHERE payload IS NOT NULL
                ORDER BY size DESC
                LIMIT 5
            """)
            distribution['largest_payloads'] = cursor.fetchall()
        except sqlite3.OperationalError:
            distribution['largest_payloads'] = []

    return distribution

def main():
    print("=" * 80)
    print("TELEMETRY DB AUDIT REPORT")
    print("=" * 80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    db_path = Path(get_db_path())
    print(f"Database Path: {db_path}")
    print(f"Database Exists: {db_path.exists()}")

    if not db_path.exists():
        print("ERROR: Database file does not exist")
        return

    size_bytes = get_db_size(db_path)
    size_mb = size_bytes / (1024 * 1024)
    print(f"{size_mb:.2f} MB")
    print()

    # Connect to database
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        # Schema analysis
        print("SCHEMA ANALYSIS")
        print("-" * 40)
        schema_info, total_rows = analyze_schema(conn)

        print(f"Total Tables: {len(schema_info)}")
        print(f"Total Rows: {total_rows}")
        print()

        print("Tables (sorted by row count):")
        for table, info in sorted(schema_info.items(), key=lambda x: x[1]['row_count'], reverse=True):
            print(f"  {table}: {info['row_count']:6d} rows")
        print()

        # Detailed table info
        for table, info in schema_info.items():
            print(f"Table: {table}")
            print(f"  Rows: {info['row_count']}")
            print(f"  Columns: {info['columns']}")
            print(f"  Estimated Size: {info['estimated_size_bytes'] / 1024:.2f} KB")
            print("  Columns:")
            for col in info['column_details']:
                print(f"    - {col['name']} ({col['type']})")
            print()

        # Index analysis
        print("INDEX ANALYSIS")
        print("-" * 40)
        index_info = analyze_indexes(conn)
        print(f"Total Indexes: {len(index_info)}")
        for name, info in index_info.items():
            print(f"  - {name} (on {info['table']})")
        print()

        # Data distribution
        print("DATA DISTRIBUTION ANALYSIS")
        print("-" * 40)
        distribution = analyze_data_distribution(conn, schema_info)

        if 'top_agents' in distribution:
            print("Top Agents by Run Count:")
            for agent, count in distribution['top_agents']:
                print(f"  {agent}: {count} runs")
            print()

        if 'status_distribution' in distribution:
            print("Status Distribution:")
            for status, count in distribution['status_distribution']:
                print(f"  {status}: {count}")
            print()

        if 'daily_volume' in distribution and distribution['daily_volume']:
            print("Daily Volume (last 30 days):")
            for day, count in distribution['daily_volume'][:10]:  # Show first 10
                print(f"  {day}: {count} runs")
            print()

        if 'top_event_types' in distribution:
            print("Top Event Types:")
            for event_type, count in distribution['top_event_types']:
                print(f"  {event_type}: {count} events")
            print()

        if 'largest_payloads' in distribution and distribution['largest_payloads']:
            print("Largest Payloads:")
            for size, event_type in distribution['largest_payloads']:
                print(f"  {size} bytes ({event_type})")
            print()

    finally:
        conn.close()

    print("=" * 80)
    print("AUDIT COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    main()