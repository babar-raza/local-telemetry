# docker_retention_cleanup.ps1
# Automated retention cleanup for Docker-based telemetry database
#
# Purpose:
#   - Delete records older than N days from Docker container database
#   - Run VACUUM to reclaim disk space
#   - Comprehensive logging and statistics
#   - Safe API shutdown/restart
#
# Usage:
#   .\docker_retention_cleanup.ps1 -Days 30                # Delete records older than 30 days
#   .\docker_retention_cleanup.ps1 -Days 30 -DryRun        # Preview without changes
#
# Scheduled via Windows Task Scheduler (Daily at 2:00 AM)
#
# Exit Codes:
#   0 = Success
#   1 = Failure

# =============================================================================
# CONFIGURATION
# =============================================================================

param(
    [int]$Days = 30,
    [switch]$DryRun = $false
)

$ErrorActionPreference = "Stop"

# Paths
$LogDir = "D:\agent-metrics\logs"
$ProjectDir = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"

# Docker
$ContainerName = "local-telemetry-api"

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================

# Initialize log file
$LogDate = Get-Date -Format "yyyyMMdd"
$LogFile = "$LogDir\retention_cleanup_$LogDate.log"
$ScriptStartTime = Get-Date

function Write-RetentionLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogEntry = "[$Timestamp] [$Level] $Message"

    # Ensure log directory exists
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    }

    # Write to log file
    Add-Content -Path $LogFile -Value $LogEntry

    # Also write to console with color
    switch ($Level) {
        "ERROR"    { Write-Host $LogEntry -ForegroundColor Red }
        "WARNING"  { Write-Host $LogEntry -ForegroundColor Yellow }
        "SUCCESS"  { Write-Host $LogEntry -ForegroundColor Green }
        default    { Write-Host $LogEntry }
    }
}

function Get-Duration {
    param([DateTime]$StartTime)
    $duration = (Get-Date) - $StartTime
    return "{0:mm}m {0:ss}s" -f $duration
}

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================

function Test-DockerRunning {
    Write-RetentionLog "Checking if Docker is running..."

    try {
        $dockerVersion = docker --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Docker command failed"
        }
        Write-RetentionLog "Docker is running: $dockerVersion" "SUCCESS"
        return $true
    } catch {
        Write-RetentionLog "Docker is not running or not installed" "ERROR"
        return $false
    }
}

function Test-ContainerExists {
    Write-RetentionLog "Checking if container '$ContainerName' exists..."

    try {
        $containerStatus = docker ps -a --filter "name=$ContainerName" --format "{{.Status}}" 2>&1
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrEmpty($containerStatus)) {
            throw "Container not found"
        }
        Write-RetentionLog "Container found: $containerStatus" "SUCCESS"
        return $true
    } catch {
        Write-RetentionLog "Container '$ContainerName' not found" "ERROR"
        return $false
    }
}

function Get-DatabaseStats {
    try {
        $recordCount = docker exec $ContainerName sqlite3 /data/telemetry.sqlite "SELECT COUNT(*) FROM agent_runs" 2>&1
        $dbSize = docker exec $ContainerName du -h /data/telemetry.sqlite 2>&1 | ForEach-Object { $_.Split()[0] }
        $oldestRecord = docker exec $ContainerName sqlite3 /data/telemetry.sqlite "SELECT MIN(created_at) FROM agent_runs" 2>&1
        $newestRecord = docker exec $ContainerName sqlite3 /data/telemetry.sqlite "SELECT MAX(created_at) FROM agent_runs" 2>&1

        return @{
            RecordCount = $recordCount
            DatabaseSize = $dbSize
            OldestRecord = $oldestRecord
            NewestRecord = $newestRecord
        }
    } catch {
        Write-RetentionLog "Failed to get database stats: $_" "WARNING"
        return $null
    }
}

# =============================================================================
# MAIN EXECUTION
# =============================================================================

