"""
Standalone test runner for url_builder module
Does not require pytest or external dependencies
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import url_builder directly to avoid package dependencies
import importlib.util
spec = importlib.util.spec_from_file_location(
    "url_builder",
    Path(__file__).parent / "src" / "telemetry" / "url_builder.py"
)
url_builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(url_builder)

# Extract functions
build_commit_url = url_builder.build_commit_url
build_repo_url = url_builder.build_repo_url
detect_platform = url_builder.detect_platform
normalize_repo_url = url_builder.normalize_repo_url


def test_function(test_name, actual, expected):
    """Helper to test a single function call."""
    if actual == expected:
        print(f"[PASS] {test_name}")
        return True
    else:
        print(f"[FAIL] {test_name}")
        print(f"  Expected: {expected}")
        print(f"  Actual:   {actual}")
        return False


def run_tests():
    """Run all URL builder tests."""
    passed = 0
    failed = 0

    print("=" * 70)
    print("UNIT TESTS: URL Builder Module")
    print("=" * 70)
    print()

    # GitHub Tests
    print("GitHub URL Construction:")
    print("-" * 40)

    if test_function(
        "GitHub HTTPS commit URL",
        build_commit_url("https://github.com/owner/repo", "abc1234"),
        "https://github.com/owner/repo/commit/abc1234"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "GitHub HTTPS with .git extension",
        build_commit_url("https://github.com/owner/repo.git", "def5678"),
        "https://github.com/owner/repo/commit/def5678"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "GitHub SSH commit URL",
        build_commit_url("git@github.com:owner/repo.git", "abc123def"),
        "https://github.com/owner/repo/commit/abc123def"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "GitHub SSH repo URL normalization",
        build_repo_url("git@github.com:owner/repo.git"),
        "https://github.com/owner/repo"
    ):
        passed += 1
    else:
        failed += 1

    print()

    # GitLab Tests
    print("GitLab URL Construction:")
    print("-" * 40)

    if test_function(
        "GitLab HTTPS commit URL",
        build_commit_url("https://gitlab.com/owner/repo", "abc1234"),
        "https://gitlab.com/owner/repo/-/commit/abc1234"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "GitLab SSH commit URL",
        build_commit_url("git@gitlab.com:owner/repo.git", "def5678"),
        "https://gitlab.com/owner/repo/-/commit/def5678"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "GitLab SSH repo URL normalization",
        build_repo_url("git@gitlab.com:owner/repo.git"),
        "https://gitlab.com/owner/repo"
    ):
        passed += 1
    else:
        failed += 1

    print()

    # Bitbucket Tests
    print("Bitbucket URL Construction:")
    print("-" * 40)

    if test_function(
        "Bitbucket HTTPS commit URL",
        build_commit_url("https://bitbucket.org/owner/repo", "abc1234"),
        "https://bitbucket.org/owner/repo/commits/abc1234"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Bitbucket SSH commit URL",
        build_commit_url("git@bitbucket.org:owner/repo.git", "def5678"),
        "https://bitbucket.org/owner/repo/commits/def5678"
    ):
        passed += 1
    else:
        failed += 1

    print()

    # Platform Detection Tests
    print("Platform Detection:")
    print("-" * 40)

    if test_function(
        "Detect GitHub from HTTPS",
        detect_platform("https://github.com/owner/repo"),
        "github"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Detect GitLab from HTTPS",
        detect_platform("https://gitlab.com/owner/repo"),
        "gitlab"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Detect Bitbucket from HTTPS",
        detect_platform("https://bitbucket.org/owner/repo"),
        "bitbucket"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Detect unknown platform returns None",
        detect_platform("https://git.example.com/owner/repo"),
        None
    ):
        passed += 1
    else:
        failed += 1

    print()

    # Edge Cases
    print("Edge Cases and Error Handling:")
    print("-" * 40)

    if test_function(
        "None repo_url returns None",
        build_commit_url(None, "abc123"),
        None
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "None commit_hash returns None",
        build_commit_url("https://github.com/owner/repo", None),
        None
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Empty string repo_url returns None",
        build_commit_url("", "abc123"),
        None
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Unsupported platform returns None",
        build_commit_url("https://git.example.com/owner/repo", "abc123"),
        None
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Full 40-char commit hash",
        build_commit_url("https://github.com/owner/repo", "a" * 40),
        f"https://github.com/owner/repo/commit/{'a' * 40}"
    ):
        passed += 1
    else:
        failed += 1

    print()

    # Normalization Tests
    print("URL Normalization:")
    print("-" * 40)

    if test_function(
        "Remove .git extension from HTTPS",
        normalize_repo_url("https://github.com/owner/repo.git"),
        "https://github.com/owner/repo"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Convert SSH to HTTPS",
        normalize_repo_url("git@github.com:owner/repo.git"),
        "https://github.com/owner/repo"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Remove trailing slash",
        normalize_repo_url("https://github.com/owner/repo/"),
        "https://github.com/owner/repo"
    ):
        passed += 1
    else:
        failed += 1

    if test_function(
        "Handle nested org paths in SSH",
        normalize_repo_url("git@github.com:org/team/repo.git"),
        "https://github.com/org/team/repo"
    ):
        passed += 1
    else:
        failed += 1

    print()
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
