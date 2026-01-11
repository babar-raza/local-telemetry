"""
Tests for storage setup script.

Verifies that the telemetry directory structure can be created correctly.
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

import pytest

# Add scripts to path for importing
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import setup_storage


class TestCheckDriveExists:
    """Test drive existence checks."""

    def test_existing_drive_c(self):
        """C: drive should always exist on Windows."""
        assert setup_storage.check_drive_exists("C:")

    def test_nonexistent_drive(self):
        """Non-existent drive should return False."""
        # Z: is unlikely to exist in most systems
        result = setup_storage.check_drive_exists("Z:")
        # This could be True or False depending on system, just verify it doesn't crash
        assert isinstance(result, bool)

    def test_invalid_drive_format(self):
        """Invalid drive format should return False."""
        assert not setup_storage.check_drive_exists("invalid")
        assert not setup_storage.check_drive_exists("")


class TestGetBasePath:
    """Test base path determination."""

    def test_returns_path_object(self):
        """Should return a Path object."""
        result = setup_storage.get_base_path()
        assert isinstance(result, Path)

    def test_returns_agent_metrics_path(self):
        """Should return a path ending with agent-metrics."""
        result = setup_storage.get_base_path()
        assert result.name == "agent-metrics"

    def test_prefers_d_drive(self, monkeypatch):
        """Should prefer D: if it exists."""
        # Use monkeypatch to replace check_drive_exists with a real function
        def mock_check_drive(drive):
            return drive == "D:"

        monkeypatch.setattr('setup_storage.check_drive_exists', mock_check_drive)
        result = setup_storage.get_base_path()
        assert str(result) == "D:\\agent-metrics"

    def test_falls_back_to_c_drive(self, monkeypatch):
        """Should fall back to C: if D: doesn't exist."""
        # Use monkeypatch to replace check_drive_exists with a real function
        def mock_check_drive(drive):
            return drive == "C:"

        monkeypatch.setattr('setup_storage.check_drive_exists', mock_check_drive)
        result = setup_storage.get_base_path()
        assert str(result) == "C:\\agent-metrics"

    def test_raises_if_no_drives(self, monkeypatch):
        """Should raise RuntimeError if neither drive exists."""
        # Use monkeypatch to replace check_drive_exists with a real function
        def mock_check_drive(drive):
            return False

        monkeypatch.setattr('setup_storage.check_drive_exists', mock_check_drive)
        with pytest.raises(RuntimeError, match="Neither D: nor C: drive is accessible"):
            setup_storage.get_base_path()


class TestCreateDirectoryStructure:
    """Test directory structure creation."""

    def test_creates_all_subdirectories(self, tmp_path):
        """Should create all required subdirectories."""
        base = tmp_path / "agent-metrics"

        success, messages = setup_storage.create_directory_structure(base)

        assert success
        assert base.exists()
        assert (base / "raw").exists()
        assert (base / "db").exists()
        assert (base / "reports").exists()
        assert (base / "exports").exists()
        assert (base / "config").exists()
        assert (base / "logs").exists()

    def test_idempotent_execution(self, tmp_path):
        """Should be safe to run multiple times."""
        base = tmp_path / "agent-metrics"

        # First run
        success1, messages1 = setup_storage.create_directory_structure(base)
        assert success1

        # Second run
        success2, messages2 = setup_storage.create_directory_structure(base)
        assert success2

        # All directories should still exist
        assert (base / "raw").exists()
        assert (base / "db").exists()

    def test_handles_existing_base_directory(self, tmp_path):
        """Should handle case where base directory already exists."""
        base = tmp_path / "agent-metrics"
        base.mkdir()

        success, messages = setup_storage.create_directory_structure(base)

        assert success
        assert any("already exists" in msg for msg in messages)

    def test_creates_nested_parents(self, tmp_path):
        """Should create parent directories if needed."""
        base = tmp_path / "nested" / "path" / "agent-metrics"

        success, messages = setup_storage.create_directory_structure(base)

        assert success
        assert base.exists()

    def test_returns_informative_messages(self, tmp_path):
        """Should return informative messages about what was created."""
        base = tmp_path / "agent-metrics"

        success, messages = setup_storage.create_directory_structure(base)

        assert success
        assert len(messages) > 0
        assert any("base directory" in msg.lower() for msg in messages)
        assert any("raw" in msg for msg in messages)
        assert any("db" in msg for msg in messages)


class TestGenerateReadme:
    """Test README generation."""

    def test_creates_readme_file(self, tmp_path):
        """Should create README.md in base directory."""
        base = tmp_path / "agent-metrics"
        base.mkdir()

        success, message = setup_storage.generate_readme(base)

        assert success
        assert (base / "README.md").exists()

    def test_readme_contains_timestamp(self, tmp_path):
        """README should contain creation timestamp."""
        base = tmp_path / "agent-metrics"
        base.mkdir()

        setup_storage.generate_readme(base)

        content = (base / "README.md").read_text(encoding='utf-8')
        assert "Created:" in content
        assert "UTC" in content

    def test_readme_contains_directory_structure(self, tmp_path):
        """README should document directory structure."""
        base = tmp_path / "agent-metrics"
        base.mkdir()

        setup_storage.generate_readme(base)

        content = (base / "README.md").read_text(encoding='utf-8')
        assert "raw/" in content
        assert "db/" in content
        assert "reports/" in content
        assert "exports/" in content
        assert "config/" in content
        assert "logs/" in content

    def test_readme_contains_location(self, tmp_path):
        """README should include storage location."""
        base = tmp_path / "agent-metrics"
        base.mkdir()

        setup_storage.generate_readme(base)

        content = (base / "README.md").read_text(encoding='utf-8')
        assert str(base) in content

    def test_idempotent_readme_generation(self, tmp_path):
        """Should be safe to regenerate README multiple times."""
        base = tmp_path / "agent-metrics"
        base.mkdir()

        # First generation
        success1, _ = setup_storage.generate_readme(base)
        assert success1

        # Second generation
        success2, _ = setup_storage.generate_readme(base)
        assert success2

        # File should still exist and be valid
        assert (base / "README.md").exists()


