# Quick Database Analysis
# Uses the existing container's sqlite3

Write-Host "Analyzing database..." -ForegroundColor Cyan

# Function to run SQL query
function Run-SQL {
    param($query)
    docker exec local-telemetry-api sh -c "sqlite3 -readonly /data/telemetry.sqlite '$query'" 2>$null
}

Write-Host "`n--- File Sizes ---" -ForegroundColor Yellow
docker exec local-telemetry-api ls -lh /data/

Write-Host "`n--- Row Counts ---" -ForegroundColor Yellow
Write-Host "agent_runs: $(Run-SQL 'SELECT COUNT(*) FROM agent_runs;')"
Write-Host "run_events: $(Run-SQL 'SELECT COUNT(*) FROM run_events;')"
Write-Host "commits: $(Run-SQL 'SELECT COUNT(*) FROM commits;')"

Write-Host "`n--- Date Range ---" -ForegroundColor Yellow
$dates = Run-SQL "SELECT MIN(created_at) || ' to ' || MAX(created_at) FROM agent_runs;"
Write-Host "Date range: $dates"

Write-Host "`n--- Database Page Info ---" -ForegroundColor Yellow
$pageCount = Run-SQL "PRAGMA page_count;"
$pageSize = Run-SQL "PRAGMA page_size;"
$freelistCount = Run-SQL "PRAGMA freelist_count;"
Write-Host "Page count: $pageCount"
Write-Host "Page size: $pageSize bytes"
Write-Host "Freelist count: $freelistCount"
$estimatedSize = [math]::Round(($pageCount * $pageSize) / 1GB, 2)
Write-Host "Estimated DB size: $estimatedSize GB"

Write-Host "`n--- Field Size Statistics ---" -ForegroundColor Yellow
$fieldStats = Run-SQL "SELECT 'Total rows: ' || COUNT(*) || ', Avg input: ' || CAST(AVG(LENGTH(COALESCE(input_summary, ''))) AS INT) || ', Max input: ' || MAX(LENGTH(COALESCE(input_summary, ''))) || ', Avg output: ' || CAST(AVG(LENGTH(COALESCE(output_summary, ''))) AS INT) || ', Max output: ' || MAX(LENGTH(COALESCE(output_summary, ''))) FROM agent_runs;"
Write-Host $fieldStats

Write-Host "`n--- Indexes ---" -ForegroundColor Yellow
Run-SQL "SELECT name || ' on ' || tbl_name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%';"

Write-Host "`nDone!" -ForegroundColor Green
