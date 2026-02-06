#!/usr/bin/env python3
"""
Analyze Docker database size and identify space usage.
Requires the telemetry API to be stopped temporarily.
"""

import subprocess
import sys
import json

def run_docker_sql(query):
    """Execute SQL query in Docker container."""
    cmd = [
        'docker', 'exec', 'local-telemetry-api',
        'sh', '-c', f'sqlite3 /data/telemetry.sqlite "{query}"'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None, result.stderr
    return result.stdout.strip(), None

def stop_api():
    """Stop the telemetry API."""
    print("Stopping telemetry API...")
    subprocess.run(['docker', 'stop', 'local-telemetry-api'], check=True)

def start_api():
    """Start the telemetry API."""
    print("Starting telemetry API...")
    subprocess.run(['docker', 'start', 'local-telemetry-api'], check=True)

def get_table_info():
    """Get information about each table."""
    tables_query = "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"
    tables, err = run_docker_sql(tables_query)
    if err:
        print(f"Error getting tables: {err}")
        return []

    table_list = tables.split('\n') if tables else []
    table_info = []

    for table in table_list:
        if not table:
            continue

        # Get row count
        count_query = f"SELECT COUNT(*) FROM {table};"
        count, err = run_docker_sql(count_query)
        if err:
            print(f"Error counting {table}: {err}")
            count = "ERROR"

        # Get table schema
        schema_query = f"SELECT sql FROM sqlite_master WHERE name='{table}';"
        schema, err = run_docker_sql(schema_query)
        if err:
            print(f"Error getting schema for {table}: {err}")
            schema = "ERROR"

        # Get sample data size (first row)
        sample_query = f"SELECT * FROM {table} LIMIT 1;"
        sample, err = run_docker_sql(sample_query)
        sample_size = len(sample) if sample else 0

        table_info.append({
            'table': table,
            'rows': count,
            'schema': schema,
            'sample_size': sample_size
        })

    return table_info

def get_index_info():
    """Get information about indexes."""
    index_query = "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';"
    indexes, err = run_docker_sql(index_query)
    if err:
        print(f"Error getting indexes: {err}")
        return []
    return indexes

def analyze_large_columns():
    """Identify columns with large data."""
    queries = {
        'agent_runs_largest': """
            SELECT
                event_id,
                LENGTH(input_summary) as input_len,
                LENGTH(output_summary) as output_len,
                LENGTH(error_details) as error_len,
                LENGTH(metrics_json) as metrics_len,
                LENGTH(context_json) as context_len
            FROM agent_runs
            ORDER BY (
                LENGTH(COALESCE(input_summary,'')) +
                LENGTH(COALESCE(output_summary,'')) +
                LENGTH(COALESCE(error_details,'')) +
                LENGTH(COALESCE(metrics_json,'')) +
                LENGTH(COALESCE(context_json,''))
            ) DESC
            LIMIT 10;
        """,
        'run_events_largest': """
            SELECT
                event_id,
                event_type,
                LENGTH(message) as message_len,
                LENGTH(metadata_json) as metadata_len
            FROM run_events
            ORDER BY (LENGTH(COALESCE(message,'')) + LENGTH(COALESCE(metadata_json,''))) DESC
            LIMIT 10;
        """
    }

    results = {}
    for name, query in queries.items():
        result, err = run_docker_sql(query)
        if err:
            results[name] = f"ERROR: {err}"
        else:
            results[name] = result

    return results

def main():
    try:
        # Stop API
        stop_api()
        print("\n" + "="*80)
        print("DATABASE SIZE ANALYSIS")
        print("="*80)

        # Get DB info
        print("\n--- Database Statistics ---")
        dbinfo, _ = run_docker_sql(".dbinfo")
        print(dbinfo)

        # Get table info
        print("\n--- Table Information ---")
        tables = get_table_info()
        for t in tables:
            print(f"\nTable: {t['table']}")
            print(f"  Rows: {t['rows']}")
            print(f"  Sample size: {t['sample_size']} bytes")
            print(f"  Schema: {t['schema'][:200]}..." if len(t.get('schema', '')) > 200 else f"  Schema: {t.get('schema', '')}")

        # Get index info
        print("\n--- Indexes ---")
        indexes = get_index_info()
        print(indexes)

        # Analyze large columns
        print("\n--- Large Column Analysis ---")
        large_cols = analyze_large_columns()
        for name, data in large_cols.items():
            print(f"\n{name}:")
            print(data)

        # Check for date ranges
        print("\n--- Date Range Analysis ---")
        date_query = "SELECT MIN(created_at) as first, MAX(created_at) as last, COUNT(*) as total FROM agent_runs;"
        dates, _ = run_docker_sql(date_query)
        print(f"Agent runs: {dates}")

        # Analyze JSON field sizes
        print("\n--- JSON Field Size Analysis ---")
        json_query = """
            SELECT
                COUNT(*) as total_rows,
                AVG(LENGTH(COALESCE(metrics_json, ''))) as avg_metrics_size,
                MAX(LENGTH(COALESCE(metrics_json, ''))) as max_metrics_size,
                AVG(LENGTH(COALESCE(context_json, ''))) as avg_context_size,
                MAX(LENGTH(COALESCE(context_json, ''))) as max_context_size,
                AVG(LENGTH(COALESCE(input_summary, ''))) as avg_input_size,
                MAX(LENGTH(COALESCE(input_summary, ''))) as max_input_size,
                AVG(LENGTH(COALESCE(output_summary, ''))) as avg_output_size,
                MAX(LENGTH(COALESCE(output_summary, ''))) as max_output_size
            FROM agent_runs;
        """
        json_sizes, _ = run_docker_sql(json_query)
        print(json_sizes)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        # Always restart API
        start_api()
        print("\n" + "="*80)
        print("Analysis complete. API restarted.")
        print("="*80)

    return 0

if __name__ == '__main__':
    sys.exit(main())
