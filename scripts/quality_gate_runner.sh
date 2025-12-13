#!/usr/bin/env bash
#
# Quality Gate Runner
#
# Wrapper script to run quality gate after agent task completion.
# Integrates with TodoWrite workflow and blocks marking tasks complete if gate fails.

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default values
TASK_SPEC=""
AGENT_ID=""
CONFIG_FILE="${PROJECT_ROOT}/config/quality_gate_config.yaml"
REPORT_DIR="${PROJECT_ROOT}/reports/quality_gates"
LOG_FILE="${PROJECT_ROOT}/logs/quality_gate.log"
BLOCK_ON_FAILURE=true

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage
usage() {
    cat <<EOF
Usage: $0 [OPTIONS]

Run quality gate validation after agent task completion.

OPTIONS:
    --task-spec PATH      Path to task specification file (required)
    --agent-id ID         Agent ID for logging
    --config PATH         Path to quality gate config file
    --report-dir PATH     Directory for gate reports
    --no-block            Don't block on failure (for testing)
    -h, --help            Show this help message

EXAMPLES:
    # Run quality gate for task
    $0 --task-spec plans/tasks/day5_task3_update_docs.md --agent-id ef82d1bf

    # Run with custom config
    $0 --task-spec task.md --agent-id abc123 --config custom_config.yaml

INTEGRATION:
    This script should be called after agent completion and before marking
    the task complete in TodoWrite. If the gate fails, the task should not
    be marked complete.

EXIT CODES:
    0 - Quality gate passed
    1 - Quality gate failed
    2 - Error running quality gate
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --task-spec)
            TASK_SPEC="$2"
            shift 2
            ;;
        --agent-id)
            AGENT_ID="$2"
            shift 2
            ;;
        --config)
            CONFIG_FILE="$2"
            shift 2
            ;;
        --report-dir)
            REPORT_DIR="$2"
            shift 2
            ;;
        --no-block)
            BLOCK_ON_FAILURE=false
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            usage
            exit 2
            ;;
    esac
done

# Validate required arguments
if [[ -z "$TASK_SPEC" ]]; then
    echo -e "${RED}Error: --task-spec is required${NC}" >&2
    usage
    exit 2
fi

if [[ ! -f "$TASK_SPEC" ]]; then
    echo -e "${RED}Error: Task spec not found: $TASK_SPEC${NC}" >&2
    exit 2
fi

# Create log directory
mkdir -p "$(dirname "$LOG_FILE")"

# Create report directory
mkdir -p "$REPORT_DIR"

# Log start
echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting quality gate: task=$TASK_SPEC agent=$AGENT_ID" >> "$LOG_FILE"

# Generate report filename
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
TASK_NAME=$(basename "$TASK_SPEC" .md)
REPORT_FILE="${REPORT_DIR}/gate_${TASK_NAME}_${AGENT_ID}_${TIMESTAMP}.txt"

# Print header
echo "======================================================================"
echo "QUALITY GATE VALIDATION"
echo "======================================================================"
echo "Task Spec: $TASK_SPEC"
if [[ -n "$AGENT_ID" ]]; then
    echo "Agent ID:  $AGENT_ID"
fi
echo "Config:    $CONFIG_FILE"
echo "Report:    $REPORT_FILE"
echo ""

# Run quality gate
echo "Running quality gate checks..."
echo ""

# Build command
CMD=(
    python3 "${SCRIPT_DIR}/quality_gate.py"
    --task-spec "$TASK_SPEC"
    --config "$CONFIG_FILE"
    --output "$REPORT_FILE"
    --format text
)

if [[ -n "$AGENT_ID" ]]; then
    CMD+=(--agent-id "$AGENT_ID")
fi

# Execute quality gate
set +e
"${CMD[@]}"
EXIT_CODE=$?
set -e

# Log result
echo "$(date '+%Y-%m-%d %H:%M:%S') - Quality gate result: exit_code=$EXIT_CODE" >> "$LOG_FILE"

# Print result
echo ""
echo "======================================================================"
if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}✓ QUALITY GATE PASSED${NC}"
    echo "======================================================================"
    echo ""
    echo "All deliverables validated successfully."
    echo "Task can be marked complete in TodoWrite."
    exit 0
elif [[ $EXIT_CODE -eq 1 ]]; then
    echo -e "${RED}✗ QUALITY GATE FAILED${NC}"
    echo "======================================================================"
    echo ""
    echo "Quality gate validation failed. See report for details:"
    echo "  $REPORT_FILE"
    echo ""

    # Show summary from report
    if [[ -f "$REPORT_FILE" ]]; then
        echo "Failed Checks:"
        grep -A 5 "FAILED CHECKS" "$REPORT_FILE" | head -20 || true
    fi

    echo ""
    if [[ "$BLOCK_ON_FAILURE" == "true" ]]; then
        echo -e "${YELLOW}Task CANNOT be marked complete until issues are resolved.${NC}"
        echo ""
        echo "Next steps:"
        echo "  1. Review the quality gate report"
        echo "  2. Fix the identified issues"
        echo "  3. Re-run the quality gate"
        echo "  4. Mark task complete only after gate passes"
    else
        echo -e "${YELLOW}Warning: --no-block specified, allowing task completion despite failures${NC}"
    fi

    echo ""
    exit 1
else
    echo -e "${RED}✗ QUALITY GATE ERROR${NC}"
    echo "======================================================================"
    echo ""
    echo "Error running quality gate (exit code: $EXIT_CODE)"
    echo "Check logs for details: $LOG_FILE"
    exit 2
fi
