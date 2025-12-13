#!/usr/bin/env bash
#
# Post-Agent File Extraction Hook
#
# Automatically runs after agent completion to extract file contents
# from agent output when Write tool fails.

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default values
AGENT_LOG_FILE="${AGENT_LOG_FILE:-}"
OUTPUT_DIR="${OUTPUT_DIR:-${PROJECT_ROOT}}"
DRY_RUN="${DRY_RUN:-false}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo "======================================================================" Post-Agent File Extraction Hook
echo "======================================================================"

# Check if agent log file is provided
if [[ -z "$AGENT_LOG_FILE" ]]; then
    echo -e "${YELLOW}Warning: AGENT_LOG_FILE not set, skipping extraction${NC}"
    exit 0
fi

if [[ ! -f "$AGENT_LOG_FILE" ]]; then
    echo -e "${YELLOW}Warning: Agent log file not found: $AGENT_LOG_FILE${NC}"
    exit 0
fi

echo "Agent log: $AGENT_LOG_FILE"
echo "Output directory: $OUTPUT_DIR"

# Run extraction
CMD=(
    python3 "${SCRIPT_DIR}/extract_files_from_agent_output.py"
    --log-file "$AGENT_LOG_FILE"
    --output-dir "$OUTPUT_DIR"
)

if [[ "$DRY_RUN" == "true" ]]; then
    CMD+=(--dry-run)
    echo -e "${YELLOW}DRY RUN MODE${NC}"
fi

# Execute extraction
set +e
"${CMD[@]}"
EXIT_CODE=$?
set -e

if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}✓ File extraction completed successfully${NC}"
elif [[ $EXIT_CODE -eq 1 ]]; then
    echo -e "${YELLOW}⚠ File extraction completed with some failures${NC}"
else
    echo -e "${RED}✗ File extraction failed${NC}"
fi

exit $EXIT_CODE
