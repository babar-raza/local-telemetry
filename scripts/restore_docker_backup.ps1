# restore_docker_backup.ps1
# Restore telemetry database from Docker backup
#
# Purpose:
#   - Disaster recovery from verified backup
#   - Safety backup before restore
#   - Container health verification
#   - Integrity validation
#
# Usage:
#   .\restore_docker_backup.ps1 -BackupPath "D:\agent-metrics\docker-backups\20260102_150000\telemetry.sqlite"
#   .\restore_docker_backup.ps1 -BackupPath "D:\agent-metrics\docker-backups\20260102_150000\telemetry.sqlite" -Force
#
# Parameters:
#   -BackupPath: Path to backup SQLite file to restore
#   -Force: Skip confirmation prompt
#
# Exit Codes:
#   0 = Success
#   1 = Failure
#   2 = User cancelled

# =============================================================================
# PARAMETERS
# =============================================================================

param(
    [Parameter(Mandatory=$true, HelpMessage="Path to backup SQLite file to restore")]
    [string]$BackupPath,

    [Parameter(Mandatory=$false, HelpMessage="Skip confirmation prompt")]
    [switch]$Force
)

$ErrorActionPreference = "Stop"

# =============================================================================
# CONFIGURATION
# =============================================================================

# Paths
$ProjectDir = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"
$SafetyBackupBaseDir = "D:\agent-metrics\docker-backups\safety_backups"
$LogDir = "D:\agent-metrics\logs"

# Docker
$ContainerName = "local-telemetry-api"
$DockerComposeFile = "$ProjectDir\docker-compose.yml"

# Health check settings
$HealthCheckUrl = "http://localhost:8765/health"
$MaxHealthCheckAttempts = 15
$HealthCheckDelaySeconds = 2

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================

# Initialize log file
$LogDate = Get-Date -Format "yyyyMMdd"
$LogFile = "$LogDir\docker_restore_$LogDate.log"

function Write-Log {
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
        "INFO"     { Write-Host $LogEntry -ForegroundColor Cyan }
        default    { Write-Host $LogEntry }
    }
}

# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

function Test-BackupExists {
    param([string]$Path)

    Write-Log "Checking if backup file exists..."

    if (-not (Test-Path $Path)) {
        Write-Log "Backup file not found: $Path" "ERROR"
        return $false
    }

    $backupFile = Get-Item $Path
    $sizeMB = [math]::Round($backupFile.Length / 1MB, 2)

    Write-Log "Backup file found: ${sizeMB}MB" "SUCCESS"
    return $true
}

function Test-BackupIntegrity {
    param([string]$Path)

    Write-Log "Verifying backup integrity..."

    try {
        $pythonScript = "$ProjectDir\scripts\verify_backup_integrity.py"
        $output = python $pythonScript --backup-path $Path 2>&1

        if ($LASTEXITCODE -eq 0) {
            Write-Log "Backup verified successfully" "SUCCESS"
            Write-Log "  $output"
            return $true
        } else {
            Write-Log "Backup verification failed" "ERROR"
            Write-Log "  $output" "ERROR"
            return $false
        }
    } catch {
        Write-Log "Error running verification script: $_" "ERROR"
        return $false
    }
}

function Test-DockerRunning {
    Write-Log "Checking if Docker is running..."

    try {
        $dockerVersion = docker --version 2>&1
        if ($LASTEXITCODE -ne 0) {
            throw "Docker command failed"
        }
        Write-Log "Docker is running: $dockerVersion" "SUCCESS"
        return $true
    } catch {
        Write-Log "Docker is not running or not installed" "ERROR"
        return $false
    }
}

function Test-ContainerExists {
    Write-Log "Checking if container exists: $ContainerName..."

    try {
        $containerExists = docker ps -a --filter "name=$ContainerName" --format "{{.Names}}" 2>&1
        if ($containerExists -ne $ContainerName) {
            Write-Log "Container does not exist: $ContainerName" "ERROR"
            return $false
        }

        Write-Log "Container exists" "SUCCESS"
        return $true
    } catch {
        Write-Log "Error checking container: $_" "ERROR"
        return $false
    }
}

