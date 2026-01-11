# Alerting Thresholds - Custom Run ID Feature

**Feature**: Custom Run ID (v2.1.0)
**Last Updated**: 2026-01-01
**Version**: 1.0

---

## Overview

This document defines production alerting thresholds for the custom run_id feature. All thresholds are based on realistic production estimates and RunIDMetrics implementation analysis.

**Purpose**: Enable operators to detect and respond to issues before they impact business operations.

**Scope**: Covers all metrics tracked by RunIDMetrics class (src/telemetry/client.py:39-150).

---

## Metrics and Thresholds

### 1. Validation Rejection Rate

**Metric**: `rejected_* / total_requests * 100`

**Calculation**:
```
rejection_rate = (rejected_empty + rejected_too_long + rejected_invalid_chars) / total_requests * 100
```

**Thresholds**:
- **Normal**: 0-2% (occasional malformed requests)
- **Warning**: 2-10% (unusual but not critical, investigate)
- **Critical**: >10% (likely client issue or attack)

**Rationale**:

Most custom run_ids should be valid since they are developer-controlled, not user input. The validation rules are simple and well-documented:
- Not empty/whitespace
- Maximum 255 characters
- No path separators (/, \) or null bytes

A normal baseline of 0-2% allows for occasional client bugs during development or edge cases. This represents ~20 rejections per 1000 requests, which is noticeable but expected.

High rejection rates indicate:
- **2-10% (Warning)**: Client misconfiguration or recent deployment issue
  - Likely a single client with a bug
  - May resolve automatically with client rollback
  - Requires investigation within 1-2 hours

- **>10% (Critical)**: Systematic client bug or attack
  - Multiple clients affected OR single client with severe bug
  - Possible injection attack (path traversal attempts)
  - Requires immediate investigation and potential client blocking

**Alert Action**:
- **Warning**:
  - Review logs for common rejection patterns
  - Identify which rejection type is most common
  - Contact affected client teams
  - Timeline: Investigate within 2 hours

- **Critical**:
  - Review logs for attack patterns (rejected_invalid_chars spike)
  - Check for client bugs (rejected_empty or rejected_too_long spike)
  - Review recent client deployments
  - Contact client teams immediately
  - Consider blocking affected clients if attack suspected
  - Timeline: Respond within 15 minutes

---

### 2. Duplicate Detection Rate

**Metric**: `duplicates_detected / total_requests * 100`

**Thresholds**:
- **Normal**: 0-0.1% (rare concurrency edge cases)
- **Warning**: 0.1-1% (possible client issue)
- **Critical**: >1% (likely client bug or logic error)

**Rationale**:

Duplicates should be extremely rare in production:
- **Generated run_ids**: UUID v4 collision probability is ~10^-18 (mathematically impossible)
- **Custom run_ids**: Clients should track active runs and avoid reuse

A normal baseline of 0-0.1% allows for 1 duplicate per 1000 runs, accounting for rare race conditions when multiple processes start runs simultaneously.

High duplicate rates indicate:
- **0.1-1% (Warning)**: Possible client issue
  - Client not properly tracking active runs
  - Concurrent processes using same run_id prefix
  - Run_id generation logic may be flawed

- **>1% (Critical)**: Systematic client bug
  - Client reusing run_ids across restarts
  - Client using hardcoded or predictable run_ids
  - Database constraint may be violated if duplicates increase

**Alert Action**:
- **Warning**:
  - Review logs for duplicate patterns (which run_ids are duplicating?)
  - Check if duplicates are from custom or generated run_ids
  - Contact client teams to review run_id generation logic
  - Timeline: Investigate within 4 hours

- **Critical**:
  - Identify affected clients immediately
  - Review client run_id generation code
  - Check duplicate detection logic (verify not a telemetry bug)
  - Contact client teams for emergency fix
  - Monitor for database constraint violations
  - Timeline: Respond within 30 minutes

---

### 3. Custom Run ID Adoption Rate

**Metric**: `custom_accepted / total_requests * 100`

