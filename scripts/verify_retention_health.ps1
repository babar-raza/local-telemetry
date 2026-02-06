# verify_retention_health.ps1
# Health check script for retention cleanup monitoring
#
# Purpose:
#   - Verify database size and record counts
#   - Check oldest/newest records
#   - View scheduled task status
#   - Review recent cleanup logs
#   - Quick status overview
#
# Usage:
#   .\verify_retention_health.ps1
#   .\verify_retention_health.ps1 -Detailed (show more information)
#
# Exit Codes:
#   0 = Healthy
#   1 = Issues detected
#   2 = Docker not running

# =============================================================================
# PARAMETERS
# =============================================================================

param(
    [Parameter(Mandatory=$false, HelpMessage="Show detailed information")]
    [switch]$Detailed = $false
)

# =============================================================================
# CONFIGURATION
# =============================================================================

$ErrorActionPreference = "Stop"

$ContainerName = "local-telemetry-api"
$TaskName = "TelemetryDockerRetentionCleanup"
$LogDir = "D:\agent-metrics\logs"
$ExpectedRetentionDays = 30
$ExpectedRecordsMin = 1500000  # ~1.5 million (allow some variance)
$ExpectedRecordsMax = 2000000  # ~2 million
$ExpectedSizeMin = 3  # GB
$ExpectedSizeMax = 5  # GB

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

