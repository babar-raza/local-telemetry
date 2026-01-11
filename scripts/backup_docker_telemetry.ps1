# backup_docker_telemetry.ps1
# Automated backup of Docker-based telemetry database
#
# Purpose:
#   - Hot backup of /data/telemetry.sqlite from Docker container to Windows host
#   - Integrity verification
#   - Retention management (14 days)
#   - Email alerts on failure
#   - Comprehensive logging
#
# Usage:
#   .\backup_docker_telemetry.ps1
#
# Scheduled via Windows Task Scheduler (Daily at 3:00 PM)
#
# Exit Codes:
#   0 = Success
#   1 = Failure

# =============================================================================
# CONFIGURATION
# =============================================================================

$ErrorActionPreference = "Stop"

# Paths
$BackupBaseDir = "D:\agent-metrics\docker-backups"
$LogDir = "D:\agent-metrics\logs"
$ProjectDir = "C:\Users\prora\OneDrive\Documents\GitHub\local-telemetry"

# Docker
$ContainerName = "local-telemetry-api"
$DockerComposeFile = "$ProjectDir\docker-compose.yml"

# Retention
$RetentionDays = 14

# Email alerts (configured in Send-BackupAlert.ps1)
$EmailAlertsEnabled = $true

# Disk space check (require at least 5 GB free)
$MinFreeDiskSpaceGB = 5

# Retry settings
$MaxRetries = 3
$RetryDelaySeconds = @(10, 30, 60)  # Exponential backoff

# =============================================================================
# LOGGING FUNCTIONS
# =============================================================================

# Initialize log file
$LogDate = Get-Date -Format "yyyyMMdd"
$LogFile = "$LogDir\docker_backup_$LogDate.log"

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
        default    { Write-Host $LogEntry }
    }
}

# =============================================================================
# PRE-FLIGHT CHECKS
# =============================================================================

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

function Test-ContainerHealthy {
    Write-Log "Checking container health: $ContainerName..."

    try {
        # Check if container exists
        $containerExists = docker ps -a --filter "name=$ContainerName" --format "{{.Names}}" 2>&1
        if ($containerExists -ne $ContainerName) {
            Write-Log "Container does not exist: $ContainerName" "ERROR"
            return $false
        }

        # Check if container is running
        $containerRunning = docker ps --filter "name=$ContainerName" --format "{{.Names}}" 2>&1
        if ($containerRunning -ne $ContainerName) {
            Write-Log "Container is not running: $ContainerName" "ERROR"
            return $false
        }

        # Check health status (if healthcheck is configured)
        $health = docker inspect $ContainerName --format='{{.State.Health.Status}}' 2>$null
        if ($health -eq "healthy") {
            Write-Log "Container is healthy" "SUCCESS"
            return $true
        } elseif ($health -eq "starting") {
            Write-Log "Container is starting, waiting..." "WARNING"
            Start-Sleep -Seconds 30
            return Test-ContainerHealthy  # Recursive retry
        } elseif ($null -eq $health) {
            # No healthcheck configured, check if running
            Write-Log "Container is running (no healthcheck configured)" "SUCCESS"
            return $true
        } else {
            Write-Log "Container health check failed: $health" "ERROR"
            return $false
        }
    } catch {
        Write-Log "Error checking container health: $_" "ERROR"
        return $false
    }
}

function Test-DiskSpace {
    Write-Log "Checking disk space..."

    $Drive = "D:"
    $Disk = Get-PSDrive -Name ($Drive.TrimEnd(':'))
    $FreeSpaceGB = [math]::Round($Disk.Free / 1GB, 2)

    if ($FreeSpaceGB -lt $MinFreeDiskSpaceGB) {
        Write-Log "Insufficient disk space: ${FreeSpaceGB}GB free (need ${MinFreeDiskSpaceGB}GB)" "ERROR"
        return $false
    }

    Write-Log "Disk space OK: ${FreeSpaceGB}GB free" "SUCCESS"
    return $true
}

# =============================================================================
# BACKUP FUNCTIONS
# =============================================================================