**Thresholds**:
- **Normal**: Depends on rollout plan
  - **Phase 1** (SEO Intelligence only): 5-15%
  - **Phase 2** (Multiple clients): 50-80%
  - **Phase 3** (Full adoption): >80%
- **Warning**: <expected_phase_rate - 20%
- **Critical**: Sudden drop >50% from baseline

**Rationale**:

Custom run_id adoption is opt-in and controlled by client teams. The expected adoption rate varies by rollout phase:

- **Phase 1**: Only SEO Intelligence uses custom run_ids. Expected 5-15% of all runs.
- **Phase 2**: Multiple clients migrated. Expected 50-80% of all runs.
- **Phase 3**: All clients using custom run_ids. Expected >80% of all runs.

Thresholds track trend changes, not absolute values. Compare to 1-hour baseline to detect sudden drops.

Sudden drops indicate:
- **>20% drop from baseline (Warning)**:
  - Client team rolled back feature
  - Validation rules too strict (rejecting valid IDs)
  - Client deployment issue

- **>50% drop from baseline (Critical)**:
  - Feature regression in telemetry client
  - Validation logic bug rejecting all custom IDs
  - Multiple clients rolled back simultaneously
  - Possible telemetry system outage

**Alert Action**:
- **Warning**:
  - Check if validation rejection rate also increased (correlated?)
  - Contact client teams to verify if intentional rollback
  - Review recent telemetry client changes
  - Timeline: Investigate within 2 hours

- **Critical**:
  - Emergency investigation - possible telemetry regression
  - Check for validation logic bugs
  - Review recent deployments (telemetry client or API)
  - Contact all client teams to verify status
  - Prepare rollback plan if telemetry bug confirmed
  - Timeline: Respond within 15 minutes

---

### 4. Generated Run ID Fallback Rate

**Metric**: `generated / total_requests * 100`

**Thresholds**:
- **Normal**: Inverse of custom adoption (see Metric 3)
  - Phase 1: 85-95%
  - Phase 2: 20-50%
  - Phase 3: <20%
- **Warning**: Sudden increase >20%
- **Critical**: Sudden increase >50%

**Rationale**:

The generated run_id fallback rate is the inverse of custom adoption. Increases in fallback rate indicate custom run_ids are being rejected or clients stopped providing them.

This metric correlates with validation rejection rate and custom adoption rate. Use it to confirm issues detected by other metrics.

Sudden increases indicate:
- **>20% increase (Warning)**:
  - Custom IDs rejected due to validation
  - Client stopped providing custom IDs (rollback)
  - Client deployment issue

- **>50% increase (Critical)**:
  - Feature regression in telemetry
  - Validation too strict
  - Multiple clients affected

**Alert Action**:
- **Warning**:
  - Correlate with rejection rate metrics
  - If rejection rate also high: validation issue
  - If rejection rate normal: clients stopped using feature
  - Timeline: Investigate within 2 hours

- **Critical**:
  - Correlate with custom adoption drop
  - Check for feature regression
  - Review validation logic
  - Timeline: Respond within 15 minutes

---

### 5. Specific Rejection Reasons

Track each rejection type separately to identify patterns and root causes.

#### 5a. Empty/Whitespace Rejections

**Metric**: `rejected_empty / total_requests * 100`

**Thresholds**:
- **Normal**: <0.5%
- **Warning**: 0.5-2%
- **Critical**: >2%

**Indicates**: Client sending empty strings, likely client-side validation bug

**Validation Code** (src/telemetry/client.py:436):
```python
if not run_id or not run_id.strip():
    return False, "empty"
```

**Alert Action**:
- Review logs for clients sending empty run_ids
- Contact client teams to add client-side validation
- Likely a recent client deployment bug

#### 5b. Too Long Rejections

**Metric**: `rejected_too_long / total_requests * 100`

**Thresholds**:
- **Normal**: <0.1%
- **Warning**: 0.1-1%
- **Critical**: >1%

**Indicates**: Client generating IDs >255 chars, format issue

