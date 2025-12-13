"""
Verified TodoWrite Update.

Wrapper for TodoWrite that verifies deliverables before marking tasks complete.
Integrates with quality gate to ensure task completion is validated.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

# Import quality gate for verification
sys.path.insert(0, str(Path(__file__).parent))
from quality_gate import parse_task_spec, run_quality_gate


def load_task_spec(spec_path: Path) -> Optional[dict]:
    """
    Load task specification.

    Args:
        spec_path: Path to task spec markdown file

    Returns:
        Task spec dict or None if not found
    """
    if not spec_path.exists():
        print(f"Error: Task spec not found: {spec_path}", file=sys.stderr)
        return None

    try:
        task_spec = parse_task_spec(spec_path)
        return {
            'task_id': task_spec.task_id,
            'deliverables': task_spec.deliverables,
            'acceptance_checks': task_spec.acceptance_checks,
            'min_lines': task_spec.min_lines
        }
    except Exception as e:
        print(f"Error parsing task spec: {e}", file=sys.stderr)
        return None


def verify_deliverables_exist(
    deliverables: list,
    project_root: Path
) -> Tuple[bool, list]:
    """
    Check if all deliverable files exist on disk.

    Args:
        deliverables: List of deliverable dicts with 'file' key
        project_root: Project root directory

    Returns:
        Tuple of (all_exist, missing_files)
    """
    missing_files = []

    for deliv in deliverables:
        filepath = deliv.get('file', '')
        if not filepath:
            continue

        file_path = project_root / filepath
        if not file_path.exists():
            missing_files.append(filepath)

    all_exist = len(missing_files) == 0
    return all_exist, missing_files


def run_quality_gate_verification(
    task_spec_path: Path,
    project_root: Path,
    agent_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Run quality gate verification on task deliverables.

    Args:
        task_spec_path: Path to task specification
        project_root: Project root directory
        agent_id: Optional agent ID for logging

    Returns:
        Tuple of (passed, report_summary)
    """
    try:
        results, all_passed = run_quality_gate(
            task_spec_path,
            agent_id=agent_id,
            project_root=project_root
        )

        # Generate summary
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count

        summary = f"Quality Gate: {passed_count}/{len(results)} checks passed"
        if not all_passed:
            summary += f" ({failed_count} failures)"

        return all_passed, summary

    except Exception as e:
        return False, f"Quality gate error: {str(e)}"


def generate_verification_log(
    task_id: str,
    status: str,
    verification_passed: bool,
    details: dict
) -> str:
    """
    Generate verification log entry.

    Args:
        task_id: Task identifier
        status: Requested status
        verification_passed: Whether verification passed
        details: Verification details

    Returns:
        Log entry text
    """
    timestamp = datetime.now().isoformat()

    log_lines = []
    log_lines.append(f"Timestamp: {timestamp}")
    log_lines.append(f"Task ID: {task_id}")
    log_lines.append(f"Requested Status: {status}")
    log_lines.append(f"Verification: {'PASSED' if verification_passed else 'FAILED'}")

    if 'missing_files' in details:
        log_lines.append(f"Missing Files: {', '.join(details['missing_files']) if details['missing_files'] else 'None'}")

    if 'quality_gate_summary' in details:
        log_lines.append(f"Quality Gate: {details['quality_gate_summary']}")

    return '\n'.join(log_lines)


