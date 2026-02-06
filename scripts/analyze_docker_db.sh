#!/bin/bash
# Analyze Docker database size
# This script temporarily stops the API to query the database

echo "Stopping API..."
docker stop local-telemetry-api
sleep 2

echo "Starting temporary container for analysis..."

# Run analysis queries using a temporary container with the volume mounted
docker run --rm \
  -v local-telemetry_telemetry-data:/data:ro \
  alpine:latest sh -c "
    apk add --no-cache sqlite

    echo '============================================'
    echo 'DATABASE SIZE ANALYSIS'
    echo '============================================'

    echo ''
    echo '--- File Sizes ---'
    ls -lh /data/

    echo ''
    echo '--- Database Info ---'
    sqlite3 /data/telemetry.sqlite '.dbinfo'

    echo ''
    echo '--- Table Row Counts ---'
    sqlite3 /data/telemetry.sqlite 'SELECT \"agent_runs\", COUNT(*) FROM agent_runs;'
    sqlite3 /data/telemetry.sqlite 'SELECT \"run_events\", COUNT(*) FROM run_events;'
    sqlite3 /data/telemetry.sqlite 'SELECT \"commits\", COUNT(*) FROM commits;'
    sqlite3 /data/telemetry.sqlite 'SELECT \"schema_migrations\", COUNT(*) FROM schema_migrations;'

    echo ''
    echo '--- Date Range ---'
    sqlite3 /data/telemetry.sqlite 'SELECT MIN(created_at), MAX(created_at) FROM agent_runs;'

    echo ''
    echo '--- JSON Field Sizes (agent_runs) ---'
    sqlite3 /data/telemetry.sqlite '
      SELECT
        \"Total Rows:\", COUNT(*),
        \"Avg metrics_json:\", AVG(LENGTH(COALESCE(metrics_json, \"\"))),
        \"Max metrics_json:\", MAX(LENGTH(COALESCE(metrics_json, \"\"))),
        \"Avg context_json:\", AVG(LENGTH(COALESCE(context_json, \"\"))),
        \"Max context_json:\", MAX(LENGTH(COALESCE(context_json, \"\")))
      FROM agent_runs;'

    echo ''
    echo '--- Text Field Sizes (agent_runs) ---'
    sqlite3 /data/telemetry.sqlite '
      SELECT
        \"Avg input_summary:\", AVG(LENGTH(COALESCE(input_summary, \"\"))),
        \"Max input_summary:\", MAX(LENGTH(COALESCE(input_summary, \"\"))),
        \"Avg output_summary:\", AVG(LENGTH(COALESCE(output_summary, \"\"))),
        \"Max output_summary:\", MAX(LENGTH(COALESCE(output_summary, \"\"))),
        \"Avg error_details:\", AVG(LENGTH(COALESCE(error_details, \"\"))),
        \"Max error_details:\", MAX(LENGTH(COALESCE(error_details, \"\")))
      FROM agent_runs;'

    echo ''
    echo '--- Top 10 Largest Rows by Total Size ---'
    sqlite3 /data/telemetry.sqlite '
      SELECT
        event_id,
        LENGTH(COALESCE(input_summary,\"\")) +
        LENGTH(COALESCE(output_summary,\"\")) +
        LENGTH(COALESCE(error_details,\"\")) +
        LENGTH(COALESCE(metrics_json,\"\")) +
        LENGTH(COALESCE(context_json,\"\")) as total_size
      FROM agent_runs
      ORDER BY total_size DESC
      LIMIT 10;'

    echo ''
    echo '--- Schema Version ---'
    sqlite3 /data/telemetry.sqlite 'SELECT * FROM schema_migrations;'
"

echo ""
echo "Restarting API..."
docker start local-telemetry-api

echo "Done!"