**Validation Code** (src/telemetry/client.py:443):
```python
if len(run_id) > MAX_RUN_ID_LENGTH:  # MAX_RUN_ID_LENGTH = 255
    return False, "too_long"
```

**Alert Action**:
- Review logs for run_id lengths being generated
- Contact client teams to fix run_id format
- Typical custom run_id: 30-50 chars (should be nowhere near 255)

#### 5c. Invalid Characters Rejections

**Metric**: `rejected_invalid_chars / total_requests * 100`

**Thresholds**:
- **Normal**: <0.1%
- **Warning**: 0.1-1%
- **Critical**: >1%

**Indicates**: Client including path separators/null bytes, possible attack

**Validation Code** (src/telemetry/client.py:451):
```python
if '/' in run_id or '\\' in run_id or '\x00' in run_id:
    return False, "invalid_chars"
```

**Security Implications**:
- Path separators (/, \) could enable directory traversal
- Null bytes (\x00) could enable string termination attacks
- This validation is a security control

**Alert Action**:
- **Warning**: Review logs for invalid characters being used
- **Critical**: Treat as possible attack
  - Review which clients are sending invalid characters
  - Check for attack patterns (scanning, injection)
  - Consider blocking affected clients
  - Escalate to security team if attack suspected

---

## Baseline Establishment

**Post-Deployment Actions**:

### Week 1: Monitor without alerting
- Collect baseline metrics hourly
- Calculate mean, median, p95, p99 for each metric
- Identify normal ranges and daily patterns
- Document actual baselines vs predicted baselines
- Adjust thresholds if reality differs significantly

**Expected Baselines** (Phase 1: SEO Intelligence only):
```
custom_accepted:      100/day  (10%)
generated:            900/day  (90%)
rejected_empty:       1/day    (0.1%)
rejected_too_long:    0/day    (0%)
rejected_invalid_chars: 0/day  (0%)
duplicates_detected:  0-1/day  (0.01%)
total_requests:       1000/day
```

### Week 2: Enable warning alerts only
- Validate thresholds are reasonable
- Tune false positive rate
- Adjust timeframes (5-15 min) if needed
- Document any threshold adjustments made

### Week 3+: Enable all alerts
- Full production monitoring (warning + critical)
- Continuous threshold refinement based on incidents
- Monthly review of alert effectiveness
- Update documentation with lessons learned

---

## Example Alert Configurations

### Prometheus Alert Rules

**File**: `/etc/prometheus/rules/custom_run_id_alerts.yml`

