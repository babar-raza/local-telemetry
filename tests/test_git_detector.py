"""
Unit tests for GitDetector (GT-01: Automatic Git Detection Helper)

Tests cover:
- Basic detection in Git repository
- Handling of non-Git directories
- Caching behavior
- Error handling and fail-safe
- Disable flag
- Force refresh
- Edge cases (detached HEAD, missing remote, etc.)
"""

import pytest
import subprocess
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from src.telemetry.git_detector import GitDetector


class TestGitDetectorBasicDetection:
    """Test basic Git context detection functionality."""

    def test_detect_in_git_repo(self):
        """Test detection when in a Git repository with full context."""
        detector = GitDetector()

        # Mock subprocess calls to simulate Git repo
        with patch('subprocess.run') as mock_run:
            # Setup mock responses for Git commands
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    # git rev-parse --git-dir
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    # git config --get remote.origin.url
                    mock_result.stdout = "https://github.com/user/local-telemetry.git\n"
                elif '--abbrev-ref' in cmd:
                    # git rev-parse --abbrev-ref HEAD
                    mock_result.stdout = "main\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            # Execute
            context = detector.get_git_context()

            # Verify
            assert context["git_repo"] == "local-telemetry"
            assert context["git_branch"] == "main"
            assert context["git_run_tag"] == "local-telemetry/main"
            assert len(context) == 3

    def test_detect_in_non_git_directory(self):
        """Test detection returns empty dict when not in Git repo."""
        detector = GitDetector()

        # Mock subprocess to simulate non-Git directory
        with patch('subprocess.run') as mock_run:
            mock_result = Mock()
            mock_result.returncode = 128  # Git error code for not a repo
            mock_run.return_value = mock_result

            # Execute
            context = detector.get_git_context()

            # Verify
            assert context == {}

    def test_detect_with_ssh_url(self):
        """Test detection works with SSH-style Git URLs."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    mock_result.stdout = "git@github.com:user/my-repo.git\n"
                elif '--abbrev-ref' in cmd:
                    mock_result.stdout = "develop\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            context = detector.get_git_context()

            assert context["git_repo"] == "my-repo"
            assert context["git_branch"] == "develop"
            assert context["git_run_tag"] == "my-repo/develop"


class TestGitDetectorCaching:
    """Test caching behavior for performance."""

    def test_caching_avoids_repeated_subprocess_calls(self):
        """Test that second call uses cached result (no subprocess)."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            # Setup first call
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    mock_result.stdout = "https://github.com/user/test-repo.git\n"
                elif '--abbrev-ref' in cmd:
                    mock_result.stdout = "main\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            # First call - should trigger subprocess
            context1 = detector.get_git_context()
            call_count_first = mock_run.call_count

            # Second call - should use cache (no new subprocess calls)
            context2 = detector.get_git_context()
            call_count_second = mock_run.call_count

            # Verify results are identical
            assert context1 == context2
            assert context1["git_repo"] == "test-repo"

            # Verify no new subprocess calls on second call
            assert call_count_second == call_count_first

    def test_force_refresh_bypasses_cache(self):
        """Test force_refresh=True triggers new detection."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    mock_result.stdout = "https://github.com/user/test-repo.git\n"
                elif '--abbrev-ref' in cmd:
                    mock_result.stdout = "main\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            # First call
            context1 = detector.get_git_context()
            call_count_first = mock_run.call_count

            # Force refresh - should trigger new subprocess calls
            context2 = detector.get_git_context(force_refresh=True)
            call_count_second = mock_run.call_count

            # Verify results are identical
            assert context1 == context2

            # Verify new subprocess calls were made
            assert call_count_second > call_count_first

    def test_clear_cache_resets_detection(self):
        """Test clear_cache() allows re-detection."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    mock_result.stdout = "https://github.com/user/test-repo.git\n"
                elif '--abbrev-ref' in cmd:
                    mock_result.stdout = "main\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            # First call
            detector.get_git_context()
            call_count_first = mock_run.call_count

            # Clear cache
            detector.clear_cache()

            # Next call should re-detect
            detector.get_git_context()
            call_count_second = mock_run.call_count

            # Verify new subprocess calls were made
            assert call_count_second > call_count_first


