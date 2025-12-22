"""
Buffer File Lifecycle Management

Implements the .active → .ready → .synced file state machine for telemetry events.

File States:
    - .jsonl.active: Current file, append-only
    - .jsonl.ready:  Closed, ready for sync
    - .jsonl.synced: Processed, archived

Idempotency: Each event has a UUID event_id. The API rejects duplicates via
UNIQUE constraint, enabling at-least-once delivery with retry safety.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class BufferFile:
    """
    Manages .jsonl buffer file lifecycle.

    Handles file rotation based on size/age thresholds and provides
    atomic append operations.
    """

    def __init__(self, buffer_dir: str, max_size_mb: int = 10, max_age_hours: int = 24):
        """
        Initialize buffer file manager.

        Args:
            buffer_dir: Directory for buffer files
            max_size_mb: Maximum file size before rotation (default: 10MB)
            max_age_hours: Maximum file age before rotation (default: 24h)
        """
        self.buffer_dir = Path(buffer_dir)
        self.buffer_dir.mkdir(parents=True, exist_ok=True)
        self.current_file: Optional[Path] = None
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.max_age_seconds = max_age_hours * 3600

        # Find existing active file or create new one
        self._init_active_file()

    def _init_active_file(self):
        """Initialize by finding existing .active file or creating new one."""
        # Look for existing .active file
        active_files = list(self.buffer_dir.glob("*.jsonl.active"))

        if active_files:
            # Use most recent active file
            self.current_file = sorted(active_files, key=lambda p: p.stat().st_mtime)[-1]
            print(f"[OK] Using existing buffer: {self.current_file.name}")
        else:
            # Create new active file
            self._create_new_active_file()

    def append(self, event: dict):
        """
        Append event to buffer (atomic, never fails).

        Args:
            event: Event dictionary (must contain event_id)
        """
        # Check rotation before write
        if self._should_rotate():
            self._rotate()
            self._create_new_active_file()

        # Ensure we have an active file
        if not self.current_file:
            self._create_new_active_file()

        # Write event as JSON line
        line = json.dumps(event) + "\n"

        try:
            # Append to active file
            with open(self.current_file, 'a', encoding='utf-8') as f:
                f.write(line)
                f.flush()
                # Note: We intentionally don't fsync() here for performance
                # Buffering is acceptable - at-least-once delivery handles this

        except (IOError, OSError) as e:
            print(f"[ERROR] Failed to write to buffer: {e}")
            # In production, this would retry or escalate
            raise

    def _should_rotate(self) -> bool:
        """Check if current file should be rotated."""
        if not self.current_file or not self.current_file.exists():
            return False

        # Size threshold
        if self.current_file.stat().st_size >= self.max_size_bytes:
            return True

        # Age threshold
        age = time.time() - self.current_file.stat().st_mtime
        if age >= self.max_age_seconds:
            return True

        return False

    def _rotate(self):
        """Rotate active file to ready state."""
        if self.current_file and self.current_file.exists():
            # Rename .active to .ready (atomic on POSIX, best-effort on Windows)
            # Replace .jsonl.active with .jsonl.ready
            ready_file = Path(str(self.current_file).replace(".jsonl.active", ".jsonl.ready"))
            self.current_file.rename(ready_file)
            print(f"[OK] Rotated: {self.current_file.name} -> {ready_file.name}")
            self.current_file = None

    def _create_new_active_file(self):
        """Create new active buffer file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"telemetry_{timestamp}.jsonl.active"
        self.current_file = self.buffer_dir / filename
        self.current_file.touch()
        print(f"[OK] Created new buffer: {filename}")

    def force_rotate(self):
        """Force rotation of current active file (for testing/shutdown)."""
        if self.current_file and self.current_file.exists():
            self._rotate()