```yaml
groups:
  - name: custom_run_id_alerts
    interval: 60s
    rules:
      # Validation Rejection Rate - Critical
      - alert: HighRunIDRejectionRate
        expr: |
          (
            sum(rate(run_id_metrics_rejected_empty[5m])) +
            sum(rate(run_id_metrics_rejected_too_long[5m])) +
            sum(rate(run_id_metrics_rejected_invalid_chars[5m]))
          ) / sum(rate(run_id_metrics_total_requests[5m])) * 100 > 10
        for: 5m
        labels:
          severity: critical
          component: telemetry
        annotations:
          summary: "High run_id rejection rate: {{ $value | humanize }}%"
          description: "Custom run_id rejection rate is {{ $value | humanize }}%, exceeds 10% critical threshold"
          runbook_url: "https://docs.example.com/runbooks/custom-run-id-high-rejections"

      # Validation Rejection Rate - Warning
      - alert: ElevatedRunIDRejectionRate
        expr: |
          (
            sum(rate(run_id_metrics_rejected_empty[5m])) +
            sum(rate(run_id_metrics_rejected_too_long[5m])) +
            sum(rate(run_id_metrics_rejected_invalid_chars[5m]))
          ) / sum(rate(run_id_metrics_total_requests[5m])) * 100 > 2
        for: 10m
        labels:
          severity: warning
          component: telemetry
        annotations:
          summary: "Elevated run_id rejection rate: {{ $value | humanize }}%"
          description: "Custom run_id rejection rate is {{ $value | humanize }}%, exceeds 2% warning threshold"

      # Duplicate Detection Rate - Critical
      - alert: HighDuplicateRunIDRate
        expr: |
          sum(rate(run_id_metrics_duplicates_detected[5m])) / sum(rate(run_id_metrics_total_requests[5m])) * 100 > 1
        for: 5m
        labels:
          severity: critical
          component: telemetry
        annotations:
          summary: "High duplicate run_id rate: {{ $value | humanize }}%"
          description: "Duplicate run_id rate is {{ $value | humanize }}%, exceeds 1% critical threshold"
          runbook_url: "https://docs.example.com/runbooks/duplicate-run-ids"

      # Duplicate Detection Rate - Warning
      - alert: ElevatedDuplicateRunIDRate
        expr: |
          sum(rate(run_id_metrics_duplicates_detected[5m])) / sum(rate(run_id_metrics_total_requests[5m])) * 100 > 0.1
        for: 10m
        labels:
          severity: warning
          component: telemetry
        annotations:
          summary: "Elevated duplicate run_id rate: {{ $value | humanize }}%"
          description: "Duplicate run_id rate is {{ $value | humanize }}%, exceeds 0.1% warning threshold"

      # Custom Run ID Adoption Drop - Critical
      - alert: CustomRunIDAdoptionDropCritical
        expr: |
          (
            sum(rate(run_id_metrics_custom_accepted[5m])) / sum(rate(run_id_metrics_total_requests[5m])) * 100
          ) <
          (
            sum(rate(run_id_metrics_custom_accepted[1h] offset 1h)) / sum(rate(run_id_metrics_total_requests[1h] offset 1h)) * 100
          ) * 0.5
        for: 15m
        labels:
          severity: critical
          component: telemetry
        annotations:
          summary: "Custom run_id adoption dropped >50%"
          description: "Custom run_id usage dropped >50% compared to 1 hour ago, possible telemetry regression"
          runbook_url: "https://docs.example.com/runbooks/custom-run-id-adoption-drop"

      # Custom Run ID Adoption Drop - Warning
      - alert: CustomRunIDAdoptionDropWarning
        expr: |
          (
            sum(rate(run_id_metrics_custom_accepted[5m])) / sum(rate(run_id_metrics_total_requests[5m])) * 100
          ) <
          (
            sum(rate(run_id_metrics_custom_accepted[1h] offset 1h)) / sum(rate(run_id_metrics_total_requests[1h] offset 1h)) * 100
          ) * 0.8
        for: 15m
        labels:
          severity: warning
          component: telemetry
        annotations:
          summary: "Custom run_id adoption dropped >20%"
          description: "Custom run_id usage dropped >20% compared to 1 hour ago"

      # Invalid Characters Security Alert
      - alert: InvalidCharactersInRunID
        expr: |
          sum(rate(run_id_metrics_rejected_invalid_chars[5m])) / sum(rate(run_id_metrics_total_requests[5m])) * 100 > 0.1
        for: 5m
        labels:
          severity: warning
          component: telemetry
          security: true
        annotations:
          summary: "Invalid characters detected in run_ids"
          description: "Run_ids with path separators or null bytes detected, possible attack. Rate: {{ $value | humanize }}%"
          runbook_url: "https://docs.example.com/runbooks/security-invalid-run-ids"
```

---

### Grafana Alert Example

**Dashboard**: Custom Run ID Metrics

```json
{
  "alert": {
    "name": "High Run ID Rejection Rate",
    "conditions": [
      {
        "evaluator": {
          "params": [10],
          "type": "gt"
        },
        "operator": {
          "type": "and"
        },
        "query": {
          "params": ["A", "5m", "now"]
        },
        "reducer": {
          "params": [],
          "type": "avg"
        },
        "type": "query"
      }
    ],
    "executionErrorState": "alerting",
    "for": "5m",
    "frequency": "1m",
    "handler": 1,
    "message": "Custom run_id rejection rate exceeds 10% critical threshold. Review logs for rejection patterns and contact affected client teams.",
    "name": "High Run ID Rejection Rate",
    "noDataState": "no_data",
    "notifications": [
      {
        "uid": "pagerduty-critical"
      }
    ]
  },
  "targets": [
    {
      "expr": "(sum(rate(run_id_metrics_rejected_empty[5m])) + sum(rate(run_id_metrics_rejected_too_long[5m])) + sum(rate(run_id_metrics_rejected_invalid_chars[5m]))) / sum(rate(run_id_metrics_total_requests[5m])) * 100",
      "refId": "A"
    }
  ]
}
```

