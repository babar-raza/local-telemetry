"""
Telemetry Platform - Local NDJSON Writer

Writes telemetry events to newline-delimited JSON files with file locking for concurrent access.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any


class NDJSONWriter:
    """
    Writes telemetry data to NDJSON files with file locking.

    Features:
    - Daily log rotation (one file per day)
    - File locking for concurrent writes (Windows: msvcrt, Unix: fcntl)
    - Explicit flush after every write (crash resilience)
    - Atomic appends

    File naming: events_YYYYMMDD.ndjson
    Example: events_20251210.ndjson
    """

    def __init__(self, ndjson_dir: Path):
        """
        Initialize NDJSON writer.

        Args:
            ndjson_dir: Directory where NDJSON files will be written
        """
        self.ndjson_dir = Path(ndjson_dir)

        # Ensure directory exists
        self.ndjson_dir.mkdir(parents=True, exist_ok=True)

    def _get_daily_file(self) -> Path:
        """
        Get the NDJSON file path for today.

        Returns:
            Path: NDJSON file path for today

        Example:
            D:\\agent-metrics\\raw\\events_20251210.ndjson
        """
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        filename = f"events_{today}.ndjson"
        return self.ndjson_dir / filename

    def append(self, payload: Dict[str, Any]) -> tuple[bool, str]:
        """
        Append a JSON object to the daily NDJSON file with file locking.

        Args:
            payload: Dictionary to write as JSON

        Returns:
            Tuple of (success: bool, message: str)
        """
        ndjson_file = self._get_daily_file()

        try:
            # Open file in append mode
            with open(ndjson_file, "a", encoding="utf-8") as f:
                # Apply file lock based on platform
                if sys.platform == "win32":
                    # Windows file locking
                    self._lock_windows(f)
                else:
                    # Unix/Linux file locking
                    self._lock_unix(f)

                try:
                    # Write JSON line
                    json_line = json.dumps(payload)
                    f.write(json_line + "\n")

                    # Explicit flush (crash resilience per review feedback)
                    f.flush()

                    # Force to disk (fsync)
                    os.fsync(f.fileno())

                finally:
                    # Release lock
                    if sys.platform == "win32":
                        self._unlock_windows(f)
                    else:
                        self._unlock_unix(f)

            return True, f"[OK] Wrote to {ndjson_file.name}"

        except Exception as e:
            return False, f"[FAIL] NDJSON write error: {e}"

    def _lock_windows(self, file_handle):
        """
        Lock file on Windows using msvcrt.

        Args:
            file_handle: Open file handle
        """
        import msvcrt

        # Seek to start to lock at position 0
        file_handle.seek(0)

        # Lock 1 byte at position 0
        # LK_LOCK = exclusive lock, will block until available
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_LOCK, 1)

        # Seek to end for appending
        file_handle.seek(0, 2)  # 2 = os.SEEK_END

    def _unlock_windows(self, file_handle):
        """
        Unlock file on Windows using msvcrt.

        Args:
            file_handle: Open file handle
        """
        import msvcrt

        # Seek to start for unlock
        file_handle.seek(0)

        # Unlock the byte
        msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)

    def _lock_unix(self, file_handle):
        """
        Lock file on Unix/Linux using fcntl.

        Args:
            file_handle: Open file handle
        """
        import fcntl

        # Exclusive lock (LOCK_EX), will block until available
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)

    def _unlock_unix(self, file_handle):
        """
        Unlock file on Unix/Linux using fcntl.

        Args:
            file_handle: Open file handle
        """
        import fcntl

        # Unlock
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)

    def read_file(self, date_str: str) -> list[Dict[str, Any]]:
        """
        Read and parse an NDJSON file for a specific date.

        Args:
            date_str: Date string in YYYYMMDD format

        Returns:
            List of dictionaries (parsed JSON objects)

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        filename = f"events_{date_str}.ndjson"
        filepath = self.ndjson_dir / filename

        if not filepath.exists():
            raise FileNotFoundError(f"NDJSON file not found: {filepath}")

        records = []

        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:  # Skip empty lines
                    try:
                        record = json.loads(line)
                        records.append(record)
                    except json.JSONDecodeError as e:
                        # Log error but continue
                        print(f"Warning: Invalid JSON line: {e}")
                        continue

        return records

    def list_files(self) -> list[Path]:
        """
        List all NDJSON files in the directory.

        Returns:
            List of Path objects, sorted by filename
        """
        pattern = "events_*.ndjson"
        files = list(self.ndjson_dir.glob(pattern))
        return sorted(files)

    def get_file_info(self, filepath: Path) -> Dict[str, Any]:
        """
        Get information about an NDJSON file.

        Args:
            filepath: Path to NDJSON file

        Returns:
            Dictionary with file info (size, line count, date range)
        """
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        # Get file size
        size_bytes = filepath.stat().st_size

        # Count lines
        line_count = 0
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    line_count += 1

        return {
            "filename": filepath.name,
            "size_bytes": size_bytes,
            "line_count": line_count,
            "path": str(filepath),
        }
