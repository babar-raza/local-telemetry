# Automatic Agent Output Extraction

## Overview

Automatically extracts deliverables from agent output logs with validation against task specifications. Prevents documentation and code loss when Write tool fails.

## Purpose

This tool (DC-05) wraps the file extraction functionality (PH-03) and adds task specification validation to ensure all expected deliverables are extracted.

**Use Cases:**
- Agent completed but files not written to disk
- Permission errors prevented file writing
- Recovering documentation from historical agents
- Validating extraction completeness against task requirements

## How It Works

### 1. Agent Output Parsing

Parses agent output logs for file content blocks (delegated to PH-03 implementation).

### 2. File Extraction

Extracts files from agent output (delegated to PH-03 implementation).

### 3. Task Spec Validation (NEW in DC-05)

Validates that all deliverables specified in the task spec were successfully extracted:
- Parses task spec **Deliverables** section
- Extracts expected file paths
- Compares against extracted files
- Reports missing deliverables

## Usage

### Basic Extraction with Validation

```bash
python scripts/auto_extract_agent_outputs.py \
    --agent-id ef82d1bf \
    --task-spec plans/tasks/day5_task3_update_docs.md \
    --output-dir docs/
```

### Dry Run (Preview)

```bash
python scripts/auto_extract_agent_outputs.py \
    --log-file logs/agent_ef82d1bf.log \
    --task-spec plans/tasks/day5_task3_update_docs.md \
    --dry-run
```

### Without Task Spec (PH-03 Mode)

```bash
python scripts/auto_extract_agent_outputs.py \
    --log-file logs/agent_output.log \
    --output-dir .
```

## Post-Agent Hook Integration

Automatically run after every agent completion:

### 1. Create Hook Configuration

Create/edit `.claude/hooks/post_agent_config`:

```bash
# Agent output extraction configuration
export AGENT_ID="<will-be-set-by-system>"
export AGENT_LOG_FILE="<will-be-set-by-system>"
export TASK_SPEC="plans/tasks/current_task.md"
export OUTPUT_DIR="."
```

### 2. Enable Hook

Create `.claude/hooks/post_agent.sh`:

```bash
#!/usr/bin/env bash
source scripts/post_agent_hook.sh
```

### 3. Make Executable

```bash
chmod +x .claude/hooks/post_agent.sh
```

## Extraction Report with Validation

Example report:

```
======================================================================
AGENT OUTPUT FILE EXTRACTION REPORT
======================================================================
Log file: logs/agent_ef82d1bf.log
Output directory: docs/
Mode: WRITE

SUMMARY
----------------------------------------------------------------------
Total files found: 4
Successfully extracted: 3
Failed: 1
Total lines extracted: 891

SUCCESSFULLY EXTRACTED FILES
----------------------------------------------------------------------
✓ docs/QUICK_START.md (230 lines)
✓ docs/TROUBLESHOOTING.md (320 lines)
✓ docs/FAQ.md (341 lines)

FAILED EXTRACTIONS
----------------------------------------------------------------------
✗ docs/checklist.md
  Error: Failed validation (insufficient content)

TASK SPEC VALIDATION
----------------------------------------------------------------------
Expected deliverables: 4
Successfully extracted: 3

✗ MISSING EXPECTED DELIVERABLES

  ✗ docs/production-readiness-checklist.md

RECOMMENDATION:
Check agent output log for these files.
They may not have been produced due to agent errors.

======================================================================
```

## Differences from PH-03

| Feature | PH-03 | DC-05 (this tool) |
|---------|-------|-------------------|
| File extraction | ✅ | ✅ (delegated to PH-03) |
| Task spec parsing | ❌ | ✅ |
| Deliverable validation | ❌ | ✅ |
| Missing file reporting | ❌ | ✅ |
| Agent ID parameter | Optional | Supported |
| Use case | General file recovery | Task-driven extraction |

## Troubleshooting

### Expected Deliverable Not Extracted

**Symptom**: Validation reports missing deliverable

**Cause**: File not produced by agent or extraction pattern didn't match

**Solution**:
1. Check agent log manually for the file content
2. Verify file was actually produced by agent
3. If content exists but not extracted, improve extraction patterns
4. If agent didn't produce file, re-run task

### Task Spec Not Parsed

**Symptom**: "Expected deliverables: 0"

**Cause**: Task spec has no **Deliverables** section or incorrect format

**Solution**:
Ensure task spec has deliverables in this format:
```markdown
**Deliverables**:
1. **path/to/file.ext** (100-150 lines)
   - Description
```

## Exit Codes

- **0**: All expected deliverables extracted successfully
- **1**: Some expected deliverables missing or extraction failures
- **2**: Critical error (log file not found, etc.)

## Configuration

No configuration file needed. All options via CLI arguments or environment variables (for hook mode).

---

**Last Updated**: 2025-12-11
**Version**: 1.0.0
**Status**: Production Ready
**Related**: PH-03 (underlying implementation)
