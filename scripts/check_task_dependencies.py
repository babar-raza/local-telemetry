#!/usr/bin/env python3
"""
Task Dependency Checker

Validates that all task dependencies are met before allowing task execution.
Checks prerequisite files, completed tasks, and environment variables.
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Dependencies:
    """Task dependencies extracted from spec."""
    files: List[str] = field(default_factory=list)
    tasks: List[str] = field(default_factory=list)
    env_vars: List[str] = field(default_factory=list)


@dataclass
class DependencyCheckResult:
    """Result of a dependency check."""
    dep_type: str  # 'file', 'task', 'env_var'
    name: str
    satisfied: bool
    details: str


def parse_task_spec_dependencies(spec_path: Path) -> Dependencies:
    """
    Parse task specification to extract dependencies.

    Looks for a **Dependencies** or **Prerequisites** section with format:
    - Files: path/to/file.py
    - Tasks: TASK-ID
    - Environment: VAR_NAME
    """
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to read task spec {spec_path}: {e}")

    deps = Dependencies()

    # Find dependencies section
    dep_section_pattern = r'(?:##\s+|\*\*)(Dependencies|Prerequisites)(?:\*\*)?[:\s]*\n(.*?)(?=\n##|\n\*\*|\Z)'
    match = re.search(dep_section_pattern, content, re.DOTALL | re.IGNORECASE)

    if not match:
        # No dependencies section found
        return deps

    dep_content = match.group(2)

    # Parse file dependencies
    file_pattern = r'[-*]\s+(?:Files?:|File dependency:)\s+`?([^`\n]+)`?'
    deps.files = re.findall(file_pattern, dep_content, re.IGNORECASE)

    # Parse task dependencies
    task_pattern = r'[-*]\s+(?:Tasks?:|Task dependency:)\s+`?([A-Z]+-[A-Z0-9-]+)`?'
    deps.tasks = re.findall(task_pattern, dep_content, re.IGNORECASE)

    # Parse environment variable dependencies
    env_pattern = r'[-*]\s+(?:Environment:|Env var:|ENV:)\s+`?([A-Z_][A-Z0-9_]*)`?'
    deps.env_vars = re.findall(env_pattern, dep_content, re.IGNORECASE)

    return deps


def check_file_dependencies(files: List[str], project_root: Path) -> List[DependencyCheckResult]:
    """Check that all required files exist."""
    results = []

    for filepath in files:
        file_path = project_root / filepath
        exists = file_path.exists()

        results.append(DependencyCheckResult(
            dep_type='file',
            name=filepath,
            satisfied=exists,
            details=f"File {'exists' if exists else 'MISSING'}: {file_path}"
        ))

    return results


def check_task_dependencies(tasks: List[str], project_root: Path) -> List[DependencyCheckResult]:
    """
    Check that all required tasks are completed.

    Looks for task completion markers in:
    1. TodoWrite logs
    2. Plan files with task status
    """
    results = []

    # Look for TodoWrite log
    todo_log_paths = [
        project_root / 'logs' / 'todo_updates.log',
        project_root / '.claude' / 'todo.log'
    ]

    todo_log = None
    for log_path in todo_log_paths:
        if log_path.exists():
            todo_log = log_path
            break

    for task_id in tasks:
        satisfied = False
        details = f"Task {task_id} not found in completion logs"

        # Check TodoWrite log if it exists
        if todo_log:
            try:
                with open(todo_log, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                    # Look for task completion markers
                    if re.search(rf'{re.escape(task_id)}.*completed', log_content, re.IGNORECASE):
                        satisfied = True
                        details = f"Task {task_id} marked completed in {todo_log}"
            except Exception:
                pass

        # Also check plan files for status markers
        if not satisfied:
            plan_dir = project_root / 'plans'
            if plan_dir.exists():
                for plan_file in plan_dir.rglob('*.md'):
                    try:
                        with open(plan_file, 'r', encoding='utf-8') as f:
                            content = f.read()
                            # Look for task ID with Done/Complete status
                            pattern = rf'\[{re.escape(task_id)}\].*?Status.*?(?:Done|Completed|✅)'
                            if re.search(pattern, content, re.DOTALL | re.IGNORECASE):
                                satisfied = True
                                details = f"Task {task_id} marked done in {plan_file}"
                                break
                    except Exception:
                        continue

        results.append(DependencyCheckResult(
            dep_type='task',
            name=task_id,
            satisfied=satisfied,
            details=details
        ))

    return results


def check_env_dependencies(env_vars: List[str]) -> List[DependencyCheckResult]:
    """Check that all required environment variables are set."""
    results = []

    for var_name in env_vars:
        value = os.environ.get(var_name)
        satisfied = value is not None

        results.append(DependencyCheckResult(
            dep_type='env_var',
            name=var_name,
            satisfied=satisfied,
            details=f"Environment variable {var_name} {'set' if satisfied else 'NOT SET'}"
        ))

    return results


def generate_dependency_report(
    deps: Dependencies,
    results: List[DependencyCheckResult],
    spec_path: Path
) -> Tuple[str, bool]:
    """
    Generate dependency check report.

    Returns:
        (report_text, all_satisfied)
    """
    satisfied = [r for r in results if r.satisfied]
    unsatisfied = [r for r in results if not r.satisfied]
    all_satisfied = len(unsatisfied) == 0

    report = []
    report.append("=" * 70)
    report.append("TASK DEPENDENCY CHECK")
    report.append("=" * 70)
    report.append(f"Task spec: {spec_path}")
    report.append("")

    report.append("SUMMARY")
    report.append("-" * 70)
    report.append(f"Total dependencies: {len(results)}")
    report.append(f"Satisfied: {len(satisfied)}")
    report.append(f"Unsatisfied: {len(unsatisfied)}")
    report.append("")

    if all_satisfied:
        report.append("✓ ALL DEPENDENCIES SATISFIED")
        report.append("")
    else:
        report.append("✗ UNSATISFIED DEPENDENCIES")
        report.append("-" * 70)

        # Group by type
        for dep_type in ['file', 'task', 'env_var']:
            type_unsatisfied = [r for r in unsatisfied if r.dep_type == dep_type]
            if type_unsatisfied:
                type_name = {
                    'file': 'File Dependencies',
                    'task': 'Task Dependencies',
                    'env_var': 'Environment Variables'
                }[dep_type]

                report.append(f"\n{type_name}:")
                for result in type_unsatisfied:
                    report.append(f"  ✗ {result.name}")
                    report.append(f"     {result.details}")

        report.append("")
        report.append("Task CANNOT proceed until dependencies are satisfied.")
        report.append("")

    # Show satisfied dependencies
    if satisfied:
        report.append("SATISFIED DEPENDENCIES")
        report.append("-" * 70)
        for result in satisfied:
            report.append(f"✓ {result.name} ({result.dep_type})")
        report.append("")

    report.append("=" * 70)

    return '\n'.join(report), all_satisfied


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check task dependencies before execution",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--task-spec',
        type=Path,
        required=True,
        help='Path to task specification file'
    )

    parser.add_argument(
        '--project-root',
        type=Path,
        default=Path.cwd(),
        help='Project root directory (default: current directory)'
    )

    parser.add_argument(
        '--report',
        type=Path,
        help='Save dependency report to file'
    )

    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.task_spec.exists():
        print(f"Error: Task spec not found: {args.task_spec}", file=sys.stderr)
        return 2

    # Parse dependencies from task spec
    print(f"Checking dependencies for: {args.task_spec}")
    deps = parse_task_spec_dependencies(args.task_spec)

    if not deps.files and not deps.tasks and not deps.env_vars:
        print("No dependencies found in task spec")
        return 0

    # Check dependencies
    results = []
    results.extend(check_file_dependencies(deps.files, args.project_root))
    results.extend(check_task_dependencies(deps.tasks, args.project_root))
    results.extend(check_env_dependencies(deps.env_vars))

    # Generate report
    report, all_satisfied = generate_dependency_report(
        deps,
        results,
        args.task_spec
    )

    # Output report
    if args.format == 'text':
        print(report)
    elif args.format == 'json':
        json_report = {
            'task_spec': str(args.task_spec),
            'all_satisfied': all_satisfied,
            'total_dependencies': len(results),
            'satisfied': len([r for r in results if r.satisfied]),
            'unsatisfied': len([r for r in results if not r.satisfied]),
            'results': [
                {
                    'type': r.dep_type,
                    'name': r.name,
                    'satisfied': r.satisfied,
                    'details': r.details
                }
                for r in results
            ]
        }
        print(json.dumps(json_report, indent=2))

    # Save report if requested
    if args.report:
        with open(args.report, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {args.report}")

    # Exit code based on dependencies
    if all_satisfied:
        return 0  # All dependencies satisfied
    else:
        return 1  # Some dependencies not satisfied


if __name__ == '__main__':
    sys.exit(main())
