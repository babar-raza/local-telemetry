# Analyze Docker Database Size
# PowerShell script to investigate database bloat

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Docker Database Size Analysis" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Stop the API
Write-Host "`nStopping telemetry API..." -ForegroundColor Yellow
docker stop local-telemetry-api | Out-Null
Start-Sleep -Seconds 3

try {
    Write-Host "`nRunning analysis..." -ForegroundColor Yellow

    # Use a temporary container to analyze the database
    $commands = @'
apk add --no-cache sqlite

echo "--- File Sizes ---"
ls -lh /data/

echo ""
echo "--- Table Row Counts ---"
sqlite3 /data/telemetry.sqlite "SELECT 'agent_runs', COUNT(*) FROM agent_runs;"
sqlite3 /data/telemetry.sqlite "SELECT 'run_events', COUNT(*) FROM run_events;"
sqlite3 /data/telemetry.sqlite "SELECT 'commits', COUNT(*) FROM commits;"

echo ""
echo "--- Date Range ---"
sqlite3 /data/telemetry.sqlite "SELECT 'First run:', MIN(created_at), 'Last run:', MAX(created_at) FROM agent_runs;"

echo ""
echo "--- Field Size Analysis ---"
sqlite3 /data/telemetry.sqlite "
SELECT
  'Total rows:', COUNT(*),
  'Avg input_summary:', CAST(AVG(LENGTH(COALESCE(input_summary, ''))) AS INT),
  'Max input_summary:', MAX(LENGTH(COALESCE(input_summary, ''))),
  'Avg output_summary:', CAST(AVG(LENGTH(COALESCE(output_summary, ''))) AS INT),
  'Max output_summary:', MAX(LENGTH(COALESCE(output_summary, ''))),
  'Avg metrics_json:', CAST(AVG(LENGTH(COALESCE(metrics_json, ''))) AS INT),
  'Max metrics_json:', MAX(LENGTH(COALESCE(metrics_json, ''))),
  'Avg context_json:', CAST(AVG(LENGTH(COALESCE(context_json, ''))) AS INT),
  'Max context_json:', MAX(LENGTH(COALESCE(context_json, '')))
FROM agent_runs;"

echo ""
echo "--- Top 10 Largest Records ---"
sqlite3 /data/telemetry.sqlite "
SELECT
  run_id,
  CAST((
    LENGTH(COALESCE(input_summary,'')) +
    LENGTH(COALESCE(output_summary,'')) +
    LENGTH(COALESCE(error_details,'')) +
    LENGTH(COALESCE(metrics_json,'')) +
    LENGTH(COALESCE(context_json,''))
  ) / 1024.0 AS INT) || ' KB' as total_size
FROM agent_runs
ORDER BY (
  LENGTH(COALESCE(input_summary,'')) +
  LENGTH(COALESCE(output_summary,'')) +
  LENGTH(COALESCE(error_details,'')) +
  LENGTH(COALESCE(metrics_json,'')) +
  LENGTH(COALESCE(context_json,''))
) DESC
LIMIT 10;"

echo ""
echo "--- Indexes ---"
sqlite3 /data/telemetry.sqlite "SELECT name, tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';"

echo ""
echo "--- Page Count and Freelist ---"
sqlite3 /data/telemetry.sqlite "PRAGMA page_count; PRAGMA freelist_count;"
'@

    docker run --rm `
        -v local-telemetry_telemetry-data:/data:ro `
        alpine:latest `
        sh -c $commands

} finally {
    # Always restart the API
    Write-Host "`nRestarting telemetry API..." -ForegroundColor Yellow
    docker start local-telemetry-api | Out-Null
    Start-Sleep -Seconds 2
    Write-Host "API restarted." -ForegroundColor Green
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Analysis Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
