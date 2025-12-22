"""
Analyze corruption patterns to find root cause.
"""

import sys
import sqlite3
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def check_wal_files():
    """Check for WAL and SHM files that might indicate incomplete transactions."""
    db_dir = Path("D:/agent-metrics/db")

    print("=" * 80)
    print("CHECKING FOR WAL/SHM FILES (incomplete transactions)")
    print("=" * 80)

    wal_files = list(db_dir.glob("*.sqlite-wal"))
    shm_files = list(db_dir.glob("*.sqlite-shm"))

    if wal_files:
        print("\n⚠ Found WAL files (Write-Ahead Log):")
        for f in wal_files:
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name} ({size_kb:.1f} KB)")
            if size_kb > 1024:  # > 1 MB
                print(f"    WARNING: Large WAL file suggests checkpoint issues!")

    if shm_files:
        print("\n⚠ Found SHM files (Shared Memory):")
        for f in shm_files:
            size_kb = f.stat().st_size / 1024
            print(f"  - {f.name} ({size_kb:.1f} KB)")

    if not wal_files and not shm_files:
        print("\n✓ No WAL/SHM files found (good)")

    return bool(wal_files or shm_files)


def check_file_timestamps():
    """Check file modification times to understand corruption timeline."""
    db_dir = Path("D:/agent-metrics/db")

    print("\n" + "=" * 80)
    print("FILE MODIFICATION TIMELINE")
    print("=" * 80)

    db_files = sorted(db_dir.glob("*.sqlite*"), key=lambda f: f.stat().st_mtime)

    for f in db_files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        size_mb = f.stat().st_size / (1024 * 1024)
        print(f"\n{mtime.strftime('%Y-%m-%d %H:%M:%S')} - {f.name}")
        print(f"  Size: {size_mb:.2f} MB")


def check_concurrent_access():
    """Check if database supports concurrent access properly."""
    db_path = Path("D:/agent-metrics/db/telemetry.backup.20251211_194517.sqlite")

    print("\n" + "=" * 80)
    print("CHECKING DATABASE CONFIGURATION (using healthy backup)")
    print("=" * 80)

    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Check journal mode
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        print(f"\nJournal mode: {journal_mode}")
        if journal_mode != "wal":
            print("  ⚠ WARNING: Not using WAL mode! This can cause corruption with concurrent access.")

        # Check synchronous setting
        cursor.execute("PRAGMA synchronous")
        synchronous = cursor.fetchone()[0]
        sync_names = {0: "OFF", 1: "NORMAL", 2: "FULL", 3: "EXTRA"}
        print(f"Synchronous: {sync_names.get(synchronous, synchronous)}")
        if synchronous == 0:
            print("  ⚠ WARNING: Synchronous=OFF increases corruption risk on crashes!")

        # Check locking mode
        cursor.execute("PRAGMA locking_mode")
        locking = cursor.fetchone()[0]
        print(f"Locking mode: {locking}")

        # Check page size
        cursor.execute("PRAGMA page_size")
        page_size = cursor.fetchone()[0]
        print(f"Page size: {page_size} bytes")

        # Check auto_vacuum
        cursor.execute("PRAGMA auto_vacuum")
        auto_vacuum = cursor.fetchone()[0]
        vacuum_names = {0: "NONE", 1: "FULL", 2: "INCREMENTAL"}
        print(f"Auto vacuum: {vacuum_names.get(auto_vacuum, auto_vacuum)}")

        conn.close()

    except Exception as e:
        print(f"⚠ Error checking database config: {e}")


def check_disk_space():
    """Check available disk space on D: drive."""
    import shutil

    print("\n" + "=" * 80)
    print("DISK SPACE CHECK")
    print("=" * 80)

    try:
        usage = shutil.disk_usage("D:\\")
        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        percent_used = (usage.used / usage.total) * 100

        print(f"\nD: drive usage:")
        print(f"  Total: {total_gb:.1f} GB")
        print(f"  Used: {used_gb:.1f} GB ({percent_used:.1f}%)")
        print(f"  Free: {free_gb:.1f} GB")

        if free_gb < 1:
            print("  ⚠ WARNING: Very low disk space! This can cause database corruption.")
        elif free_gb < 5:
            print("  ⚠ WARNING: Low disk space may affect database operations.")

    except Exception as e:
        print(f"⚠ Error checking disk space: {e}")


def analyze_corruption_size():
    """Analyze the corrupted database file size patterns."""
    db_dir = Path("D:/agent-metrics/db")

    print("\n" + "=" * 80)
    print("CORRUPTION SIZE ANALYSIS")
    print("=" * 80)

    sizes = {
        "Healthy backup 1": 1.06,
        "Healthy backup 2": 1.06,
        "Current (corrupted)": 0.77,
        "Forensic copy (corrupted)": 42.34,
    }

    print("\nDatabase sizes:")
    for name, size in sizes.items():
        print(f"  {name}: {size:.2f} MB")

    print("\nObservations:")
    print("  - Healthy databases: ~1.06 MB (consistent)")
    print("  - Current corrupted: 0.77 MB (SMALLER - data loss!)")
    print("  - Forensic corrupted: 42.34 MB (MUCH LARGER - bloat!)")
    print("\nPossible causes:")
    print("  - Small corrupted file: Incomplete writes, system crash, disk full")
    print("  - Large corrupted file: WAL checkpoint failure, abandoned WAL accumulation")


def main():
    """Run all corruption analysis checks."""
    print("DATABASE CORRUPTION ROOT CAUSE ANALYSIS")
    print("=" * 80)

    # Run checks
    has_wal = check_wal_files()
    check_file_timestamps()
    check_concurrent_access()
    check_disk_space()
    analyze_corruption_size()

    # Summary
    print("\n" + "=" * 80)
    print("LIKELY ROOT CAUSES")
    print("=" * 80)

    print("\nBased on the analysis, the most likely causes are:")
    print("\n1. WAL CHECKPOINT ISSUES")
    print("   - Large corrupted file (42 MB) suggests WAL not checkpointing")
    print("   - Solution: Ensure proper WAL checkpoints, reduce wal_autocheckpoint value")

    print("\n2. INCOMPLETE WRITES / SYSTEM CRASHES")
    print("   - Small corrupted file (0.77 MB) suggests interrupted write")
    print("   - Solution: Use PRAGMA synchronous=FULL, backup before critical ops")

    print("\n3. CONCURRENT ACCESS WITHOUT PROPER LOCKING")
    print("   - Multiple processes may be accessing the database")
    print("   - Solution: Ensure all processes use busy_timeout, WAL mode")

    if has_wal:
        print("\n4. ACTIVE WAL FILES FOUND")
        print("   - WAL files present indicate incomplete transactions")
        print("   - Solution: Run 'PRAGMA wal_checkpoint(TRUNCATE)' to clean up")

    print("\n" + "=" * 80)
    print("RECOMMENDED FIXES")
    print("=" * 80)
    print("\n1. Enable robust corruption prevention settings:")
    print("   - PRAGMA journal_mode=WAL")
    print("   - PRAGMA synchronous=FULL (not NORMAL)")
    print("   - PRAGMA busy_timeout=30000 (increase from 5000)")
    print("   - PRAGMA wal_autocheckpoint=100 (decrease from 1000)")

    print("\n2. Add database health checks before/after operations")

    print("\n3. Implement automatic backup before critical operations")

    print("\n4. Add WAL checkpoint after large write batches")

    print("\n5. Consider using a connection pool to prevent concurrent issues")

    return 0


if __name__ == "__main__":
    sys.exit(main())
