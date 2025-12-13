#!/usr/bin/env python3
"""
Agent Output File Extraction

Automatically extracts file contents from agent output logs when Write tool
fails due to permissions or other issues. Parses agent output for file
content blocks and writes them to the correct locations.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class FileBlock:
    """Represents a file content block found in agent output."""
    filepath: str
    content: str
    line_number: int
    block_type: str  # 'code', 'markdown', 'yaml', 'shell', etc.
    confidence: float  # 0.0-1.0, how confident we are about the extraction


@dataclass
class ExtractionResult:
    """Result of file extraction."""
    filepath: str
    success: bool
    lines_written: int
    error: Optional[str] = None


def parse_agent_output_log(log_path: Path) -> str:
    """Load agent output log content."""
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        raise RuntimeError(f"Failed to read log file {log_path}: {e}")


def extract_file_blocks(output_content: str) -> List[FileBlock]:
    """
    Parse agent output to find file content blocks.

    Looks for patterns like:
    - "Writing to scripts/example.py:"
    - "File: docs/README.md"
    - Code blocks with file paths in comments
    """
    blocks = []
    lines = output_content.split('\n')

    # Pattern 1: Explicit file declarations
    file_declaration_pattern = r'(?:Writing to|File:|Creating|Updating)\s+([^\s:]+\.\w+)[\s:]'

    # Pattern 2: Code blocks with language specifiers
    code_block_pattern = r'```(\w+)\s*\n(.*?)\n```'

    # Pattern 3: File paths in bold markdown
    bold_file_pattern = r'\*\*([^\*]+\.\w+)\*\*'

    current_file = None
    current_content = []
    in_code_block = False
    block_type = None
    start_line = 0

    for line_num, line in enumerate(lines, 1):
        # Check for file declaration
        match = re.search(file_declaration_pattern, line)
        if match:
            # Save previous block if exists
            if current_file and current_content:
                blocks.append(FileBlock(
                    filepath=current_file,
                    content='\n'.join(current_content),
                    line_number=start_line,
                    block_type=block_type or 'unknown',
                    confidence=0.9
                ))

            current_file = match.group(1)
            current_content = []
            start_line = line_num
            in_code_block = False
            continue

        # Check for code block start
        if line.strip().startswith('```'):
            if not in_code_block:
                # Starting code block
                in_code_block = True
                lang_match = re.match(r'```(\w+)', line)
                block_type = lang_match.group(1) if lang_match else 'code'

                # Check if next few lines might be a file
                if not current_file:
                    # Look ahead for file path hints
                    for future_line in lines[line_num:line_num+5]:
                        bold_match = re.search(bold_file_pattern, future_line)
                        if bold_match:
                            current_file = bold_match.group(1)
                            start_line = line_num
                            break
            else:
                # Ending code block
                in_code_block = False

                if current_file and current_content:
                    blocks.append(FileBlock(
                        filepath=current_file,
                        content='\n'.join(current_content),
                        line_number=start_line,
                        block_type=block_type or 'code',
                        confidence=0.8
                    ))
                    current_file = None
                    current_content = []
            continue

        # Collect content if we're tracking a file
        if in_code_block and current_file:
            current_content.append(line)

    # Save final block if exists
    if current_file and current_content:
        blocks.append(FileBlock(
            filepath=current_file,
            content='\n'.join(current_content),
            line_number=start_line,
            block_type=block_type or 'unknown',
            confidence=0.8
        ))

    return blocks


def validate_file_block(block: FileBlock) -> bool:
    """Validate that a file block looks legitimate."""
    # Must have content
    if not block.content or not block.content.strip():
        return False

    # Must have valid file extension
    valid_extensions = {'.py', '.md', '.yaml', '.yml', '.sh', '.txt', '.json', '.toml', '.cfg'}
    ext = Path(block.filepath).suffix.lower()
    if ext not in valid_extensions:
        return False

    # Must have minimum confidence
    if block.confidence < 0.5:
        return False

    # Content should have minimum length
    if len(block.content) < 10:
        return False

    return True


def write_extracted_files(
    blocks: List[FileBlock],
    output_dir: Path,
    dry_run: bool = False,
    overwrite: bool = False
) -> List[ExtractionResult]:
    """
    Write extracted file blocks to disk.

    Args:
        blocks: File blocks to write
        output_dir: Base directory for output files
        dry_run: If True, don't actually write files
        overwrite: If True, overwrite existing files

    Returns:
        List of extraction results
    """
    results = []

    for block in blocks:
        if not validate_file_block(block):
            results.append(ExtractionResult(
                filepath=block.filepath,
                success=False,
                lines_written=0,
                error="Failed validation (insufficient content or confidence)"
            ))
            continue

        file_path = output_dir / block.filepath

        # Check if file already exists
        if file_path.exists() and not overwrite:
            results.append(ExtractionResult(
                filepath=block.filepath,
                success=False,
                lines_written=0,
                error="File already exists (use --overwrite to replace)"
            ))
            continue

        if dry_run:
            line_count = len(block.content.split('\n'))
            results.append(ExtractionResult(
                filepath=block.filepath,
                success=True,
                lines_written=line_count,
                error=None
            ))
            continue

        # Create parent directories
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            results.append(ExtractionResult(
                filepath=block.filepath,
                success=False,
                lines_written=0,
                error=f"Failed to create directory: {e}"
            ))
            continue

        # Write file
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(block.content)

            line_count = len(block.content.split('\n'))
            results.append(ExtractionResult(
                filepath=block.filepath,
                success=True,
                lines_written=line_count,
                error=None
            ))
        except Exception as e:
            results.append(ExtractionResult(
                filepath=block.filepath,
                success=False,
                lines_written=0,
                error=f"Failed to write file: {e}"
            ))

    return results


def generate_extraction_report(
    results: List[ExtractionResult],
    log_path: Path,
    output_dir: Path,
    dry_run: bool
) -> str:
    """Generate extraction report."""
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    total_lines = sum(r.lines_written for r in successful)

    report = []
    report.append("=" * 70)
    report.append("AGENT OUTPUT FILE EXTRACTION REPORT")
    report.append("=" * 70)
    report.append(f"Log file: {log_path}")
    report.append(f"Output directory: {output_dir}")
    report.append(f"Mode: {'DRY RUN' if dry_run else 'WRITE'}")
    report.append("")

    report.append("SUMMARY")
    report.append("-" * 70)
    report.append(f"Total files found: {len(results)}")
    report.append(f"Successfully extracted: {len(successful)}")
    report.append(f"Failed: {len(failed)}")
    report.append(f"Total lines extracted: {total_lines}")
    report.append("")

    if successful:
        report.append("SUCCESSFULLY EXTRACTED FILES")
        report.append("-" * 70)
        for result in successful:
            report.append(f"✓ {result.filepath} ({result.lines_written} lines)")
        report.append("")

    if failed:
        report.append("FAILED EXTRACTIONS")
        report.append("-" * 70)
        for result in failed:
            report.append(f"✗ {result.filepath}")
            report.append(f"  Error: {result.error}")
        report.append("")

    report.append("=" * 70)

    return '\n'.join(report)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract files from agent output logs",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--log-file',
        type=Path,
        required=True,
        help='Path to agent output log file'
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

    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.log_file.exists():
        print(f"Error: Log file not found: {args.log_file}", file=sys.stderr)
        return 1

    # Parse agent output
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

    # Generate report
    report = generate_extraction_report(
        results,
        args.log_file,
        args.output_dir,
        args.dry_run
    )

    # Output report
    if args.format == 'text':
        print(report)
    elif args.format == 'json':
        json_report = {
            'log_file': str(args.log_file),
            'output_dir': str(args.output_dir),
            'dry_run': args.dry_run,
            'total_files': len(results),
            'successful': len([r for r in results if r.success]),
            'failed': len([r for r in results if not r.success]),
            'results': [
                {
                    'filepath': r.filepath,
                    'success': r.success,
                    'lines_written': r.lines_written,
                    'error': r.error
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

    # Exit code based on success
    if all(r.success for r in results):
        return 0
    elif any(r.success for r in results):
        return 1  # Partial success
    else:
        return 2  # Complete failure


if __name__ == '__main__':
    sys.exit(main())
