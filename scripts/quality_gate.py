"""
Quality Gate for Agent Task Completion.

Validates deliverables against task specification before marking tasks complete.
Prevents incomplete work from passing as "done".
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml


@dataclass
class CheckResult:
    """Result of a single quality gate check."""
    check_name: str
    passed: bool
    expected: str
    actual: str
    severity: str = "CRITICAL"
    message: str = ""


@dataclass
class TaskSpec:
    """Parsed task specification."""
    task_id: str
    deliverables: List[Dict[str, any]]
    acceptance_checks: List[str]
    min_lines: Dict[str, Tuple[int, int]]  # file -> (min, max)


def parse_task_spec(spec_path: Path) -> TaskSpec:
    """
    Parse task specification markdown to extract deliverables and acceptance criteria.

    Args:
        spec_path: Path to task spec markdown file

    Returns:
        TaskSpec object with parsed information
    """
    content = spec_path.read_text(encoding='utf-8')

    # Extract task ID from filename or first heading
    task_id = spec_path.stem
    match = re.search(r'#\s+(.+)', content)
    if match:
        task_id = match.group(1).strip()

    # Extract deliverables section
    deliverables = []
    deliverables_match = re.search(
        r'\*\*Deliverables\*\*:?\s*(.*?)(?=\*\*[A-Z]|\Z)',
        content,
        re.DOTALL | re.IGNORECASE
    )

    if deliverables_match:
        deliverables_text = deliverables_match.group(1)
        # Parse numbered deliverable items
        for item_match in re.finditer(
            r'^\s*\d+\.\s+\*\*(.+?)\*\*\s*\((\d+)-(\d+)\s+lines\)',
            deliverables_text,
            re.MULTILINE
        ):
            filepath = item_match.group(1).strip()
            min_lines = int(item_match.group(2))
            max_lines = int(item_match.group(3))
            deliverables.append({
                'file': filepath,
                'min_lines': min_lines,
                'max_lines': max_lines
            })

    # Extract acceptance checks
    acceptance_checks = []
    acceptance_match = re.search(
        r'\*\*Acceptance checks\*\*:?\s*```bash\s*(.*?)```',
        content,
        re.DOTALL | re.IGNORECASE
    )

    if acceptance_match:
        checks_text = acceptance_match.group(1)
        # Extract each check line (ignore comments)
        for line in checks_text.split('\n'):
            line = line.strip()
            if line and not line.startswith('#'):
                acceptance_checks.append(line)

    # Build min_lines dictionary
    min_lines = {}
    for deliv in deliverables:
        min_lines[deliv['file']] = (deliv['min_lines'], deliv['max_lines'])

    return TaskSpec(
        task_id=task_id,
        deliverables=deliverables,
        acceptance_checks=acceptance_checks,
        min_lines=min_lines
    )


def check_file_exists(filepath: str, project_root: Path) -> CheckResult:
    """Check if a deliverable file exists."""
    file_path = project_root / filepath

    exists = file_path.exists()
    return CheckResult(
        check_name=f"file_exists:{filepath}",
        passed=exists,
        expected=f"File exists: {filepath}",
        actual=f"File {'exists' if exists else 'MISSING'}",
        severity="CRITICAL",
        message=f"File {filepath} {'found' if exists else 'not found'}"
    )


def check_line_count(filepath: str, min_lines: int, max_lines: int, project_root: Path) -> CheckResult:
    """Check if file meets line count requirements."""
    file_path = project_root / filepath

    if not file_path.exists():
        return CheckResult(
            check_name=f"line_count:{filepath}",
            passed=False,
            expected=f"{min_lines}-{max_lines} lines",
            actual="File missing",
            severity="CRITICAL",
            message=f"Cannot check line count: file {filepath} missing"
        )

    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            actual_lines = len(f.readlines())

        passed = min_lines <= actual_lines <= max_lines

        return CheckResult(
            check_name=f"line_count:{filepath}",
            passed=passed,
            expected=f"{min_lines}-{max_lines} lines",
            actual=f"{actual_lines} lines",
            severity="HIGH" if not passed else "PASS",
            message=f"File {filepath}: {actual_lines} lines (expected {min_lines}-{max_lines})"
        )
    except Exception as e:
        return CheckResult(
            check_name=f"line_count:{filepath}",
            passed=False,
            expected=f"{min_lines}-{max_lines} lines",
            actual=f"Error: {str(e)}",
            severity="CRITICAL",
            message=f"Failed to read {filepath}: {str(e)}"
        )


def load_config(config_path: Path) -> dict:
    """Load quality gate configuration from YAML."""
    if not config_path.exists():
        # Return default config
        return {
            'severity_levels': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
            'blocking_severities': ['CRITICAL', 'HIGH'],
            'test_timeout_seconds': 300
        }

    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def generate_report(
    task_spec: TaskSpec,
    results: List[CheckResult],
    config: dict
) -> Tuple[str, bool]:
    """
    Generate quality gate report.

    Returns:
        Tuple of (report_text, all_passed)
    """
    blocking_severities = config.get('blocking_severities', ['CRITICAL', 'HIGH'])

    # Categorize results
    passed_checks = [r for r in results if r.passed]
    failed_checks = [r for r in results if not r.passed]

    blocking_failures = [
        r for r in failed_checks
        if r.severity in blocking_severities
    ]

    all_passed = len(blocking_failures) == 0

    # Build report
    lines = []
    lines.append("=" * 70)
    lines.append("QUALITY GATE REPORT")
    lines.append("=" * 70)
    lines.append(f"Task: {task_spec.task_id}")
    lines.append("")

    # Summary
    lines.append("SUMMARY")
    lines.append("-" * 70)
    lines.append(f"Total checks: {len(results)}")
    lines.append(f"Passed: {len(passed_checks)}")
    lines.append(f"Failed: {len(failed_checks)}")
    lines.append(f"Blocking failures: {len(blocking_failures)}")
    lines.append("")

    if all_passed:
        lines.append("✓ QUALITY GATE PASSED")
    else:
        lines.append("✗ QUALITY GATE FAILED")

    lines.append("")

    # Failed checks
    if failed_checks:
        lines.append("FAILED CHECKS")
        lines.append("-" * 70)
        for result in failed_checks:
            marker = "✗ BLOCKER" if result.severity in blocking_severities else "! WARNING"
            lines.append(f"{marker} [{result.severity}] {result.check_name}")
            lines.append(f"  Expected: {result.expected}")
            lines.append(f"  Actual:   {result.actual}")
            lines.append(f"  Message:  {result.message}")
            lines.append("")

    # Passed checks
    if passed_checks:
        lines.append("PASSED CHECKS")
        lines.append("-" * 70)
        for result in passed_checks:
            lines.append(f"✓ {result.check_name}")
        lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines), all_passed


def run_quality_gate(
    task_spec_path: Path,
    agent_id: Optional[str] = None,
    project_root: Optional[Path] = None,
    config_path: Optional[Path] = None,
    output_format: str = "text"
) -> Tuple[List[CheckResult], bool]:
    """
    Run quality gate validation.

    Args:
        task_spec_path: Path to task specification
        agent_id: Optional agent ID for logging
        project_root: Project root directory (default: current working directory)
        config_path: Path to config file
        output_format: Output format (text, json, yaml)

    Returns:
        Tuple of (results, all_passed)
    """
    if project_root is None:
        project_root = Path.cwd()

    if config_path is None:
        config_path = project_root / "config" / "quality_gate_config.yaml"

    # Load configuration
    config = load_config(config_path)

    # Parse task spec
    task_spec = parse_task_spec(task_spec_path)

    # Run checks
    results = []

    # Check file existence for all deliverables
    for deliv in task_spec.deliverables:
        filepath = deliv['file']
        result = check_file_exists(filepath, project_root)
        results.append(result)

    # Check line counts for files that exist
    for deliv in task_spec.deliverables:
        filepath = deliv['file']
        min_lines = deliv['min_lines']
        max_lines = deliv['max_lines']
        result = check_line_count(filepath, min_lines, max_lines, project_root)
        results.append(result)

    # Determine if gate passed
    blocking_severities = config.get('blocking_severities', ['CRITICAL', 'HIGH'])
    blocking_failures = [
        r for r in results
        if not r.passed and r.severity in blocking_severities
    ]
    all_passed = len(blocking_failures) == 0

    return results, all_passed


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Quality gate validation for agent task completion"
    )
    parser.add_argument(
        "--task-spec",
        required=True,
        help="Path to task specification markdown file"
    )
    parser.add_argument(
        "--agent-id",
        help="Agent ID for logging"
    )
    parser.add_argument(
        "--config",
        help="Path to quality gate config file"
    )
    parser.add_argument(
        "--output",
        help="Output report file path"
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "yaml"],
        default="text",
        help="Output format"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be checked without executing"
    )

    args = parser.parse_args()

    task_spec_path = Path(args.task_spec)
    if not task_spec_path.exists():
        print(f"Error: Task spec not found: {task_spec_path}", file=sys.stderr)
        return 2

    project_root = Path.cwd()
    config_path = Path(args.config) if args.config else None

    if args.dry_run:
        # Just show what would be checked
        task_spec = parse_task_spec(task_spec_path)
        print(f"Task: {task_spec.task_id}")
        print(f"Deliverables to check: {len(task_spec.deliverables)}")
        for deliv in task_spec.deliverables:
            print(f"  - {deliv['file']} ({deliv['min_lines']}-{deliv['max_lines']} lines)")
        print(f"Acceptance checks: {len(task_spec.acceptance_checks)}")
        return 0

    # Run quality gate
    results, all_passed = run_quality_gate(
        task_spec_path,
        agent_id=args.agent_id,
        project_root=project_root,
        config_path=config_path,
        output_format=args.format
    )

    # Load config for report generation
    if config_path is None:
        config_path = project_root / "config" / "quality_gate_config.yaml"
    config = load_config(config_path)

    # Parse task spec for report
    task_spec = parse_task_spec(task_spec_path)

    # Generate report
    if args.format == "json":
        report_data = {
            'task_id': task_spec.task_id,
            'passed': all_passed,
            'checks': [
                {
                    'name': r.check_name,
                    'passed': r.passed,
                    'expected': r.expected,
                    'actual': r.actual,
                    'severity': r.severity,
                    'message': r.message
                }
                for r in results
            ]
        }
        report_text = json.dumps(report_data, indent=2)
    elif args.format == "yaml":
        report_data = {
            'task_id': task_spec.task_id,
            'passed': all_passed,
            'checks': [
                {
                    'name': r.check_name,
                    'passed': r.passed,
                    'expected': r.expected,
                    'actual': r.actual,
                    'severity': r.severity,
                    'message': r.message
                }
                for r in results
            ]
        }
        report_text = yaml.dump(report_data)
    else:
        report_text, _ = generate_report(task_spec, results, config)

    # Output report
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report_text)
        print(f"Report written to: {output_path}")
    else:
        print(report_text)

    # Exit with appropriate code
    if all_passed:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