try {
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Docker Retention Cleanup" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host ""

    Write-RetentionLog "=== Retention Cleanup Started ==="
    Write-RetentionLog "Retention period: $Days days"
    Write-RetentionLog "Dry run mode: $DryRun"
    Write-RetentionLog "Log file: $LogFile"

    # Pre-flight checks
    if (-not (Test-DockerRunning)) {
        throw "Docker is not running. Please start Docker Desktop and try again."
    }

    if (-not (Test-ContainerExists)) {
        throw "Container '$ContainerName' not found. Please check docker-compose setup."
    }

    # Get before statistics
    Write-RetentionLog "Getting database statistics before cleanup..."
    $beforeStats = Get-DatabaseStats

    if ($beforeStats) {
        Write-RetentionLog "Records before: $($beforeStats.RecordCount)"
        Write-RetentionLog "Database size before: $($beforeStats.DatabaseSize)"
        Write-RetentionLog "Oldest record: $($beforeStats.OldestRecord)"
        Write-RetentionLog "Newest record: $($beforeStats.NewestRecord)"
    }

    # Stop API for safe cleanup (unless dry-run)
    if (-not $DryRun) {
        Write-RetentionLog "Stopping API container for safe cleanup..." "WARNING"
        $stopStart = Get-Date
        docker stop $ContainerName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to stop container"
        }
        Start-Sleep -Seconds 3
        Write-RetentionLog "API stopped in $(Get-Duration $stopStart)" "SUCCESS"
    }

    try {
        # Run retention policy
        Write-RetentionLog "Running retention policy (this may take several minutes)..."
        $cleanupStart = Get-Date

        $dryRunFlag = if ($DryRun) { "--dry-run" } else { "" }

        # Execute retention policy inside container
        if ($DryRun) {
            # For dry-run, container is still running
            $output = docker exec $ContainerName python3 /app/scripts/db_retention_policy_batched.py /data/telemetry.sqlite --days $Days --dry-run 2>&1
        } else {
            # For actual cleanup, we need to start container temporarily to run the script
            docker start $ContainerName | Out-Null
            Start-Sleep -Seconds 2

            $output = docker exec $ContainerName python3 /app/scripts/db_retention_policy_batched.py /data/telemetry.sqlite --days $Days 2>&1

            # Stop again after cleanup
            docker stop $ContainerName | Out-Null
            Start-Sleep -Seconds 2
        }

        # Log output from Python script
        if ($output) {
            $output | ForEach-Object { Write-RetentionLog $_ }
        }

        if ($LASTEXITCODE -ne 0) {
            throw "Retention policy script failed with exit code $LASTEXITCODE"
        }

        $cleanupDuration = Get-Duration $cleanupStart
        Write-RetentionLog "Retention policy completed in $cleanupDuration" "SUCCESS"

    } finally {
        # Always restart API (unless dry-run)
        if (-not $DryRun) {
            Write-RetentionLog "Restarting API container..." "WARNING"
            $restartStart = Get-Date
            docker start $ContainerName | Out-Null

            # Wait for API to be healthy
            Start-Sleep -Seconds 3

            # Test API health
            try {
                $healthResponse = Invoke-WebRequest -Uri "http://localhost:8765/health" -TimeoutSec 10 -UseBasicParsing
                if ($healthResponse.StatusCode -eq 200) {
                    Write-RetentionLog "API restarted and healthy in $(Get-Duration $restartStart)" "SUCCESS"
                } else {
                    Write-RetentionLog "API restarted but health check returned: $($healthResponse.StatusCode)" "WARNING"
                }
            } catch {
                Write-RetentionLog "API restarted but health check failed: $_" "WARNING"
            }
        }
    }

    # Get after statistics (only if not dry-run)
    if (-not $DryRun) {
        Write-RetentionLog "Getting database statistics after cleanup..."
        Start-Sleep -Seconds 2
        $afterStats = Get-DatabaseStats

        if ($afterStats) {
            Write-RetentionLog "Records after: $($afterStats.RecordCount)"
            Write-RetentionLog "Database size after: $($afterStats.DatabaseSize)"
            Write-RetentionLog "Oldest record: $($afterStats.OldestRecord)"

            # Calculate changes
            if ($beforeStats -and $afterStats) {
                try {
                    $recordsDeleted = [int]$beforeStats.RecordCount - [int]$afterStats.RecordCount
                    Write-RetentionLog "Records deleted: $recordsDeleted" "SUCCESS"
                } catch {
                    Write-RetentionLog "Could not calculate deleted records" "WARNING"
                }
            }
        }
    }

    $totalDuration = Get-Duration $ScriptStartTime
    Write-RetentionLog "=== Retention Cleanup Completed Successfully in $totalDuration ===" "SUCCESS"

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "Cleanup Complete" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    exit 0

} catch {
    $errorMessage = $_.Exception.Message
    Write-RetentionLog "=== Retention Cleanup Failed ===" "ERROR"
    Write-RetentionLog "Error: $errorMessage" "ERROR"
    Write-RetentionLog "Stack trace: $($_.ScriptStackTrace)" "ERROR"

    # Try to restart API if it was stopped
    try {
        $containerStatus = docker ps --filter "name=$ContainerName" --format "{{.Status}}" 2>&1
        if ([string]::IsNullOrEmpty($containerStatus)) {
            Write-RetentionLog "Attempting to restart API after error..." "WARNING"
            docker start $ContainerName | Out-Null
            Start-Sleep -Seconds 2
            Write-RetentionLog "API restarted" "WARNING"
        }
    } catch {
        Write-RetentionLog "Failed to restart API: $_" "ERROR"
    }

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "Cleanup Failed - See log: $LogFile" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red

    exit 1
}