function Invoke-BackupWithRetry {
    param(
        [string]$BackupDir,
        [string]$Timestamp
    )

    for ($attempt = 1; $attempt -le $MaxRetries; $attempt++) {
        Write-Log "Backup attempt $attempt of $MaxRetries..."

        try {
            # Step 1: Copy Python helper script to container
            Write-Log "Copying backup helper script to container..."
            docker cp "$ProjectDir\scripts\sqlite_backup_helper.py" "${ContainerName}:/tmp/sqlite_backup_helper.py" 2>&1

            if ($LASTEXITCODE -ne 0) {
                throw "Failed to copy helper script to container"
            }

            # Step 2: Execute hot backup inside container using Python API
            Write-Log "Creating hot backup inside container using Python SQLite backup API..."
            $result = docker exec $ContainerName python /tmp/sqlite_backup_helper.py /data/telemetry.sqlite /data/telemetry_backup_temp.sqlite 2>&1

            if ($LASTEXITCODE -ne 0) {
                throw "SQLite backup command failed: $result"
            }

            Write-Log "Hot backup created inside container" "SUCCESS"
            Write-Log "  $result"

            # Step 3: Copy backup from container to host
            Write-Log "Copying backup from container to host..."
            docker cp "${ContainerName}:/data/telemetry_backup_temp.sqlite" "$BackupDir\telemetry.sqlite" 2>&1

            if ($LASTEXITCODE -ne 0) {
                throw "Docker cp failed"
            }

            $backupFile = Get-Item "$BackupDir\telemetry.sqlite"
            $sizeMB = [math]::Round($backupFile.Length / 1MB, 2)
            Write-Log "Backup copied to host: ${sizeMB}MB" "SUCCESS"

            # Step 4: Cleanup temp files in container (best effort, non-fatal)
            Write-Log "Cleaning up temp files in container..."
            docker exec $ContainerName rm -f /data/telemetry_backup_temp.sqlite 2>$null
            docker exec $ContainerName rm -f /tmp/sqlite_backup_helper.py 2>$null

            if ($LASTEXITCODE -eq 0) {
                Write-Log "Cleanup completed" "SUCCESS"
            } else {
                Write-Log "Cleanup had permission issues (non-fatal)" "WARNING"
            }

            return $true

        } catch {
            Write-Log "Backup attempt $attempt failed: $_" "WARNING"

            if ($attempt -lt $MaxRetries) {
                $delay = $RetryDelaySeconds[$attempt - 1]
                Write-Log "Retrying in $delay seconds..." "WARNING"
                Start-Sleep -Seconds $delay
            } else {
                Write-Log "All backup attempts failed" "ERROR"
                return $false
            }
        }
    }

    return $false
}

