"""
Check database integrity for telemetry database.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry.database import DatabaseWriter

def main():
    db_path = Path("D:/agent-metrics/db/telemetry.sqlite")

    if not db_path.exists():
        print(f"[ERROR] Database file not found: {db_path}")
        return 1

    print(f"Checking database integrity: {db_path}")
    print("-" * 60)

    # Create writer instance
    writer = DatabaseWriter(db_path)

    # Run quick check
    print("\n[1/2] Running quick integrity check...")
    is_ok, message = writer.check_integrity(quick=True)
    print(f"      {message}")

    if not is_ok:
        # Run comprehensive check
        print("\n[2/2] Running comprehensive integrity check...")
        is_ok_full, message_full = writer.check_integrity(quick=False)
        print(f"      {message_full}")

        if not is_ok_full:
            print("\n" + "=" * 60)
            print("[RESULT] DATABASE IS CORRUPTED")
            print("=" * 60)
            print("\nRecommended actions:")
            print("1. Backup the corrupted database file")
            print("2. Check if there's a recent backup in the same directory")
            print("3. Run recovery script: python scripts/recover_database.py")
            print("4. Or rebuild from NDJSON: python scripts/rebuild_from_ndjson.py")
            return 1

    print("\n" + "=" * 60)
    print("[RESULT] DATABASE IS HEALTHY")
    print("=" * 60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