class TestGitDetectorErrorHandling:
    """Test error handling and fail-safe behavior."""

    def test_git_command_timeout(self):
        """Test graceful handling of Git command timeout."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            # Simulate timeout
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=['git'], timeout=5)

            # Execute - should not raise exception
            context = detector.get_git_context()

            # Verify empty result
            assert context == {}

    def test_git_not_installed(self):
        """Test graceful handling when Git is not installed."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            # Simulate git not found
            mock_run.side_effect = FileNotFoundError("git not found")

            # Execute - should not raise exception
            context = detector.get_git_context()

            # Verify empty result
            assert context == {}

    def test_unexpected_exception(self):
        """Test graceful handling of unexpected exceptions."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            # Simulate unexpected error
            mock_run.side_effect = RuntimeError("Unexpected error")

            # Execute - should not raise exception
            context = detector.get_git_context()

            # Verify empty result
            assert context == {}

    def test_failed_detection_is_cached(self):
        """Test that failed detection is cached to avoid repeated failures."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            # First call - fails
            mock_result = Mock()
            mock_result.returncode = 128  # Not a git repo
            mock_run.return_value = mock_result

            # First call
            context1 = detector.get_git_context()
            call_count_first = mock_run.call_count

            # Second call - should use cached failure (no new subprocess)
            context2 = detector.get_git_context()
            call_count_second = mock_run.call_count

            # Verify both return empty
            assert context1 == {}
            assert context2 == {}

            # Verify no new subprocess calls
            assert call_count_second == call_count_first


class TestGitDetectorDisableFlag:
    """Test auto_detect=False flag."""

    def test_auto_detect_disabled(self):
        """Test that auto_detect=False prevents detection."""
        detector = GitDetector(auto_detect=False)

        with patch('subprocess.run') as mock_run:
            # Execute
            context = detector.get_git_context()

            # Verify no subprocess calls were made
            assert mock_run.call_count == 0

            # Verify empty result
            assert context == {}


class TestGitDetectorEdgeCases:
    """Test edge cases and special Git states."""

    def test_detached_head_state(self):
        """Test handling of detached HEAD state."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    mock_result.stdout = "https://github.com/user/test-repo.git\n"
                elif '--abbrev-ref' in cmd:
                    # Detached HEAD returns "HEAD"
                    mock_result.stdout = "HEAD\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            context = detector.get_git_context()

            # Should have repo but no branch
            assert context["git_repo"] == "test-repo"
            assert "git_branch" not in context
            # git_run_tag should still be set (repo only)
            assert context["git_run_tag"] == "test-repo"

    def test_no_remote_configured(self):
        """Test handling when no remote.origin.url is configured."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()

                if '--git-dir' in cmd:
                    mock_result.returncode = 0
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    # No remote configured
                    mock_result.returncode = 1
                    mock_result.stdout = ""
                elif '--abbrev-ref' in cmd:
                    mock_result.returncode = 0
                    mock_result.stdout = "main\n"
                else:
                    mock_result.returncode = 0
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            context = detector.get_git_context()

            # Should have branch but no repo
            assert "git_repo" not in context
            assert context["git_branch"] == "main"
            assert "git_run_tag" not in context  # No tag without repo

    def test_url_without_git_suffix(self):
        """Test parsing URL without .git suffix."""
        detector = GitDetector()

        with patch('subprocess.run') as mock_run:
            def mock_git_command(cmd, **kwargs):
                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    # URL without .git suffix
                    mock_result.stdout = "https://github.com/user/test-repo\n"
                elif '--abbrev-ref' in cmd:
                    mock_result.stdout = "main\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            context = detector.get_git_context()

            assert context["git_repo"] == "test-repo"
            assert context["git_branch"] == "main"

    def test_custom_working_directory(self):
        """Test detection with custom working directory."""
        custom_dir = "/custom/path"
        detector = GitDetector(working_dir=custom_dir)

        with patch('subprocess.run') as mock_run:
            def mock_git_command(cmd, **kwargs):
                # Verify cwd is set correctly
                assert kwargs.get('cwd') == custom_dir

                mock_result = Mock()
                mock_result.returncode = 0

                if '--git-dir' in cmd:
                    mock_result.stdout = ".git\n"
                elif 'remote.origin.url' in cmd:
                    mock_result.stdout = "https://github.com/user/test-repo.git\n"
                elif '--abbrev-ref' in cmd:
                    mock_result.stdout = "main\n"
                else:
                    mock_result.stdout = ""

                return mock_result

            mock_run.side_effect = mock_git_command

            context = detector.get_git_context()

            assert context["git_repo"] == "test-repo"
