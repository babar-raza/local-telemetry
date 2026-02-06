"""
Single-Writer Guard - Ensures exactly one telemetry API process writes to database.

This module provides runtime enforcement of the single-writer constraint to prevent
database corruption from concurrent writes.

Usage:
    guard = SingleWriterGuard("/data/telemetry_api.lock")
    guard.acquire()  # Fails fast if another instance running
    try:
        # Run API server
        pass
    finally:
        guard.release()
"""

import os
import sys
import platform
from pathlib import Path
from typing import Optional

# Platform-specific imports
if platform.system() == "Windows":
    import msvcrt
else:
    import fcntl


class SingleWriterGuard:
    """
    Ensures exactly one telemetry API process writes to database.

    Uses file locking to prevent multiple API instances from starting.
    Platform-agnostic: supports both Windows (msvcrt) and Unix (fcntl).
    """

    def __init__(self, lock_file: str):
        """
        Initialize the single-writer guard.

        Args:
            lock_file: Path to lock file (e.g., "/tmp/telemetry_api.lock")
        """
        self.lock_file = Path(lock_file)
        self.lock_fd = None  # file handle
        self.is_windows = platform.system() == "Windows"

    def acquire(self):
        """
        Acquire exclusive lock - fails if another instance running.

        Uses OS-level file locking. Locks are released automatically if the process dies,
        preventing stale lock-file wedges after crashes or abrupt container stops.

        Raises:
            SystemExit: If lock cannot be acquired (another instance running)
        """
        # Ensure parent directory exists
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)

        # Robust single-writer enforcement: use OS-level file locking.
        #
        # Why this change:
        # - Relying on "file exists" can wedge the service if the lock file is left behind
        #   (empty/truncated) after a crash or abrupt container stop.
        # - OS-level locks are released automatically when the process dies.
        #
        # Strategy:
        # - Open the lock file (create if needed)
        # - Acquire a non-blocking exclusive lock
        # - Truncate + write PID/hostname for troubleshooting
        try:
            self.lock_fd = open(self.lock_file, 'a+')

            if self.is_windows:
                # Lock 1 byte at start of file
                try:
                    self.lock_fd.seek(0)
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                except (IOError, OSError):
                    self._print_lock_error()
                    sys.exit(1)
            else:
                try:
                    fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (IOError, OSError):
                    self._print_lock_error()
                    sys.exit(1)

            # Write PID and hostname to lock file for troubleshooting
            self.lock_fd.seek(0)
            self.lock_fd.truncate()
            self.lock_fd.write(f"{os.getpid()}\n")
            self.lock_fd.write(f"{platform.node()}\n")
            self.lock_fd.flush()

            print(f"[OK] Acquired single-writer lock: {self.lock_file}")

        except (IOError, OSError) as e:
            self._print_lock_error()
            sys.exit(1)

    def release(self):
        """
        Release lock on graceful shutdown.

        Safe to call multiple times (idempotent).
        """
        if self.lock_fd:
            try:
                # Release Unix flock if applicable
                if not self.is_windows:
                    try:
                        fcntl.flock(self.lock_fd.fileno(), fcntl.LOCK_UN)
                    except (IOError, OSError):
                        pass  # Already unlocked

                # Release Windows lock if applicable
                if self.is_windows:
                    try:
                        self.lock_fd.seek(0)
                        msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                    except (IOError, OSError):
                        pass  # Already unlocked

                # Close file descriptor
                self.lock_fd.close()
                self.lock_fd = None

                # Remove lock file
                self.lock_file.unlink(missing_ok=True)

                print(f"[OK] Released single-writer lock")

            except (IOError, OSError) as e:
                # Log error but don't raise (shutdown in progress)
                print(f"[WARN] Error releasing lock: {e}")
            finally:
                self.lock_fd = None

    def _is_stale_lock(self) -> bool:
        """
        Detect if a text-based lock marker appears stale (legacy helper; currently unused).

        A lock is considered stale if:
        - Lock holder hostname differs from current hostname (different container)
        - Lock holder hostname matches but PID doesn't exist (same container restarted)

        In Docker, PID 1 is always the main process. If we're PID 1 and lock says PID 1
        but we're starting up, the old PID 1 is dead (same container restarted).

        Returns:
            True if lock appears stale and can be cleaned up
        """
        try:
            with open(self.lock_file, 'r') as f:
                lock_pid = f.readline().strip()
                lock_host = f.readline().strip()

            current_host = platform.node()
            current_pid = os.getpid()

            # Case 1: Different hostname = different container (definitely stale)
            if lock_host and lock_host != current_host:
                print(f"[INFO] Lock held by host '{lock_host}', current host is '{current_host}'")
                return True

            # Case 2: Same hostname - check if it's us restarting
            # In Docker, we're usually PID 1. If lock says PID 1 from same host,
            # and we're PID 1 and just starting, the old process is dead.
            if lock_pid and lock_host == current_host:
                try:
                    lock_pid_int = int(lock_pid)
                    # If lock PID matches our PID on same host, we're restarting
                    if lock_pid_int == current_pid:
                        print(f"[INFO] Lock held by same PID {lock_pid} on same host - container restarted")
                        return True
                except ValueError:
                    pass

            # Case 3: On Unix, check if the process actually exists
            if not self.is_windows and lock_pid:
                try:
                    lock_pid_int = int(lock_pid)
                    # Send signal 0 to check if process exists (doesn't actually signal)
                    os.kill(lock_pid_int, 0)
                    # Process exists - not stale
                    print(f"[INFO] Lock holder PID {lock_pid} is still running")
                    return False
                except (ProcessLookupError, OSError):
                    # Process doesn't exist - stale lock
                    print(f"[INFO] Lock holder PID {lock_pid} not found - stale lock")
                    return True
                except ValueError:
                    pass

            # Can't determine - be conservative
            return False

        except Exception as e:
            # Can't read lock file - assume not stale to be safe
            print(f"[WARN] Could not read lock file: {e}")
            return False

    def _print_lock_error(self):
        """Print helpful error when lock acquisition fails."""
        print("=" * 70)
        print("[CRITICAL] Another telemetry API instance is already running")
        print("=" * 70)

        # Try to read lock file to show PID and host
        if self.lock_file.exists():
            try:
                with open(self.lock_file, 'r') as f:
                    pid = f.readline().strip()
                    host = f.readline().strip()
                print(f"Lock held by PID: {pid} on host: {host}")
            except Exception as e:
                print(f"Lock file exists but couldn't read: {self.lock_file}")
                print(f"Error: {e}")

        print("\nOptions:")
        print("1. Stop the other instance before starting this one")
        print(f"2. If stale lock (process dead), delete: {self.lock_file}")
        print("3. Check with: ps aux | grep telemetry_api  (Unix)")
        print("              tasklist | findstr telemetry  (Windows)")
        print("=" * 70)

    def __enter__(self):
        """Context manager support."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager support."""
        self.release()
        return False


