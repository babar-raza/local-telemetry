"""
Telemetry system health monitoring script.
Run this periodically to check system health.
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path for telemetry imports
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root / "src"))

from telemetry import TelemetryConfig

def check_storage_availability():
    """Check if storage directories are accessible."""
    print("[1/6] Checking storage availability...")

    try:
        config = TelemetryConfig.from_env()

        if not config.metrics_dir.exists():
            print("  X Storage directory not found")
            return False

        if not config.ndjson_dir.exists():
            print("  X NDJSON directory not found")
            return False

        if not config.database_path.parent.exists():
            print("  X Database directory not found")
            return False

        print("  OK All directories accessible")
        return True

    except Exception as e:
        print(f"  X Error: {e}")
        return False

def check_database_accessible():
    """Check if database is accessible and not corrupted."""
    print("[2/6] Checking database...")

    try:
        config = TelemetryConfig.from_env()

        if not config.database_path.exists():
            print("  X Database file not found")
            return False

        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        # Integrity check
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()[0]

        if result != "ok":
            print(f"  X Database corrupted: {result}")
            conn.close()
            return False

        # Check tables exist (using actual table names from schema)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        required_tables = {"agent_runs", "run_events", "schema_migrations"}
        if required_tables.issubset(tables):
            print("  OK Database accessible and intact")
        else:
            missing = required_tables - tables
            print(f"  X Missing tables: {missing}")
            conn.close()
            return False

        conn.close()
        return True

    except Exception as e:
        print(f"  X Error: {e}")
        return False

def check_disk_space():
    """Check available disk space."""
    print("[3/6] Checking disk space...")

    try:
        config = TelemetryConfig.from_env()
        import shutil
        total, used, free = shutil.disk_usage(str(config.metrics_dir))

        free_gb = free / (1024**3)
        free_percent = (free / total) * 100

        print(f"  Free space: {free_gb:.2f} GB ({free_percent:.1f}%)")

        if free_gb < 1:
            print("  X Less than 1GB free")
            return False
        elif free_gb < 5:
            print("  ! Less than 5GB free")
            return True
        else:
            print("  OK Sufficient disk space")
            return True

    except Exception as e:
        print(f"  X Error: {e}")
        return False

def check_write_permissions():
    """Check write permissions."""
    print("[4/6] Checking write permissions...")

    try:
        config = TelemetryConfig.from_env()
        test_file = config.ndjson_dir / ".health_check"

        test_file.write_text("health check")
        test_file.unlink()

        print("  OK Write permissions OK")
        return True

    except Exception as e:
        print(f"  X Cannot write: {e}")
        return False

def check_recent_activity():
    """Check if system is receiving data."""
    print("[5/6] Checking recent activity...")

    try:
        config = TelemetryConfig.from_env()
        conn = sqlite3.connect(str(config.database_path))
        cursor = conn.cursor()

        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        cursor.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE start_time >= ?
        """, (one_hour_ago,))

        count = cursor.fetchone()[0]

        if count == 0:
            print("  ! No activity in last hour")
        else:
            print(f"  OK {count} runs in last hour")

        conn.close()
        return True

    except Exception as e:
        print(f"  X Error: {e}")
        return False

def check_database_size():
    """Check if database size is reasonable."""
    print("[6/6] Checking database size...")

    try:
        config = TelemetryConfig.from_env()
        size_mb = config.database_path.stat().st_size / (1024 * 1024)

        print(f"  Database size: {size_mb:.2f} MB")

        if size_mb > 500:
            print("  ! Database large (> 500MB), consider archiving")
            return True
        else:
            print("  OK Database size reasonable")
            return True

    except Exception as e:
        print(f"  X Error: {e}")
        return False

def main():
    """Run all health checks."""
    print("=" * 70)
    print(f"Telemetry Health Check - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    print()

    checks = [
        check_storage_availability(),
        check_database_accessible(),
        check_disk_space(),
        check_write_permissions(),
        check_recent_activity(),
        check_database_size(),
    ]

    print()
    print("=" * 70)

    if all(checks):
        print("OK ALL CHECKS PASSED - System healthy")
        return 0
    else:
        failed_count = sum(1 for c in checks if not c)
        print(f"X {failed_count} CHECK(S) FAILED - Action required")
        return 1

if __name__ == "__main__":
    sys.exit(main())