function Test-DockerRunning {
    try {
        docker ps > $null 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-DatabaseSize {
    try {
        $sizeOutput = docker exec $ContainerName du -h /data/telemetry.sqlite 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return $sizeOutput.Split()[0]
    } catch {
        return $null
    }
}

function Get-RecordCount {
    try {
        $count = docker exec $ContainerName sqlite3 /data/telemetry.sqlite "SELECT COUNT(*) FROM agent_runs" 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return [long]$count
    } catch {
        return $null
    }
}

function Get-OldestRecord {
    try {
        $oldest = docker exec $ContainerName sqlite3 /data/telemetry.sqlite "SELECT MIN(created_at) FROM agent_runs" 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return $oldest
    } catch {
        return $null
    }
}

function Get-NewestRecord {
    try {
        $newest = docker exec $ContainerName sqlite3 /data/telemetry.sqlite "SELECT MAX(created_at) FROM agent_runs" 2>&1
        if ($LASTEXITCODE -ne 0) {
            return $null
        }
        return $newest
    } catch {
        return $null
    }
}

function Get-RetentionDays {
    param([string]$OldestRecord)

    if ([string]::IsNullOrEmpty($OldestRecord)) {
        return $null
    }

    try {
        $oldestDate = [DateTime]::Parse($OldestRecord)
        $days = ((Get-Date) - $oldestDate).Days
        return $days
    } catch {
        return $null
    }
}

function Get-TaskStatus {
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($null -eq $task) {
            return @{
                Exists = $false
                State = "Not Found"
            }
        }

        $taskInfo = $task | Get-ScheduledTaskInfo

        return @{
            Exists = $true
            State = $task.State
            LastRunTime = $taskInfo.LastRunTime
            LastTaskResult = $taskInfo.LastTaskResult
            NextRunTime = $taskInfo.NextRunTime
        }
    } catch {
        return @{
            Exists = $false
            State = "Error"
        }
    }
}

function Get-RecentLogs {
    param([int]$Count = 7)

    if (-not (Test-Path $LogDir)) {
        return @()
    }

    try {
        $logs = Get-ChildItem "$LogDir\retention_cleanup_*.log" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First $Count

        return $logs
    } catch {
        return @()
    }
}

function Get-StatusIndicator {
    param([string]$Status, [bool]$IsGood)

    if ($IsGood) {
        return "[OK] $Status" | Write-Host -ForegroundColor Green
    } else {
        return "[WARN] $Status" | Write-Host -ForegroundColor Yellow
    }
}

# =============================================================================
# MAIN
# =============================================================================

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Retention Health Check" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$issues = @()

# Check Docker
Write-Host "Docker Status:" -ForegroundColor Yellow
if (-not (Test-DockerRunning)) {
    Write-Host "  [ERROR] Docker is not running" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please start Docker Desktop and try again." -ForegroundColor Yellow
    exit 2
}
Write-Host "  [OK] Docker is running" -ForegroundColor Green
Write-Host ""

# Database Metrics
Write-Host "Database Metrics:" -ForegroundColor Yellow

$dbSize = Get-DatabaseSize
if ($dbSize) {
    Write-Host "  Database Size: $dbSize" -ForegroundColor White

    # Check if size is in expected range
    $sizeGB = $null
    if ($dbSize -match '(\d+\.?\d*)G') {
        $sizeGB = [double]$Matches[1]
    } elseif ($dbSize -match '(\d+)M') {
        $sizeGB = [double]$Matches[1] / 1024
    }

    if ($sizeGB -and ($sizeGB -lt $ExpectedSizeMin -or $sizeGB -gt $ExpectedSizeMax)) {
        $issues += "Database size ($sizeGB GB) outside expected range ($ExpectedSizeMin-$ExpectedSizeMax GB)"
        Write-Host "    WARNING: Size outside expected range ($ExpectedSizeMin-$ExpectedSizeMax GB)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [ERROR] Could not get database size" -ForegroundColor Red
    $issues += "Failed to get database size"
}

$recordCount = Get-RecordCount
if ($recordCount) {
    $recordCountFormatted = "{0:N0}" -f $recordCount
    Write-Host "  Total Records: $recordCountFormatted" -ForegroundColor White

    if ($recordCount -lt $ExpectedRecordsMin -or $recordCount -gt $ExpectedRecordsMax) {
        $issues += "Record count ($recordCountFormatted) outside expected range"
        Write-Host "    WARNING: Count outside expected range (1.5M-2M)" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [ERROR] Could not get record count" -ForegroundColor Red
    $issues += "Failed to get record count"
}

$oldestRecord = Get-OldestRecord
if ($oldestRecord) {
    Write-Host "  Oldest Record: $oldestRecord" -ForegroundColor White

    $retentionDays = Get-RetentionDays -OldestRecord $oldestRecord
    if ($retentionDays) {
        Write-Host "  Retention Days: ~$retentionDays days" -ForegroundColor White

        if ($retentionDays -gt ($ExpectedRetentionDays + 5)) {
            $issues += "Retention period ($retentionDays days) exceeds target ($ExpectedRetentionDays days)"
            Write-Host "    WARNING: Retention exceeds target by $($retentionDays - $ExpectedRetentionDays) days" -ForegroundColor Yellow
        }
    }
} else {
    Write-Host "  [ERROR] Could not get oldest record" -ForegroundColor Red
    $issues += "Failed to get oldest record"
}

$newestRecord = Get-NewestRecord
if ($newestRecord) {
    Write-Host "  Newest Record: $newestRecord" -ForegroundColor White
} else {
    Write-Host "  [ERROR] Could not get newest record" -ForegroundColor Red
}

Write-Host ""

# Scheduled Task Status
Write-Host "Scheduled Task:" -ForegroundColor Yellow
$taskStatus = Get-TaskStatus

if ($taskStatus.Exists) {
    Write-Host "  Status: $($taskStatus.State)" -ForegroundColor White

    if ($taskStatus.State -ne "Ready") {
        $issues += "Task state is '$($taskStatus.State)' (expected: Ready)"
        Write-Host "    WARNING: Task is not in 'Ready' state" -ForegroundColor Yellow
    }

    if ($taskStatus.LastRunTime) {
        $daysSinceRun = ((Get-Date) - $taskStatus.LastRunTime).Days
        Write-Host "  Last Run: $($taskStatus.LastRunTime)" -ForegroundColor White
        Write-Host "  Days Since Run: $daysSinceRun" -ForegroundColor White

        if ($daysSinceRun -gt 2) {
            $issues += "Task hasn't run for $daysSinceRun days"
            Write-Host "    WARNING: Task hasn't run recently" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Last Run: Never" -ForegroundColor White
        $issues += "Task has never run"
        Write-Host "    WARNING: Task has never run" -ForegroundColor Yellow
    }

    if ($taskStatus.LastTaskResult -ne $null) {
        if ($taskStatus.LastTaskResult -eq 0) {
            Write-Host "  Last Result: 0 (Success)" -ForegroundColor Green
        } else {
            Write-Host "  Last Result: $($taskStatus.LastTaskResult) (Failed)" -ForegroundColor Red
            $issues += "Last task execution failed (code: $($taskStatus.LastTaskResult))"
        }
    }

    if ($taskStatus.NextRunTime) {
        Write-Host "  Next Run: $($taskStatus.NextRunTime)" -ForegroundColor Cyan
    }
} else {
    Write-Host "  [ERROR] Task not found: $TaskName" -ForegroundColor Red
    $issues += "Scheduled task not configured"
    Write-Host "    Run setup_docker_retention_task.ps1 to create it" -ForegroundColor Yellow
}

Write-Host ""

# Recent Logs
Write-Host "Recent Cleanup Logs:" -ForegroundColor Yellow
$recentLogs = Get-RecentLogs -Count 7

if ($recentLogs.Count -gt 0) {
    foreach ($log in $recentLogs) {
        $daysSince = ((Get-Date) - $log.LastWriteTime).Days
        $dateStr = $log.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
        Write-Host "  $($log.Name) - $dateStr ($daysSince days ago)" -ForegroundColor Gray

        if ($Detailed) {
            # Show last few lines of log
            $lastLines = Get-Content $log.FullName -Tail 3 -ErrorAction SilentlyContinue
            if ($lastLines) {
                $lastLines | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
            }
        }
    }

    if (-not $Detailed) {
        Write-Host ""
        Write-Host "  Tip: Use -Detailed flag to see log contents" -ForegroundColor DarkGray
    }
} else {
    Write-Host "  No logs found in $LogDir" -ForegroundColor Gray
}

Write-Host ""

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($issues.Count -eq 0) {
    Write-Host "Health Check: PASSED" -ForegroundColor Green
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "All retention metrics are within expected ranges." -ForegroundColor Green
    Write-Host ""
    exit 0
} else {
    Write-Host "Health Check: ISSUES DETECTED" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Issues found:" -ForegroundColor Yellow
    $issues | ForEach-Object { Write-Host "  - $_" -ForegroundColor Yellow }
    Write-Host ""

    Write-Host "Recommended Actions:" -ForegroundColor Cyan
    Write-Host "  1. Review recent logs:" -ForegroundColor Gray
    Write-Host "     Get-Content $LogDir\retention_cleanup_$(Get-Date -Format 'yyyyMMdd').log" -ForegroundColor White
    Write-Host ""
    Write-Host "  2. Check Task Scheduler history:" -ForegroundColor Gray
    Write-Host "     Get-ScheduledTask -TaskName '$TaskName' | Get-ScheduledTaskInfo" -ForegroundColor White
    Write-Host ""
    Write-Host "  3. Test manual cleanup:" -ForegroundColor Gray
    Write-Host "     .\scripts\docker_retention_cleanup.ps1 -Days 30 -DryRun" -ForegroundColor White
    Write-Host ""

    exit 1
}
