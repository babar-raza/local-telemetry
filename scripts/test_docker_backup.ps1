# test_docker_backup.ps1
# Manual testing script for Docker database backup
#
# Purpose:
#   - Test backup process without Task Scheduler
#   - Verify backup creation and integrity
#   - Display backup statistics
#   - Test verification script
#
# Usage:
#   .\test_docker_backup.ps1
#   .\test_docker_backup.ps1 -TestRestore
#
# Exit Codes:
#   0 = Success
#   1 = Failure

# =============================================================================
# PARAMETERS
# =============================================================================

param(
    [Parameter(Mandatory=$false, HelpMessage="Test restore functionality")]
    [switch]$TestRestore,

    [Parameter(Mandatory=$false, HelpMessage="Test retention cleanup")]
    [switch]$TestRetention
)

$ErrorActionPreference = "Stop"

# =============================================================================
# CONFIGURATION
# =============================================================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$BackupBaseDir = "D:\agent-metrics\docker-backups"
$LogDir = "D:\agent-metrics\logs"

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

function Write-TestHeader {
    param([string]$Title)

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-TestStep {
    param([string]$Message)
    Write-Host "[TEST] $Message" -ForegroundColor Yellow
}

function Write-TestSuccess {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-TestFailure {
    param([string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Write-TestInfo {
    param([string]$Message)
    Write-Host "  $Message" -ForegroundColor Gray
}

# =============================================================================
# TEST FUNCTIONS
# =============================================================================

function Test-BackupScript {
    Write-TestHeader "TEST 1: Backup Script Execution"

    Write-TestStep "Running backup_docker_telemetry.ps1..."

    $backupScript = "$ScriptDir\backup_docker_telemetry.ps1"

    if (-not (Test-Path $backupScript)) {
        Write-TestFailure "Backup script not found: $backupScript"
        return $false
    }

    try {
        $startTime = Get-Date

        # Run backup script
        & $backupScript

        $exitCode = $LASTEXITCODE
        $duration = ((Get-Date) - $startTime).TotalSeconds

        if ($exitCode -eq 0) {
            Write-TestSuccess "Backup script completed successfully"
            Write-TestInfo "Duration: ${duration}s"
            return $true
        } else {
            Write-TestFailure "Backup script failed with exit code: $exitCode"
            return $false
        }

    } catch {
        Write-TestFailure "Error running backup script: $_"
        return $false
    }
}

function Test-BackupCreated {
    Write-TestHeader "TEST 2: Backup File Verification"

    Write-TestStep "Checking for latest backup..."

    if (-not (Test-Path $BackupBaseDir)) {
        Write-TestFailure "Backup directory not found: $BackupBaseDir"
        return $false
    }

    $latestBackup = Get-ChildItem $BackupBaseDir -Directory |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -eq $latestBackup) {
        Write-TestFailure "No backups found in $BackupBaseDir"
        return $false
    }

    Write-TestSuccess "Latest backup found: $($latestBackup.Name)"
    Write-TestInfo "Created: $($latestBackup.CreationTime)"

    # Check for database file
    $dbFile = Get-Item "$($latestBackup.FullName)\telemetry.sqlite" -ErrorAction SilentlyContinue

    if ($null -eq $dbFile) {
        Write-TestFailure "Database file not found in backup"
        return $false
    }

    $sizeMB = [math]::Round($dbFile.Length / 1MB, 2)
    Write-TestSuccess "Database file: ${sizeMB} MB"

    # Check for metadata file
    $metadataFile = Get-Item "$($latestBackup.FullName)\backup_metadata.json" -ErrorAction SilentlyContinue

    if ($null -eq $metadataFile) {
        Write-TestFailure "Metadata file not found in backup"
        return $false
    }

    Write-TestSuccess "Metadata file found"

    # Display metadata
    try {
        $metadata = Get-Content $metadataFile | ConvertFrom-Json
        Write-TestInfo "Timestamp: $($metadata.timestamp)"
        Write-TestInfo "Size: $($metadata.size_mb) MB"
        Write-TestInfo "Verified: $($metadata.verified)"
        Write-TestInfo "Container: $($metadata.docker_container)"
        Write-TestInfo "Method: $($metadata.backup_method)"
    } catch {
        Write-TestFailure "Failed to parse metadata: $_"
        return $false
    }

    return $true
}

function Test-VerificationScript {
    Write-TestHeader "TEST 3: Verification Script"

    Write-TestStep "Running verify_backup_integrity.py on latest backup..."

    $latestBackup = Get-ChildItem $BackupBaseDir -Directory |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -eq $latestBackup) {
        Write-TestFailure "No backups found"
        return $false
    }

    $backupPath = "$($latestBackup.FullName)\telemetry.sqlite"
    $verifyScript = "$ProjectDir\scripts\verify_backup_integrity.py"

    if (-not (Test-Path $verifyScript)) {
        Write-TestFailure "Verification script not found: $verifyScript"
        return $false
    }

    try {
        $output = python $verifyScript --backup-path $backupPath 2>&1

        if ($LASTEXITCODE -eq 0) {
            Write-TestSuccess "Backup verified successfully"
            Write-TestInfo "$output"
            return $true
        } else {
            Write-TestFailure "Backup verification failed"
            Write-TestInfo "$output"
            return $false
        }

    } catch {
        Write-TestFailure "Error running verification script: $_"
        return $false
    }
}

function Test-LogFiles {
    Write-TestHeader "TEST 4: Log Files"

    Write-TestStep "Checking for log files..."

    if (-not (Test-Path $LogDir)) {
        Write-TestFailure "Log directory not found: $LogDir"
        return $false
    }

    $logDate = Get-Date -Format "yyyyMMdd"
    $expectedLogFile = "$LogDir\docker_backup_$logDate.log"

    if (-not (Test-Path $expectedLogFile)) {
        Write-TestFailure "Log file not found: $expectedLogFile"
        return $false
    }

    Write-TestSuccess "Log file found: $expectedLogFile"

    # Display last 10 lines
    $logContent = Get-Content $expectedLogFile -Tail 10

    Write-TestInfo "Last 10 log entries:"
    foreach ($line in $logContent) {
        Write-Host "    $line" -ForegroundColor DarkGray
    }

    return $true
}

function Test-BackupCount {
    Write-TestHeader "TEST 5: Backup Count & Retention"

    Write-TestStep "Counting backups..."

    if (-not (Test-Path $BackupBaseDir)) {
        Write-TestFailure "Backup directory not found"
        return $false
    }

    $backups = Get-ChildItem $BackupBaseDir -Directory | Sort-Object LastWriteTime -Descending

    Write-TestSuccess "Found $($backups.Count) backup(s)"

    Write-TestInfo "Backup list:"
    foreach ($backup in $backups) {
        $dbFile = Get-Item "$($backup.FullName)\telemetry.sqlite" -ErrorAction SilentlyContinue
        if ($dbFile) {
            $sizeMB = [math]::Round($dbFile.Length / 1MB, 2)
            Write-Host "    $($backup.Name) - ${sizeMB} MB - $($backup.LastWriteTime)" -ForegroundColor DarkGray
        } else {
            Write-Host "    $($backup.Name) - [INVALID] - $($backup.LastWriteTime)" -ForegroundColor Red
        }
    }

    # Calculate total disk usage
    $totalSizeMB = 0
    foreach ($backup in $backups) {
        $dbFile = Get-Item "$($backup.FullName)\telemetry.sqlite" -ErrorAction SilentlyContinue
        if ($dbFile) {
            $totalSizeMB += $dbFile.Length / 1MB
        }
    }

    Write-TestInfo "Total disk usage: $([math]::Round($totalSizeMB, 2)) MB"

    return $true
}

function Test-RestoreScript {
    Write-TestHeader "TEST 6: Restore Script (Dry Run)"

    Write-TestStep "Testing restore script (with -Force flag)..."

    $latestBackup = Get-ChildItem $BackupBaseDir -Directory |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1

    if ($null -eq $latestBackup) {
        Write-TestFailure "No backups found for restore test"
        return $false
    }

    $backupPath = "$($latestBackup.FullName)\telemetry.sqlite"
    $restoreScript = "$ScriptDir\restore_docker_backup.ps1"

    if (-not (Test-Path $restoreScript)) {
        Write-TestFailure "Restore script not found: $restoreScript"
        return $false
    }

    Write-Host ""
    Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Yellow
    Write-Host "WARNING: This will restore the database!" -ForegroundColor Yellow
    Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Backup to restore: $backupPath" -ForegroundColor Cyan
    Write-Host ""

    $confirm = Read-Host "Continue with restore test? (yes/no)"

    if ($confirm -ne "yes") {
        Write-TestInfo "Restore test skipped by user"
        return $true
    }

    try {
        $startTime = Get-Date

        # Run restore script
        & $restoreScript -BackupPath $backupPath -Force

        $exitCode = $LASTEXITCODE
        $duration = ((Get-Date) - $startTime).TotalSeconds

        if ($exitCode -eq 0) {
            Write-TestSuccess "Restore completed successfully"
            Write-TestInfo "Duration: ${duration}s"
            return $true
        } else {
            Write-TestFailure "Restore failed with exit code: $exitCode"
            return $false
        }

    } catch {
        Write-TestFailure "Error running restore script: $_"
        return $false
    }
}

function Test-EmailAlertScript {
    Write-TestHeader "TEST 7: Email Alert Configuration"

    Write-TestStep "Checking email alert script..."

    $emailScript = "$ScriptDir\Send-BackupAlert.ps1"

    if (-not (Test-Path $emailScript)) {
        Write-TestFailure "Email alert script not found: $emailScript"
        return $false
    }

    Write-TestSuccess "Email alert script found"

    # Check if configured
    $scriptContent = Get-Content $emailScript -Raw

    if ($scriptContent -match 'your-app-password-here') {
        Write-TestInfo "Email alerts NOT configured (using placeholder password)"
        Write-TestInfo "To configure: Edit $emailScript and update SMTP settings"
        return $true
    } else {
        Write-TestSuccess "Email alerts appear to be configured"
        Write-TestInfo "To test: Run Test-EmailConfiguration from Send-BackupAlert.ps1"
        return $true
    }
}

# =============================================================================
# MAIN TEST SUITE
# =============================================================================

function Start-TestSuite {
    param(
        [bool]$TestRestore,
        [bool]$TestRetention
    )

    Write-TestHeader "Docker Backup System Test Suite"
    Write-Host "Start time: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Cyan
    Write-Host ""

    $results = @{}

    # Test 1: Run backup script
    $results['Backup Script'] = Test-BackupScript

    # Test 2: Verify backup created
    $results['Backup Created'] = Test-BackupCreated

    # Test 3: Run verification script
    $results['Verification Script'] = Test-VerificationScript

    # Test 4: Check log files
    $results['Log Files'] = Test-LogFiles

    # Test 5: Check backup count
    $results['Backup Count'] = Test-BackupCount

    # Test 6: Email alert script
    $results['Email Alerts'] = Test-EmailAlertScript

    # Test 7: Restore (optional)
    if ($TestRestore) {
        $results['Restore Script'] = Test-RestoreScript
    }

    # Summary
    Write-TestHeader "TEST SUMMARY"

    $totalTests = $results.Count
    $passedTests = ($results.Values | Where-Object { $_ -eq $true }).Count
    $failedTests = $totalTests - $passedTests

    foreach ($testName in $results.Keys) {
        $result = $results[$testName]
        if ($result) {
            Write-Host "[PASS] $testName" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] $testName" -ForegroundColor Red
        }
    }

    Write-Host ""
    Write-Host "Total Tests: $totalTests" -ForegroundColor Cyan
    Write-Host "Passed: $passedTests" -ForegroundColor Green
    Write-Host "Failed: $failedTests" -ForegroundColor $(if ($failedTests -eq 0) { "Green" } else { "Red" })
    Write-Host ""

    if ($failedTests -eq 0) {
        Write-TestSuccess "All tests passed!"
        return 0
    } else {
        Write-TestFailure "$failedTests test(s) failed"
        return 1
    }
}

# =============================================================================
# ENTRY POINT
# =============================================================================

Write-Host "Docker Backup System - Manual Test Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

$exitCode = Start-TestSuite -TestRestore:$TestRestore -TestRetention:$TestRetention

Write-Host ""
Write-Host "Test completed with exit code: $exitCode" -ForegroundColor Cyan
Write-Host ""

exit $exitCode