# =============================================================================
# RESTORE FUNCTIONS
# =============================================================================

function New-SafetyBackup {
    Write-Log "Creating safety backup of current database..."

    try {
        # Create safety backup directory with timestamp
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $safetyBackupDir = "$SafetyBackupBaseDir\pre_restore_$timestamp"

        if (-not (Test-Path $safetyBackupDir)) {
            New-Item -ItemType Directory -Path $safetyBackupDir -Force | Out-Null
        }

        # Check if container is running
        $containerRunning = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>&1

        if ($containerRunning -eq $ContainerName) {
            # Container is running - use docker cp
            Write-Log "Copying current database from running container..."
            docker cp "${ContainerName}:/data/telemetry.sqlite" "$safetyBackupDir\telemetry.sqlite" 2>&1

            if ($LASTEXITCODE -ne 0) {
                throw "Failed to copy database from container"
            }

            # Also copy WAL and SHM files if they exist
            docker cp "${ContainerName}:/data/telemetry.sqlite-wal" "$safetyBackupDir\telemetry.sqlite-wal" 2>$null
            docker cp "${ContainerName}:/data/telemetry.sqlite-shm" "$safetyBackupDir\telemetry.sqlite-shm" 2>$null
        } else {
            Write-Log "Container is not running, cannot create safety backup" "WARNING"
            Write-Log "Proceeding without safety backup..." "WARNING"
            return $safetyBackupDir
        }

        $backupFile = Get-Item "$safetyBackupDir\telemetry.sqlite"
        $sizeMB = [math]::Round($backupFile.Length / 1MB, 2)

        Write-Log "Safety backup created: ${sizeMB}MB" "SUCCESS"
        Write-Log "Location: $safetyBackupDir"

        return $safetyBackupDir

    } catch {
        Write-Log "Failed to create safety backup: $_" "ERROR"
        throw
    }
}

function Stop-TelemetryContainer {
    Write-Log "Stopping telemetry container..."

    try {
        # Check if container is running
        $containerRunning = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>&1

        if ($containerRunning -eq $ContainerName) {
            docker compose -f $DockerComposeFile stop 2>&1

            if ($LASTEXITCODE -ne 0) {
                throw "Failed to stop container"
            }

            Write-Log "Container stopped" "SUCCESS"
        } else {
            Write-Log "Container is not running, skipping stop" "INFO"
        }

        return $true
    } catch {
        Write-Log "Error stopping container: $_" "ERROR"
        return $false
    }
}

function Invoke-DatabaseRestore {
    param([string]$BackupPath)

    Write-Log "Restoring database from backup..."

    try {
        # Copy backup to container
        docker cp $BackupPath "${ContainerName}:/data/telemetry.sqlite" 2>&1

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to copy backup to container"
        }

        # Remove WAL and SHM files (force clean state)
        docker exec $ContainerName rm -f /data/telemetry.sqlite-wal 2>$null
        docker exec $ContainerName rm -f /data/telemetry.sqlite-shm 2>$null

        Write-Log "Database restored from backup" "SUCCESS"
        return $true

    } catch {
        Write-Log "Database restore failed: $_" "ERROR"
        return $false
    }
}

function Start-TelemetryContainer {
    Write-Log "Starting telemetry container..."

    try {
        docker compose -f $DockerComposeFile start 2>&1

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start container"
        }

        Write-Log "Container started" "SUCCESS"
        return $true
    } catch {
        Write-Log "Error starting container: $_" "ERROR"
        return $false
    }
}

