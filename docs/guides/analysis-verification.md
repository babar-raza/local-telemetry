# Analysis Verification Protocol

CLI flags are documented in `../reference/cli.md`. Use this guide for workflow and interpretation. Examples use placeholder file names—replace with your actual deliverables.

## Overview

The Analysis Verification Protocol provides systematic verification of claims made in analysis documents before publication. This prevents unverified claims, assumptions stated as facts, and incomplete evidence from being published as authoritative analysis.

## Purpose

During Day 5 production readiness analysis, several unverified claims were published:
- **File status claims not verified**: "README.md updated", "FAQ.md missing" - not checked on filesystem
- **Line count claims not verified**: "89/230 lines" - not independently confirmed
- **Agent output claims not verified**: "Agent produced X" - not checked in agent logs
- **Functionality not tested**: "Backup restore works" - assumed without testing

These unverified claims reduce confidence for production deployment decisions. The Verification Protocol solves this by:
1. **Extracting claims** from analysis documents automatically
2. **Verifying each claim** against ground truth (filesystem, tests, agent logs)
3. **Collecting evidence** for each verified claim
4. **Generating reports** distinguishing verified facts from assumptions

## How It Works

### 1. Claim Extraction

The verification script parses analysis documents to identify factual claims using configured patterns:

**Claim Types**:
- `file_exists`: "File `path/to/file` exists"
- `file_missing`: "File `path/to/file` is missing"
- `line_count`: "`path/to/file` has N lines"
- `test_passed`: "Tests in `test_file` passed"
- `test_failed`: "Tests in `test_file` failed"
- `agent_output`: "Agent ABC123 produced X"

**Example**:
```markdown
# Analysis

File `scripts/monitor.py` exists with 213 lines.
File `docs/FAQ.md` is missing.
Tests in `tests/test_monitor.py` passed.
```

**Extracted Claims**:
1. [file_exists] `scripts/monitor.py` - Expected: File exists
2. [line_count] `scripts/monitor.py` - Expected: 213 lines
3. [file_missing] `docs/FAQ.md` - Expected: File missing
4. [test_passed] `tests/test_monitor.py` - Expected: Tests passed

### 2. Claim Verification

Each claim is verified against ground truth:

| Claim Type | Verification Method | Evidence Collected |
|------------|--------------------|--------------------|
| file_exists | Filesystem check with `Path.exists()` | Full file path, modification timestamp |
| file_missing | Filesystem check (inverse) | Confirmed absence at expected path |
| line_count | Count lines with `len(f.readlines())` | Exact line count, verification timestamp |
| test_passed | Execute tests (optional, disabled by default for safety) | Test output, exit code |
| agent_output | Parse agent logs for content | Agent log excerpts |

**Tolerance**: Line counts allow ±5% variance to account for minor differences.

### 3. Evidence Collection

Every verified claim includes evidence:

```yaml
claim:
  type: line_count
  subject: scripts/monitor.py
  expected: "213 lines"
  actual: "213 lines (matches claim)"
  verified: true
  verification_method: line_count_check
  evidence: "Line count verified: 213 lines at 2025-06-11 14:30:22"
```

### 4. Report Generation

The verification report shows:
- **Summary**: Total claims, verified%, unverified%, failed%
- **Unverified claims**: What couldn't be verified and why
- **Failed claims**: What was verified but contradicted the claim
- **Verified claims**: What was successfully confirmed with evidence

## Usage

### Basic Usage

```bash
# Dry-run: Show claims that would be verified (no actual verification)
python scripts/verify_analysis.py reports/readiness.md --dry-run

# Full verification
python scripts/verify_analysis.py reports/readiness.md --verify

# Save report to file
python scripts/verify_analysis.py reports/readiness.md \\
    --verify \\
    --output reports/verification_report.txt

# JSON output for CI/CD
python scripts/verify_analysis.py reports/readiness.md \\
    --verify \\
    --format json \\
    --output reports/verification.json
```

### Integration with Analysis Workflow

**Recommended workflow**:

```bash
# 1. Write analysis document
vim reports/production_readiness.md

# 2. BEFORE publishing, run verification
python scripts/verify_analysis.py reports/production_readiness.md \\
    --verify \\
    --output reports/verification_production_readiness.txt

# 3. Review verification report
cat reports/verification_production_readiness.txt

# 4. If unverified claims found:
#    - Verify them manually
#    - Update document to mark as "⚠️ Assumption" if can't verify
#    - Re-run verification

# 5. Only publish after verification passes (≥80% verified)
if [ $? -eq 0 ]; then
    # Publish analysis
    cp reports/production_readiness.md published/
fi
```

### Configuration

Verification behavior is configured via `config/verification_checklist.yaml`:

