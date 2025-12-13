"""
Tests for telemetry.local module

Tests cover:
- NDJSONWriter file creation and appending
- Daily log rotation
- File locking (platform-specific)
- Reading and parsing NDJSON files
- File listing and info
- Crash resilience (explicit flush)
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.local import NDJSONWriter


class TestNDJSONWriterCreation:
    """Test NDJSONWriter initialization."""

    def test_writer_creation(self, tmp_path):
        """Test creating NDJSONWriter."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        assert writer.ndjson_dir == ndjson_dir

    def test_writer_creates_directory(self, tmp_path):
        """Test that writer creates directory if it doesn't exist."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        assert ndjson_dir.exists()
        assert ndjson_dir.is_dir()


class TestNDJSONAppend:
    """Test appending records to NDJSON files."""

    def test_append_single_record(self, tmp_path):
        """Test appending a single record."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        payload = {"run_id": "test-123", "status": "success"}
        success, message = writer.append(payload)

        assert success is True
        assert "[OK]" in message

    def test_append_creates_daily_file(self, tmp_path):
        """Test that append creates daily file."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        payload = {"run_id": "test-123", "status": "success"}
        writer.append(payload)

        # Check that file was created
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        expected_file = ndjson_dir / f"events_{today}.ndjson"
        assert expected_file.exists()

    def test_append_multiple_records(self, tmp_path):
        """Test appending multiple records."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        payloads = [
            {"run_id": "test-1", "status": "success"},
            {"run_id": "test-2", "status": "failed"},
            {"run_id": "test-3", "status": "success"},
        ]

        for i, payload in enumerate(payloads):
            success, message = writer.append(payload)
            if not success:
                print(f"\nAppend {i+1} failed: {message}")
            assert success is True, f"Append {i+1} failed: {message}"

        # Read file and verify all records
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = ndjson_dir / f"events_{today}.ndjson"

        with open(file_path, "r") as f:
            lines = f.readlines()

        assert len(lines) == 3

    def test_append_preserves_json_structure(self, tmp_path):
        """Test that appended records preserve JSON structure."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        payload = {
            "run_id": "test-123",
            "status": "success",
            "nested": {"key": "value", "count": 42},
            "array": [1, 2, 3],
        }

        writer.append(payload)

        # Read and parse
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = ndjson_dir / f"events_{today}.ndjson"

        with open(file_path, "r") as f:
            line = f.readline()

        restored = json.loads(line)
        assert restored["nested"]["key"] == "value"
        assert restored["array"] == [1, 2, 3]

    def test_append_handles_unicode(self, tmp_path):
        """Test appending records with Unicode characters."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        payload = {
            "run_id": "test-123",
            "message": "Hello 世界 🌍",
            "emoji": "✓ ✗",
        }

        success, _ = writer.append(payload)
        assert success is True

        # Read and verify
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = ndjson_dir / f"events_{today}.ndjson"

        with open(file_path, "r", encoding="utf-8") as f:
            line = f.readline()

        restored = json.loads(line)
        assert restored["message"] == "Hello 世界 🌍"


class TestDailyRotation:
    """Test daily file rotation."""

    def test_daily_file_naming(self, tmp_path):
        """Test that daily files are named correctly."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        payload = {"run_id": "test-123"}
        writer.append(payload)

        # Check filename format
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        expected_file = ndjson_dir / f"events_{today}.ndjson"
        assert expected_file.exists()

    def test_get_daily_file(self, tmp_path):
        """Test _get_daily_file returns correct path."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        file_path = writer._get_daily_file()

        # Should contain today's date
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        assert today in str(file_path)
        assert file_path.name.startswith("events_")
        assert file_path.name.endswith(".ndjson")


class TestReadingFiles:
    """Test reading NDJSON files."""

    def test_read_file(self, tmp_path):
        """Test reading an NDJSON file."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        # Write some records
        payloads = [
            {"run_id": "test-1", "status": "success"},
            {"run_id": "test-2", "status": "failed"},
        ]

        for payload in payloads:
            writer.append(payload)

        # Read file
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        records = writer.read_file(today)

        assert len(records) == 2
        assert records[0]["run_id"] == "test-1"
        assert records[1]["run_id"] == "test-2"

    def test_read_file_not_found(self, tmp_path):
        """Test reading non-existent file raises error."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        with pytest.raises(FileNotFoundError):
            writer.read_file("20990101")  # Far future date

    def test_read_file_skips_empty_lines(self, tmp_path):
        """Test that read_file skips empty lines."""
        ndjson_dir = tmp_path / "ndjson"
        ndjson_dir.mkdir(parents=True, exist_ok=True)

        # Create file with empty lines
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = ndjson_dir / f"events_{today}.ndjson"

        with open(file_path, "w") as f:
            f.write('{"run_id": "test-1"}\n')
            f.write('\n')  # Empty line
            f.write('{"run_id": "test-2"}\n')
            f.write('   \n')  # Whitespace line

        writer = NDJSONWriter(ndjson_dir)
        records = writer.read_file(today)

        # Should only get 2 records, empty lines ignored
        assert len(records) == 2

    def test_read_file_handles_invalid_json(self, tmp_path):
        """Test that read_file handles invalid JSON gracefully."""
        ndjson_dir = tmp_path / "ndjson"
        ndjson_dir.mkdir(parents=True, exist_ok=True)

        # Create file with invalid JSON
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = ndjson_dir / f"events_{today}.ndjson"

        with open(file_path, "w") as f:
            f.write('{"run_id": "test-1"}\n')
            f.write('invalid json line\n')
            f.write('{"run_id": "test-2"}\n')

        writer = NDJSONWriter(ndjson_dir)
        records = writer.read_file(today)

        # Should get 2 valid records, invalid line skipped
        assert len(records) == 2