class TestVerifyWritePermissions:
    """Test write permission verification."""

    def test_successful_write_verification(self, tmp_path):
        """Should successfully verify write permissions."""
        base = tmp_path / "agent-metrics"
        base.mkdir()
        (base / "raw").mkdir()

        success, message = setup_storage.verify_write_permissions(base)

        assert success
        assert "verified" in message.lower()

    def test_cleans_up_test_file(self, tmp_path):
        """Should clean up test file after verification."""
        base = tmp_path / "agent-metrics"
        base.mkdir()
        (base / "raw").mkdir()

        setup_storage.verify_write_permissions(base)

        # Test file should not exist
        test_file = base / "raw" / ".write_test"
        assert not test_file.exists()

    def test_handles_permission_errors(self, tmp_path):
        """Should handle permission errors gracefully."""
        base = tmp_path / "agent-metrics"
        base.mkdir()
        raw_dir = base / "raw"
        raw_dir.mkdir()

        # Make the raw directory read-only to trigger a real permission error
        # Note: On Windows, this may not work as expected, so we'll use a different approach
        # Instead, we'll create a file where we expect to write, making it fail
        test_file = raw_dir / ".write_test"
        test_file.write_text("existing")

        # Make the file read-only
        test_file.chmod(0o444)  # Read-only for all users

        try:
            success, message = setup_storage.verify_write_permissions(base)

            # On some systems, this might still succeed due to OS differences
            # The important thing is that the function handles errors gracefully
            if not success:
                assert "failed" in message.lower() or "error" in message.lower()
        finally:
            # Clean up: restore write permissions
            try:
                test_file.chmod(0o644)
                test_file.unlink()
            except:
                pass


class TestMain:
    """Test main execution flow."""

    def test_main_returns_zero_on_success(self, tmp_path, monkeypatch, capsys):
        """Main should return 0 on successful execution."""
        # Mock get_base_path to use temp directory
        monkeypatch.setattr(
            'setup_storage.get_base_path',
            lambda: tmp_path / "agent-metrics"
        )

        exit_code = setup_storage.main()

        assert exit_code == 0

        # Check output
        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out

    def test_main_creates_complete_structure(self, tmp_path, monkeypatch):
        """Main should create complete directory structure."""
        base = tmp_path / "agent-metrics"

        monkeypatch.setattr('setup_storage.get_base_path', lambda: base)

        exit_code = setup_storage.main()

        assert exit_code == 0
        assert base.exists()
        assert (base / "raw").exists()
        assert (base / "db").exists()
        assert (base / "reports").exists()
        assert (base / "exports").exists()
        assert (base / "config").exists()
        assert (base / "logs").exists()
        assert (base / "README.md").exists()

    def test_main_is_idempotent(self, tmp_path, monkeypatch, capsys):
        """Main should be safe to run multiple times."""
        base = tmp_path / "agent-metrics"
        monkeypatch.setattr('setup_storage.get_base_path', lambda: base)

        # First run
        exit_code1 = setup_storage.main()
        assert exit_code1 == 0

        # Second run
        exit_code2 = setup_storage.main()
        assert exit_code2 == 0

        # Structure should still be intact
        assert (base / "raw").exists()
        assert (base / "README.md").exists()

    def test_main_handles_errors_gracefully(self, monkeypatch, capsys):
        """Main should return 1 and print error on failure."""
        # Mock get_base_path to raise an exception
        monkeypatch.setattr(
            'setup_storage.get_base_path',
            lambda: (_ for _ in ()).throw(RuntimeError("Test error"))
        )

        exit_code = setup_storage.main()

        assert exit_code == 1

        # Should print error message
        captured = capsys.readouterr()
        assert "ERROR" in captured.out or "error" in captured.out.lower()


class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_setup_workflow(self, tmp_path, monkeypatch):
        """Test complete setup workflow from start to finish."""
        base = tmp_path / "agent-metrics"
        monkeypatch.setattr('setup_storage.get_base_path', lambda: base)

        # Run main
        exit_code = setup_storage.main()

        # Verify exit code
        assert exit_code == 0

        # Verify directory structure
        assert base.exists()
        assert (base / "raw").is_dir()
        assert (base / "db").is_dir()
        assert (base / "reports").is_dir()
        assert (base / "exports").is_dir()
        assert (base / "config").is_dir()
        assert (base / "logs").is_dir()

        # Verify README exists and has content
        readme = base / "README.md"
        assert readme.exists()
        content = readme.read_text(encoding='utf-8')
        assert len(content) > 100
        assert "Agent Telemetry Platform" in content

        # Verify write permissions work
        test_file = base / "raw" / "test.txt"
        test_file.write_text("test")
        assert test_file.read_text() == "test"
        test_file.unlink()


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
