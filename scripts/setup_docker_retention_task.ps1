# setup_docker_retention_task.ps1
# Create Windows Task Scheduler task for daily Docker database retention cleanup
#
# Purpose:
#   - Automate daily retention cleanup at 3:30 PM
#   - Delete records older than 30 days
#   - Run VACUUM to reclaim disk space
#   - Configure retry logic and error handling
#   - Run as SYSTEM for reliability
#
# Usage:
#   Run this script as Administrator to create the scheduled task
#   .\setup_docker_retention_task.ps1
#   .\setup_docker_retention_task.ps1 -Remove (to remove existing task)
#
# Requirements:
#   - Must run as Administrator
#   - Docker must be installed and running
#   - Retention cleanup scripts must exist in scripts/ directory
#
# Exit Codes:
#   0 = Success
#   1 = Failure

# =============================================================================
# PARAMETERS
# =============================================================================

param(
    [Parameter(Mandatory=$false, HelpMessage="Remove existing task instead of creating")]
    [switch]$Remove,

    [Parameter(Mandatory=$false, HelpMessage="Retention period in days")]
    [int]$RetentionDays = 30
)

$ErrorActionPreference = "Stop"

# =============================================================================
# CONFIGURATION
# =============================================================================

$taskName = "TelemetryDockerRetentionCleanup"
$scriptPath = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry\scripts\docker_retention_cleanup.ps1"
$projectDir = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"

# Schedule configuration
$cleanupTime = "15:30"  # 3:30 PM

# Task settings
$executionTimeLimit = New-TimeSpan -Hours 2  # Allow up to 2 hours for VACUUM on large databases
$restartCount = 1  # Retry once if fails
$restartInterval = New-TimeSpan -Minutes 30

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