def test_single_writer_guard():
    """
    Test the single-writer guard functionality.

    This is a simple test that can be run directly.
    """
    import tempfile
    import time

    print("=== Testing Single-Writer Guard ===\n")

    # Create temporary lock file
    lock_file = os.path.join(tempfile.gettempdir(), "test_telemetry.lock")

    # Remove if exists
    if os.path.exists(lock_file):
        os.remove(lock_file)

    # Test 1: Acquire lock successfully
    print("Test 1: Acquire lock successfully")
    guard1 = SingleWriterGuard(lock_file)
    guard1.acquire()
    assert os.path.exists(lock_file), "Lock file should exist"
    print("[PASS]\n")

    # Test 2: Second instance should fail
    print("Test 2: Second instance should fail")
    guard2 = SingleWriterGuard(lock_file)
    try:
        guard2.acquire()
        print("[FAIL] Second instance should have failed")
        sys.exit(1)
    except SystemExit:
        print("[PASS] (expected failure)\n")

    # Test 3: Release lock and acquire again
    print("Test 3: Release lock and acquire again")
    guard1.release()
    assert not os.path.exists(lock_file), "Lock file should be removed"
    guard3 = SingleWriterGuard(lock_file)
    guard3.acquire()
    print("[PASS]\n")

    # Cleanup
    guard3.release()

    print("=== All Tests Passed ===")


if __name__ == "__main__":
    test_single_writer_guard()