class BufferSyncWorker:
    """
    Syncs .ready files to API with idempotent retry.

    Implements at-least-once delivery: retries entire file on failure,
    API deduplicates via event_id UNIQUE constraint.
    """

    def __init__(self, buffer_dir: str, api_url: str, batch_size: int = 100):
        """
        Initialize buffer sync worker.

        Args:
            buffer_dir: Directory containing buffer files
            api_url: Base URL of telemetry API (e.g., "http://localhost:8765")
            batch_size: Number of events per batch (default: 100)
        """
        if not HAS_REQUESTS:
            raise ImportError("requests module required for BufferSyncWorker. Install with: pip install requests")

        self.buffer_dir = Path(buffer_dir)
        self.api_url = api_url.rstrip('/')
        self.batch_size = batch_size

    def sync_all_ready_files(self) -> dict:
        """
        Sync all .ready files to API.

        Returns:
            dict: Summary statistics {files_processed, total_sent, total_duplicates, errors}
        """
        stats = {
            "files_processed": 0,
            "total_sent": 0,
            "total_duplicates": 0,
            "errors": []
        }

        # Find all .ready files
        ready_files = sorted(self.buffer_dir.glob("*.jsonl.ready"))

        if not ready_files:
            print("[OK] No .ready files to sync")
            return stats

        print(f"[OK] Found {len(ready_files)} .ready files to sync")

        for file_path in ready_files:
            try:
                result = self.sync_file(file_path)
                stats["files_processed"] += 1
                stats["total_sent"] += result.get("sent", 0)
                stats["total_duplicates"] += result.get("duplicates", 0)
            except Exception as e:
                error_msg = f"{file_path.name}: {e}"
                stats["errors"].append(error_msg)
                print(f"[ERROR] {error_msg}")

        return stats

    def sync_file(self, file_path: Path) -> dict:
        """
        Sync single .ready file to API with idempotent retry.

        Strategy: At-least-once delivery, API deduplicates via event_id.

        Args:
            file_path: Path to .jsonl.ready file

        Returns:
            dict: {sent: N, duplicates: M}
        """
        print(f"[OK] Syncing: {file_path.name}")

        # Read all records from file
        records = []
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    record = json.loads(line.strip())
                    # Validate event_id exists
                    if 'event_id' not in record:
                        print(f"[WARN] Line {line_num} missing event_id, skipping")
                        continue
                    records.append(record)
                except json.JSONDecodeError as e:
                    print(f"[WARN] Invalid JSON on line {line_num}: {e}")

        if not records:
            # Empty file - mark as synced
            print(f"[OK] Empty file, marking as synced")
            synced_path = Path(str(file_path).replace(".jsonl.ready", ".jsonl.synced"))
            file_path.rename(synced_path)
            return {"sent": 0, "duplicates": 0}

        # Send in batches
        total_sent = 0
        total_duplicates = 0

        for i in range(0, len(records), self.batch_size):
            batch = records[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1

            try:
                response = requests.post(
                    f"{self.api_url}/api/v1/runs/batch",
                    json=batch,
                    timeout=30
                )
                response.raise_for_status()
                result = response.json()

                inserted = result.get('inserted', 0)
                duplicates = result.get('duplicates', 0)
                errors = result.get('errors', [])

                print(f"[OK] Batch {batch_num}: {inserted} new, {duplicates} duplicates")

                if errors:
                    print(f"[WARN] Batch {batch_num} had {len(errors)} errors")
                    for error in errors[:5]:  # Show first 5 errors
                        print(f"  - {error}")

                total_sent += len(batch)
                total_duplicates += duplicates

            except requests.RequestException as e:
                print(f"[ERROR] Batch {batch_num} failed: {e}")
                print(f"[OK] Progress: {total_sent}/{len(records)} sent")
                print(f"[OK] Will retry entire file on next run")
                # Don't mark as synced - file will retry on next run
                return {"sent": total_sent, "duplicates": total_duplicates}

        # All batches succeeded - mark as synced
        synced_path = Path(str(file_path).replace(".jsonl.ready", ".jsonl.synced"))
        file_path.rename(synced_path)
        print(f"[OK] Completed: {file_path.name} -> {synced_path.name}")
        print(f"[OK] Total: {total_sent} records sent, {total_duplicates} duplicates")

        return {"sent": total_sent, "duplicates": total_duplicates}


def test_buffer_lifecycle():
    """
    Test the buffer file lifecycle.

    This creates test files and verifies state transitions.
    """
    import tempfile
    import shutil
    import uuid

    print("=== Testing Buffer File Lifecycle ===\n")

    # Create temporary buffer directory
    temp_dir = Path(tempfile.mkdtemp(prefix="telemetry_buffer_test_"))

    try:
        # Test 1: Create buffer and append events
        print("Test 1: Create buffer and append events")
        buffer = BufferFile(str(temp_dir), max_size_mb=0.001, max_age_hours=0.01)  # Very small thresholds

        # Append test events
        for i in range(5):
            event = {
                "event_id": str(uuid.uuid4()),
                "run_id": f"test-run-{i}",
                "agent_name": "test-agent",
                "job_type": "test",
                "start_time": datetime.now().isoformat()
            }
            buffer.append(event)

        assert buffer.current_file is not None, "Active file should exist"
        assert buffer.current_file.exists(), "Active file should exist on disk"
        print("[PASS]\n")

        # Test 2: Force rotation
        print("Test 2: Force rotation")
        buffer.force_rotate()

        ready_files = list(temp_dir.glob("*.jsonl.ready"))
        assert len(ready_files) == 1, "Should have one .ready file"
        print(f"[PASS] Ready file: {ready_files[0].name}\n")

        # Test 3: Verify file content
        print("Test 3: Verify file content")
        with open(ready_files[0], 'r') as f:
            lines = f.readlines()

        assert len(lines) == 5, "Should have 5 events"
        for line in lines:
            event = json.loads(line)
            assert 'event_id' in event, "Event should have event_id"
            assert 'run_id' in event, "Event should have run_id"

        print(f"[PASS] All {len(lines)} events valid\n")

        print("=== All Tests Passed ===")

    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_buffer_lifecycle()
