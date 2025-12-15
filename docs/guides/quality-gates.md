# Quality Gates

See `../reference/cli.md` for the full command/flag list; this guide focuses on how to run gates and interpret results. Example file paths below are illustrative—substitute your actual deliverables.

## Overview

Quality gates are systematic validation checks that run after agent task completion to ensure deliverables meet specifications before marking tasks "done". This prevents incomplete work from passing as complete.

## Purpose

During Day 5 production hardening, agents completed tasks but deliverables were not verified against task specifications, resulting in:
- Documentation files 61-75% incomplete
- FAQ.md completely missing (0/410 lines)
- Production readiness checklist missing
- Total: 1,071 missing documentation lines

Quality gates solve this by:
1. **Parsing task specs** to extract deliverable requirements
2. **Validating deliverables** against requirements (file existence, line counts, tests)
3. **Blocking task completion** until validation passes
4. **Generating reports** showing exactly what failed

## How It Works

### 1. Task Specification Format

Task specs must include **Deliverables** and **Acceptance checks** sections:

```markdown
## [TASK-01] Example Task

**Deliverables**:
1. **scripts/example.py** (300-400 lines)
   - Main implementation
2. **tests/test_example.py** (200-250 lines)
   - Test suite
3. **docs/EXAMPLE.md** (100-150 lines)
   - Documentation

**Acceptance checks**:
```bash
# Must pass all checks
[ -f scripts/example.py ]
[ $(wc -l < scripts/example.py) -ge 300 ]
pytest tests/test_example.py -v
```
```

### 2. Quality Gate Validation

When an agent completes a task, run the quality gate:

```bash
python scripts/quality_gate.py \\
    --task-spec plans/tasks/task_spec.md \\
    --agent-id abc123 \\
    --output reports/quality_gates/gate_report.txt
```

The quality gate will:

1. **Parse** the task spec to extract requirements
2. **Check file existence** for all deliverables
3. **Validate line counts** against specified ranges
4. **Run acceptance checks** (optional, configured)
5. **Generate report** with pass/fail details
6. **Exit with code** 0=pass, 1=fail

### 3. Integration with Workflow

The recommended workflow is:

```bash
# 1. Agent completes task
./run_agent.sh --task-spec task.md

# 2. Run quality gate BEFORE marking task complete
./scripts/quality_gate_runner.sh --task-spec task.md --agent-id <id>

# 3. If gate passes (exit code 0), mark task complete
if [ $? -eq 0 ]; then
    # Mark task complete in TodoWrite
    ./scripts/verified_todo_update.py --task-id <id> --status completed
else
    # Fix issues and re-run gate
    echo "Quality gate failed. Fix issues before marking complete."
fi
```

## Configuration

Quality gates are configured via `config/quality_gate_config.yaml`:

```yaml
# Severity levels
severity_levels:
  - CRITICAL  # Must fix
  - HIGH      # Should fix
  - MEDIUM    # Nice to fix
  - LOW       # Optional

# Which severities block task completion
blocking_severities:
  - CRITICAL
  - HIGH

# Line count tolerance
line_count_rules:
  tolerance_percentage: 10  # ±10% is acceptable

# File type specific rules
file_type_rules:
  python:
    extensions: [".py"]
    min_lines_default: 50
    require_docstring: true
    require_tests: true
```

### Customizing Gate Rules

To add rules for a new file type:

```yaml
file_type_rules:
  typescript:
    extensions: [".ts", ".tsx"]
    min_lines_default: 30
    require_types: true
    test_file_pattern: "*.test.ts"
```

## Quality Gate Report

A typical quality gate report looks like:

