# setup_docker_backup_task.ps1
# Create Windows Task Scheduler task for daily Docker database backups
#
# Purpose:
#   - Automate daily backups at 3:00 PM
#   - Configure retry logic and error handling
#   - Run as SYSTEM for reliability
#
# Usage:
#   Run this script as Administrator to create the scheduled task
#   .\setup_docker_backup_task.ps1
#   .\setup_docker_backup_task.ps1 -Remove (to remove existing task)
#
# Requirements:
#   - Must run as Administrator
#   - Docker must be installed and running
#   - Backup scripts must exist in scripts/ directory
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

    [Parameter(Mandatory=$false, HelpMessage="Update existing task (force replace)")]
    [switch]$Update
)

$ErrorActionPreference = "Stop"

# =============================================================================
# CONFIGURATION
# =============================================================================

$taskName = "TelemetryDockerDailyBackup"
$scriptPath = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry\scripts\backup_docker_telemetry.ps1"
$projectDir = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"

# Schedule configuration
$backupTime = "15:00"  # 3:00 PM
$retentionDays = 14

# Task settings
$executionTimeLimit = New-TimeSpan -Hours 1
$restartCount = 3
$restartInterval = New-TimeSpan -Minutes 5

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

function Test-BackupScriptExists {
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

function New-BackupTask {
    param([string]$TaskName, [string]$ScriptPath)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "Creating Windows Task Scheduler Task" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Task Name:        $TaskName" -ForegroundColor White
    Write-Host "Script:           $ScriptPath" -ForegroundColor White
    Write-Host "Schedule:         Daily at $backupTime" -ForegroundColor White
    Write-Host "Retention:        $retentionDays days" -ForegroundColor White
    Write-Host "Execution Limit:  $($executionTimeLimit.TotalMinutes) minutes" -ForegroundColor White
    Write-Host "Restart Count:    $restartCount" -ForegroundColor White
    Write-Host ""

    try {
        # Create action: Run PowerShell script
        Write-Host "[1/5] Creating task action..." -ForegroundColor Yellow

        $action = New-ScheduledTaskAction `
            -Execute "PowerShell.exe" `
            -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`"" `
            -WorkingDirectory $projectDir

        Write-Host "      Action created" -ForegroundColor Green

        # Create trigger: Daily at 3:00 PM
        Write-Host "[2/5] Creating task trigger..." -ForegroundColor Yellow

        $trigger = New-ScheduledTaskTrigger -Daily -At $backupTime

        Write-Host "      Trigger created: Daily at $backupTime" -ForegroundColor Green

        # Create settings: Production-ready configuration
        Write-Host "[3/5] Creating task settings..." -ForegroundColor Yellow

        $settings = New-ScheduledTaskSettingsSet `
            -AllowStartIfOnBatteries `
            -DontStopIfGoingOnBatteries `
            -StartWhenAvailable `
            -RunOnlyIfNetworkAvailable `
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
Daily automated backup of Docker telemetry database at $backupTime with $retentionDays-day retention.

Features:
- Hot backup using SQLite backup API
- Integrity verification
- Automatic retention management
- Email alerts on failure
- Comprehensive logging

Backup destination: D:\agent-metrics\docker-backups\
Log files: D:\agent-metrics\logs\

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
        Write-Host ""

        # Display helpful commands
        Write-Host "Useful Commands:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  View task details:" -ForegroundColor Gray
        Write-Host "    Get-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Test immediately:" -ForegroundColor Gray
        Write-Host "    Start-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  View task history:" -ForegroundColor Gray
        Write-Host "    Get-ScheduledTask -TaskName `"$TaskName`" | Get-ScheduledTaskInfo" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  View logs:" -ForegroundColor Gray
        Write-Host "    Get-Content D:\agent-metrics\logs\docker_backup_$(Get-Date -Format 'yyyyMMdd').log -Tail 50" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Disable task:" -ForegroundColor Gray
        Write-Host "    Disable-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Enable task:" -ForegroundColor Gray
        Write-Host "    Enable-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Remove task:" -ForegroundColor Gray
        Write-Host "    Unregister-ScheduledTask -TaskName `"$TaskName`" -Confirm:`$false" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  Or run this script with -Remove flag:" -ForegroundColor Gray
        Write-Host "    .\setup_docker_backup_task.ps1 -Remove" -ForegroundColor Cyan
        Write-Host ""

        # Recommendations
        Write-Host "Recommendations:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  1. Test the backup now:" -ForegroundColor Gray
        Write-Host "     Start-ScheduledTask -TaskName `"$TaskName`"" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  2. Verify backup created:" -ForegroundColor Gray
        Write-Host "     Get-ChildItem D:\agent-metrics\docker-backups\ | Sort-Object LastWriteTime -Descending" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  3. Configure email alerts (optional):" -ForegroundColor Gray
        Write-Host "     Edit scripts\Send-BackupAlert.ps1 with SMTP settings" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  4. Monitor Task Scheduler history:" -ForegroundColor Gray
        Write-Host "     Open Task Scheduler > Task Scheduler Library > $TaskName" -ForegroundColor Cyan
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
    Write-Host "Docker Telemetry Backup - Task Scheduler Setup" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
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
        Write-Host "          The task will be created, but backups will fail until Docker is running" -ForegroundColor Yellow
    } else {
        Write-Host "[OK] Docker is available" -ForegroundColor Green
    }

    # Check backup script exists
    if (-not (Test-BackupScriptExists)) {
        Write-Host "[ERROR] Backup script not found: $scriptPath" -ForegroundColor Red
        Write-Host ""
        Write-Host "Make sure all backup scripts are created before setting up the task." -ForegroundColor Yellow
        Write-Host ""
        return 1
    }

    Write-Host "[OK] Backup script found" -ForegroundColor Green

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
        Write-Host "[INFO] Task already exists: $taskName" -ForegroundColor Yellow
        Write-Host ""

        if ($Update) {
            Write-Host "Update flag detected. Task will be replaced." -ForegroundColor Yellow
            if (-not (Remove-ExistingTask -TaskName $taskName)) {
                return 1
            }
        } else {
            Write-Host "Options:" -ForegroundColor Cyan
            Write-Host "  1. Remove and recreate (recommended): Run with -Update flag" -ForegroundColor Gray
            Write-Host "  2. Remove only: Run with -Remove flag" -ForegroundColor Gray
            Write-Host "  3. Keep existing: Do nothing" -ForegroundColor Gray
            Write-Host ""

            $choice = Read-Host "What would you like to do? (1/2/3)"

            switch ($choice) {
                "1" {
                    Write-Host ""
                    if (-not (Remove-ExistingTask -TaskName $taskName)) {
                        return 1
                    }
                }
                "2" {
                    Write-Host ""
                    if (Remove-ExistingTask -TaskName $taskName) {
                        Write-Host ""
                        return 0
                    } else {
                        Write-Host ""
                        return 1
                    }
                }
                "3" {
                    Write-Host ""
                    Write-Host "Keeping existing task. No changes made." -ForegroundColor Yellow
                    Write-Host ""
                    return 0
                }
                default {
                    Write-Host ""
                    Write-Host "Invalid choice. Exiting." -ForegroundColor Red
                    Write-Host ""
                    return 1
                }
            }
        }
    }

    # Create the task
    if (New-BackupTask -TaskName $taskName -ScriptPath $scriptPath) {
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
