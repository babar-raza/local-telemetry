# Create Windows Task Scheduler task for weekly sync
# Run this script as Administrator to create the scheduled task

$taskName = "TelemetryWeeklyGoogleSheetsSync"
$scriptPath = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry\scripts\sync_to_sheets_weekly.py"
$pythonPath = "python"  # or full path to python.exe, e.g., "C:\Python311\python.exe"

Write-Host "Creating Windows Task Scheduler task..."
Write-Host "Task name: $taskName"
Write-Host "Script: $scriptPath"
Write-Host ""

# Create action
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $scriptPath

# Create trigger (every Monday at 9:00 AM)
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9:00AM

# Create task settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# Register task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Description "Weekly telemetry sync to Google Sheets" `
        -Force

    Write-Host "[OK] Task created successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Schedule: Every Monday at 9:00 AM"
    Write-Host ""
    Write-Host "To verify, run:" -ForegroundColor Yellow
    Write-Host "  Get-ScheduledTask -TaskName $taskName" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To test immediately, run:" -ForegroundColor Yellow
    Write-Host "  Start-ScheduledTask -TaskName $taskName" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To view task history, open Task Scheduler and navigate to:" -ForegroundColor Yellow
    Write-Host "  Task Scheduler Library > $taskName" -ForegroundColor Cyan
}
catch {
    Write-Host "[ERROR] Failed to create task: $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "Make sure you run this script as Administrator!" -ForegroundColor Yellow
    exit 1
}
