#!/usr/bin/env python3
"""
Test Runner Script

Runs the test suite with proper path configuration.
For most cases, use `pytest` or `python -m pytest` directly.

Usage:
    python scripts/run_tests.py              # Run all tests
    python scripts/run_tests.py --unit       # Run unit tests only
    python scripts/run_tests.py --integration # Run integration tests only
    python scripts/run_tests.py --smoke      # Run smoke test only
"""

import subprocess
import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Run telemetry tests")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--smoke", action="store_true", help="Run smoke test only")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage")
    args = parser.parse_args()

    # Determine project root
    project_root = Path(__file__).parent.parent

    # Build pytest command
    cmd = [sys.executable, "-m", "pytest"]

    # Add verbosity
    if args.verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")

    # Add coverage if requested
    if args.coverage:
        cmd.extend(["--cov=src/telemetry", "--cov-report=term-missing"])

    # Determine what tests to run
    if args.smoke:
        cmd.append(str(project_root / "tests" / "smoke_test.py"))
    elif args.integration:
        cmd.append(str(project_root / "tests" / "integration"))
    elif args.unit:
        cmd.extend([
            str(project_root / "tests"),
            "-m", "not integration",
        ])
    else:
        cmd.append(str(project_root / "tests"))

    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)

    # Run pytest
    result = subprocess.run(cmd, cwd=project_root)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
