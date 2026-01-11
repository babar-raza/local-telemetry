"""
Unit tests for URL Builder module

Tests cover:
- GitHub URL construction (HTTPS and SSH formats)
- GitLab URL construction (HTTPS and SSH formats)
- Bitbucket URL construction (HTTPS and SSH formats)
- Platform detection from repository URLs
- Error handling for invalid/malformed URLs
- Graceful fallback for unsupported platforms

NO MOCKING: All tests use real string manipulation with known URL patterns.
This is pure function testing with deterministic inputs/outputs.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.url_builder import (
    build_commit_url,
    build_repo_url,
    detect_platform,
    normalize_repo_url
)


class TestGitHubURLConstruction:
    """Test GitHub URL construction for commit and repo URLs."""

    def test_build_commit_url_github_https(self):
        """Test building commit URL from GitHub HTTPS repository URL."""
        repo_url = "https://github.com/owner/repo"
        commit_hash = "abc1234567890"

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://github.com/owner/repo/commit/abc1234567890"

    def test_build_commit_url_github_https_with_git_extension(self):
        """Test building commit URL from GitHub HTTPS URL with .git extension."""
        repo_url = "https://github.com/owner/repo.git"
        commit_hash = "def4567890abc"

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://github.com/owner/repo/commit/def4567890abc"

    def test_build_commit_url_github_ssh(self):
        """Test building commit URL from GitHub SSH URL (git@github.com:owner/repo.git)."""
        repo_url = "git@github.com:owner/repo.git"
        commit_hash = "1234567890abcdef"

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://github.com/owner/repo/commit/1234567890abcdef"

    def test_build_repo_url_github_ssh_normalization(self):
        """Test normalizing GitHub SSH URL to HTTPS format."""
        repo_url = "git@github.com:owner/repo.git"

        result = build_repo_url(repo_url)

        assert result == "https://github.com/owner/repo"

    def test_build_repo_url_github_https_strips_git_extension(self):
        """Test that GitHub HTTPS URL strips .git extension."""
        repo_url = "https://github.com/owner/repo.git"

        result = build_repo_url(repo_url)

        assert result == "https://github.com/owner/repo"


class TestGitLabURLConstruction:
    """Test GitLab URL construction for commit and repo URLs."""

    def test_build_commit_url_gitlab_https(self):
        """Test building commit URL from GitLab HTTPS repository URL."""
        repo_url = "https://gitlab.com/owner/repo"
        commit_hash = "abc1234567890"

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://gitlab.com/owner/repo/-/commit/abc1234567890"

    def test_build_commit_url_gitlab_ssh(self):
        """Test building commit URL from GitLab SSH URL."""
        repo_url = "git@gitlab.com:owner/repo.git"
        commit_hash = "def4567890abc"

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://gitlab.com/owner/repo/-/commit/def4567890abc"

    def test_build_repo_url_gitlab_ssh_normalization(self):
        """Test normalizing GitLab SSH URL to HTTPS format."""
        repo_url = "git@gitlab.com:owner/repo.git"

        result = build_repo_url(repo_url)

        assert result == "https://gitlab.com/owner/repo"


class TestBitbucketURLConstruction:
    """Test Bitbucket URL construction for commit and repo URLs."""

    def test_build_commit_url_bitbucket_https(self):
        """Test building commit URL from Bitbucket HTTPS repository URL."""
        repo_url = "https://bitbucket.org/owner/repo"
        commit_hash = "abc1234567890"

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://bitbucket.org/owner/repo/commits/abc1234567890"

    def test_build_commit_url_bitbucket_ssh(self):
        """Test building commit URL from Bitbucket SSH URL."""
        repo_url = "git@bitbucket.org:owner/repo.git"
        commit_hash = "def4567890abc"

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://bitbucket.org/owner/repo/commits/def4567890abc"

    def test_build_repo_url_bitbucket_ssh_normalization(self):
        """Test normalizing Bitbucket SSH URL to HTTPS format."""
        repo_url = "git@bitbucket.org:owner/repo.git"

        result = build_repo_url(repo_url)

        assert result == "https://bitbucket.org/owner/repo"


class TestPlatformDetection:
    """Test platform detection from repository URLs."""

    def test_detect_platform_github_https(self):
        """Test detecting GitHub platform from HTTPS URL."""
        repo_url = "https://github.com/owner/repo"

        result = detect_platform(repo_url)

        assert result == "github"

    def test_detect_platform_github_ssh(self):
        """Test detecting GitHub platform from SSH URL."""
        repo_url = "git@github.com:owner/repo.git"

        result = detect_platform(repo_url)

        assert result == "github"

    def test_detect_platform_gitlab_https(self):
        """Test detecting GitLab platform from HTTPS URL."""
        repo_url = "https://gitlab.com/owner/repo"

        result = detect_platform(repo_url)

        assert result == "gitlab"

    def test_detect_platform_gitlab_ssh(self):
        """Test detecting GitLab platform from SSH URL."""
        repo_url = "git@gitlab.com:owner/repo.git"

        result = detect_platform(repo_url)

        assert result == "gitlab"

    def test_detect_platform_bitbucket_https(self):
        """Test detecting Bitbucket platform from HTTPS URL."""
        repo_url = "https://bitbucket.org/owner/repo"

        result = detect_platform(repo_url)

        assert result == "bitbucket"

    def test_detect_platform_bitbucket_ssh(self):
        """Test detecting Bitbucket platform from SSH URL."""
        repo_url = "git@bitbucket.org:owner/repo.git"

        result = detect_platform(repo_url)

        assert result == "bitbucket"

    def test_detect_platform_unknown_returns_none(self):
        """Test that unknown platforms return None."""
        repo_url = "https://git.example.com/owner/repo"

        result = detect_platform(repo_url)

        assert result is None

    def test_detect_platform_self_hosted_gitlab_returns_none(self):
        """Test that self-hosted GitLab instances return None (not gitlab.com)."""
        repo_url = "https://gitlab.mycompany.com/owner/repo"

        result = detect_platform(repo_url)

        assert result is None


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling for URL construction."""

    def test_build_commit_url_none_repo_url(self):
        """Test that None repo_url returns None gracefully."""
        result = build_commit_url(None, "abc123")

        assert result is None

    def test_build_commit_url_none_commit_hash(self):
        """Test that None commit_hash returns None gracefully."""
        result = build_commit_url("https://github.com/owner/repo", None)

        assert result is None

    def test_build_commit_url_empty_string_repo_url(self):
        """Test that empty string repo_url returns None gracefully."""
        result = build_commit_url("", "abc123")

        assert result is None

    def test_build_commit_url_empty_string_commit_hash(self):
        """Test that empty string commit_hash returns None gracefully."""
        result = build_commit_url("https://github.com/owner/repo", "")

        assert result is None

    def test_build_commit_url_unsupported_platform_returns_none(self):
        """Test that unsupported platform returns None."""
        repo_url = "https://git.example.com/owner/repo"
        commit_hash = "abc123"

        result = build_commit_url(repo_url, commit_hash)

        assert result is None

    def test_build_repo_url_none_returns_none(self):
        """Test that None repo_url returns None gracefully."""
        result = build_repo_url(None)

        assert result is None

    def test_build_repo_url_empty_string_returns_none(self):
        """Test that empty string repo_url returns None gracefully."""
        result = build_repo_url("")

        assert result is None

    def test_build_repo_url_malformed_url_returns_none(self):
        """Test that malformed URL returns None gracefully."""
        result = build_repo_url("not-a-valid-url")

        assert result is None

    def test_normalize_repo_url_github_ssh_with_complex_path(self):
        """Test normalizing GitHub SSH URL with nested organization paths."""
        repo_url = "git@github.com:org/team/repo.git"

        result = normalize_repo_url(repo_url)

        # Should handle nested paths correctly
        assert result == "https://github.com/org/team/repo"

    def test_build_commit_url_with_short_commit_hash(self):
        """Test building commit URL with short commit hash (7 chars minimum)."""
        repo_url = "https://github.com/owner/repo"
        commit_hash = "abc1234"  # 7 chars

        result = build_commit_url(repo_url, commit_hash)

        assert result == "https://github.com/owner/repo/commit/abc1234"

    def test_build_commit_url_with_full_commit_hash(self):
        """Test building commit URL with full 40-character commit hash."""
        repo_url = "https://github.com/owner/repo"
        commit_hash = "a" * 40  # Full SHA-1 hash

        result = build_commit_url(repo_url, commit_hash)

        assert result == f"https://github.com/owner/repo/commit/{'a' * 40}"


class TestNormalizeRepoURL:
    """Test URL normalization function."""

    def test_normalize_https_url_no_change(self):
        """Test that HTTPS URLs remain unchanged (except .git removal)."""
        repo_url = "https://github.com/owner/repo.git"

        result = normalize_repo_url(repo_url)

        assert result == "https://github.com/owner/repo"

    def test_normalize_ssh_url_converts_to_https(self):
        """Test that SSH URLs are converted to HTTPS format."""
        repo_url = "git@github.com:owner/repo.git"

        result = normalize_repo_url(repo_url)

        assert result == "https://github.com/owner/repo"

    def test_normalize_removes_trailing_slash(self):
        """Test that trailing slashes are removed."""
        repo_url = "https://github.com/owner/repo/"

        result = normalize_repo_url(repo_url)

        assert result == "https://github.com/owner/repo"

    def test_normalize_preserves_https_without_git_extension(self):
        """Test that HTTPS URLs without .git extension are preserved."""
        repo_url = "https://github.com/owner/repo"

        result = normalize_repo_url(repo_url)

        assert result == "https://github.com/owner/repo"
