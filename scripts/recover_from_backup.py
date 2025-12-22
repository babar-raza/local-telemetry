"""
Database Recovery Script - Restore from Healthy Backup

Recovers from database corruption by:
1. Backing up corrupted database for forensics
2. Restoring from most recent healthy backup
3. Verifying integrity of recovered database

Usage:
    python scripts/recover_from_backup.py

This is the fastest way to recover - simply restores the last known good backup.
For rebuilding from NDJSON, use scripts/recover_database.py instead.
"""

import sys
import shutil
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from telemetry.database import DatabaseWriter


def print_header(title):
    """Print formatted header."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def backup_corrupted_database(db_path: Path) -> tuple[bool, Path]:
    """Backup the corrupted database for forensic analysis."""
    print_header("STEP 1: Backup Corrupted Database")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"telemetry.corrupted.{timestamp}.sqlite"

    try:
        if db_path.exists():
            shutil.copy2(db_path, backup_path)
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            print(f"[OK] Backed up corrupted database to: {backup_path}")
            print(f"     Size: {size_mb:.2f} MB")
            return True, backup_path
        else:
            print(f"[SKIP] No database file found at: {db_path}")
            return True, None

    except Exception as e:
        print(f"[FAIL] Failed to backup corrupted database: {e}")
        return False, None


def find_healthy_backup(db_dir: Path) -> Path:
    """Find the most recent healthy backup."""
    print_header("STEP 2: Find Healthy Backup")

    # Find all backup files
    backup_files = sorted(
        db_dir.glob("telemetry.backup.*.sqlite"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    # Also check pre-migration backups
    pre_v4_backups = sorted(
        db_dir.glob("telemetry.pre_v*_backup.*.sqlite"),
        key=lambda f: f.stat().st_mtime,
        reverse=True
    )

    all_backups = backup_files + pre_v4_backups

    if not all_backups:
        print("[FAIL] No backup files found!")
        return None

    print(f"Found {len(all_backups)} backup file(s):")

    # Check each backup until we find a healthy one
    for backup_path in all_backups:
        size_mb = backup_path.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(backup_path.stat().st_mtime)
        print(f"\nChecking: {backup_path.name}")
        print(f"  Modified: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Size: {size_mb:.2f} MB")

        writer = DatabaseWriter(backup_path)
        is_healthy, message = writer.check_integrity(quick=True)
        print(f"  {message}")

        if is_healthy:
            stats = writer.get_run_stats()
            if "error" not in stats:
                print(f"  Total runs: {stats.get('total_runs', 0)}")

            print(f"\n[OK] Found healthy backup: {backup_path.name}")
            return backup_path

    print("\n[FAIL] No healthy backup found!")
    return None


def restore_from_backup(backup_path: Path, target_path: Path) -> bool:
    """Restore database from healthy backup."""
    print_header("STEP 3: Restore from Backup")

    try:
        if target_path.exists():
            target_path.unlink()
            print(f"[OK] Removed corrupted database")

        shutil.copy2(backup_path, target_path)
        print(f"[OK] Restored from: {backup_path.name}")

        writer = DatabaseWriter(target_path)
        is_healthy, message = writer.check_integrity(quick=False)
        print(f"\n{message}")

        if not is_healthy:
            print("[FAIL] Restored database is still corrupted!")
            return False

        # Checkpoint WAL
        success, msg = writer.checkpoint_wal(mode="TRUNCATE")
        print(msg)

        # Show stats
        stats = writer.get_run_stats()
        if "error" not in stats:
            print(f"\nRestored statistics:")
            print(f"  Total runs: {stats['total_runs']}")
            print(f"  By status: {stats['status_counts']}")

        return True

    except Exception as e:
        print(f"[FAIL] Restoration failed: {e}")
        return False


def main():
    """Main recovery routine."""
    print("=" * 80)
    print("TELEMETRY DATABASE RECOVERY - Restore from Backup")
    print("=" * 80)

    response = input("\nProceed with recovery? (yes/no): ")
    if response.lower() not in ("yes", "y"):
        print("\n[CANCELLED]")
        return 1

    db_dir = Path("D:/agent-metrics/db")
    db_path = db_dir / "telemetry.sqlite"

    success, _ = backup_corrupted_database(db_path)
    if not success:
        return 1

    healthy_backup = find_healthy_backup(db_dir)
    if not healthy_backup:
        return 1

    if not restore_from_backup(healthy_backup, db_path):
        return 1

    print_header("RECOVERY COMPLETE")
    print("\nDatabase restored successfully!")
    print("\nIMPORTANT: The code has been updated with corruption prevention:")
    print("  - PRAGMA synchronous=FULL (prevents corruption on crashes)")
    print("  - PRAGMA wal_autocheckpoint=100 (prevents WAL bloat)")
    print("  - PRAGMA busy_timeout=30000 (handles concurrent access)")
    print("\nSee docs/DATABASE_CORRUPTION_ROOT_CAUSE.md for full analysis")

    return 0


if __name__ == "__main__":
    sys.exit(main())