function Test-ContainerHealth {
    Write-Log "Waiting for container to become healthy..."

    for ($attempt = 1; $attempt -le $MaxHealthCheckAttempts; $attempt++) {
        Start-Sleep -Seconds $HealthCheckDelaySeconds

        # Check Docker health status
        $health = docker inspect $ContainerName --format='{{.State.Health.Status}}' 2>$null

        if ($health -eq "healthy") {
            Write-Log "Container is healthy (Docker health check)" "SUCCESS"
            return $true
        } elseif ($health -eq "starting") {
            Write-Log "[$attempt/$MaxHealthCheckAttempts] Container is starting..." "INFO"
            continue
        } elseif ($null -eq $health) {
            # No healthcheck configured, check if running
            $running = docker inspect $ContainerName --format='{{.State.Running}}' 2>$null
            if ($running -eq "true") {
                Write-Log "Container is running (no health check configured)" "SUCCESS"
                return $true
            }
        }

        Write-Log "[$attempt/$MaxHealthCheckAttempts] Waiting for health check..." "INFO"
    }

    Write-Log "Container health check timed out" "WARNING"
    return $false
}

function Test-HealthEndpoint {
    Write-Log "Testing health endpoint..."

    try {
        $response = Invoke-RestMethod -Uri $HealthCheckUrl -TimeoutSec 10

        Write-Log "Health endpoint is responsive" "SUCCESS"
        Write-Log "  Database: $($response.db_path)"
        Write-Log "  Status: $($response.status)"

        if ($response.status -eq "ok") {
            return $true
        } else {
            Write-Log "Health endpoint returned non-OK status" "WARNING"
            return $false
        }

    } catch {
        Write-Log "Health endpoint test failed: $_" "ERROR"
        return $false
    }
}

function Test-RestoredDatabase {
    param([string]$SafetyBackupDir)

    Write-Log "Verifying restored database..."

    try {
        # Copy database from container for verification
        $tempVerifyPath = "$env:TEMP\telemetry_verify_$(Get-Date -Format 'yyyyMMddHHmmss').sqlite"
        docker cp "${ContainerName}:/data/telemetry.sqlite" $tempVerifyPath 2>&1

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to copy database for verification"
        }

        # Verify integrity
        $pythonScript = "$ProjectDir\scripts\verify_backup_integrity.py"
        $output = python $pythonScript --backup-path $tempVerifyPath 2>&1

        # Cleanup temp file
        Remove-Item $tempVerifyPath -Force

        if ($LASTEXITCODE -eq 0) {
            Write-Log "Restored database verified successfully" "SUCCESS"
            Write-Log "  $output"
            return $true
        } else {
            Write-Log "Restored database verification failed" "ERROR"
            Write-Log "  $output" "ERROR"

            # Offer to rollback
            Write-Host ""
            Write-Host "VERIFICATION FAILED! The restored database may be corrupted." -ForegroundColor Red
            Write-Host "Safety backup is available at: $SafetyBackupDir" -ForegroundColor Yellow
            Write-Host ""
            $rollback = Read-Host "Do you want to rollback to the safety backup? (yes/no)"

            if ($rollback -eq "yes") {
                Write-Log "Rolling back to safety backup..." "WARNING"
                Stop-TelemetryContainer
                Invoke-DatabaseRestore -BackupPath "$SafetyBackupDir\telemetry.sqlite"
                Start-TelemetryContainer
                Test-ContainerHealth
                Write-Log "Rollback completed" "SUCCESS"
            }

            return $false
        }

    } catch {
        Write-Log "Error verifying restored database: $_" "ERROR"
        return $false
    }
}

# =============================================================================
# MAIN RESTORE PROCESS
# =============================================================================

