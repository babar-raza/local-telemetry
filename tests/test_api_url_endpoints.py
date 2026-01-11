"""
API Tests for URL Builder Endpoints

Tests cover:
- GET /api/v1/runs/{event_id}/commit-url endpoint
- GET /api/v1/runs/{event_id}/repo-url endpoint
- GET /api/v1/runs endpoint enhancement with commit_url and repo_url fields
- GitHub, GitLab, and Bitbucket URL construction
- Error handling (404 for missing runs, graceful null handling)
- Edge cases (missing git data, invalid platforms)

NO MOCKING: Uses real HTTP calls to telemetry service via requests.
Server must be running at localhost:8765 for these tests.
"""

import sys
import uuid
import time
from datetime import datetime, timezone
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import test server utilities
try:
    import requests
except ImportError:
    print("[WARN] requests not installed. Run: pip install requests")
    sys.exit(1)

import pytest

# Test configuration
API_URL = "http://localhost:8765"
TEST_TIMEOUT = 10


# Fixtures
@pytest.fixture
def unique_event_id():
    """Generate a unique event ID for each test."""
    return str(uuid.uuid4())


@pytest.fixture
def test_cleanup_event_ids():
    """Track event IDs for cleanup after test."""
    event_ids = []
    yield event_ids
    # Cleanup logic could go here if needed


# Helper functions
def create_test_run_with_git(event_id: str, repo_url: str, commit_hash: str, **kwargs):
    """Create a test run payload with git metadata."""
    payload = {
        "event_id": event_id,
        "run_id": f"test-{event_id[:8]}",
        "agent_name": "url-test-agent",
        "job_type": "url-test",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "status": "success",
        "git_repo": repo_url,
        "git_commit_hash": commit_hash,
    }
    payload.update(kwargs)
    return payload


def create_test_run_without_git(event_id: str):
    """Create a test run payload without git metadata."""
    return {
        "event_id": event_id,
        "run_id": f"test-{event_id[:8]}",
        "agent_name": "url-test-agent",
        "job_type": "url-test",
        "start_time": datetime.now(timezone.utc).isoformat(),
        "status": "success",
    }