```yaml
# Minimum % of claims that must verify for report to pass
min_verification_rate: 0.8  # 80%

# Require evidence for all verified claims
require_evidence: true

# Claim extraction patterns (regex)
claim_patterns:
  file_exists:
    - '(?:File|Document)\s+`([^`]+)`\s+(?:exists|present)'
  line_count:
    - '`([^`]+)`.*?(\d+)\s+lines'
  missing_file:
    - '`([^`]+)`.*?(?:missing|not found)'

# Verification method configuration
verification_methods:
  filesystem_check:
    timeout_seconds: 5
  line_count_check:
    timeout_seconds: 10
    tolerance_percentage: 5  # ±5% variance allowed
```

### Customizing Claim Patterns

To detect new claim types, add patterns to config:

```yaml
claim_patterns:
  custom_claim:
    - 'Pattern that matches your claim type with capture group `([^`]+)`'
```

Then implement verification logic:

```python
# In verify_analysis.py
def verify_custom_claim(claim: Claim, project_root: Path) -> Claim:
    # Verification logic here
    claim.verified = True  # or False
    claim.actual = "Verification result"
    claim.evidence = "Evidence collected"
    return claim
```

## Verification Report

### Text Format (Default)

```
======================================================================
ANALYSIS VERIFICATION REPORT
======================================================================
Document: reports/readiness.md

SUMMARY
----------------------------------------------------------------------
Total claims found: 10
Verified claims:    8 (80.0%)
Unverified claims:  1
Failed claims:      1

✓ VERIFICATION PASSED

UNVERIFIED/FAILED CLAIMS
----------------------------------------------------------------------
✗ [file_exists] docs/FAQ.md
  Location: line 142
  Expected: File exists
  Actual:   File NOT FOUND
  Evidence: File not found at docs/FAQ.md

! [agent_output] Agent ef82d1bf
  Location: line 98
  Expected: Agent produced documentation
  Actual:   Unknown claim type
  Evidence: No verification method for claim type: agent_output

VERIFIED CLAIMS
----------------------------------------------------------------------
✓ [file_exists] scripts/monitor_telemetry_health.py
  Location: line 45
  Evidence: Verified at scripts/monitor_telemetry_health.py

✓ [line_count] scripts/monitor_telemetry_health.py
  Location: line 45
  Evidence: Line count verified: 213 lines

... (remaining verified claims)

======================================================================
```

### JSON Format

```json
{
  "document_path": "reports/readiness.md",
  "total_claims": 10,
  "verified_claims": 8,
  "unverified_claims": 1,
  "failed_claims": 1,
  "verification_passed": true,
  "claims": [
    {
      "claim_type": "file_exists",
      "location": "line 45",
      "subject": "scripts/monitor_telemetry_health.py",
      "expected": "File exists",
      "actual": "File exists",
      "verified": true,
      "verification_method": "filesystem_check",
      "evidence": "Verified at scripts/monitor_telemetry_health.py"
    }
  ]
}
```

## Verification Transparency

To clearly communicate verification status in analysis documents, use these markers:

- **✓ Verified**: Claim has been verified with evidence
- **⚠️ Assumption**: Claim is assumed but not verified (state this explicitly)
- **❓ Unknown**: Status unknown, requires investigation

**Example**:

```markdown
## File Status

✓ **Verified**: File `scripts/monitor.py` exists with 213 lines
    (verified via filesystem check on 2025-06-11 14:30:22)

⚠️ **Assumption**: Backup restore functionality works correctly
    (not tested during this analysis, HIGH priority to verify)

❓ **Unknown**: Agent ef82d1bf output completeness
    (agent logs not available for verification)
```

This transparency helps readers understand confidence levels.

## Troubleshooting

### High Unverified Rate

**Symptom**: Verification report shows <80% claims verified

**Causes**:
1. Many claims can't be automatically verified (e.g., "system is fast")
2. Files referenced in claims don't exist
3. Claim patterns don't match actual claim phrasing

**Solutions**:
1. Review unverified claims - are they verifiable?
2. Update claim patterns to match your writing style:
   ```yaml
   file_exists:
     - 'Created file `([^`]+)`'  # Add pattern for "Created" phrasing
   ```
3. Manually verify unverified claims and mark explicitly:
   ```markdown
   ✓ **Verified manually**: System performance is acceptable
       (tested with load test on 2025-06-11, avg latency 45ms)
   ```

### False Failures

**Symptom**: Claim marked as failed but is actually correct

**Causes**:
1. Line count tolerance too strict
2. File path case sensitivity (Windows vs Linux)
3. Verification timing (file created after claim extraction)

**Solutions**:
1. Increase tolerance in config:
   ```yaml
   line_count_check:
     tolerance_percentage: 10  # Allow ±10% instead of ±5%
   ```
2. Normalize file paths (use lowercase in claims)
3. Run verification after all file operations complete

### Can't Parse Claims

**Symptom**: Dry-run shows 0 claims found

**Causes**:
1. Claim patterns don't match document phrasing
2. Documents use different markup (no backticks)
3. Claims stated implicitly, not explicitly

**Solutions**:
1. Test patterns against sample text:
   ```bash
   echo 'File `test.py` exists' | grep -P 'File\s+`([^`]+)`\s+exists'
   ```
2. Add patterns for your markup style
3. Rephrase claims to be explicit:
   - Bad: "The monitoring script works"
   - Good: "File `scripts/monitor.py` exists with 213 lines"

## Examples

### Example 1: Verify Readiness Analysis

```bash
$ python scripts/verify_analysis.py reports/readiness.md --verify

======================================================================
ANALYSIS VERIFICATION REPORT
======================================================================
Document: reports/readiness.md

SUMMARY
----------------------------------------------------------------------
Total claims found: 15
Verified claims:    12 (80.0%)
Unverified claims:  2
Failed claims:      1

✓ VERIFICATION PASSED

UNVERIFIED/FAILED CLAIMS
----------------------------------------------------------------------
✗ [file_exists] docs/FAQ.md
  Location: line 142
  Expected: File exists
  Actual:   File NOT FOUND
  Evidence: File not found at docs/FAQ.md

! [line_count] docs/QUICK_START.md
  Location: line 138
  Expected: 230 lines
  Actual:   89 lines (does NOT match claim of 230)
  Evidence: Line count mismatch: actual 89, claimed 230

======================================================================

# Exit code: 1 (failed due to unverified claim about FAQ.md)
```

### Example 2: Dry-Run Before Verification

```bash
$ python scripts/verify_analysis.py reports/draft_analysis.md --dry-run

Document: reports/draft_analysis.md
Claims found: 8

1. [file_exists] scripts/quality_gate.py
   Location: line 12
   Expected: File exists
   Verification method: filesystem_check

2. [line_count] scripts/quality_gate.py
   Location: line 12
   Expected: 300 lines
   Verification method: line_count_check

3. [file_missing] docs/FAQ.md
   Location: line 45
   Expected: File missing
   Verification method: filesystem_check

... (remaining claims)
```

### Example 3: JSON Output for CI/CD

```bash
$ python scripts/verify_analysis.py reports/readiness.md \\
    --verify \\
    --format json \\
    --output reports/verification.json

$ cat reports/verification.json | jq '.verification_passed'
true

$ cat reports/verification.json | jq '.verified_claims'
12

# Use in CI pipeline
if [ $(jq '.verification_passed' reports/verification.json) == "true" ]; then
    echo "Analysis verified - safe to publish"
else
    echo "Analysis has unverified claims - review required"
    exit 1
fi
```

## Best Practices

1. **Verify before publishing** - Make verification the last step before publishing analysis

2. **State assumptions explicitly** - If you can't verify something, say so:
   ```markdown
   ⚠️ **Assumption**: Backup restore works (not tested, HIGH priority to verify)
   ```

3. **Use specific claims** - Vague claims can't be verified:
   - Bad: "Documentation is complete"
   - Good: "File `docs/FAQ.md` exists with 410 lines"

4. **Collect evidence** - Keep verification artifacts (test outputs, screenshots, logs)

5. **Update patterns** - As your writing style evolves, update claim patterns to match

6. **Target 90%+ verification rate** - 80% is minimum, but aim for 90%+ for production analysis

7. **Review unverified claims** - Don't ignore them, either verify manually or mark as assumptions

## Integration with Quality Gates

Verification framework complements quality gates:

- **Quality gates**: Validate deliverables against task specs (forward-looking)
- **Verification framework**: Validate analysis claims against reality (backward-looking)

**Combined workflow**:

```bash
# 1. Agent completes task
./run_agent.sh --task-spec task.md

# 2. Quality gate validates deliverables
./scripts/quality_gate_runner.sh --task-spec task.md --agent-id <id>

# 3. Write analysis of results
vim reports/task_analysis.md

# 4. Verify analysis claims
python scripts/verify_analysis.py reports/task_analysis.md --verify

# 5. Only publish if both pass
if [ quality_gate_passed ] && [ verification_passed ]; then
    cp reports/task_analysis.md published/
fi
```

## Metrics

Track verification metrics to improve analysis quality:

```bash
# Average verification rate
grep "Verified claims:" reports/verification_*.txt | \\
    awk -F'[()%]' '{sum+=$2; count++} END {print sum/count "%"}'

# Most common unverified claim types
grep "\\[.*\\]" reports/verification_*.txt | \\
    grep "!" | cut -d'[' -f2 | cut -d']' -f1 | \\
    sort | uniq -c | sort -rn

# Verification rate over time
for f in reports/verification_*.txt; do
    date=$(stat -c %y "$f" | cut -d' ' -f1)
    rate=$(grep "Verified claims:" "$f" | grep -oP '\d+\.\d+(?=%)')
    echo "$date,$rate"
done
```

## References

- **Configuration reference**: `config/verification_checklist.yaml`
- **Implementation**: `scripts/verify_analysis.py`
- **Test suite**: `tests/test_verify_analysis.py`
- **Quality gates integration**: `../guides/quality-gates.md`

---

**Last Updated**: 2025-12-11
**Version**: 1.0.0
**Status**: Production Ready
