#!/usr/bin/env pwsh
<#
.SYNOPSIS
Monitor ongoing database cleanup progress

.DESCRIPTION
Monitors the batched deletion process by checking:
- Database lock status
- Journal file size
- Record count (when database is not locked)

.PARAMETER IntervalMinutes
How often to check (default: 10 minutes)

.PARAMETER MaxChecks
Maximum number of checks before stopping (default: 30 = 5 hours)

.EXAMPLE
.\monitor_cleanup_progress.ps1 -IntervalMinutes 10
#>

param(
    [int]$IntervalMinutes = 10,
    [int]$MaxChecks = 30
)

$LogFile = "D:\agent-metrics\logs\cleanup_monitor_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"
$ContainerName = "local-telemetry-api"

function Write-MonitorLog {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogEntry = "[$Timestamp] $Message"
    Write-Host $LogEntry
    Add-Content -Path $LogFile -Value $LogEntry
}

Write-MonitorLog "=== Cleanup Monitoring Started ==="
Write-MonitorLog "Checking every $IntervalMinutes minutes (max $MaxChecks checks)"
Write-MonitorLog "Log file: $LogFile"
Write-MonitorLog ""

$CheckCount = 0
$LastRecordCount = $null

while ($CheckCount -lt $MaxChecks) {
    $CheckCount++
    Write-MonitorLog "Check $CheckCount/$MaxChecks"

    # Check if container is running
    $containerStatus = docker ps --filter "name=$ContainerName" --format "{{.Status}}"
    if (-not $containerStatus) {
        Write-MonitorLog "ERROR: Container not running"
        break
    }
    Write-MonitorLog "Container status: $containerStatus"

    # Check for journal file (indicates active transaction)
    $journalCheck = docker exec $ContainerName sh -c "ls -lh /data/telemetry.sqlite-journal 2>/dev/null"
    if ($LASTEXITCODE -eq 0) {
        $journalSize = ($journalCheck -split '\s+')[4]
        Write-MonitorLog "Active transaction: Journal file size = $journalSize"
    } else {
        Write-MonitorLog "No active transaction (journal file not found)"
    }

    # Try to get record count
    $recordCount = docker exec $ContainerName sh -c "sqlite3 /data/telemetry.sqlite 'SELECT COUNT(*) FROM agent_runs' 2>&1"
    if ($LASTEXITCODE -eq 0 -and $recordCount -match '^\d+$') {
        $recordCountFormatted = [int]$recordCount
        Write-MonitorLog "Current record count: $($recordCountFormatted.ToString('N0'))"

        if ($null -ne $LastRecordCount) {
            $deleted = $LastRecordCount - $recordCountFormatted
            if ($deleted -gt 0) {
                Write-MonitorLog "Deleted since last check: $($deleted.ToString('N0')) records"
            }
        }
        $LastRecordCount = $recordCountFormatted
    } elseif ($recordCount -match "locked") {
        Write-MonitorLog "Database locked (cleanup in progress)"
    } else {
        Write-MonitorLog "Unable to query database: $recordCount"
    }

    # Check database file size
    $dbSize = docker exec $ContainerName sh -c "du -sh /data/telemetry.sqlite" 2>&1
    if ($LASTEXITCODE -eq 0) {
        $sizeValue = ($dbSize -split '\s+')[0]
        Write-MonitorLog "Database size: $sizeValue"
    }

    Write-MonitorLog ""

    # Check if cleanup is complete (no journal file and database not locked)
    if ($LASTEXITCODE -eq 0 -and $recordCount -match '^\d+$' -and -not $journalCheck) {
        Write-MonitorLog "=== Cleanup appears to be complete ==="
        Write-MonitorLog "Final record count: $($recordCountFormatted.ToString('N0'))"
        break
    }

    # Wait before next check
    if ($CheckCount -lt $MaxChecks) {
        Write-MonitorLog "Waiting $IntervalMinutes minutes before next check..."
        Start-Sleep -Seconds ($IntervalMinutes * 60)
    }
}

if ($CheckCount -ge $MaxChecks) {
    Write-MonitorLog "=== Reached maximum checks ($MaxChecks) ==="
}

Write-MonitorLog "=== Monitoring Complete ==="
Write-MonitorLog "Log saved to: $LogFile"