class TestFileManagement:
    """Test file listing and info functions."""

    def test_list_files_empty(self, tmp_path):
        """Test listing files when directory is empty."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        files = writer.list_files()
        assert len(files) == 0

    def test_list_files(self, tmp_path):
        """Test listing NDJSON files."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        # Create some files
        writer.append({"run_id": "test-1"})
        writer.append({"run_id": "test-2"})

        files = writer.list_files()
        assert len(files) >= 1
        assert all(f.name.startswith("events_") for f in files)
        assert all(f.name.endswith(".ndjson") for f in files)

    def test_list_files_sorted(self, tmp_path):
        """Test that list_files returns sorted list."""
        ndjson_dir = tmp_path / "ndjson"
        ndjson_dir.mkdir(parents=True, exist_ok=True)

        # Create multiple files with different dates
        dates = ["20250101", "20250103", "20250102"]
        for date in dates:
            file_path = ndjson_dir / f"events_{date}.ndjson"
            file_path.write_text('{"test": true}\n')

        writer = NDJSONWriter(ndjson_dir)
        files = writer.list_files()

        # Should be sorted
        assert len(files) == 3
        assert "20250101" in files[0].name
        assert "20250102" in files[1].name
        assert "20250103" in files[2].name

    def test_get_file_info(self, tmp_path):
        """Test getting file info."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        # Write some records
        for i in range(5):
            writer.append({"run_id": f"test-{i}"})

        # Get file info
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = ndjson_dir / f"events_{today}.ndjson"

        info = writer.get_file_info(file_path)

        assert info["filename"] == file_path.name
        assert info["size_bytes"] > 0
        assert info["line_count"] == 5
        assert info["path"] == str(file_path)

    def test_get_file_info_not_found(self, tmp_path):
        """Test getting info for non-existent file."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        fake_path = ndjson_dir / "nonexistent.ndjson"

        with pytest.raises(FileNotFoundError):
            writer.get_file_info(fake_path)


class TestConcurrency:
    """Test concurrent write scenarios."""

    def test_multiple_appends_sequential(self, tmp_path):
        """Test multiple sequential appends work correctly."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        # Append 100 records sequentially
        for i in range(100):
            payload = {"run_id": f"test-{i}", "index": i}
            success, _ = writer.append(payload)
            assert success is True

        # Verify all records written
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        records = writer.read_file(today)
        assert len(records) == 100

    def test_file_locking_availability(self):
        """Test that file locking modules are available."""
        import sys

        if sys.platform == "win32":
            import msvcrt
            assert msvcrt is not None
        else:
            import fcntl
            assert fcntl is not None


class TestErrorHandling:
    """Test error handling in NDJSONWriter."""

    def test_append_returns_error_on_invalid_path(self):
        """Test that append returns error for invalid path."""
        import sys

        # Use an invalid path that will cause write to fail
        # On Windows, CON is a reserved device name that cannot be used as a directory
        if sys.platform == "win32":
            invalid_dir = Path("CON:")
        else:
            # On Unix, use a path that requires root permissions
            invalid_dir = Path("/root/nonexistent/path")

        try:
            writer = NDJSONWriter(invalid_dir)
            payload = {"run_id": "test-123"}

            # Should return False, not crash
            success, message = writer.append(payload)
            assert success is False
            assert "[FAIL]" in message
        except (OSError, PermissionError):
            # It's also acceptable if initialization itself fails
            pass


class TestFileFlushing:
    """Test explicit file flushing for crash resilience."""

    def test_append_flushes_to_disk(self, tmp_path):
        """Test that append flushes data to disk."""
        ndjson_dir = tmp_path / "ndjson"
        writer = NDJSONWriter(ndjson_dir)

        payload = {"run_id": "test-123", "large_data": "x" * 10000}
        writer.append(payload)

        # File should be written and flushed
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        file_path = ndjson_dir / f"events_{today}.ndjson"

        # Should be readable immediately (not buffered)
        with open(file_path, "r") as f:
            content = f.read()
            assert len(content) > 0
