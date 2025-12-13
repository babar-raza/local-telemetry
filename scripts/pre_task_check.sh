#!/usr/bin/env bash
#
# Pre-Task Dependency Check
#
# Validates task dependencies before allowing task execution.

set -euo pipefail

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Default values
TASK_SPEC=""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Usage
usage() {
    cat <<EOF
Usage: $0 --task-spec PATH

Check task dependencies before execution.

OPTIONS:
    --task-spec PATH    Path to task specification file (required)
    -h, --help          Show this help message

EXIT CODES:
    0 - All dependencies satisfied
    1 - Some dependencies not satisfied
    2 - Error

EXAMPLES:
    # Check dependencies before task
    $0 --task-spec plans/tasks/task.md && python execute_task.py
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --task-spec)
            TASK_SPEC="$2"
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

# Validate required arguments
if [[ -z "$TASK_SPEC" ]]; then
    echo -e "${RED}Error: --task-spec is required${NC}" >&2
    usage
    exit 2
fi

# Run dependency check
python3 "${SCRIPT_DIR}/check_task_dependencies.py" \
    --task-spec "$TASK_SPEC" \
    --project-root "$PROJECT_ROOT"

EXIT_CODE=$?

if [[ $EXIT_CODE -eq 0 ]]; then
    echo -e "${GREEN}✓ All dependencies satisfied - Task can proceed${NC}"
else
    echo -e "${RED}✗ Dependencies not satisfied - Task blocked${NC}"
fi

exit $EXIT_CODE
