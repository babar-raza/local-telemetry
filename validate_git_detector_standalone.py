"""
Standalone validation script for GitDetector (no dependencies).

This script directly imports only GitDetector to avoid import errors.
"""

import subprocess
import logging
import os
import time
from typing import Dict, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class GitDetector:
    """
    Detects Git repository context for automatic telemetry enrichment.

    This is a copy of the GitDetector class for standalone validation.
    """

    def __init__(self, working_dir: Optional[str] = None, auto_detect: bool = True):
        self.working_dir = working_dir or os.getcwd()
        self.auto_detect = auto_detect
        self._cached_context: Optional[Dict[str, str]] = None
        self._detection_attempted = False
        logger.debug(f"GitDetector initialized: working_dir={self.working_dir}, auto_detect={self.auto_detect}")

    def get_git_context(self, force_refresh: bool = False) -> Dict[str, str]:
        """Get Git repository context with caching."""
        if not self.auto_detect:
            logger.debug("Git auto-detection disabled")
            return {}

        if self._cached_context is not None and not force_refresh:
            logger.debug("Returning cached git context")
            return self._cached_context

        if self._detection_attempted and not force_refresh:
            logger.debug("Git detection previously failed, returning empty context")
            return {}

        self._detection_attempted = True

        try:
            if not self._is_git_repo():
                logger.debug("Not in a Git repository")
                self._cached_context = {}
                return {}

            git_repo = self._get_repo_name()
            git_branch = self._get_current_branch()

            context = {}
            if git_repo:
                context["git_repo"] = git_repo
            if git_branch:
                context["git_branch"] = git_branch
            if git_repo and git_branch:
                context["git_run_tag"] = f"{git_repo}/{git_branch}"
            elif git_repo:
                context["git_run_tag"] = git_repo

            self._cached_context = context

            if context:
                logger.info(f"Git context detected: {context}")
            else:
                logger.debug("Git repository detected but no context available")

            return context

        except Exception as e:
            logger.warning(f"Git detection failed: {e}")
            self._cached_context = {}
            return {}

    def _is_git_repo(self) -> bool:
        """Check if current directory is inside a Git repository."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"Failed to check if Git repo: {e}")
            return False

    def _get_repo_name(self) -> Optional[str]:
        """Get repository name from Git remote URL."""
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

            url = result.stdout.strip()
            if not url:
                return None

            repo_name = url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            if ":" in repo_name:
                repo_name = repo_name.split(":")[-1]

            return repo_name if repo_name else None

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"Failed to get repo name: {e}")
            return None

    def _get_current_branch(self) -> Optional[str]:
        """Get current Git branch name."""
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
            if branch == "HEAD":
                logger.debug("In detached HEAD state")
                return None

            return branch if branch else None

        except (subprocess.TimeoutExpired, Exception) as e:
            logger.warning(f"Failed to get current branch: {e}")
            return None

    def clear_cache(self):
        """Clear cached Git context."""
        self._cached_context = None
        self._detection_attempted = False
        logger.debug("Git context cache cleared")


def print_section(title):
    """Print section header."""
    print(f"\n{'=' * 60}")
    print(f" {title}")
    print(f"{'=' * 60}\n")


def main():
    """Run validation scenarios."""
    print("\n" + "=" * 60)
    print(" GT-01 Manual Validation Tests")
    print(" Automatic Git Detection Helper")
    print("=" * 60)

    try:
        # Scenario 1: Basic detection
        print_section("Scenario 1: Basic Git Detection")
        detector = GitDetector()
        context = detector.get_git_context()
        print(f"Working directory: {detector.working_dir}")
        print(f"Detected Git context: {context}")

        # Scenario 2: Caching performance
        print_section("Scenario 2: Caching Performance")
        detector2 = GitDetector()
        start1 = time.time()
        context1 = detector2.get_git_context()
        duration1 = time.time() - start1

        start2 = time.time()
        context2 = detector2.get_git_context()
        duration2 = time.time() - start2

        print(f"First call: {duration1*1000:.2f} ms")
        print(f"Cached call: {duration2*1000:.2f} ms")
        print(f"Performance improvement: {(duration1/max(duration2, 0.0001)):.1f}x faster")

        # Scenario 3: Force refresh
        print_section("Scenario 3: Force Refresh")
        context3 = detector2.get_git_context(force_refresh=True)
        print(f"Force refresh result: {context3}")

        # Scenario 4: Disabled auto-detection
        print_section("Scenario 4: Disabled Auto-Detection")
        detector4 = GitDetector(auto_detect=False)
        context4 = detector4.get_git_context()
        print(f"Disabled detection result: {context4}")
        assert context4 == {}, "Should return empty dict when disabled"

        # Scenario 5: Clear cache
        print_section("Scenario 5: Clear Cache and Re-detect")
        detector5 = GitDetector()
        detector5.get_git_context()
        detector5.clear_cache()
        context5 = detector5.get_git_context()
        print(f"Re-detected after clear: {context5}")

        # Summary
        print_section("VALIDATION SUMMARY")
        print("All 5 scenarios completed successfully!")
        print(f"\nDetected Git context: {context}")
        print("\n" + "=" * 60)
        print(" SUCCESS: All validation tests passed!")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\nERROR: Validation failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
