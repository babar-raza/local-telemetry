#!/usr/bin/env powershell
# Quick setup script for retention task - Run as Administrator
# This creates a scheduled task that runs daily at 3:30 PM PKT and also runs at startup if missed

$ErrorActionPreference = "Stop"

# Configuration
$taskName = "TelemetryDockerRetentionCleanup"
$scriptPath = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry\scripts\docker_retention_cleanup.ps1"
$retentionDays = 30
$cleanupTime = "15:30"  # 3:30 PM PKT

Write-Host "=== Setting up Docker Telemetry Retention Scheduled Task ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Configuration:" -ForegroundColor Yellow
Write-Host "  Task Name: $taskName"
Write-Host "  Script: $scriptPath"
Write-Host "  Retention: $retentionDays days"
Write-Host "  Schedule: Daily at $cleanupTime"
Write-Host "  Run at startup if missed: Yes"
Write-Host ""

# Check if running as Administrator
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "[ERROR] This script must be run as Administrator" -ForegroundColor Red
    Write-Host ""
    Write-Host "Right-click PowerShell and select 'Run as Administrator', then run this script again." -ForegroundColor Yellow
    exit 1
}

# Check if script exists
if (-not (Test-Path $scriptPath)) {
    Write-Host "[ERROR] Cleanup script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

# Remove existing task if it exists
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Write-Host "[INFO] Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[SUCCESS] Existing task removed" -ForegroundColor Green
}

# Create task action
$action = New-ScheduledTaskAction -Execute "PowerShell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Days $retentionDays"

# Create triggers
# Trigger 1: Daily at 3:30 PM PKT
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
Write-Host "[INFO] Registering scheduled task..." -ForegroundColor Yellow
$task = Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger @($dailyTrigger, $startupTrigger) `
    -Settings $settings `
    -Principal $principal `
    -Description "Automated daily cleanup of Docker telemetry database to maintain $retentionDays-day retention policy"

Write-Host ""
Write-Host "[SUCCESS] Scheduled task created successfully!" -ForegroundColor Green
Write-Host ""

# Display task info
Write-Host "Task Details:" -ForegroundColor Cyan
Write-Host "  Name: $($task.TaskName)"
Write-Host "  State: $($task.State)"
Write-Host "  Next Run: $(Get-ScheduledTaskInfo -TaskName $taskName | Select-Object -ExpandProperty NextRunTime)"
Write-Host ""

Write-Host "The task will:" -ForegroundColor Yellow
Write-Host "  - Run daily at 3:30 PM PKT"
Write-Host "  - Run at system startup if a scheduled run was missed"
Write-Host "  - Delete records older than $retentionDays days"
Write-Host "  - Run VACUUM to reclaim disk space"
Write-Host "  - Log results to D:\agent-metrics\logs\"
Write-Host ""

Write-Host "To verify the task:" -ForegroundColor Cyan
Write-Host "  Get-ScheduledTask -TaskName '$taskName'"
Write-Host ""

Write-Host "To manually trigger the task (for testing):" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""

Write-Host "Setup complete!" -ForegroundColor Green
