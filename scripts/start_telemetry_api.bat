@echo off
REM Telemetry API Service Startup Script (Windows Batch)
REM
REM Usage:
REM   scripts\start_telemetry_api.bat

setlocal

REM Get script directory and project root
set SCRIPT_DIR=%~dp0
set PROJECT_ROOT=%SCRIPT_DIR%..

REM Default configuration
if not defined TELEMETRY_API_HOST set TELEMETRY_API_HOST=0.0.0.0
if not defined TELEMETRY_API_PORT set TELEMETRY_API_PORT=8765
if not defined TELEMETRY_LOG_LEVEL set TELEMETRY_LOG_LEVEL=info

echo ========================================================================
echo TELEMETRY API SERVICE STARTUP
echo ========================================================================
echo Project root: %PROJECT_ROOT%
echo API host: %TELEMETRY_API_HOST%
echo API port: %TELEMETRY_API_PORT%
echo Log level: %TELEMETRY_LOG_LEVEL%
echo.

REM Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Please install Python 3.7+
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo [OK] %PYTHON_VERSION%

REM Check virtual environment
if exist "%PROJECT_ROOT%\venv\Scripts\activate.bat" (
    echo [OK] Virtual environment found
    call "%PROJECT_ROOT%\venv\Scripts\activate.bat"
) else (
    echo [WARN] No virtual environment found. Using system Python.
)

REM Check FastAPI
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] FastAPI not installed
    echo Install dependencies with: pip install -r requirements.txt
    exit /b 1
)

echo [OK] FastAPI installed

REM Check telemetry_service.py
if not exist "%PROJECT_ROOT%\telemetry_service.py" (
    echo [ERROR] telemetry_service.py not found
    exit /b 1
)

echo [OK] telemetry_service.py found

REM Set PYTHONPATH
set PYTHONPATH=%PROJECT_ROOT%\src;%PYTHONPATH%

REM Start service
echo.
echo ========================================================================
echo STARTING TELEMETRY API SERVICE
echo ========================================================================
echo Endpoint: http://%TELEMETRY_API_HOST%:%TELEMETRY_API_PORT%
echo Health check: http://%TELEMETRY_API_HOST%:%TELEMETRY_API_PORT%/health
echo Metrics: http://%TELEMETRY_API_HOST%:%TELEMETRY_API_PORT%/metrics
echo.
echo Press Ctrl+C to stop
echo ========================================================================
echo.

cd /d "%PROJECT_ROOT%"

REM Start uvicorn
python -m uvicorn telemetry_service:app ^
    --host %TELEMETRY_API_HOST% ^
    --port %TELEMETRY_API_PORT% ^
    --workers 1 ^
    --log-level %TELEMETRY_LOG_LEVEL%

endlocal