function Test-BackupIntegrity {
    param(
        [string]$BackupPath
    )

    Write-Log "Verifying backup integrity..."

    try {
        # Call Python verification script
        $pythonScript = "$ProjectDir\scripts\verify_backup_integrity.py"
        $output = python $pythonScript --backup-path $BackupPath 2>&1

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

function New-BackupMetadata {
    param(
        [string]$BackupDir,
        [string]$Timestamp,
        [bool]$Verified
    )

    Write-Log "Creating backup metadata..."

    $backupFile = Get-Item "$BackupDir\telemetry.sqlite"
    $sizeMB = [math]::Round($backupFile.Length / 1MB, 2)

    $metadata = @{
        timestamp = $Timestamp
        created_at = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        size_mb = $sizeMB
        size_bytes = $backupFile.Length
        verified = $Verified
        docker_container = $ContainerName
        retention_days = $RetentionDays
        backup_method = "docker_exec_sqlite_backup"
    } | ConvertTo-Json -Depth 3

    $metadataFile = "$BackupDir\backup_metadata.json"
    Set-Content -Path $metadataFile -Value $metadata

    Write-Log "Metadata saved: $metadataFile"
}

function Remove-OldBackups {
    Write-Log "Applying retention policy (keep last $RetentionDays days)..."

    if (-not (Test-Path $BackupBaseDir)) {
        Write-Log "Backup directory does not exist yet: $BackupBaseDir"
        return
    }

    $cutoffDate = (Get-Date).AddDays(-$RetentionDays)
    $allBackups = Get-ChildItem -Path $BackupBaseDir -Directory | Sort-Object LastWriteTime -Descending

    $deletedCount = 0
    foreach ($backup in $allBackups) {
        if ($backup.LastWriteTime -lt $cutoffDate) {
            Write-Log "Deleting old backup: $($backup.Name) (modified: $($backup.LastWriteTime))"
            Remove-Item -Path $backup.FullName -Recurse -Force
            $deletedCount++
        }
    }

    if ($deletedCount -eq 0) {
        Write-Log "No old backups to delete" "SUCCESS"
    } else {
        Write-Log "Deleted $deletedCount old backup(s)" "SUCCESS"
    }

    # Show current backup count
    $currentCount = (Get-ChildItem -Path $BackupBaseDir -Directory).Count
    Write-Log "Current backup count: $currentCount (retention: $RetentionDays days)"
}

# =============================================================================
# MAIN BACKUP PROCESS
# =============================================================================

function Start-BackupProcess {
    $startTime = Get-Date

    Write-Log "============================================================"
    Write-Log "DOCKER TELEMETRY DATABASE BACKUP STARTED"
    Write-Log "============================================================"
    Write-Log "Container: $ContainerName"
    Write-Log "Backup destination: $BackupBaseDir"
    Write-Log "Retention: $RetentionDays days"
    Write-Log ""

    try {
        # Step 1: Pre-flight checks
        Write-Log "=== PRE-FLIGHT CHECKS ===" "INFO"

        if (-not (Test-DockerRunning)) {
            throw "Docker is not running"
        }

        if (-not (Test-ContainerHealthy)) {
            throw "Container is not healthy"
        }

        if (-not (Test-DiskSpace)) {
            throw "Insufficient disk space"
        }

        Write-Log "All pre-flight checks passed" "SUCCESS"
        Write-Log ""

        # Step 2: Create timestamped backup directory
        Write-Log "=== CREATING BACKUP DIRECTORY ===" "INFO"

        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupDir = "$BackupBaseDir\$timestamp"

        if (-not (Test-Path $backupDir)) {
            New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
            Write-Log "Created backup directory: $backupDir" "SUCCESS"
        }

        Write-Log ""

        # Step 3: Execute backup
        Write-Log "=== EXECUTING BACKUP ===" "INFO"

        if (-not (Invoke-BackupWithRetry -BackupDir $backupDir -Timestamp $timestamp)) {
            throw "Backup failed after $MaxRetries attempts"
        }

        Write-Log ""

        # Step 4: Verify backup integrity
        Write-Log "=== VERIFYING BACKUP ===" "INFO"

        $backupPath = "$backupDir\telemetry.sqlite"
        if (-not (Test-BackupIntegrity -BackupPath $backupPath)) {
            throw "Backup verification failed"
        }

        Write-Log ""

        # Step 5: Create metadata
        Write-Log "=== CREATING METADATA ===" "INFO"

        New-BackupMetadata -BackupDir $backupDir -Timestamp $timestamp -Verified $true

        Write-Log ""

        # Step 6: Apply retention policy
        Write-Log "=== RETENTION MANAGEMENT ===" "INFO"

        Remove-OldBackups

        Write-Log ""

        # Step 7: Success summary
        $duration = ((Get-Date) - $startTime).TotalSeconds
        $backupFile = Get-Item "$backupDir\telemetry.sqlite"
        $sizeMB = [math]::Round($backupFile.Length / 1MB, 2)

        Write-Log "============================================================"
        Write-Log "BACKUP COMPLETED SUCCESSFULLY" "SUCCESS"
        Write-Log "============================================================"
        Write-Log "Backup: $backupDir"
        Write-Log "Size: ${sizeMB}MB"
        Write-Log "Duration: ${duration}s"
        Write-Log "Status: SUCCESS"
        Write-Log "============================================================"

        # Optional: Send success email (comment out if too noisy)
        # if ($EmailAlertsEnabled) {
        #     . "$PSScriptRoot\Send-BackupAlert.ps1"
        #     Send-BackupAlert -Subject "Backup Completed" -Body "Backup: $backupDir`nSize: ${sizeMB}MB`nDuration: ${duration}s" -Severity "INFO"
        # }

        return 0  # Success

    } catch {
        $errorMessage = $_.Exception.Message
        Write-Log "============================================================"
        Write-Log "BACKUP FAILED" "ERROR"
        Write-Log "============================================================"
        Write-Log "Error: $errorMessage" "ERROR"
        Write-Log "============================================================"

        # Send failure email alert
        if ($EmailAlertsEnabled) {
            try {
                . "$PSScriptRoot\Send-BackupAlert.ps1"
                Send-BackupAlert -Subject "Docker Backup Failed" -Body "Error: $errorMessage`n`nLog: $LogFile" -Severity "CRITICAL"
            } catch {
                Write-Log "Failed to send email alert: $_" "WARNING"
            }
        }

        return 1  # Failure
    }
}

# =============================================================================
# ENTRY POINT
# =============================================================================

# Load email alert function if enabled
if ($EmailAlertsEnabled) {
    if (Test-Path "$PSScriptRoot\Send-BackupAlert.ps1") {
        . "$PSScriptRoot\Send-BackupAlert.ps1"
    } else {
        Write-Log "Send-BackupAlert.ps1 not found, email alerts disabled" "WARNING"
        $EmailAlertsEnabled = $false
    }
}

# Run backup
$exitCode = Start-BackupProcess

# Exit with appropriate code for Task Scheduler
exit $exitCode
