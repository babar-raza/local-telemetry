"""
URL Builder for Git Repository Platforms

Provides helper functions to construct commit URLs and repository URLs
for GitHub, GitLab, and Bitbucket platforms.

Supports both HTTPS and SSH repository URL formats with automatic normalization.

Functions:
- build_commit_url(repo_url, commit_hash) -> Optional[str]
- build_repo_url(repo_url) -> Optional[str]
- detect_platform(repo_url) -> Optional[str]
- normalize_repo_url(repo_url) -> str

Platform Support:
- GitHub: https://github.com/{owner}/{repo}/commit/{hash}
- GitLab: https://gitlab.com/{owner}/{repo}/-/commit/{hash}
- Bitbucket: https://bitbucket.org/{owner}/{repo}/commits/{hash}

Error Handling:
- Returns None for invalid/missing inputs
- Returns None for unsupported platforms
- Gracefully handles malformed URLs
"""

from typing import Optional
import re


def detect_platform(repo_url: str) -> Optional[str]:
    """
    Detect the Git platform from a repository URL.

    Args:
        repo_url: Repository URL (HTTPS or SSH format)

    Returns:
        Platform identifier: 'github', 'gitlab', 'bitbucket', or None if unsupported

    Examples:
        >>> detect_platform("https://github.com/owner/repo")
        'github'
        >>> detect_platform("git@gitlab.com:owner/repo.git")
        'gitlab'
        >>> detect_platform("https://git.example.com/repo")
        None
    """
    if not repo_url:
        return None

    # Normalize to lowercase for case-insensitive matching
    url_lower = repo_url.lower()

    # Check for GitHub
    if "github.com" in url_lower:
        return "github"

    # Check for GitLab (only gitlab.com, not self-hosted instances)
    if "gitlab.com" in url_lower:
        return "gitlab"

    # Check for Bitbucket
    if "bitbucket.org" in url_lower:
        return "bitbucket"

    # Unknown platform
    return None


def normalize_repo_url(repo_url: str) -> str:
    """
    Normalize a repository URL to HTTPS format without .git extension.

    Converts SSH URLs (git@host:path) to HTTPS URLs (https://host/path).
    Removes .git extension and trailing slashes.

    Args:
        repo_url: Repository URL in any format

    Returns:
        Normalized HTTPS URL without .git extension

    Examples:
        >>> normalize_repo_url("git@github.com:owner/repo.git")
        'https://github.com/owner/repo'
        >>> normalize_repo_url("https://github.com/owner/repo.git")
        'https://github.com/owner/repo'
    """
    if not repo_url:
        return ""

    url = repo_url.strip()

    # Convert SSH format to HTTPS: git@host:path -> https://host/path
    if url.startswith("git@"):
        # Pattern: git@host:path
        ssh_pattern = r'^git@([^:]+):(.+)$'
        match = re.match(ssh_pattern, url)

        if match:
            host = match.group(1)
            path = match.group(2)
            url = f"https://{host}/{path}"

    # Remove .git extension
    if url.endswith(".git"):
        url = url[:-4]

    # Remove trailing slash
    if url.endswith("/"):
        url = url.rstrip("/")

    return url


def build_repo_url(repo_url: str) -> Optional[str]:
    """
    Build a normalized repository URL for browsing.

    Args:
        repo_url: Repository URL (HTTPS or SSH format)

    Returns:
        Normalized HTTPS repository URL, or None if invalid

    Examples:
        >>> build_repo_url("git@github.com:owner/repo.git")
        'https://github.com/owner/repo'
        >>> build_repo_url("https://gitlab.com/owner/repo.git")
        'https://gitlab.com/owner/repo'
    """
    if not repo_url or not repo_url.strip():
        return None

    # Normalize the URL
    normalized = normalize_repo_url(repo_url)

    # Validate that we got a proper URL
    if not normalized or not normalized.startswith("https://"):
        return None

    return normalized


def build_commit_url(repo_url: str, commit_hash: str) -> Optional[str]:
    """
    Build a commit URL for GitHub, GitLab, or Bitbucket.

    Args:
        repo_url: Repository URL (HTTPS or SSH format)
        commit_hash: Git commit SHA (7-40 characters)

    Returns:
        Full commit URL for the platform, or None if unsupported/invalid

    Examples:
        >>> build_commit_url("https://github.com/owner/repo", "abc1234")
        'https://github.com/owner/repo/commit/abc1234'
        >>> build_commit_url("git@gitlab.com:owner/repo.git", "def5678")
        'https://gitlab.com/owner/repo/-/commit/def5678'
        >>> build_commit_url("https://bitbucket.org/owner/repo", "123abcd")
        'https://bitbucket.org/owner/repo/commits/123abcd'
    """
    # Validate inputs
    if not repo_url or not repo_url.strip():
        return None

    if not commit_hash or not commit_hash.strip():
        return None

    # Detect platform
    platform = detect_platform(repo_url)

    if not platform:
        # Unsupported platform
        return None

    # Normalize repository URL
    normalized_repo = build_repo_url(repo_url)

    if not normalized_repo:
        return None

    # Build platform-specific commit URL
    if platform == "github":
        return f"{normalized_repo}/commit/{commit_hash}"
    elif platform == "gitlab":
        return f"{normalized_repo}/-/commit/{commit_hash}"
    elif platform == "bitbucket":
        return f"{normalized_repo}/commits/{commit_hash}"
    else:
        # This shouldn't happen, but handle gracefully
        return None
