"""
Telemetry Platform - Storage Setup Script

Creates the central telemetry directory structure on Windows.
Idempotent and safe to run multiple times.

Usage:
    python scripts/setup_storage.py

Exit codes:
    0 - Success
    1 - Failure
"""

import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Tuple


def check_drive_exists(drive: str) -> bool:
    """
    Check if a drive letter exists and is accessible.

    Args:
        drive: Drive letter (e.g., 'D:' or 'C:')

    Returns:
        bool: True if drive exists and is accessible
    """
    if not drive or not drive.strip():
        return False

    try:
        drive_path = Path(f"{drive}\\")
        return drive_path.exists() and drive_path.is_dir()
    except (OSError, PermissionError):
        return False


def get_base_path() -> Path:
    """
    Determine the base path for telemetry storage.

    Primary: D:\\agent-metrics
    Fallback: C:\\agent-metrics

    Returns:
        Path: The selected base directory path
    """
    # Check for D: drive first (primary)
    if check_drive_exists("D:"):
        return Path("D:\\agent-metrics")

    # Fallback to C: drive
    if check_drive_exists("C:"):
        return Path("C:\\agent-metrics")

    # This should never happen on Windows, but handle gracefully
    raise RuntimeError("Neither D: nor C: drive is accessible")


def create_directory_structure(base: Path) -> Tuple[bool, list[str]]:
    """
    Create the telemetry directory structure.

    Directory structure:
        base/
        ├── raw/           # NDJSON event logs
        ├── db/            # SQLite database
        ├── reports/       # Generated reports
        ├── exports/       # CSV exports
        ├── config/        # Configuration files
        └── logs/          # System logs

    Args:
        base: Base directory path

    Returns:
        Tuple of (success: bool, messages: list[str])
    """
    subdirs = [
        ("raw", "NDJSON event logs (append-only)"),
        ("db", "SQLite database (single file)"),
        ("reports", "Generated Markdown/CSV reports"),
        ("exports", "CSV exports for Google Sheets"),
        ("config", "Configuration files (JSON, SQL)"),
        ("logs", "Scheduler and system logs"),
    ]

    messages = []

    try:
        # Create base directory
        if not base.exists():
            base.mkdir(parents=True, exist_ok=True)
            messages.append(f"[OK] Created base directory: {base}")
        else:
            messages.append(f"[OK] Base directory already exists: {base}")

        # Create subdirectories
        for subdir_name, description in subdirs:
            subdir_path = base / subdir_name
            if not subdir_path.exists():
                subdir_path.mkdir(parents=True, exist_ok=True)
                messages.append(f"[OK] Created {subdir_name}/ - {description}")
            else:
                messages.append(f"[OK] {subdir_name}/ already exists")

        return True, messages

    except (OSError, PermissionError) as e:
        messages.append(f"[FAIL] Error creating directory structure: {e}")
        return False, messages


def generate_readme(base: Path) -> Tuple[bool, str]:
    """
    Generate README.md with directory structure documentation.

    Args:
        base: Base directory path

    Returns:
        Tuple of (success: bool, message: str)
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    readme_content = f"""# Agent Telemetry Platform Storage

**Created:** {timestamp}
**Location:** `{base}`

## Directory Structure

```
{base.name}/
├── raw/           # NDJSON event logs (append-only)
├── db/            # SQLite database (single file)
├── reports/       # Generated Markdown/CSV reports
├── exports/       # CSV exports for Google Sheets
├── config/        # Configuration files (JSON, SQL)
└── logs/          # Scheduler and system logs
```

## Purpose

This directory serves as the central storage location for the multi-agent telemetry platform.

### Subdirectory Details

- **raw/**: Contains newline-delimited JSON (NDJSON) files with raw telemetry events. Files are named `events_YYYYMMDD.ndjson` and are append-only for crash resilience.

- **db/**: Contains the SQLite database file `telemetry.sqlite` which stores aggregated telemetry data from all agents.

- **reports/**: Contains generated Markdown and CSV reports for human consumption.

- **exports/**: Contains CSV files prepared for upload to Google Sheets dashboard.

- **config/**: Contains configuration files including database schema definitions and API credentials (encrypted).

- **logs/**: Contains system logs from scheduled tasks and background processes.

## Maintenance

- **Backup**: The SQLite database should be backed up regularly using hot backup procedures.
- **Archival**: NDJSON files older than 90 days should be compressed and archived.
- **Monitoring**: Check disk space regularly - telemetry data grows over time.

## Security

- This directory should NOT be placed in OneDrive or any cloud-synced location.
- API credentials in config/ should be encrypted at rest.
- Database should be readable only by authorized users/services.

## Generated By

Telemetry Platform Setup Script
Repository: local-telemetry
Script: scripts/setup_storage.py
"""

    readme_path = base / "README.md"

    try:
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        return True, f"[OK] Generated README.md at {readme_path}"
    except (OSError, PermissionError) as e:
        return False, f"[FAIL] Error generating README.md: {e}"


def verify_write_permissions(base: Path) -> Tuple[bool, str]:
    """
    Verify write permissions by creating and deleting a test file.

    Args:
        base: Base directory path

    Returns:
        Tuple of (success: bool, message: str)
    """
    test_file = base / "raw" / ".write_test"

    try:
        # Write test file
        with open(test_file, 'w') as f:
            f.write("test")

        # Read it back
        with open(test_file, 'r') as f:
            content = f.read()

        if content != "test":
            return False, "[FAIL] Write verification failed: content mismatch"

        # Delete test file
        test_file.unlink()

        return True, f"[OK] Write permissions verified in {base / 'raw'}"

    except (OSError, PermissionError) as e:
        return False, f"[FAIL] Write permission check failed: {e}"


def main() -> int:
    """
    Main entry point for storage setup.

    Returns:
        int: Exit code (0 = success, 1 = failure)
    """
    print("=" * 70)
    print("Telemetry Platform - Storage Setup")
    print("=" * 70)
    print()

    try:
        # Step 1: Determine base path
        print("[1/4] Determining storage location...")
        base_path = get_base_path()
        print(f"      Selected: {base_path}")
        print()

        # Step 2: Create directory structure
        print("[2/4] Creating directory structure...")
        success, messages = create_directory_structure(base_path)
        for msg in messages:
            print(f"      {msg}")

        if not success:
            print()
            print("[FAIL] Could not create directory structure")
            return 1
        print()

        # Step 3: Generate README
        print("[3/4] Generating README.md...")
        success, message = generate_readme(base_path)
        print(f"      {message}")

        if not success:
            print()
            print("[FAIL] Could not generate README.md")
            return 1
        print()

        # Step 4: Verify write permissions
        print("[4/4] Verifying write permissions...")
        success, message = verify_write_permissions(base_path)
        print(f"      {message}")

        if not success:
            print()
            print("[FAIL] Write permissions not available")
            return 1
        print()

        # Success
        print("=" * 70)
        print(f"[SUCCESS] Telemetry storage initialized at {base_path}")
        print("=" * 70)

        return 0

    except Exception as e:
        print()
        print(f"[ERROR] Unexpected error: {e}")
        print()
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
