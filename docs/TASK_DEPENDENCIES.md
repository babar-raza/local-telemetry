# Task Dependencies

## Overview

Validates that all task dependencies are satisfied before allowing task execution. Prevents failures due to missing prerequisite files, incomplete tasks, or unset environment variables.

## Purpose

Tasks may fail mid-execution if dependencies aren't validated upfront:
- Missing prerequisite files cause import/load errors
- Incomplete prerequisite tasks mean required data unavailable
- Unset environment variables cause configuration errors

Dependency checking catches these issues before task execution begins.

## Specifying Dependencies

Add a **Dependencies** section to your task specification:

```markdown
## Dependencies

- File: scripts/setup.py
- File: config/database.yaml
- Task: SETUP-01
- Task: CONFIG-02
- Environment: DATABASE_URL
- Environment: API_KEY
```

### Dependency Types

**File Dependencies**: Files that must exist
```markdown
- File: path/to/file.py
```

**Task Dependencies**: Tasks that must be completed
```markdown
- Task: TASK-ID
```

**Environment Dependencies**: Environment variables that must be set
```markdown
- Environment: VAR_NAME
```

## Usage

### Check Dependencies Before Task

```bash
./scripts/pre_task_check.sh --task-spec plans/tasks/task.md
```

Exit codes:
- **0**: All dependencies satisfied
- **1**: Some dependencies not satisfied
- **2**: Error

### Integrate with Task Execution

```bash
./scripts/pre_task_check.sh --task-spec task.md && python execute_task.py
```

Task only executes if dependency check passes.

## Dependency Report

Example report:

```
======================================================================
TASK DEPENDENCY CHECK
======================================================================
Task spec: plans/tasks/feature_task.md

SUMMARY
----------------------------------------------------------------------
Total dependencies: 5
Satisfied: 3
Unsatisfied: 2

✗ UNSATISFIED DEPENDENCIES
----------------------------------------------------------------------

File Dependencies:
  ✗ scripts/setup.py
     File MISSING: /project/scripts/setup.py

Environment Variables:
  ✗ API_KEY
     Environment variable API_KEY NOT SET

Task CANNOT proceed until dependencies are satisfied.

SATISFIED DEPENDENCIES
----------------------------------------------------------------------
✓ config/database.yaml (file)
✓ SETUP-01 (task)
✓ DATABASE_URL (env_var)

======================================================================
```

## How Dependency Checking Works

### File Dependencies

Checks if files exist on filesystem using absolute paths.

### Task Dependencies

Checks completion status in two locations:
1. **TodoWrite logs**: `logs/todo_updates.log` for "completed" markers
2. **Plan files**: `plans/*.md` for "Status: Done ✅" markers

### Environment Variables

Checks if variables are set in current environment using `os.environ`.

## Troubleshooting

### File Dependency Failed But File Exists

**Cause**: Path mismatch (relative vs absolute, case sensitivity)

**Solution**: Ensure paths in task spec match actual file locations exactly.

### Task Dependency Not Detected

**Cause**: Task completion not logged in expected locations

**Solution**:
1. Check TodoWrite log exists: `logs/todo_updates.log`
2. Check plan files have Status markers
3. Verify task ID matches exactly (case-sensitive)

### Environment Variable Not Detected

**Cause**: Variable not exported or in different shell

**Solution**:
```bash
export VAR_NAME=value
./scripts/pre_task_check.sh --task-spec task.md
```

## Best Practices

1. **Declare all dependencies explicitly** - Don't assume files/tasks exist
2. **Order tasks by dependencies** - Complete prerequisites first
3. **Set environment variables early** - Export in shell startup scripts
4. **Validate before long-running tasks** - Catch issues early

---

**Last Updated**: 2025-12-11
**Version**: 1.0.0
**Status**: Production Ready
