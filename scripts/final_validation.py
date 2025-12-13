"""
Final validation before production deployment.
Runs all checks and generates production readiness report.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add src to path for telemetry imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

def run_check(name, command):
    """Run a validation check."""
    print(f"\n{'='*70}")
    print(f"Running: {name}")
    print(f"{'='*70}\n")

    result = subprocess.run(command, shell=True, capture_output=True, text=True)

    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)

    if result.returncode == 0:
        print(f"OK {name} PASSED")
        return True
    else:
        print(f"X {name} FAILED")
        return False

def main():
    print("="*70)
    print("FINAL PRODUCTION READINESS VALIDATION")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)

    checks = [
        ("Installation Validation", "python scripts/validate_installation.py"),
        ("Health Check", "python scripts/monitor_telemetry_health.py"),
        ("Day 1 Tests", "pytest tests/ -v -k 'not integration and not stress' --tb=short"),
        ("Day 2 Integration Tests", "pytest tests/integration/ -v --tb=short"),
    ]

    results = []
    for name, command in checks:
        results.append((name, run_check(name, command)))

    # Summary
    print("\n" + "="*70)
    print("VALIDATION SUMMARY")
    print("="*70)

    for name, passed in results:
        status = "OK PASS" if passed else "X FAIL"
        print(f"{status:12s} {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)
    pass_rate = (passed / total * 100) if total > 0 else 0

    print(f"\nPass Rate: {passed}/{total} ({pass_rate:.1f}%)")

    print("\n" + "="*70)
    if pass_rate == 100:
        print("OK ALL VALIDATIONS PASSED - SYSTEM IS PRODUCTION READY")
    elif pass_rate >= 90:
        print("! MOSTLY READY - Review failures before production")
    else:
        print("X NOT PRODUCTION READY - Fix critical issues")
    print("="*70)

    return 0 if pass_rate >= 95 else 1

if __name__ == "__main__":
    sys.exit(main())
