# Telemetry API Service Startup Script (Windows PowerShell)
#
# Usage:
#   .\scripts\start_telemetry_api.ps1
#   .\scripts\start_telemetry_api.ps1 -Port 8765
#   .\scripts\start_telemetry_api.ps1 -Help

param(
    [int]$Port = 8765,
    [string]$Host = "0.0.0.0",
    [string]$LogLevel = "info",
    [switch]$Help
)

# Show help
if ($Help) {
    Write-Host "Telemetry API Service Startup Script"
    Write-Host ""
    Write-Host "Usage: .\scripts\start_telemetry_api.ps1 [options]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Port <PORT>         API port (default: 8765)"
    Write-Host "  -Host <HOST>         API host (default: 0.0.0.0)"
    Write-Host "  -LogLevel <LEVEL>    Log level (default: info)"
    Write-Host "  -Help                Show this help message"
    Write-Host ""
    Write-Host "Environment Variables:"
    Write-Host "  TELEMETRY_DB_PATH              Database path (default: D:/agent-metrics/db/telemetry.sqlite)"
    Write-Host "  TELEMETRY_DB_JOURNAL_MODE      Journal mode (default: DELETE)"
    Write-Host "  TELEMETRY_DB_SYNCHRONOUS       Synchronous mode (default: FULL)"
    Write-Host "  TELEMETRY_API_WORKERS          Worker count (must be 1)"
    exit 0
}

# Check for environment variable overrides
if ($env:TELEMETRY_API_PORT) {
    $Port = [int]$env:TELEMETRY_API_PORT
}
if ($env:TELEMETRY_API_HOST) {
    $Host = $env:TELEMETRY_API_HOST
}
if ($env:TELEMETRY_LOG_LEVEL) {
    $LogLevel = $env:TELEMETRY_LOG_LEVEL
}

# Get script location
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Write-Host "========================================================================"
Write-Host "TELEMETRY API SERVICE STARTUP"
Write-Host "========================================================================"
Write-Host "Project root: $ProjectRoot"
Write-Host "API host: $Host"
Write-Host "API port: $Port"
Write-Host "Log level: $LogLevel"
Write-Host ""

# Check Python
$PythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        $PythonCmd = $cmd
        break
    }
}

if (-not $PythonCmd) {
    Write-Host "[ERROR] Python not found. Please install Python 3.7+" -ForegroundColor Red
    exit 1
}

$PythonVersion = & $PythonCmd --version 2>&1
Write-Host "[OK] $PythonVersion" -ForegroundColor Green

# Check virtual environment
$VenvPath = Join-Path $ProjectRoot "venv"
if (Test-Path $VenvPath) {
    Write-Host "[OK] Virtual environment found" -ForegroundColor Green
    $VenvActivate = Join-Path $VenvPath "Scripts\Activate.ps1"
    if (Test-Path $VenvActivate) {
        & $VenvActivate
    }
} else {
    Write-Host "[WARN] No virtual environment found. Using system Python." -ForegroundColor Yellow
}

# Check FastAPI
try {
    & $PythonCmd -c "import fastapi" 2>$null
    Write-Host "[OK] FastAPI installed" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] FastAPI not installed" -ForegroundColor Red
    Write-Host "Install dependencies with: pip install -r requirements.txt"
    exit 1
}

# Check telemetry_service.py
$ServiceFile = Join-Path $ProjectRoot "telemetry_service.py"
if (-not (Test-Path $ServiceFile)) {
    Write-Host "[ERROR] telemetry_service.py not found" -ForegroundColor Red
    exit 1
}

Write-Host "[OK] telemetry_service.py found" -ForegroundColor Green

# Set PYTHONPATH
$SrcPath = Join-Path $ProjectRoot "src"
$env:PYTHONPATH = "$SrcPath;$env:PYTHONPATH"

# Start service
Write-Host ""
Write-Host "========================================================================"
Write-Host "STARTING TELEMETRY API SERVICE"
Write-Host "========================================================================"
Write-Host "Endpoint: http://$Host`:$Port"
Write-Host "Health check: http://$Host`:$Port/health"
Write-Host "Metrics: http://$Host`:$Port/metrics"
Write-Host ""
Write-Host "Press Ctrl+C to stop"
Write-Host "========================================================================"
Write-Host ""

# Change to project root
Set-Location $ProjectRoot

# Start uvicorn
& $PythonCmd -m uvicorn telemetry_service:app `
    --host $Host `
    --port $Port `
    --workers 1 `
    --log-level $LogLevel
