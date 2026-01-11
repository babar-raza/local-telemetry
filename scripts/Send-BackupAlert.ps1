# Send-BackupAlert.ps1
# Reusable function for sending email notifications from backup scripts
#
# Usage:
#   . "$PSScriptRoot\Send-BackupAlert.ps1"
#   Send-BackupAlert -Subject "Backup Failed" -Body $ErrorMessage -Severity "CRITICAL"

# =============================================================================
# SMTP CONFIGURATION - UPDATE THESE VALUES BEFORE FIRST USE
# =============================================================================

# SMTP Server Settings
$script:SmtpServer = "smtp.gmail.com"          # Gmail
# $script:SmtpServer = "smtp.office365.com"    # Outlook/Office 365
# $script:SmtpServer = "smtp.mail.yahoo.com"   # Yahoo

$script:SmtpPort = 587  # Standard TLS port

# Email Addresses
$script:From = "telemetry-backup@example.com"   # Sender email
$script:To = "admin@example.com"                # Recipient email

# Authentication
# For Gmail: Use App Password from https://myaccount.google.com/apppasswords
# For Outlook: Use regular password or App Password
$script:Username = $script:From                 # Usually same as From address
$script:PasswordPlainText = "your-app-password-here"  # UPDATE THIS!

# Convert password to secure string
$script:SecurePassword = ConvertTo-SecureString $script:PasswordPlainText -AsPlainText -Force
$script:Credential = New-Object System.Management.Automation.PSCredential($script:Username, $script:SecurePassword)

# =============================================================================
# EMAIL FUNCTION
# =============================================================================

function Send-BackupAlert {
    <#
    .SYNOPSIS
        Send email alert for backup events

    .DESCRIPTION
        Sends formatted email notifications for backup success/failure events.
        Falls back to file logging if email fails.

    .PARAMETER Subject
        Brief subject line for the alert

    .PARAMETER Body
        Detailed message body

    .PARAMETER Severity
        Alert severity level: INFO, WARNING, ERROR, CRITICAL

    .EXAMPLE
        Send-BackupAlert -Subject "Backup Failed" -Body "Database not accessible" -Severity "CRITICAL"

    .EXAMPLE
        Send-BackupAlert -Subject "Backup Completed" -Body "Backup size: 68 MB" -Severity "INFO"
    #>

    param(
        [Parameter(Mandatory=$true)]
        [string]$Subject,

        [Parameter(Mandatory=$true)]
        [string]$Body,

        [Parameter(Mandatory=$false)]
        [ValidateSet("INFO", "WARNING", "ERROR", "CRITICAL")]
        [string]$Severity = "ERROR"
    )

    # Check if email is configured
    if ($script:PasswordPlainText -eq "your-app-password-here") {
        Write-Warning "Email not configured. Update Send-BackupAlert.ps1 with SMTP credentials."
        Write-Warning "Alert not sent: [$Severity] $Subject"

        # Log to fallback file
        $LogFile = "D:\agent-metrics\logs\email_alert_failures.log"
        $LogDir = Split-Path $LogFile -Parent
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }

        $LogEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [$Severity] $Subject - $Body"
        Add-Content -Path $LogFile -Value $LogEntry

        return $false
    }

    # Build email subject with severity tag
    $EmailSubject = "[$Severity] Telemetry Backup - $Subject"

    # Build formatted email body
    $EmailBody = @"
Telemetry Database Backup Alert

Severity:     $Severity
Time:         $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Host:         $env:COMPUTERNAME
User:         $env:USERNAME

Message:
$Body

---
Automated alert from TelemetryDockerDailyBackup task
Container: local-telemetry-api
Database:  /data/telemetry.sqlite
"@

    try {
        # Send email
        Send-MailMessage `
            -From $script:From `
            -To $script:To `
            -Subject $EmailSubject `
            -Body $EmailBody `
            -SmtpServer $script:SmtpServer `
            -Port $script:SmtpPort `
            -UseSsl `
            -Credential $script:Credential `
            -ErrorAction Stop

        Write-Host "[OK] Alert email sent to $($script:To)" -ForegroundColor Green
        return $true

    } catch {
        Write-Warning "Failed to send email alert: $_"

        # Log to fallback file
        $LogFile = "D:\agent-metrics\logs\email_alert_failures.log"
        $LogDir = Split-Path $LogFile -Parent
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
        }

        $LogEntry = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [SEND_FAILED] [$Severity] $Subject - $Body - Error: $_"
        Add-Content -Path $LogFile -Value $LogEntry

        return $false
    }
}

# =============================================================================
# SMTP CONFIGURATION TEST
# =============================================================================

function Test-EmailConfiguration {
    <#
    .SYNOPSIS
        Test email configuration by sending a test message

    .DESCRIPTION
        Sends a test email to verify SMTP settings are correct.
        Use this after configuring the script.

    .EXAMPLE
        Test-EmailConfiguration
    #>

    Write-Host "Testing email configuration..." -ForegroundColor Cyan
    Write-Host "SMTP Server: $script:SmtpServer"
    Write-Host "SMTP Port: $script:SmtpPort"
    Write-Host "From: $script:From"
    Write-Host "To: $script:To"
    Write-Host ""

    if ($script:PasswordPlainText -eq "your-app-password-here") {
        Write-Host "[FAIL] Email not configured. Update SMTP settings first." -ForegroundColor Red
        return $false
    }

    $result = Send-BackupAlert `
        -Subject "Test Email Configuration" `
        -Body "This is a test email to verify SMTP configuration for Docker telemetry backup alerts." `
        -Severity "INFO"

    if ($result) {
        Write-Host "[OK] Test email sent successfully!" -ForegroundColor Green
        Write-Host "Check inbox at: $($script:To)" -ForegroundColor Green
        return $true
    } else {
        Write-Host "[FAIL] Test email failed. Check configuration." -ForegroundColor Red
        return $false
    }
}

# =============================================================================
# CONFIGURATION GUIDE
# =============================================================================

<#
.NOTES
    CONFIGURATION INSTRUCTIONS:

    1. Choose your email provider and update $SmtpServer:
       - Gmail:        smtp.gmail.com
       - Outlook:      smtp.office365.com
       - Yahoo:        smtp.mail.yahoo.com
       - Other:        Contact your email provider

    2. Update email addresses:
       - $From: The sender email address (your email)
       - $To: The recipient email address (admin email)

    3. Get an App Password:
       Gmail:
         a. Go to https://myaccount.google.com/apppasswords
         b. Create app password for "Windows Computer"
         c. Copy the 16-character password

       Outlook:
         a. Go to https://account.microsoft.com/security
         b. Enable 2-factor authentication if not already
         c. Create app password

    4. Update $PasswordPlainText with your app password

    5. Test the configuration:
       PS> . .\Send-BackupAlert.ps1
       PS> Test-EmailConfiguration

    6. For security, consider using Windows Credential Manager:
       - Store password securely
       - Retrieve in script using Get-Credential

    SECURITY NOTE:
    - Never commit this file with real passwords to git
    - Consider using encrypted credential storage
    - Keep App Passwords separate from main account passwords
#>