function Start-RestoreProcess {
    param(
        [string]$BackupPath,
        [bool]$Force
    )

    $startTime = Get-Date

    Write-Log "============================================================"
    Write-Log "DOCKER TELEMETRY DATABASE RESTORE STARTED"
    Write-Log "============================================================"
    Write-Log "Backup: $BackupPath"
    Write-Log "Container: $ContainerName"
    Write-Log ""

    try {
        # Step 1: Pre-flight checks
        Write-Log "=== PRE-FLIGHT CHECKS ===" "INFO"

        if (-not (Test-BackupExists -Path $BackupPath)) {
            throw "Backup file not found"
        }

        if (-not (Test-BackupIntegrity -Path $BackupPath)) {
            throw "Backup integrity check failed"
        }

        if (-not (Test-DockerRunning)) {
            throw "Docker is not running"
        }

        if (-not (Test-ContainerExists)) {
            throw "Container does not exist"
        }

        Write-Log "All pre-flight checks passed" "SUCCESS"
        Write-Log ""

        # Step 2: Confirmation
        if (-not $Force) {
            Write-Log "=== CONFIRMATION ===" "WARNING"
            Write-Host ""
            Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Yellow
            Write-Host "WARNING: This will replace the current Docker database!" -ForegroundColor Yellow
            Write-Host "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!" -ForegroundColor Yellow
            Write-Host ""
            Write-Host "Container: $ContainerName" -ForegroundColor Cyan
            Write-Host "Backup: $BackupPath" -ForegroundColor Cyan
            Write-Host ""
            Write-Host "A safety backup will be created before the restore." -ForegroundColor Green
            Write-Host ""

            $confirm = Read-Host "Continue with restore? (yes/no)"

            if ($confirm -ne "yes") {
                Write-Log "Restore cancelled by user" "WARNING"
                return 2  # User cancelled
            }

            Write-Log "User confirmed restore" "INFO"
            Write-Log ""
        }

        # Step 3: Create safety backup
        Write-Log "=== SAFETY BACKUP ===" "INFO"
        $safetyBackupDir = New-SafetyBackup
        Write-Log ""

        # Step 4: Stop container
        Write-Log "=== STOPPING CONTAINER ===" "INFO"
        if (-not (Stop-TelemetryContainer)) {
            throw "Failed to stop container"
        }
        Write-Log ""

        # Step 5: Restore database
        Write-Log "=== RESTORING DATABASE ===" "INFO"
        if (-not (Invoke-DatabaseRestore -BackupPath $BackupPath)) {
            throw "Database restore failed"
        }
        Write-Log ""

        # Step 6: Start container
        Write-Log "=== STARTING CONTAINER ===" "INFO"
        if (-not (Start-TelemetryContainer)) {
            throw "Failed to start container"
        }
        Write-Log ""

        # Step 7: Wait for health
        Write-Log "=== HEALTH CHECKS ===" "INFO"
        if (-not (Test-ContainerHealth)) {
            Write-Log "Container health check failed, but continuing..." "WARNING"
        }

        if (-not (Test-HealthEndpoint)) {
            Write-Log "Health endpoint test failed, but continuing..." "WARNING"
        }
        Write-Log ""

        # Step 8: Verify restored database
        Write-Log "=== VERIFICATION ===" "INFO"
        if (-not (Test-RestoredDatabase -SafetyBackupDir $safetyBackupDir)) {
            throw "Restored database verification failed"
        }
        Write-Log ""

        # Step 9: Success summary
        $duration = ((Get-Date) - $startTime).TotalSeconds

        Write-Log "============================================================"
        Write-Log "RESTORE COMPLETED SUCCESSFULLY" "SUCCESS"
        Write-Log "============================================================"
        Write-Log "Restored from: $BackupPath"
        Write-Log "Safety backup: $safetyBackupDir"
        Write-Log "Duration: ${duration}s"
        Write-Log "Status: SUCCESS"
        Write-Log "============================================================"

        return 0  # Success

    } catch {
        $errorMessage = $_.Exception.Message
        Write-Log "============================================================"
        Write-Log "RESTORE FAILED" "ERROR"
        Write-Log "============================================================"
        Write-Log "Error: $errorMessage" "ERROR"
        Write-Log "============================================================"

        # Attempt to restart container if it's stopped
        try {
            $containerRunning = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>&1
            if ($containerRunning -ne $ContainerName) {
                Write-Log "Attempting to restart container..." "WARNING"
                Start-TelemetryContainer
            }
        } catch {
            Write-Log "Failed to restart container: $_" "ERROR"
        }

        return 1  # Failure
    }
}

# =============================================================================
# ENTRY POINT
# =============================================================================

# Run restore
$exitCode = Start-RestoreProcess -BackupPath $BackupPath -Force:$Force

# Exit with appropriate code
exit $exitCode
