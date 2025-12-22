"""
Check integrity of all database files in the db directory.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry.database import DatabaseWriter

def main():
    db_dir = Path("D:/agent-metrics/db")

    if not db_dir.exists():
        print(f"[ERROR] Database directory not found: {db_dir}")
        return 1

    # Find all SQLite files
    db_files = list(db_dir.glob("*.sqlite"))

    if not db_files:
        print(f"[ERROR] No SQLite files found in {db_dir}")
        return 1

    print(f"Found {len(db_files)} database files:")
    print("=" * 80)

    results = []

    for db_file in sorted(db_files):
        print(f"\nChecking: {db_file.name}")
        print("-" * 80)

        # Check file size
        size_mb = db_file.stat().st_size / (1024 * 1024)
        print(f"  Size: {size_mb:.2f} MB")

        # Check integrity
        writer = DatabaseWriter(db_file)
        is_ok, message = writer.check_integrity(quick=True)
        print(f"  {message}")

        # Get stats if healthy
        if is_ok:
            stats = writer.get_run_stats()
            if "error" not in stats:
                print(f"  Total runs: {stats.get('total_runs', 0)}")
                print(f"  Status counts: {stats.get('status_counts', {})}")

        results.append((db_file.name, is_ok, size_mb))

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    healthy_dbs = [(name, size) for name, is_ok, size in results if is_ok]
    corrupted_dbs = [(name, size) for name, is_ok, size in results if not is_ok]

    if healthy_dbs:
        print(f"\n✓ Healthy databases ({len(healthy_dbs)}):")
        for name, size in healthy_dbs:
            print(f"  - {name} ({size:.2f} MB)")

    if corrupted_dbs:
        print(f"\n✗ Corrupted databases ({len(corrupted_dbs)}):")
        for name, size in corrupted_dbs:
            print(f"  - {name} ({size:.2f} MB)")

    return 0 if corrupted_dbs else 0

if __name__ == "__main__":
    sys.exit(main())
