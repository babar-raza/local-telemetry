# Database Cleanup Script
# Deletes old records and reclaims space using VACUUM

param(
    [int]$DaysToKeep = 90,
    [switch]$DryRun = $false,
    [switch]$VacuumOnly = $false,
    [string]$AgentFilter = "",
    [switch]$KeepBackup = $true
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Database Cleanup Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "DRY RUN MODE - No changes will be made" -ForegroundColor Yellow
}

# Calculate cutoff date
$cutoffDate = (Get-Date).AddDays(-$DaysToKeep).ToString("yyyy-MM-ddT00:00:00Z")
Write-Host "`nSettings:" -ForegroundColor Yellow
Write-Host "  Days to keep: $DaysToKeep"
Write-Host "  Cutoff date: $cutoffDate"
if ($AgentFilter) {
    Write-Host "  Agent filter: $AgentFilter"
}

# Function to run SQL
function Run-SQL {
    param($query)
    docker exec local-telemetry-api sh -c "sqlite3 /data/telemetry.sqlite `"$query`"" 2>$null
}

# Check current state
Write-Host "`n--- Current Database State ---" -ForegroundColor Yellow
$totalRows = Run-SQL "SELECT COUNT(*) FROM agent_runs;"
Write-Host "Total records: $totalRows"

if (-not $VacuumOnly) {
    # Count records to delete
    $deleteQuery = "SELECT COUNT(*) FROM agent_runs WHERE created_at < '$cutoffDate'"
    if ($AgentFilter) {
        $deleteQuery += " AND agent_name LIKE '%$AgentFilter%'"
    }

    $toDelete = Run-SQL $deleteQuery
    Write-Host "Records older than $DaysToKeep days: $toDelete"
    Write-Host "Records to keep: $($totalRows - $toDelete)"

    if ($toDelete -eq 0) {
        Write-Host "`nNo records to delete." -ForegroundColor Green
        exit 0
    }

    if (-not $DryRun) {
        # Confirm deletion
        Write-Host "`nThis will delete $toDelete records. Continue? (Y/N): " -ForegroundColor Red -NoNewline
        $confirm = Read-Host
        if ($confirm -ne 'Y' -and $confirm -ne 'y') {
            Write-Host "Cancelled." -ForegroundColor Yellow
            exit 0
        }

        # Create backup
        if ($KeepBackup) {
            Write-Host "`nCreating backup..." -ForegroundColor Yellow
            $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
            docker exec local-telemetry-api sh -c "cp /data/telemetry.sqlite /data/telemetry.backup_$timestamp.sqlite"
            Write-Host "Backup created: telemetry.backup_$timestamp.sqlite" -ForegroundColor Green
        }

        # Stop API for safe deletion
        Write-Host "`nStopping API..." -ForegroundColor Yellow
        docker stop local-telemetry-api | Out-Null
        Start-Sleep -Seconds 3

        try {
            # Delete old records
            Write-Host "Deleting old records..." -ForegroundColor Yellow
            $deleteCmd = "DELETE FROM agent_runs WHERE created_at < '$cutoffDate'"
            if ($AgentFilter) {
                $deleteCmd += " AND agent_name LIKE '%$AgentFilter%'"
            }

            Run-SQL $deleteCmd

            # Delete orphaned run_events
            Write-Host "Cleaning up orphaned run_events..." -ForegroundColor Yellow
            Run-SQL "DELETE FROM run_events WHERE event_id NOT IN (SELECT event_id FROM agent_runs);"

            Write-Host "Records deleted successfully." -ForegroundColor Green

        } finally {
            # Restart API
            Write-Host "Restarting API..." -ForegroundColor Yellow
            docker start local-telemetry-api | Out-Null
            Start-Sleep -Seconds 2
        }
    }
}

# VACUUM to reclaim space
if (-not $DryRun) {
    Write-Host "`n--- Running VACUUM to reclaim space ---" -ForegroundColor Yellow
    Write-Host "This may take several minutes for large databases..." -ForegroundColor Yellow

    # Stop API for VACUUM
    docker stop local-telemetry-api | Out-Null
    Start-Sleep -Seconds 3

    try {
        $vacuumStart = Get-Date
        Run-SQL "VACUUM;"
        $vacuumEnd = Get-Date
        $duration = ($vacuumEnd - $vacuumStart).TotalSeconds

        Write-Host "VACUUM completed in $([math]::Round($duration, 2)) seconds" -ForegroundColor Green

    } finally {
        docker start local-telemetry-api | Out-Null
        Start-Sleep -Seconds 2
    }

    # Check new size
    Write-Host "`n--- New Database State ---" -ForegroundColor Yellow
    docker exec local-telemetry-api ls -lh /data/telemetry.sqlite

    $newRows = Run-SQL "SELECT COUNT(*) FROM agent_runs;"
    Write-Host "Total records: $newRows"
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Cleanup Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
