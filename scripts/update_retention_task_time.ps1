#!/usr/bin/env powershell
# Update retention task to run at 2 PM instead of 2 AM
# Run as Administrator

$ErrorActionPreference = "Stop"

# Configuration
$taskName = "TelemetryDockerRetentionCleanup"
$scriptPath = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry\scripts\docker_retention_cleanup.ps1"
$retentionDays = 30
$cleanupTime = "14:00"  # 2 PM

Write-Host "=== Updating Scheduled Task Time ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Task Name: $taskName"
Write-Host "  New Time: $cleanupTime (2 PM)"
Write-Host "  Retention: $retentionDays days"
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] This script must be run as Administrator" -ForegroundColor Red
    Write-Host ""
    Write-Host "Right-click PowerShell and select 'Run as Administrator', then run this script again." -ForegroundColor Yellow
    exit 1
}

# Check if task exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $existingTask) {
    Write-Host "[ERROR] Task not found: $taskName" -ForegroundColor Red
    exit 1
}

Write-Host "[INFO] Removing existing task..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
Write-Host "[SUCCESS] Existing task removed" -ForegroundColor Green
Write-Host ""

# Create task action
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Days $retentionDays"

# Create triggers
# Trigger 1: Daily at 2 PM
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At $cleanupTime

# Trigger 2: At startup (run if missed)
$startupTrigger = New-ScheduledTaskTrigger -AtStartup

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

# Create principal (run as SYSTEM)
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Register the task
Write-Host "[INFO] Registering scheduled task with new time..." -ForegroundColor Yellow
$task = Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($dailyTrigger, $startupTrigger) `
    -Settings $settings `
    -Principal $principal `
    -Description "Automated daily cleanup of Docker telemetry database to maintain $retentionDays-day retention policy"

Write-Host ""
Write-Host "[SUCCESS] Scheduled task updated successfully!" -ForegroundColor Green
Write-Host ""

# Display task info
Write-Host "Task Details:" -ForegroundColor Cyan
Write-Host "  Name: $($task.TaskName)"
Write-Host "  State: $($task.State)"
Write-Host "  Next Run: $(Get-ScheduledTaskInfo -TaskName $taskName | Select-Object -ExpandProperty NextRunTime)"
Write-Host ""

Write-Host "The task will now:" -ForegroundColor Yellow
Write-Host "  - Run daily at 2:00 PM"
Write-Host "  - Run at system startup if a scheduled run was missed"
Write-Host "  - Delete records older than $retentionDays days"
Write-Host "  - Run VACUUM to reclaim disk space"
Write-Host "  - Log results to D:\agent-metrics\logs\"
Write-Host ""

Write-Host "Update complete!" -ForegroundColor Green
