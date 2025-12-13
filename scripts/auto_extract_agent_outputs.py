#!/usr/bin/env python3
"""
Automatic Agent Output Extraction (DC-05)

Wrapper for extract_files_from_agent_output.py that adds task spec validation.
This is the DC-05 interface that delegates to the PH-03 implementation.
"""

import argparse
import sys
from pathlib import Path

# Import the PH-03 implementation
from extract_files_from_agent_output import (
    parse_agent_output_log,
    extract_file_blocks,
    write_extracted_files,
    generate_extraction_report,
    ExtractionResult
)


def load_task_spec_deliverables(spec_path: Path) -> list:
    """
    Parse task specification to extract expected deliverables.

    Returns list of expected file paths.
    """
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Warning: Could not read task spec {spec_path}: {e}", file=sys.stderr)
        return []

    import re
    deliverables = []

    # Look for deliverables section
    deliverables_pattern = r'\*\*Deliverables\*\*:(.*?)(?=\n##|\n\*\*|\Z)'
    match = re.search(deliverables_pattern, content, re.DOTALL | re.IGNORECASE)

    if match:
        deliv_section = match.group(1)
        # Extract file paths from entries like "1. **docs/FILE.md**"
        file_pattern = r'\*\*([^\*]+\.(md|py|yaml|yml|sh|txt|json))\*\*'
        deliverables = re.findall(file_pattern, deliv_section, re.IGNORECASE)
        deliverables = [d[0] for d in deliverables]  # Extract just the filepath

    return deliverables


def validate_extracted_files(results: list, expected_deliverables: list) -> tuple:
    """
    Validate that all expected deliverables were extracted.

    Returns (all_found, missing_files)
    """
    extracted_files = {r.filepath for r in results if r.success}
    expected_set = set(expected_deliverables)

    missing = expected_set - extracted_files

    return len(missing) == 0, list(missing)


def generate_validated_report(
    results: list,
    log_path: Path,
    output_dir: Path,
    dry_run: bool,
    expected_deliverables: list,
    validation_passed: bool,
    missing_files: list
) -> str:
    """Generate extraction report with spec validation."""

    # Get base report from PH-03 implementation
    base_report = generate_extraction_report(
        results,
        log_path,
        output_dir,
        dry_run
    )

    # Add validation section
    validation_section = []
    validation_section.append("\nTASK SPEC VALIDATION")
    validation_section.append("-" * 70)
    validation_section.append(f"Expected deliverables: {len(expected_deliverables)}")
    validation_section.append(f"Successfully extracted: {len(expected_deliverables) - len(missing_files)}")
    validation_section.append("")

    if validation_passed:
        validation_section.append("✓ ALL EXPECTED DELIVERABLES EXTRACTED")
    else:
        validation_section.append("✗ MISSING EXPECTED DELIVERABLES")
        validation_section.append("")
        for filepath in missing_files:
            validation_section.append(f"  ✗ {filepath}")
        validation_section.append("")
        validation_section.append("RECOMMENDATION:")
        validation_section.append("Check agent output log for these files.")
        validation_section.append("They may not have been produced due to agent errors.")

    validation_section.append("")

    # Insert validation section before final separator
    parts = base_report.rsplit("=" * 70, 1)
    if len(parts) == 2:
        return parts[0] + '\n'.join(validation_section) + "=" * 70 + parts[1]
    else:
        return base_report + '\n' + '\n'.join(validation_section)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Automatically extract agent outputs with task spec validation",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--agent-id',
        type=str,
        help='Agent ID (used for logging, optional)'
    )

    parser.add_argument(
        '--log-file',
        type=Path,
        help='Path to agent output log file'
    )

    parser.add_argument(
        '--task-spec',
        type=Path,
        help='Path to task specification file (for validation)'
    )

    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path.cwd(),
        help='Output directory for extracted files (default: current directory)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be extracted without writing files'
    )

    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing files'
    )

    parser.add_argument(
        '--report',
        type=Path,
        help='Save extraction report to file'
    )

    args = parser.parse_args()

    # Determine log file
    if not args.log_file:
        if not args.agent_id:
            print("Error: Either --log-file or --agent-id must be provided", file=sys.stderr)
            return 2
        # Try to find log by agent ID
        log_candidates = [
            Path(f'logs/agent_{args.agent_id}.log'),
            Path(f'logs/agent_output_{args.agent_id}.log'),
            Path(f'{args.agent_id}.log')
        ]
        args.log_file = next((p for p in log_candidates if p.exists()), None)
        if not args.log_file:
            print(f"Error: Could not find log file for agent {args.agent_id}", file=sys.stderr)
            print(f"Tried: {[str(p) for p in log_candidates]}", file=sys.stderr)
            return 2

    if not args.log_file.exists():
        print(f"Error: Log file not found: {args.log_file}", file=sys.stderr)
        return 2

    # Load expected deliverables if task spec provided
    expected_deliverables = []
    if args.task_spec:
        if not args.task_spec.exists():
            print(f"Warning: Task spec not found: {args.task_spec}", file=sys.stderr)
        else:
            expected_deliverables = load_task_spec_deliverables(args.task_spec)
            print(f"Expected deliverables from task spec: {len(expected_deliverables)}")

    # Parse agent output using PH-03 implementation
    print(f"Parsing agent output: {args.log_file}")
    output_content = parse_agent_output_log(args.log_file)

    # Extract file blocks
    print("Extracting file blocks...")
    blocks = extract_file_blocks(output_content)
    print(f"Found {len(blocks)} potential file blocks")

    # Write files
    if args.dry_run:
        print("\nDRY RUN MODE - No files will be written\n")

    results = write_extracted_files(
        blocks,
        args.output_dir,
        dry_run=args.dry_run,
        overwrite=args.overwrite
    )

    # Validate against task spec if provided
    validation_passed = True
    missing_files = []
    if expected_deliverables:
        validation_passed, missing_files = validate_extracted_files(results, expected_deliverables)
        if not validation_passed:
            print(f"\nWarning: {len(missing_files)} expected deliverables not extracted")

    # Generate report
    report = generate_validated_report(
        results,
        args.log_file,
        args.output_dir,
        args.dry_run,
        expected_deliverables,
        validation_passed,
        missing_files
    )

    print(report)

    # Save report if requested
    if args.report:
        with open(args.report, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {args.report}")

    # Exit code based on validation
    if not expected_deliverables:
        # No validation requested, use extraction success
        if all(r.success for r in results):
            return 0
        elif any(r.success for r in results):
            return 1
        else:
            return 2
    else:
        # Validation requested
        if validation_passed and all(r.success for r in results):
            return 0
        else:
            return 1


if __name__ == '__main__':
    sys.exit(main())
