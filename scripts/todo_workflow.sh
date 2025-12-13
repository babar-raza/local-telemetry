#!/usr/bin/env bash
#
# TodoWrite Workflow Wrapper
#
# Wrapper for TodoWrite operations that enforces verification for task completion.
# Always calls verified_todo_update.py for "completed" status.
# Allows direct TodoWrite for other statuses.

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default values
TASK_ID=""
STATUS=""
SPEC=""
AGENT_ID=""
SKIP_QUALITY_GATE=false
LOG_FILE="${PROJECT_ROOT}/logs/verification.log"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Usage
usage() {
    cat <<EOF
Usage: $0 <command> <task-id> [OPTIONS]

Wrapper for TodoWrite operations with verification for task completion.

COMMANDS:
    start <task-id>          Mark task as in_progress (no verification)
    complete <task-id>       Mark task as completed (requires verification)
    block <task-id>          Mark task as blocked (no verification)
    pending <task-id>        Mark task as pending (no verification)

OPTIONS:
    --spec PATH             Path to task specification (required for 'complete')
    --agent-id ID           Agent ID for logging
    --skip-quality-gate     Skip quality gate (only check file existence)
    --log-file PATH         Path to verification log file
    -h, --help              Show this help message

EXAMPLES:
    # Mark task as in progress (no verification)
    $0 start day5-task3

    # Mark task as complete (with verification)
    $0 complete day5-task3 --spec plans/tasks/day5_task3_update_docs.md

    # Mark task as complete with agent ID
    $0 complete day5-task3 --spec task.md --agent-id ef82d1bf

    # Skip quality gate (faster, less thorough)
    $0 complete day5-task3 --spec task.md --skip-quality-gate

WORKFLOW:
    For task completion, this script:
    1. Checks all deliverable files exist
    2. Runs quality gate verification (unless --skip-quality-gate)
    3. Only updates TodoWrite if verification passes

EXIT CODES:
    0 - Success
    1 - Verification failed
    2 - Error
EOF
}

# Parse command
if [[ $# -eq 0 ]]; then
    usage
    exit 0
fi

COMMAND="$1"
shift

# Validate command
case "$COMMAND" in
    start|complete|block|pending)
        ;;
    -h|--help)
        usage
        exit 0
        ;;
    *)
        echo -e "${RED}Error: Unknown command: $COMMAND${NC}" >&2
        usage
        exit 2
        ;;
esac

# Parse task ID (required positional argument)
if [[ $# -eq 0 ]]; then
    echo -e "${RED}Error: Task ID required${NC}" >&2
    usage
    exit 2
fi

TASK_ID="$1"
shift

# Parse options
while [[ $# -gt 0 ]]; do
    case $1 in
        --spec)
            SPEC="$2"
            shift 2
            ;;
        --agent-id)
            AGENT_ID="$2"
            shift 2
            ;;
        --skip-quality-gate)
            SKIP_QUALITY_GATE=true
            shift
            ;;
        --log-file)
            LOG_FILE="$2"
            shift 2
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

# Map command to status
case "$COMMAND" in
    start)
        STATUS="in_progress"
        ;;
    complete)
        STATUS="completed"
        ;;
    block)
        STATUS="blocked"
        ;;
    pending)
        STATUS="pending"
        ;;
esac

# For non-completed status, allow direct update (no verification)
if [[ "$STATUS" != "completed" ]]; then
    echo -e "${GREEN}Status '$STATUS' does not require verification${NC}"
    echo "Task $TASK_ID → $STATUS"
    # In production, would update TodoWrite here:
    # todo_write --task-id "$TASK_ID" --status "$STATUS"
    exit 0
fi

# For completed status, require verification
if [[ -z "$SPEC" ]]; then
    echo -e "${RED}Error: --spec required for 'complete' command${NC}" >&2
    usage
    exit 2
fi

if [[ ! -f "$SPEC" ]]; then
    echo -e "${RED}Error: Task spec not found: $SPEC${NC}" >&2
    exit 2
fi

# Build command for verified_todo_update.py
CMD=(
    python3 "${SCRIPT_DIR}/verified_todo_update.py"
    --task-id "$TASK_ID"
    --status "$STATUS"
    --spec "$SPEC"
    --log-file "$LOG_FILE"
)

if [[ -n "$AGENT_ID" ]]; then
    CMD+=(--agent-id "$AGENT_ID")
fi

if [[ "$SKIP_QUALITY_GATE" == "true" ]]; then
    CMD+=(--skip-quality-gate)
fi

# Execute verified update
"${CMD[@]}"
EXIT_CODE=$?

# Return exit code from verification
exit $EXIT_CODE