def update_todo_if_verified(
    task_id: str,
    status: str,
    verification_passed: bool,
    details: dict
) -> bool:
    """
    Update TodoWrite if verification passed.

    Note: This is a placeholder for actual TodoWrite integration.
    In practice, this would call the TodoWrite tool or API.

    Args:
        task_id: Task identifier
        status: New status to set
        verification_passed: Whether verification passed
        details: Verification details

    Returns:
        True if update succeeded, False otherwise
    """
    if not verification_passed:
        print(f"Cannot update status to '{status}': verification failed", file=sys.stderr)
        return False

    # Placeholder for actual TodoWrite integration
    print(f"✓ Verification passed - Task {task_id} can be marked as '{status}'")
    print(f"  (In production, this would update TodoWrite)")

    return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verified TodoWrite update - checks deliverables before marking complete"
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="Task identifier"
    )
    parser.add_argument(
        "--status",
        required=True,
        choices=["pending", "in_progress", "completed", "blocked"],
        help="New task status"
    )
    parser.add_argument(
        "--spec",
        help="Path to task specification (required for 'completed' status)"
    )
    parser.add_argument(
        "--agent-id",
        help="Agent ID for logging"
    )
    parser.add_argument(
        "--skip-quality-gate",
        action="store_true",
        help="Skip quality gate verification (only check file existence)"
    )
    parser.add_argument(
        "--log-file",
        help="Path to verification log file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be verified without executing"
    )

    args = parser.parse_args()

    project_root = Path.cwd()

    # For non-completed status, allow pass-through
    if args.status != "completed":
        print(f"Status '{args.status}' does not require verification - allowing update")
        # In production, would update TodoWrite here
        return 0

    # For completed status, require verification
    if not args.spec:
        print("Error: --spec is required when marking task as 'completed'", file=sys.stderr)
        return 2

    spec_path = Path(args.spec)
    if not spec_path.exists():
        print(f"Error: Task spec not found: {spec_path}", file=sys.stderr)
        return 2

    # Load task spec
    task_spec = load_task_spec(spec_path)
    if not task_spec:
        return 2

    print("=" * 70)
    print("VERIFIED TODO UPDATE")
    print("=" * 70)
    print(f"Task ID: {args.task_id}")
    print(f"Requested Status: {args.status}")
    print(f"Task Spec: {spec_path}")
    print()

    if args.dry_run:
        print("DRY RUN - Showing verification plan:")
        print(f"  Task: {task_spec['task_id']}")
        print(f"  Deliverables to verify: {len(task_spec['deliverables'])}")
        for deliv in task_spec['deliverables']:
            print(f"    - {deliv['file']}")
        print(f"  Quality Gate: {'Skip' if args.skip_quality_gate else 'Run'}")
        return 0

    # Step 1: Check file existence
    print("[1/2] Checking deliverable files exist...")
    all_exist, missing_files = verify_deliverables_exist(
        task_spec['deliverables'],
        project_root
    )

    if not all_exist:
        print(f"✗ Missing {len(missing_files)} deliverable file(s):")
        for filepath in missing_files:
            print(f"  - {filepath}")
        print()

        verification_details = {
            'missing_files': missing_files,
            'verification_passed': False
        }

        # Log verification failure
        log_entry = generate_verification_log(
            args.task_id,
            args.status,
            False,
            verification_details
        )

        if args.log_file:
            log_path = Path(args.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'a') as f:
                f.write(log_entry + '\n\n')

        print("=" * 70)
        print("✗ VERIFICATION FAILED")
        print("=" * 70)
        print()
        print("Task cannot be marked complete until deliverables exist.")
        print()
        return 1

    print(f"✓ All {len(task_spec['deliverables'])} deliverable files exist")
    print()

    # Step 2: Run quality gate (unless skipped)
    quality_gate_passed = True
    quality_gate_summary = "Skipped"

    if not args.skip_quality_gate:
        print("[2/2] Running quality gate verification...")
        quality_gate_passed, quality_gate_summary = run_quality_gate_verification(
            spec_path,
            project_root,
            args.agent_id
        )

        if quality_gate_passed:
            print(f"✓ {quality_gate_summary}")
        else:
            print(f"✗ {quality_gate_summary}")
        print()

    # Overall verification result
    verification_passed = all_exist and quality_gate_passed

    verification_details = {
        'missing_files': missing_files,
        'quality_gate_summary': quality_gate_summary,
        'verification_passed': verification_passed
    }

    # Log verification
    log_entry = generate_verification_log(
        args.task_id,
        args.status,
        verification_passed,
        verification_details
    )

    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'a') as f:
            f.write(log_entry + '\n\n')

    # Update TodoWrite if verification passed
    print("=" * 70)
    if verification_passed:
        print("✓ VERIFICATION PASSED")
        print("=" * 70)
        print()

        update_success = update_todo_if_verified(
            args.task_id,
            args.status,
            verification_passed,
            verification_details
        )

        if update_success:
            print()
            print("Task status updated successfully.")
            return 0
        else:
            print()
            print("Error updating task status.")
            return 2
    else:
        print("✗ VERIFICATION FAILED")
        print("=" * 70)
        print()
        print("Task cannot be marked complete. Fix the following issues:")

        if missing_files:
            print(f"  • {len(missing_files)} missing deliverable file(s)")

        if not quality_gate_passed:
            print(f"  • Quality gate failures - see quality gate report")

        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