function Test-AdminPrivileges {
    $currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-DockerAvailable {
    try {
        $dockerVersion = docker --version 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Test-CleanupScriptExists {
    return Test-Path $scriptPath
}

function Get-ExistingTask {
    try {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        return $task
    } catch {
        return $null
    }
}

function Remove-ExistingTask {
    param([string]$TaskName)

    try {
        Write-Host "Removing existing task: $TaskName..." -ForegroundColor Yellow
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Task removed successfully" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "[ERROR] Failed to remove task: $_" -ForegroundColor Red
        return $false
    }
}

# =============================================================================
# TASK CREATION
# =============================================================================

function New-RetentionTask {
    param([string]$TaskName, [string]$ScriptPath, [int]$Days)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "Creating Windows Task Scheduler Task" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Task Name:        $TaskName" -ForegroundColor White
    Write-Host "Script:           $ScriptPath" -ForegroundColor White
    Write-Host "Schedule:         Daily at $cleanupTime" -ForegroundColor White
    Write-Host "Retention:        $Days days (delete older)" -ForegroundColor White
    Write-Host "Execution Limit:  $($executionTimeLimit.TotalHours) hours" -ForegroundColor White
    Write-Host "Restart Count:    $restartCount" -ForegroundColor White
    Write-Host ""

    try {
        # Create action: Run PowerShell script with retention days parameter
        Write-Host "[1/5] Creating task action..." -ForegroundColor Yellow

        $action = New-ScheduledTaskAction `
            -Execute "PowerShell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -Days $Days" `
            -WorkingDirectory $projectDir

        Write-Host "      Action created" -ForegroundColor Green

        # Create trigger: Daily at 3:30 PM
        Write-Host "[2/5] Creating task trigger..." -ForegroundColor Yellow

        $trigger = New-ScheduledTaskTrigger -Daily -At $cleanupTime

        Write-Host "      Trigger created: Daily at $cleanupTime" -ForegroundColor Green

        # Create settings: Production-ready configuration
        Write-Host "[3/5] Creating task settings..." -ForegroundColor Yellow

        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -ExecutionTimeLimit $executionTimeLimit `
            -RestartCount $restartCount `
            -RestartInterval $restartInterval `
            -Priority 6

        Write-Host "      Settings configured" -ForegroundColor Green

        # Create principal: Run as SYSTEM
        Write-Host "[4/5] Creating task principal..." -ForegroundColor Yellow

        $principal = New-ScheduledTaskPrincipal `
            -UserId "SYSTEM" `
            -LogonType ServiceAccount `
            -RunLevel Highest

        Write-Host "      Principal: SYSTEM (highest privileges)" -ForegroundColor Green

        # Register task
        Write-Host "[5/5] Registering task..." -ForegroundColor Yellow

        $description = @"
Daily automated retention cleanup of Docker telemetry database at $cleanupTime with $Days-day retention.

Features:
- Deletes records older than $Days days
- Runs VACUUM to reclaim disk space
- Safe API shutdown during cleanup
- Automatic API restart after completion
- Comprehensive logging with statistics
- Health check verification

Database: /data/telemetry.sqlite (Docker container)
Log files: D:\agent-metrics\logs\retention_cleanup_*.log

Expected database size after cleanup: ~3-4 GB
Expected records after cleanup: ~1.7 million ($Days days worth)

Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
"@

        Register-ScheduledTask `
            -TaskName $TaskName `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -Principal $principal `
            -Description $description `
            -Force | Out-Null

        Write-Host "      Task registered successfully" -ForegroundColor Green

        # Get next run time
        $taskInfo = Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
        $nextRunTime = $taskInfo.NextRunTime

        Write-Host ""
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host "TASK CREATED SUCCESSFULLY" -ForegroundColor Green
        Write-Host "============================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Task Name:    $TaskName" -ForegroundColor White
        Write-Host "Status:       Ready" -ForegroundColor Green
        Write-Host "Next Run:     $nextRunTime" -ForegroundColor Cyan
        Write-Host "Retention:    $Days days" -ForegroundColor Cyan
        Write-Host ""

        # Display helpful commands
        Write-Host "Useful Commands:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  View task details:" -ForegroundColor Gray
        Write-Host "    Get-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  View task info (last run, next run):" -ForegroundColor Gray
        Write-Host "    Get-ScheduledTask -TaskName `"$TaskName`" | Get-ScheduledTaskInfo" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Test dry-run immediately (safe, no changes):" -ForegroundColor Gray
        Write-Host "    .\scripts\docker_retention_cleanup.ps1 -Days $Days -DryRun" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Run actual cleanup now:" -ForegroundColor Gray
        Write-Host "    .\scripts\docker_retention_cleanup.ps1 -Days $Days" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Trigger scheduled task immediately:" -ForegroundColor Gray
        Write-Host "    Start-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  View today's log:" -ForegroundColor Gray
        Write-Host "    Get-Content D:\agent-metrics\logs\retention_cleanup_$(Get-Date -Format 'yyyyMMdd').log" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  View recent logs:" -ForegroundColor Gray
        Write-Host "    Get-ChildItem D:\agent-metrics\logs\retention_cleanup_*.log | Sort-Object -Descending" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Check database size:" -ForegroundColor Gray
        Write-Host "    .\scripts\verify_retention_health.ps1" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Disable task:" -ForegroundColor Gray
        Write-Host "    Disable-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Remove task:" -ForegroundColor Gray
        Write-Host "    .\setup_docker_retention_task.ps1 -Remove" -ForegroundColor Cyan
        Write-Host ""

        # Recommendations
        Write-Host "Recommendations:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  1. Test with dry-run first (safe, no changes):" -ForegroundColor Gray
        Write-Host "     .\scripts\docker_retention_cleanup.ps1 -Days $Days -DryRun" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  2. Review the preview and decide on first manual run:" -ForegroundColor Gray
        Write-Host "     .\scripts\docker_retention_cleanup.ps1 -Days $Days" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  3. Monitor the first scheduled run:" -ForegroundColor Gray
        Write-Host "     Check Task Scheduler history at $nextRunTime" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  4. Verify cleanup worked:" -ForegroundColor Gray
        Write-Host "     .\scripts\verify_retention_health.ps1" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  5. Check logs after first run:" -ForegroundColor Gray
        Write-Host "     Look for 'SUCCESS' in D:\agent-metrics\logs\retention_cleanup_*.log" -ForegroundColor Cyan
        Write-Host ""

        # Important notes
        Write-Host "Important Notes:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  - The task will run daily at $cleanupTime" -ForegroundColor White
        Write-Host "  - API will be stopped during cleanup (~30-60 min for first run)" -ForegroundColor White
        Write-Host "  - VACUUM can take 20-45 minutes on large databases" -ForegroundColor White
        Write-Host "  - After first run, cleanups will be faster (only 1 day's data)" -ForegroundColor White
        Write-Host "  - Database will stabilize at ~3-4 GB with $Days days retention" -ForegroundColor White
        Write-Host "  - All operations are logged to D:\agent-metrics\logs\" -ForegroundColor White
        Write-Host ""

        return $true

    } catch {
        Write-Host ""
        Write-Host "[ERROR] Failed to create task: $_" -ForegroundColor Red
        return $false
    }
}

# =============================================================================
# MAIN
# =============================================================================

function Main {
    Write-Host ""
    Write-Host "Docker Telemetry Retention - Task Scheduler Setup" -ForegroundColor Cyan
    Write-Host "===================================================" -ForegroundColor Cyan
    Write-Host ""

    # Check admin privileges
    if (-not (Test-AdminPrivileges)) {
        Write-Host "[ERROR] This script must be run as Administrator" -ForegroundColor Red
        Write-Host ""
        Write-Host "Right-click PowerShell and select 'Run as Administrator', then run this script again." -ForegroundColor Yellow
        Write-Host ""
        return 1
    }

    Write-Host "[OK] Running as Administrator" -ForegroundColor Green

    # Check Docker available
    if (-not (Test-DockerAvailable)) {
        Write-Host "[WARNING] Docker is not running or not installed" -ForegroundColor Yellow
        Write-Host "          The task will be created, but cleanups will fail until Docker is running" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] Docker is available" -ForegroundColor Green
    }

    # Check cleanup script exists
    if (-not (Test-CleanupScriptExists)) {
        Write-Host "[ERROR] Cleanup script not found: $scriptPath" -ForegroundColor Red
        Write-Host ""
        Write-Host "Make sure docker_retention_cleanup.ps1 exists before setting up the task." -ForegroundColor Yellow
        Write-Host ""
        return 1
    }

    Write-Host "[OK] Cleanup script found" -ForegroundColor Green

    # Handle -Remove flag
    if ($Remove) {
        $existingTask = Get-ExistingTask

        if ($null -eq $existingTask) {
            Write-Host ""
            Write-Host "[INFO] Task does not exist: $taskName" -ForegroundColor Yellow
            Write-Host ""
            return 0
        }

        if (Remove-ExistingTask -TaskName $taskName) {
            Write-Host ""
            return 0
        } else {
            Write-Host ""
            return 1
        }
    }

    # Check if task already exists
    $existingTask = Get-ExistingTask

    if ($null -ne $existingTask) {
        Write-Host ""
        Write-Host "[INFO] Task already exists: $taskName - replacing automatically" -ForegroundColor Yellow
        if (-not (Remove-ExistingTask -TaskName $taskName)) {
            return 1
        }
    }

    # Create the task
    if (New-RetentionTask -TaskName $taskName -ScriptPath $scriptPath -Days $RetentionDays) {
        return 0
    } else {
        return 1
    }
}

# =============================================================================
# ENTRY POINT
# =============================================================================

$exitCode = Main

exit $exitCode