---

### Datadog Monitor Configuration

**Monitor Type**: Metric Alert

```yaml
name: "High Custom Run ID Rejection Rate"
type: "metric alert"
query: |
  sum(last_5m):
    (
      sum:telemetry.run_id_metrics.rejected_empty{*}.as_rate() +
      sum:telemetry.run_id_metrics.rejected_too_long{*}.as_rate() +
      sum:telemetry.run_id_metrics.rejected_invalid_chars{*}.as_rate()
    ) /
    sum:telemetry.run_id_metrics.total_requests{*}.as_rate()
    * 100 > 10
message: |
  {{#is_alert}}
  CRITICAL: Custom run_id rejection rate is {{value}}%, exceeds 10% threshold.

  Actions:
  1. Review logs for rejection patterns
  2. Check which rejection type is most common
  3. Contact affected client teams
  4. Review recent client deployments

  Runbook: https://docs.example.com/runbooks/custom-run-id-high-rejections
  {{/is_alert}}

  {{#is_warning}}
  WARNING: Custom run_id rejection rate is {{value}}%, exceeds 2% threshold.
  Investigate within 2 hours.
  {{/is_warning}}
tags:
  - component:telemetry
  - feature:custom-run-id
  - severity:critical
options:
  thresholds:
    critical: 10
    warning: 2
  notify_no_data: false
  no_data_timeframe: 10
  renotify_interval: 60
  notify_audit: true
  include_tags: true
```

---

### CloudWatch Alarm Configuration

**AWS CLI Example**:

```bash
# Critical: High Rejection Rate
aws cloudwatch put-metric-alarm \
  --alarm-name "telemetry-high-run-id-rejection-rate" \
  --alarm-description "Custom run_id rejection rate exceeds 10%" \
  --metric-name RejectionRate \
  --namespace Telemetry/RunID \
  --statistic Average \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 10.0 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:critical-alerts

# Warning: Elevated Rejection Rate
aws cloudwatch put-metric-alarm \
  --alarm-name "telemetry-elevated-run-id-rejection-rate" \
  --alarm-description "Custom run_id rejection rate exceeds 2%" \
  --metric-name RejectionRate \
  --namespace Telemetry/RunID \
  --statistic Average \
  --period 600 \
  --evaluation-periods 1 \
  --threshold 2.0 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:warning-alerts

# Critical: High Duplicate Rate
aws cloudwatch put-metric-alarm \
  --alarm-name "telemetry-high-duplicate-run-id-rate" \
  --alarm-description "Duplicate run_id rate exceeds 1%" \
  --metric-name DuplicateRate \
  --namespace Telemetry/RunID \
  --statistic Average \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 1.0 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:123456789012:critical-alerts
```

**Metric Publishing Example** (Python):

```python
import boto3

cloudwatch = boto3.client('cloudwatch')

# Publish run_id metrics to CloudWatch
def publish_run_id_metrics(metrics):
    """
    Publish RunIDMetrics to CloudWatch.

    Args:
        metrics: Dict from client.get_run_id_metrics()
    """
    run_id_metrics = metrics['run_id_metrics']

    # Calculate rates
    total = run_id_metrics['total_runs']
    if total > 0:
        rejection_rate = (run_id_metrics['rejected']['total'] / total) * 100
        duplicate_rate = (run_id_metrics['duplicates_detected'] / total) * 100
        custom_percentage = run_id_metrics['custom_percentage']
    else:
        rejection_rate = 0
        duplicate_rate = 0
        custom_percentage = 0

    # Put metrics
    cloudwatch.put_metric_data(
        Namespace='Telemetry/RunID',
        MetricData=[
            {
                'MetricName': 'RejectionRate',
                'Value': rejection_rate,
                'Unit': 'Percent'
            },
            {
                'MetricName': 'DuplicateRate',
                'Value': duplicate_rate,
                'Unit': 'Percent'
            },
            {
                'MetricName': 'CustomAdoptionRate',
                'Value': custom_percentage,
                'Unit': 'Percent'
            },
            {
                'MetricName': 'TotalRequests',
                'Value': total,
                'Unit': 'Count'
            }
        ]
    )
```

