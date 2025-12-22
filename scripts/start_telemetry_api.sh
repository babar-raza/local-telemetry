#!/bin/bash
# Telemetry API Service Startup Script (Unix/Linux/macOS)
#
# Usage:
#   ./scripts/start_telemetry_api.sh
#   ./scripts/start_telemetry_api.sh --port 8765
#   ./scripts/start_telemetry_api.sh --help

set -e  # Exit on error

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default configuration
API_HOST="${TELEMETRY_API_HOST:-0.0.0.0}"
API_PORT="${TELEMETRY_API_PORT:-8765}"
LOG_LEVEL="${TELEMETRY_LOG_LEVEL:-info}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            API_PORT="$2"
            shift 2
            ;;
        --host)
            API_HOST="$2"
            shift 2
            ;;
        --log-level)
            LOG_LEVEL="$2"
            shift 2
            ;;
        --help)
            echo "Telemetry API Service Startup Script"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --port PORT        API port (default: 8765)"
            echo "  --host HOST        API host (default: 0.0.0.0)"
            echo "  --log-level LEVEL  Log level (default: info)"
            echo "  --help             Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  TELEMETRY_DB_PATH              Database path (default: D:/agent-metrics/db/telemetry.sqlite)"
            echo "  TELEMETRY_DB_JOURNAL_MODE      Journal mode (default: DELETE)"
            echo "  TELEMETRY_DB_SYNCHRONOUS       Synchronous mode (default: FULL)"
            echo "  TELEMETRY_API_WORKERS          Worker count (must be 1)"
            exit 0
            ;;
        *)
            echo -e "${RED}[ERROR]${NC} Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "========================================================================"
echo "TELEMETRY API SERVICE STARTUP"
echo "========================================================================"
echo "Project root: $PROJECT_ROOT"
echo "API host: $API_HOST"
echo "API port: $API_PORT"
echo "Log level: $LOG_LEVEL"
echo ""

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR]${NC} Python 3 not found. Please install Python 3.7+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}[OK]${NC} Python version: $PYTHON_VERSION"

# Check if virtual environment exists
if [ -d "$PROJECT_ROOT/venv" ]; then
    echo -e "${GREEN}[OK]${NC} Virtual environment found"
    source "$PROJECT_ROOT/venv/bin/activate"
else
    echo -e "${YELLOW}[WARN]${NC} No virtual environment found. Using system Python."
fi

# Check dependencies
if ! python3 -c "import fastapi" 2>/dev/null; then
    echo -e "${RED}[ERROR]${NC} FastAPI not installed"
    echo "Install dependencies with: pip install -r requirements.txt"
    exit 1
fi

echo -e "${GREEN}[OK]${NC} FastAPI installed"

# Check if telemetry_service.py exists
if [ ! -f "$PROJECT_ROOT/telemetry_service.py" ]; then
    echo -e "${RED}[ERROR]${NC} telemetry_service.py not found"
    exit 1
fi

echo -e "${GREEN}[OK]${NC} telemetry_service.py found"

# Add src to PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT/src:$PYTHONPATH"

# Start service
echo ""
echo "========================================================================"
echo "STARTING TELEMETRY API SERVICE"
echo "========================================================================"
echo "Endpoint: http://$API_HOST:$API_PORT"
echo "Health check: http://$API_HOST:$API_PORT/health"
echo "Metrics: http://$API_HOST:$API_PORT/metrics"
echo ""
echo "Press Ctrl+C to stop"
echo "========================================================================"
echo ""

cd "$PROJECT_ROOT"

# Use exec to replace shell with uvicorn process
exec uvicorn telemetry_service:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --workers 1 \
    --log-level "$LOG_LEVEL"
