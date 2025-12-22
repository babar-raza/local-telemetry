# Quick Docker Deployment Script for Windows
# Usage: .\docker-deploy.ps1

param(
    [switch]$Stop,
    [switch]$Restart,
    [switch]$Logs,
    [switch]$Status,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "TELEMETRY API - DOCKER DEPLOYMENT" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# Check Docker is installed
try {
    $dockerVersion = docker --version
    Write-Host "[OK] $dockerVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker not found. Please install Docker Desktop." -ForegroundColor Red
    Write-Host "Download: https://www.docker.com/products/docker-desktop" -ForegroundColor Yellow
    exit 1
}

# Check Docker Compose
try {
    $composeVersion = docker compose version
    Write-Host "[OK] $composeVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker Compose not found." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Handle commands
if ($Stop) {
    Write-Host "Stopping telemetry API service..." -ForegroundColor Yellow
    docker compose stop
    Write-Host "[OK] Service stopped" -ForegroundColor Green
    exit 0
}

if ($Restart) {
    Write-Host "Restarting telemetry API service..." -ForegroundColor Yellow
    docker compose restart
    Write-Host "[OK] Service restarted" -ForegroundColor Green
    Start-Sleep -Seconds 3
    docker compose ps
    exit 0
}

if ($Logs) {
    Write-Host "Showing service logs (Ctrl+C to exit)..." -ForegroundColor Yellow
    docker compose logs -f
    exit 0
}

if ($Status) {
    Write-Host "Service Status:" -ForegroundColor Yellow
    docker compose ps
    Write-Host ""
    Write-Host "Health Check:" -ForegroundColor Yellow
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8765/health" -TimeoutSec 5
        Write-Host ($response | ConvertTo-Json) -ForegroundColor Green
    } catch {
        Write-Host "[ERROR] Service not responding" -ForegroundColor Red
    }
    exit 0
}

# Default: Start service
Write-Host "Starting telemetry API service..." -ForegroundColor Yellow
Write-Host ""

if ($Rebuild) {
    Write-Host "[INFO] Rebuilding Docker image..." -ForegroundColor Yellow
    docker compose build --no-cache
}

# Check if container already running
$running = docker compose ps -q

if ($running) {
    Write-Host "[INFO] Container already running. Stopping first..." -ForegroundColor Yellow
    docker compose down
}

# Start service
Write-Host "[INFO] Starting container in detached mode..." -ForegroundColor Yellow
docker compose up -d

# Wait for health check
Write-Host ""
Write-Host "Waiting for service to be healthy..." -ForegroundColor Yellow

$maxAttempts = 15
$attempt = 0
$healthy = $false

while ($attempt -lt $maxAttempts -and -not $healthy) {
    Start-Sleep -Seconds 2
    $attempt++

    try {
        $health = docker inspect telemetry-api --format='{{.State.Health.Status}}' 2>$null

        if ($health -eq "healthy") {
            $healthy = $true
            Write-Host "[OK] Service is healthy!" -ForegroundColor Green
        } elseif ($health -eq "starting") {
            Write-Host "  [$attempt/$maxAttempts] Status: starting..." -ForegroundColor Yellow
        } else {
            Write-Host "  [$attempt/$maxAttempts] Status: $health" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  [$attempt/$maxAttempts] Waiting for container..." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "DEPLOYMENT STATUS" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan

# Show container status
docker compose ps

Write-Host ""

# Test health endpoint
try {
    $response = Invoke-RestMethod -Uri "http://localhost:8765/health" -TimeoutSec 5
    Write-Host "[OK] Health Check Passed" -ForegroundColor Green
    Write-Host ""
    Write-Host "Service Details:" -ForegroundColor Cyan
    Write-Host "  Version: $($response.version)"
    Write-Host "  Database: $($response.db_path)"
    Write-Host "  Journal Mode: $($response.journal_mode)"
    Write-Host "  Synchronous: $($response.synchronous)"
} catch {
    Write-Host "[WARN] Health check failed. Check logs:" -ForegroundColor Yellow
    Write-Host "  docker compose logs" -ForegroundColor Gray
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "[SUCCESS] Telemetry API is running!" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Endpoints:" -ForegroundColor Cyan
Write-Host "  Health:  http://localhost:8765/health"
Write-Host "  Metrics: http://localhost:8765/metrics"
Write-Host "  API:     http://localhost:8765/api/v1/runs"
Write-Host ""
Write-Host "Useful Commands:" -ForegroundColor Cyan
Write-Host "  View logs:       .\docker-deploy.ps1 -Logs"
Write-Host "  Check status:    .\docker-deploy.ps1 -Status"
Write-Host "  Restart:         .\docker-deploy.ps1 -Restart"
Write-Host "  Stop:            .\docker-deploy.ps1 -Stop"
Write-Host "  Rebuild:         .\docker-deploy.ps1 -Rebuild"
Write-Host ""
Write-Host "Docker Commands:" -ForegroundColor Cyan
Write-Host "  docker compose ps              # Container status"
Write-Host "  docker compose logs -f         # Follow logs"
Write-Host "  docker compose restart         # Restart service"
Write-Host "  docker compose down            # Stop and remove"
Write-Host ""