---

## Dashboard Integration

See [grafana-dashboard.json](grafana-dashboard.json) for complete dashboard configuration including threshold visualizations.

**Dashboard Panels Should Include**:
1. Rejection Rate (with 2% and 10% threshold lines)
2. Duplicate Rate (with 0.1% and 1% threshold lines)
3. Custom Adoption Rate (with phase-based baseline)
4. Rejection Reasons Breakdown (bar chart)
5. Total Requests (stat panel)

---

## Runbook Links

**Alert Runbooks** (to be created):
1. High Run ID Rejection Rate: `/runbooks/custom-run-id-high-rejections.md`
2. Duplicate Run IDs: `/runbooks/duplicate-run-ids.md`
3. Custom Run ID Adoption Drop: `/runbooks/custom-run-id-adoption-drop.md`
4. Invalid Characters Security: `/runbooks/security-invalid-run-ids.md`

**Each runbook should contain**:
- Alert description and severity
- Investigation steps (what to check first)
- Common root causes
- Resolution actions
- Escalation criteria
- Examples from production

---

## Monitoring Best Practices

### 1. Use Percentages, Not Absolute Counts
- Scales with traffic volume
- Prevents false positives during low-traffic periods
- Enables consistent thresholds across environments

### 2. Require Sustained Breaches
- Use `for: 5m` or `for: 10m` in alerts
- Prevents alerting on transient spikes
- Reduces alert fatigue

### 3. Implement Alert Tiers
- **Warning**: Investigate within 2-4 hours (email, Slack)
- **Critical**: Respond within 15-30 minutes (paging)
- Don't page for everything

### 4. Correlate Metrics
- High rejection rate + high rejected_invalid_chars = possible attack
- High rejection rate + adoption drop = validation too strict
- High duplicate rate + high custom_accepted = client bug

### 5. Establish Baselines
- Don't trust predicted thresholds blindly
- Collect 1-2 weeks of data before full alerting
- Adjust thresholds based on reality

### 6. Review Alerts Monthly
- Are we getting false positives?
- Are we missing real issues?
- Do thresholds need tuning?
- Update documentation with lessons learned

---

## Maintenance Schedule

**Weekly**:
- Review alert frequency (too many? too few?)
- Check for new patterns in rejection reasons

**Monthly**:
- Review and tune thresholds based on incidents
- Update this document with lessons learned
- Verify runbook links are current

**Quarterly**:
- Comprehensive threshold review
- Compare actual baselines to documented baselines
- Update rollout phase expectations

**After Incidents**:
- Document what threshold detected (or missed) the issue
- Update thresholds if needed
- Add incident examples to runbooks

---

## Document Metadata

**Document Version**: 1.0
**Feature Version**: v2.1.0
**Created**: 2026-01-01
**Last Reviewed**: 2026-01-01
**Next Review**: 2026-02-01
**Owner**: SRE Team
**Review Frequency**: Monthly (or after incidents)

---

## References

- **RunIDMetrics Implementation**: src/telemetry/client.py (lines 39-150)
- **Validation Logic**: src/telemetry/client.py (lines 416-458)
- **Schema Constraints**: docs/schema_constraints.md
- **Feature CHANGELOG**: reports/CHANGELOG.md
- **Dashboard Example**: docs/observability/grafana-dashboard.json
- **Agent Analysis**: reports/agents/agent-e/OB-01/evidence.md
