"""
Git Detection Helper for Telemetry Client

Provides automatic detection of Git repository context (repo name, branch, run tag)
with performance caching to avoid repeated subprocess calls.

Design Goals:
- Zero dependencies beyond subprocess (standard library)
- Fail-safe: Always returns None on errors (never crashes agent)
- Performance: Single detection per session via caching
- Cross-platform: Works on Windows, Linux, macOS
- Respects explicit values: Never overrides user-provided values
"""

import subprocess
import logging
import os
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class GitDetector:
    """
    Detects Git repository context for automatic telemetry enrichment.

    Features:
    - Automatic detection of git_repo, git_branch, git_run_tag
    - Performance caching (single detection per session)
    - Fail-safe error handling (never crashes)
    - Cross-platform compatibility (Windows/Linux/macOS)
    - Respects explicit values (never overrides)

    Usage:
        detector = GitDetector()
        context = detector.get_git_context()
        # Returns: {"git_repo": "my-repo", "git_branch": "main", "git_run_tag": "my-repo/main"}
        # Or: {} if not in a Git repository
    """

    def __init__(self, working_dir: Optional[str] = None, auto_detect: bool = True):
        """
        Initialize Git detector.

        Args:
            working_dir: Directory to check for Git repo (defaults to current directory)
            auto_detect: Enable/disable automatic detection (default: True)
        """
        self.working_dir = working_dir or os.getcwd()
        self.auto_detect = auto_detect

        # Cache for git context (populated on first detection)
        self._cached_context: Optional[Dict[str, str]] = None
        self._detection_attempted = False

        logger.debug(f"GitDetector initialized: working_dir={self.working_dir}, auto_detect={self.auto_detect}")

    def get_git_context(self, force_refresh: bool = False) -> Dict[str, str]:
        """
        Get Git repository context with caching.

        Returns a dictionary with detected Git metadata:
        - git_repo: Repository name (e.g., "local-telemetry")
        - git_branch: Current branch name (e.g., "main")
        - git_run_tag: Combined tag for grouping runs (e.g., "local-telemetry/main")

        Args:
            force_refresh: Force re-detection (bypass cache)

        Returns:
            Dictionary with git metadata, or empty dict if not in Git repo

        Example:
            context = detector.get_git_context()
            # {"git_repo": "my-repo", "git_branch": "main", "git_run_tag": "my-repo/main"}
        """
        # Check if auto-detection is disabled
        if not self.auto_detect:
            logger.debug("Git auto-detection disabled")
            return {}

        # Return cached context if available (unless force_refresh)
        if self._cached_context is not None and not force_refresh:
            logger.debug("Returning cached git context")
            return self._cached_context

        # Return empty dict if detection already attempted and failed
        if self._detection_attempted and not force_refresh:
            logger.debug("Git detection previously failed, returning empty context")
            return {}

        # Perform detection
        self._detection_attempted = True

        try:
            # Detect if we're in a Git repository
            if not self._is_git_repo():
                logger.debug("Not in a Git repository")
                self._cached_context = {}
                return {}

            # Detect git metadata
            git_repo = self._get_repo_name()
            git_branch = self._get_current_branch()

            # Build context
            context = {}

            if git_repo:
                context["git_repo"] = git_repo

            if git_branch:
                context["git_branch"] = git_branch

            # Build git_run_tag (combines repo and branch for grouping)
            if git_repo and git_branch:
                context["git_run_tag"] = f"{git_repo}/{git_branch}"
            elif git_repo:
                context["git_run_tag"] = git_repo

            # Cache the result
            self._cached_context = context

            if context:
                logger.info(f"Git context detected: {context}")
            else:
                logger.debug("Git repository detected but no context available")

            return context

        except Exception as e:
            # Fail-safe: Never crash, just log and return empty
            logger.warning(f"Git detection failed: {e}")
            self._cached_context = {}
            return {}

    def _is_git_repo(self) -> bool:
        """
        Check if current directory is inside a Git repository.

        Uses: git rev-parse --git-dir

        Returns:
            True if in a Git repo, False otherwise
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=5,  # 5 second timeout
            )

            # Exit code 0 means we're in a Git repo
            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.warning("Git command timed out")
            return False

        except FileNotFoundError:
            # Git not installed
            logger.debug("Git command not found (git not installed)")
            return False

        except Exception as e:
            logger.warning(f"Failed to check if Git repo: {e}")
            return False

    def _get_repo_name(self) -> Optional[str]:
        """
        Get repository name from Git remote URL.

        Uses: git config --get remote.origin.url

        Extracts repo name from URLs like:
        - https://github.com/user/repo.git -> "repo"
        - git@github.com:user/repo.git -> "repo"
        - /path/to/repo.git -> "repo"

        Returns:
            Repository name or None if not available
        """
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.debug("No remote.origin.url configured")
                return None

            # Parse URL to extract repo name
            url = result.stdout.strip()

            if not url:
                return None

            # Extract repo name from URL
            # Handle various formats: https://.../repo.git, git@...:repo.git, /path/repo.git
            repo_name = url.rstrip("/").split("/")[-1]

            # Remove .git suffix if present
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]

            # Remove any remaining path separators (for git@... format)
            if ":" in repo_name:
                repo_name = repo_name.split(":")[-1]

            return repo_name if repo_name else None

        except subprocess.TimeoutExpired:
            logger.warning("Git config command timed out")
            return None

        except Exception as e:
            logger.warning(f"Failed to get repo name: {e}")
            return None

    def _get_current_branch(self) -> Optional[str]:
        """
        Get current Git branch name.

        Uses: git rev-parse --abbrev-ref HEAD

        Returns:
            Branch name (e.g., "main") or None if not available
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                logger.debug("Failed to get current branch")
                return None

            branch = result.stdout.strip()

            # Handle detached HEAD state
            if branch == "HEAD":
                logger.debug("In detached HEAD state")
                return None

            return branch if branch else None

        except subprocess.TimeoutExpired:
            logger.warning("Git branch command timed out")
            return None

        except Exception as e:
            logger.warning(f"Failed to get current branch: {e}")
            return None

    def clear_cache(self):
        """
        Clear cached Git context.

        Useful for testing or when Git state changes during runtime.
        """
        self._cached_context = None
        self._detection_attempted = False
        logger.debug("Git context cache cleared")