```
======================================================================
QUALITY GATE REPORT
======================================================================
Task: day5_task3_update_docs

SUMMARY
----------------------------------------------------------------------
Total checks: 8
Passed: 5
Failed: 3
Blocking failures: 3

✗ QUALITY GATE FAILED

FAILED CHECKS
----------------------------------------------------------------------
✗ BLOCKER [CRITICAL] file_exists:docs/FAQ.md
  Expected: File exists
  Actual:   File MISSING
  Message:  File docs/FAQ.md not found

✗ BLOCKER [HIGH] line_count:docs/QUICK_START.md
  Expected: 220-250 lines
  Actual:   89 lines (does NOT match claim of 230)
  Message:  File docs/QUICK_START.md: 89 lines (expected 220-250)

✗ BLOCKER [HIGH] line_count:docs/TROUBLESHOOTING.md
  Expected: 300-350 lines
  Actual:   81 lines
  Message:  File docs/TROUBLESHOOTING.md: 81 lines (expected 300-350)

PASSED CHECKS
----------------------------------------------------------------------
✓ file_exists:scripts/monitor_telemetry_health.py
✓ line_count:scripts/monitor_telemetry_health.py
✓ file_exists:scripts/backup_telemetry_db.py
✓ line_count:scripts/backup_telemetry_db.py
✓ file_exists:docs/RUNBOOK.md

======================================================================
```

## Troubleshooting Gate Failures

### File Missing

**Symptom**: `✗ BLOCKER [CRITICAL] file_exists:path/to/file`

**Causes**:
1. Agent didn't create the file
2. Agent output not extracted (Write tool permission failure)
3. File path mismatch (case sensitivity, typos)

**Solutions**:
1. Check agent output logs for file content
2. Run agent output extraction script:
   ```bash
   python scripts/extract_files_from_agent_output.py --agent-id <id>
   ```
3. Verify file path spelling and case

### Line Count Mismatch

**Symptom**: `✗ BLOCKER [HIGH] line_count:file.py`

**Causes**:
1. File truncated during Write operation
2. Agent produced incomplete file
3. Line count expectation incorrect in task spec

**Solutions**:
1. Check agent output for complete file content
2. Extract full content from agent logs
3. Verify task spec line count expectations are realistic
4. Check for file truncation:
   ```bash
   wc -l file.py
   tail -20 file.py  # Check if file ends abruptly
   ```

### Test Failures

**Symptom**: Acceptance check test failed

**Causes**:
1. Tests not implemented
2. Tests fail due to incomplete implementation
3. Test environment issues

**Solutions**:
1. Run tests manually to see specific failures:
   ```bash
   pytest tests/test_example.py -v
   ```
2. Check test implementation matches task requirements
3. Verify test environment (dependencies, env vars)

## Manual Override Procedure

**WARNING**: Manual overrides bypass quality gates and should be used sparingly.

If you must override a failing gate:

1. **Document justification** (minimum 100 characters):
   ```bash
   echo "Override justified because: [detailed explanation]" > reports/override_justification.txt
   ```

2. **Log the override**:
   ```bash
   echo "$(date): Task <id> overridden by <name>: $(cat reports/override_justification.txt)" >> reports/quality_gate_overrides.log
   ```

3. **Get approval** for CRITICAL severity failures (required by senior engineer or tech lead)

4. **Mark task complete** with override flag:
   ```bash
   ./scripts/verified_todo_update.py --task-id <id> --status completed --override
   ```

## Examples

### Example 1: Successful Gate

```bash
$ ./scripts/quality_gate_runner.sh --task-spec plans/tasks/feature_task.md --agent-id xyz789

======================================================================
QUALITY GATE VALIDATION
======================================================================
Task Spec: plans/tasks/feature_task.md
Agent ID:  xyz789
Config:    config/quality_gate_config.yaml

Running quality gate checks...

======================================================================
✓ QUALITY GATE PASSED
======================================================================

All deliverables validated successfully.
Task can be marked complete in TodoWrite.
```

### Example 2: Failed Gate

