#!/usr/bin/env bash
#
# Post-Agent Completion Hook (DC-05)
#
# Automatically extracts deliverables from agent output after completion.
# Validates against task spec deliverables.

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Configuration
AGENT_ID="${AGENT_ID:-unknown}"
AGENT_LOG_FILE="${AGENT_LOG_FILE:-}"
TASK_SPEC="${TASK_SPEC:-}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "======================================================================"
echo "Post-Agent Hook: Automatic Output Extraction"
echo "======================================================================"
echo "Agent ID: $AGENT_ID"

# Check if agent log file is set
if [[ -z "$AGENT_LOG_FILE" ]]; then
    echo -e "${YELLOW}Warning: AGENT_LOG_FILE not set${NC}"
    echo "Set AGENT_LOG_FILE environment variable to enable extraction"
    exit 0
fi

if [[ ! -f "$AGENT_LOG_FILE" ]]; then
    echo -e "${YELLOW}Warning: Agent log file not found: $AGENT_LOG_FILE${NC}"
    exit 0
fi

echo "Log file: $AGENT_LOG_FILE"
echo "Output directory: $OUTPUT_DIR"

# Build extraction command
CMD=(
    python3 "${SCRIPT_DIR}/auto_extract_agent_outputs.py"
    --log-file "$AGENT_LOG_FILE"
    --output-dir "$OUTPUT_DIR"
    --agent-id "$AGENT_ID"
)

# Add task spec if provided
if [[ -n "$TASK_SPEC" && -f "$TASK_SPEC" ]]; then
    CMD+=(--task-spec "$TASK_SPEC")
    echo "Task spec: $TASK_SPEC"
fi

# Execute extraction
echo ""
echo "Running extraction..."
set +e
"${CMD[@]}"
EXIT_CODE=$?
set -e

echo ""
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}✓ Extraction completed successfully${NC}"
elif [[ $EXIT_CODE -eq 1 ]]; then
    echo -e "${YELLOW}⚠ Extraction completed with some issues${NC}"
    echo -e "${YELLOW}Some expected deliverables may not have been extracted${NC}"
else
    echo -e "${RED}✗ Extraction failed${NC}"
fi

exit $EXIT_CODE
