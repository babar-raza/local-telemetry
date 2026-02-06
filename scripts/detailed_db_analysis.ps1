# Detailed Database Analysis - Find what's consuming space

function Run-SQL {
    param($query, $description)
    Write-Host "`n--- $description ---" -ForegroundColor Yellow
    $result = docker exec local-telemetry-api sh -c "sqlite3 -readonly /data/telemetry.sqlite '$query'" 2>$null
    if ($result) {
        $result | ForEach-Object { Write-Host $_ }
    } else {
        Write-Host "No results or query error"
    }
}

Write-Host "========================================"  -ForegroundColor Cyan
Write-Host "Detailed Database Analysis" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

Run-SQL "SELECT COUNT(*) as total_rows FROM agent_runs;" "Total Rows"

Run-SQL "SELECT
    MIN(created_at) as first_record,
    MAX(created_at) as last_record,
    CAST((JULIANDAY(MAX(created_at)) - JULIANDAY(MIN(created_at))) AS INT) as days_span
FROM agent_runs;" "Date Range"

Run-SQL "SELECT
    product,
    COUNT(*) as count,
    CAST(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM agent_runs) AS INT) || '%' as percentage
FROM agent_runs
GROUP BY product
ORDER BY count DESC
LIMIT 10;" "Top 10 Products by Record Count"

Run-SQL "SELECT
    job_type,
    COUNT(*) as count,
    CAST(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM agent_runs) AS INT) || '%' as percentage
FROM agent_runs
GROUP BY job_type
ORDER BY count DESC
LIMIT 10;" "Top 10 Job Types by Record Count"

Run-SQL "SELECT
    status,
    COUNT(*) as count
FROM agent_runs
GROUP BY status
ORDER BY count DESC;" "Status Distribution"

Run-SQL "SELECT
    DATE(created_at) as date,
    COUNT(*) as count
FROM agent_runs
GROUP BY DATE(created_at)
ORDER BY count DESC
LIMIT 10;" "Top 10 Days by Record Count"

Run-SQL "SELECT
    agent_name,
    COUNT(*) as count
FROM agent_runs
GROUP BY agent_name
ORDER BY count DESC
LIMIT 10;" "Top 10 Agent Names by Record Count"

Run-SQL "SELECT
    CAST(AVG(LENGTH(COALESCE(input_summary, ''))) AS INT) as avg_input,
    CAST(AVG(LENGTH(COALESCE(output_summary, ''))) AS INT) as avg_output,
    CAST(AVG(LENGTH(COALESCE(metrics_json, ''))) AS INT) as avg_metrics,
    CAST(AVG(LENGTH(COALESCE(context_json, ''))) AS INT) as avg_context,
    CAST(AVG(LENGTH(COALESCE(error_details, ''))) AS INT) as avg_error
FROM agent_runs;" "Average Field Sizes (bytes)"

Run-SQL "SELECT
    COUNT(CASE WHEN LENGTH(COALESCE(input_summary, '')) > 10000 THEN 1 END) as large_input,
    COUNT(CASE WHEN LENGTH(COALESCE(output_summary, '')) > 10000 THEN 1 END) as large_output,
    COUNT(CASE WHEN LENGTH(COALESCE(metrics_json, '')) > 10000 THEN 1 END) as large_metrics,
    COUNT(CASE WHEN LENGTH(COALESCE(context_json, '')) > 10000 THEN 1 END) as large_context
FROM agent_runs;" "Records with Large Fields (>10KB)"

Write-Host "`n========================================"  -ForegroundColor Cyan
Write-Host "Analysis Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