```bash
$ ./scripts/quality_gate_runner.sh --task-spec plans/tasks/day5_task3_update_docs.md --agent-id ef82d1bf

======================================================================
QUALITY GATE VALIDATION
======================================================================
Task Spec: plans/tasks/day5_task3_update_docs.md
Agent ID:  ef82d1bf

Running quality gate checks...

======================================================================
✗ QUALITY GATE FAILED
======================================================================

Quality gate validation failed. See report for details:
  reports/quality_gates/gate_day5_task3_ef82d1bf_20250611_143022.txt

Failed Checks:
✗ BLOCKER [CRITICAL] file_exists:docs/FAQ.md
✗ BLOCKER [HIGH] line_count:docs/QUICK_START.md
✗ BLOCKER [HIGH] line_count:docs/TROUBLESHOOTING.md

Task CANNOT be marked complete until issues are resolved.

Next steps:
  1. Review the quality gate report
  2. Fix the identified issues
  3. Re-run the quality gate
  4. Mark task complete only after gate passes
```

### Example 3: Historical Agent Validation

Test quality gate on historical Day 5 agents to verify it catches known issues:

```bash
# This SHOULD fail (ef82d1bf had incomplete docs)
$ python scripts/quality_gate.py \\
    --task-spec plans/tasks/day5_task3_update_docs.md \\
    --agent-id ef82d1bf

# Expected: Exit code 1, report shows 3 CRITICAL/HIGH failures

# This SHOULD also fail (19cbfe1f was missing checklist)
$ python scripts/quality_gate.py \\
    --task-spec plans/tasks/day5_task5_final_validation.md \\
    --agent-id 19cbfe1f

# Expected: Exit code 1, report shows missing production-readiness-checklist.md
```

## Adding Gates for New Task Types

To add quality gates for a new task type:

1. **Update config** with task-specific rules:

```yaml
task_type_rules:
  api_feature:
    severity: CRITICAL
    checks:
      - file_exists
      - line_count
      - tests_exist
      - tests_pass
      - api_spec_valid
    require_all_deliverables: true
    min_test_coverage: 85
```

2. **Add validation logic** if needed (e.g., for `api_spec_valid`):

```python
# In quality_gate.py
def check_api_spec_valid(filepath: str, project_root: Path) -> CheckResult:
    """Validate OpenAPI/Swagger spec."""
    # Implementation here
    pass
```

3. **Test** on sample task:

```bash
python scripts/quality_gate.py --task-spec sample_api_task.md --dry-run
```

## Integration with Other Tools

### With Verification Framework

Quality gates can integrate with the verification framework:

```yaml
# In config/quality_gate_config.yaml
integrations:
  verification_framework:
    enabled: true
    run_verification_after_gate: true
    verification_script: "scripts/verify_analysis.py"
```

When enabled, after the quality gate passes, the verification framework runs to verify claims in any analysis documents.

### With TodoWrite

Quality gates block TodoWrite status updates:

```yaml
integrations:
  todo_write:
    enabled: true
    block_completion_on_failure: true
```

Use the verified update wrapper:

```bash
./scripts/verified_todo_update.py --task-id <id> --status completed --spec task.md
```

This automatically runs the quality gate and only updates status if it passes.

## Best Practices

1. **Run gates immediately after task completion** - Don't wait; catch issues early

2. **Fix issues before moving on** - Don't accumulate quality debt

3. **Never lower acceptance criteria** to make gates pass - Fix the root cause

4. **Document overrides thoroughly** - Future you will thank present you

5. **Review gate reports** - Understand patterns of failures

6. **Update task specs** if line count expectations are consistently wrong

7. **Test gates on sample tasks** before deploying to production workflow

## Metrics

Track quality gate metrics to improve processes:

```bash
# Gate passage rate
grep "exit_code=" logs/quality_gate.log | grep "exit_code=0" | wc -l

# Most common failures
grep "✗ BLOCKER" reports/quality_gates/*.txt | cut -d':' -f2 | sort | uniq -c | sort -rn | head -10

# Average line count mismatches
grep "line_count" reports/quality_gates/*.txt | grep "does NOT match" | wc -l
```

## References

- **Task specification format**: See `plans/tasks/` for examples
- **Configuration reference**: `config/quality_gate_config.yaml`
- **Integration examples**: `scripts/quality_gate_runner.sh`
- **Test suite**: `tests/test_quality_gate.py`

---

**Last Updated**: 2025-12-11
**Version**: 1.0.0
**Status**: Production Ready
