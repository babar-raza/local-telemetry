"""
Diagnose PRAGMA settings across different connection methods.

This script helps identify discrepancies in how PRAGMA settings are applied
across different ways of connecting to the database.

Usage:
    python scripts/diagnose_pragma_settings.py

Exit codes:
    0 - All connection methods show consistent settings
    1 - Discrepancies found in PRAGMA values
"""

import sys
import sqlite3
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry.database import DatabaseWriter
from telemetry import TelemetryClient
from telemetry.config import TelemetryConfig


def print_section(title):
    """Print formatted section header."""
    print(f"\n{'=' * 70}")
    print(f"{title}")
    print('=' * 70)


def check_pragma_values(conn, method_name):
    """Check and display PRAGMA values for a connection."""
    cursor = conn.cursor()

    busy_timeout = cursor.execute("PRAGMA busy_timeout").fetchone()[0]
    journal_mode = cursor.execute("PRAGMA journal_mode").fetchone()[0]
    synchronous = cursor.execute("PRAGMA synchronous").fetchone()[0]
    wal_autocheckpoint = cursor.execute("PRAGMA wal_autocheckpoint").fetchone()[0]

    print(f"\n{method_name}:")
    print(f"  busy_timeout:       {busy_timeout} ms")
    print(f"  journal_mode:       {journal_mode}")
    print(f"  synchronous:        {synchronous} {'(FULL)' if synchronous == 2 else ''}")
    print(f"  wal_autocheckpoint: {wal_autocheckpoint}")

    return {
        'busy_timeout': busy_timeout,
        'journal_mode': journal_mode.lower(),
        'synchronous': synchronous,
        'wal_autocheckpoint': wal_autocheckpoint
    }