class TestCommitURLEndpoint:
    """Test GET /api/v1/runs/{event_id}/commit-url endpoint."""

    def test_get_commit_url_github_https(self, unique_event_id, test_cleanup_event_ids):
        """Test getting commit URL for GitHub HTTPS repository."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with GitHub repo
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="https://github.com/owner/repo",
            commit_hash="abc1234567890"
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET commit URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/commit-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert "commit_url" in data
        assert data["commit_url"] == "https://github.com/owner/repo/commit/abc1234567890"

    def test_get_commit_url_github_ssh(self, unique_event_id, test_cleanup_event_ids):
        """Test getting commit URL for GitHub SSH repository."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with GitHub SSH URL
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="git@github.com:owner/repo.git",
            commit_hash="def4567890abc"
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET commit URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/commit-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert data["commit_url"] == "https://github.com/owner/repo/commit/def4567890abc"

    def test_get_commit_url_gitlab(self, unique_event_id, test_cleanup_event_ids):
        """Test getting commit URL for GitLab repository."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with GitLab repo
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="https://gitlab.com/owner/repo",
            commit_hash="123abc456def"
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET commit URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/commit-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert data["commit_url"] == "https://gitlab.com/owner/repo/-/commit/123abc456def"

    def test_get_commit_url_bitbucket(self, unique_event_id, test_cleanup_event_ids):
        """Test getting commit URL for Bitbucket repository."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with Bitbucket repo
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="https://bitbucket.org/owner/repo",
            commit_hash="789xyz123"
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET commit URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/commit-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert data["commit_url"] == "https://bitbucket.org/owner/repo/commits/789xyz123"

    def test_get_commit_url_no_git_data(self, unique_event_id, test_cleanup_event_ids):
        """Test getting commit URL when run has no git data (should return null)."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run without git metadata
        payload = create_test_run_without_git(unique_event_id)

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET commit URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/commit-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert data["commit_url"] is None

    def test_get_commit_url_missing_commit_hash(self, unique_event_id, test_cleanup_event_ids):
        """Test getting commit URL when only repo_url exists (should return null)."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with repo but no commit hash
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="https://github.com/owner/repo",
            commit_hash=None
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET commit URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/commit-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert data["commit_url"] is None

    def test_get_commit_url_run_not_found(self):
        """Test getting commit URL for non-existent run (should return 404)."""
        fake_event_id = "nonexistent-event-id-12345"

        response = requests.get(
            f"{API_URL}/api/v1/runs/{fake_event_id}/commit-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()


class TestRepoURLEndpoint:
    """Test GET /api/v1/runs/{event_id}/repo-url endpoint."""

    def test_get_repo_url_github(self, unique_event_id, test_cleanup_event_ids):
        """Test getting repository URL for GitHub repo."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with GitHub repo
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="https://github.com/owner/repo.git",
            commit_hash="abc123"
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET repo URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/repo-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert "repo_url" in data
        assert data["repo_url"] == "https://github.com/owner/repo"

    def test_get_repo_url_ssh_normalization(self, unique_event_id, test_cleanup_event_ids):
        """Test that SSH URLs are normalized to HTTPS."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with SSH URL
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="git@gitlab.com:owner/repo.git",
            commit_hash="def456"
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET repo URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/repo-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repo_url"] == "https://gitlab.com/owner/repo"

    def test_get_repo_url_no_git_data(self, unique_event_id, test_cleanup_event_ids):
        """Test getting repo URL when run has no git data (should return null)."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run without git metadata
        payload = create_test_run_without_git(unique_event_id)

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # GET repo URL
        response = requests.get(
            f"{API_URL}/api/v1/runs/{unique_event_id}/repo-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        data = response.json()
        assert data["repo_url"] is None

    def test_get_repo_url_run_not_found(self):
        """Test getting repo URL for non-existent run (should return 404)."""
        fake_event_id = "nonexistent-repo-event-12345"

        response = requests.get(
            f"{API_URL}/api/v1/runs/{fake_event_id}/repo-url",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 404


class TestGetRunsEnhancement:
    """Test GET /api/v1/runs enhancement with commit_url and repo_url fields."""

    def test_get_runs_includes_url_fields_github(self, unique_event_id, test_cleanup_event_ids):
        """Test that GET /api/v1/runs includes commit_url and repo_url fields."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run with GitHub repo
        payload = create_test_run_with_git(
            unique_event_id,
            repo_url="https://github.com/test/repo",
            commit_hash="testcommit123",
            agent_name="url-enhancement-test"
        )

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # Small delay to ensure database write completes
        time.sleep(0.1)

        # GET runs with filter
        response = requests.get(
            f"{API_URL}/api/v1/runs?agent_name=url-enhancement-test&limit=1",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        runs = response.json()
        assert len(runs) >= 1

        # Find our run
        test_run = next((r for r in runs if r["event_id"] == unique_event_id), None)
        assert test_run is not None

        # Verify URL fields are present
        assert "commit_url" in test_run
        assert "repo_url" in test_run

        # Verify URL values
        assert test_run["commit_url"] == "https://github.com/test/repo/commit/testcommit123"
        assert test_run["repo_url"] == "https://github.com/test/repo"

    def test_get_runs_url_fields_null_when_no_git_data(self, unique_event_id, test_cleanup_event_ids):
        """Test that URL fields are null when git data is missing."""
        test_cleanup_event_ids.append(unique_event_id)

        # Create run without git metadata
        payload = create_test_run_without_git(unique_event_id)
        payload["agent_name"] = "url-null-test"

        # POST run
        response = requests.post(f"{API_URL}/api/v1/runs", json=payload, timeout=TEST_TIMEOUT)
        assert response.status_code == 201

        # Small delay
        time.sleep(0.1)

        # GET runs
        response = requests.get(
            f"{API_URL}/api/v1/runs?agent_name=url-null-test&limit=1",
            timeout=TEST_TIMEOUT
        )

        assert response.status_code == 200
        runs = response.json()
        assert len(runs) >= 1

        # Find our run
        test_run = next((r for r in runs if r["event_id"] == unique_event_id), None)
        assert test_run is not None

        # Verify URL fields are null
        assert test_run["commit_url"] is None
        assert test_run["repo_url"] is None


# Guard against pytest collection when server is not running
def pytest_configure(config):
    """Add markers for integration tests."""
    config.addinivalue_line(
        "markers", "requires_api_server: mark test as requiring running API server"
    )


# Mark all tests in this file as requiring API server
pytestmark = pytest.mark.requires_api_server


if __name__ == "__main__":
    print("NOTE: These tests require the telemetry API server running at localhost:8765")
    print("Start the server with: python telemetry_service.py")
    print()
    print("Then run tests with: pytest tests/test_api_url_endpoints.py -v")
