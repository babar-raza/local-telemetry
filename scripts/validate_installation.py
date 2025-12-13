"""
Telemetry Platform - Installation Validation Script

Validates that all Day 1 setup tasks completed successfully.
Safe to run multiple times (read-only checks).

Usage:
    python scripts/validate_installation.py

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

import os
import sys
import sqlite3
from pathlib import Path
from importlib import import_module

# Add src to path for importing telemetry package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def print_header(title):
    """Print formatted section header."""
    print(f"\n{title}")


def print_check(message, passed, details=None):
    """Print check result with checkmark or X."""
    symbol = "[OK]" if passed else "[FAIL]"
    print(f"      {symbol} {message}")
    if details and not passed:
        print(f"         -> {details}")
    return passed


def check_environment():
    """Check Python environment and packages."""
    print_header("[1/5] Checking Python Environment...")

    all_passed = True

    # Check Python version
    version_info = sys.version_info
    version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    version_ok = version_info.major == 3 and 9 <= version_info.minor <= 13
    all_passed &= print_check(
        f"Python version: {version_str}",
        version_ok,
        "Requires Python 3.9-3.13"
    )

    # Check required packages
    packages = {
        "httpx": "0.25.0",
    }

    for package, min_version in packages.items():
        try:
            mod = import_module(package)
            version = getattr(mod, "__version__", "unknown")
            all_passed &= print_check(f"Package '{package}' installed: {version}", True)
        except ImportError:
            # httpx might be installed but not in path - check if telemetry can import it
            try:
                import telemetry.client  # This will fail if httpx is truly missing
                print_check(f"Package '{package}' available to telemetry", True)
            except ImportError:
                all_passed &= print_check(
                    f"Package '{package}' installed",
                    False,
                    f"Run: pip install {package}>={min_version}"
                )

    # Check telemetry import
    try:
        import_module("telemetry")
        all_passed &= print_check("Can import 'telemetry'", True)
    except ImportError as e:
        all_passed &= print_check(
            "Can import 'telemetry'",
            False,
            f"Run: pip install -e . ({str(e)})"
        )

    return all_passed


def check_storage():
    """Check storage directories."""
    print_header("[2/5] Checking Storage Directories...")

    all_passed = True

    # Check environment variable
    metrics_dir = os.getenv("AGENT_METRICS_DIR")
    if metrics_dir:
        all_passed &= print_check(f"AGENT_METRICS_DIR: {metrics_dir}", True)
        base_path = Path(metrics_dir)
    else:
        # Try fallback detection
        if Path("D:\\agent-metrics").exists():
            base_path = Path("D:\\agent-metrics")
            all_passed &= print_check(
                "AGENT_METRICS_DIR not set, using fallback: D:\\agent-metrics",
                True
            )
        elif Path("C:\\agent-metrics").exists():
            base_path = Path("C:\\agent-metrics")
            all_passed &= print_check(
                "AGENT_METRICS_DIR not set, using fallback: C:\\agent-metrics",
                True
            )
        else:
            all_passed &= print_check(
                "AGENT_METRICS_DIR",
                False,
                "Not set and no fallback found. Run: scripts/setup_storage.py"
            )
            return False

    # Check base directory
    base_exists = base_path.exists()
    all_passed &= print_check(
        f"Base directory exists: {base_path}",
        base_exists,
        "Run: python scripts/setup_storage.py"
    )

    if not base_exists:
        return False

    # Check subdirectories
    subdirs = ["raw", "db", "reports", "exports", "config", "logs"]
    for subdir in subdirs:
        subdir_path = base_path / subdir
        subdir_exists = subdir_path.exists() and subdir_path.is_dir()
        all_passed &= print_check(
            f"Subdirectory '{subdir}' exists",
            subdir_exists,
            "Run: python scripts/setup_storage.py"
        )

    # Check README
    readme_path = base_path / "README.md"
    readme_exists = readme_path.exists()
    all_passed &= print_check(
        "README.md exists",
        readme_exists,
        "Run: python scripts/setup_storage.py"
    )

    # Check write permissions
    test_file = base_path / "raw" / ".validation_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
        all_passed &= print_check("Directories are writable", True)
    except (OSError, PermissionError) as e:
        all_passed &= print_check(
            "Directories are writable",
            False,
            f"Permission error: {e}"
        )

    return all_passed


def check_database():
    """Check database and schema."""
    print_header("[3/5] Checking Database...")

    all_passed = True

    # Find database path
    metrics_dir = os.getenv("AGENT_METRICS_DIR")
    if metrics_dir:
        db_path = Path(metrics_dir) / "db" / "telemetry.sqlite"
    elif Path("D:\\agent-metrics").exists():
        db_path = Path("D:\\agent-metrics\\db\\telemetry.sqlite")
    elif Path("C:\\agent-metrics").exists():
        db_path = Path("C:\\agent-metrics\\db\\telemetry.sqlite")
    else:
        all_passed &= print_check(
            "Database path",
            False,
            "Cannot determine database path"
        )
        return False

    # Check database file exists
    db_exists = db_path.exists()
    all_passed &= print_check(
        f"Database file exists: {db_path}",
        db_exists,
        "Run: python scripts/setup_database.py"
    )

    if not db_exists:
        return False

    # Check database connection
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        all_passed &= print_check("Can connect to database", True)

        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}

        expected_tables = {"schema_migrations", "agent_runs", "run_events", "commits"}
        for table in expected_tables:
            table_exists = table in tables
            all_passed &= print_check(
                f"Table '{table}' exists",
                table_exists,
                "Run: python scripts/setup_database.py"
            )

        # Check schema version
        if "schema_migrations" in tables:
            cursor.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1;")
            result = cursor.fetchone()
            if result:
                version = result[0]
                all_passed &= print_check(f"Schema version: {version}", True)
            else:
                all_passed &= print_check(
                    "Schema version",
                    False,
                    "No version found in schema_migrations table"
                )

        # Test read
        cursor.execute("SELECT COUNT(*) FROM agent_runs;")
        count = cursor.fetchone()[0]
        all_passed &= print_check("Can read from database", True)

        conn.close()

    except sqlite3.Error as e:
        all_passed &= print_check(
            "Database checks",
            False,
            f"SQLite error: {e}"
        )

    return all_passed


def check_configuration():
    """Check telemetry configuration."""
    print_header("[4/5] Checking Configuration...")

    all_passed = True

    # Import and load config
    try:
        from telemetry import TelemetryConfig

        config = TelemetryConfig.from_env()
        all_passed &= print_check("TelemetryConfig.from_env() works", True)

        # Check config values
        all_passed &= print_check(f"Config metrics_dir: {config.metrics_dir}", True)
        all_passed &= print_check(f"Config database_path: {config.database_path}", True)
        all_passed &= print_check(f"Config ndjson_dir: {config.ndjson_dir}", True)

        # Check paths exist
        paths_ok = (
            config.metrics_dir.exists() and
            config.database_path.exists() and
            config.ndjson_dir.exists()
        )
        all_passed &= print_check(
            "All config paths exist",
            paths_ok,
            "Some config paths don't exist"
        )

    except Exception as e:
        all_passed &= print_check(
            "Configuration loading",
            False,
            f"Error: {e}"
        )

    return all_passed


def check_tests():
    """Check test suite."""
    print_header("[5/5] Checking Test Suite...")

    all_passed = True

    # Check if test runner exists
    test_runner = Path("run_tests.py")
    if test_runner.exists():
        all_passed &= print_check("Test runner exists (run_tests.py)", True)
    else:
        all_passed &= print_check(
            "Test runner exists",
            False,
            "run_tests.py not found"
        )

    # Check if tests directory exists
    tests_dir = Path("tests")
    if tests_dir.exists():
        test_files = list(tests_dir.glob("test_*.py"))
        all_passed &= print_check(
            f"Test directory exists with {len(test_files)} test files",
            len(test_files) > 0
        )
    else:
        all_passed &= print_check(
            "Test directory exists",
            False,
            "tests/ directory not found"
        )

    # Note: We don't run tests here because it takes too long
    # User should verify test results from D1-T5
    print("      [INFO] Run 'python run_tests.py' to execute full test suite")

    return all_passed


def main():
    """Main validation routine."""
    print("=" * 70)
    print("Telemetry Platform - Installation Validation")
    print("=" * 70)

    results = []

    # Run all checks
    results.append(("Environment", check_environment()))
    results.append(("Storage", check_storage()))
    results.append(("Database", check_database()))
    results.append(("Configuration", check_configuration()))
    results.append(("Tests", check_tests()))

    # Summary
    print("\n" + "=" * 70)
    all_passed = all(passed for _, passed in results)

    if all_passed:
        print("[SUCCESS] ALL CHECKS PASSED - Installation is valid!")
        print("=" * 70)
        print("\nSystem is ready for Day 2: Library Validation")
        return 0
    else:
        print("[FAILURE] SOME CHECKS FAILED - Review errors above")
        print("=" * 70)
        print("\nFailed checks:")
        for name, passed in results:
            if not passed:
                print(f"  - {name}")
        print("\nFix the issues and run this script again.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