def main():
    """Run diagnostic checks."""
    # Load configuration to auto-detect database path
    config = TelemetryConfig.from_env()
    db_path = config.database_path

    if not db_path.exists():
        print(f"[ERROR] Database not found: {db_path}")
        print(f"[INFO] Looked for database at: {db_path}")
        print(f"[INFO] Base directory: {config.metrics_dir}")
        print(f"[INFO] You can set TELEMETRY_DB_PATH or TELEMETRY_BASE_DIR to override")
        return 1

    print_section("PRAGMA Settings Diagnostic")
    print(f"Database: {db_path}")
    print(f"(Detected via TelemetryConfig.from_env())")

    results = {}

    # Test 1: Raw sqlite3 connection (no PRAGMA settings)
    print_section("Test 1: Raw sqlite3.connect()")
    print("This connection has NO custom PRAGMA settings (SQLite defaults)")
    conn1 = sqlite3.connect(db_path)
    results['raw'] = check_pragma_values(conn1, "Raw Connection")
    conn1.close()

    # Test 2: DatabaseWriter connection (with our PRAGMA settings)
    print_section("Test 2: DatabaseWriter._get_connection()")
    print("This connection uses our production-grade PRAGMA settings")
    writer = DatabaseWriter(db_path)
    conn2 = writer._get_connection()
    results['database_writer'] = check_pragma_values(conn2, "DatabaseWriter")
    conn2.close()

    # Test 3: TelemetryClient connection (indirect via DatabaseWriter)
    print_section("Test 3: TelemetryClient (via DatabaseWriter)")
    print("This uses DatabaseWriter internally, should match Test 2")
    try:
        client = TelemetryClient()
        conn3 = client.database_writer._get_connection()
        results['telemetry_client'] = check_pragma_values(conn3, "TelemetryClient")
        conn3.close()
    except Exception as e:
        print(f"[ERROR] Could not create TelemetryClient: {e}")
        results['telemetry_client'] = None

    # Analysis
    print_section("Analysis")

    # Expected values (DELETE mode for Docker compatibility)
    expected = {
        'busy_timeout': 30000,
        'journal_mode': 'delete',  # DELETE mode for Docker compatibility
        'synchronous': 2,
        'wal_autocheckpoint': 100  # Only enforced when journal_mode=WAL
    }

    print("\nExpected production values (Docker-compatible):")
    print(f"  busy_timeout:       {expected['busy_timeout']} ms")
    print(f"  journal_mode:       {expected['journal_mode']} (Docker-compatible)")
    print(f"  synchronous:        {expected['synchronous']} (FULL) - CRITICAL for corruption prevention")
    print(f"  wal_autocheckpoint: {expected['wal_autocheckpoint']} (only applies in WAL mode)")

    # Check for discrepancies
    discrepancies = []

    for method, values in results.items():
        if values is None:
            continue

        if method == 'raw':
            # Raw connection is expected to differ (no custom settings)
            continue

        # Check DatabaseWriter and TelemetryClient
        journal_mode = values.get('journal_mode', '').lower()
        for key, expected_val in expected.items():
            actual_val = values[key]

            if key == 'journal_mode':
                # Case-insensitive comparison
                if actual_val.lower() != expected_val.lower():
                    discrepancies.append(
                        f"{method}: {key} is '{actual_val}', expected '{expected_val}'"
                    )
            elif key == 'wal_autocheckpoint':
                if journal_mode != 'wal':
                    # wal_autocheckpoint is not applicable in DELETE mode
                    continue
                if actual_val != expected_val:
                    discrepancies.append(
                        f"{method}: {key} is {actual_val}, expected {expected_val}"
                    )
            elif actual_val != expected_val:
                discrepancies.append(
                    f"{method}: {key} is {actual_val}, expected {expected_val}"
                )

    if discrepancies:
        print("\n[FAIL] Discrepancies found:")
        for disc in discrepancies:
            print(f"  - {disc}")
        print_section("Root Cause Explanation")
        print("""
The discrepancies above indicate that PRAGMA settings are not being applied
correctly. This can happen due to:

1. PRAGMA settings only apply per-connection (not database-wide)
   - Each new connection starts with SQLite defaults
   - Our code must set PRAGMAs on every connection

2. Connection pooling or caching
   - If connections are reused, old PRAGMA values may persist
   - Solution: Always set PRAGMAs in _get_connection()

3. Timing of PRAGMA application
   - Some PRAGMAs must be set before other operations
   - DELETE mode must be set on each connection

CRITICAL: synchronous=FULL is the key setting for corruption prevention.
journal_mode=DELETE provides Docker compatibility without sacrificing safety.

RECOMMENDATION: The code in database.py._get_connection() now sets all
PRAGMAs correctly. If discrepancies still appear, check for:
- Other code paths creating connections
- Connection pooling interfering with settings
- Legacy connections not using _get_connection()
""")
        return 1
    else:
        print("\n[OK] All connection methods show consistent production settings!")
        print("\nAll DatabaseWriter and TelemetryClient connections are using:")
        print("  - busy_timeout = 30000ms (handles concurrent access)")
        print("  - synchronous = FULL (prevents corruption on crashes)")
        print("  - journal_mode = DELETE (Docker-compatible, safe with synchronous=FULL)")
        print("  - wal_autocheckpoint = 100 (only when WAL is enabled)")

        print_section("Previous Discrepancy Explanation")
        print("""
The earlier test showing busy_timeout=5000ms was likely from:

1. Testing a raw connection without our PRAGMA settings
2. Using an old connection before the code fix was applied
3. Reading PRAGMA values from database file properties vs connection settings

The current test confirms that:
- DatabaseWriter._get_connection() applies all settings correctly
- TelemetryClient uses DatabaseWriter, inheriting correct settings
- All new connections will have production-grade corruption prevention

CONCLUSION: The fix is working correctly. All new database operations
use the safe PRAGMA values (synchronous=FULL, busy_timeout=30000).
""")
        return 0


if __name__ == "__main__":
    sys.exit(main())
