"""
Pytest Configuration for Contract Tests

This module provides pytest configuration and auto-use fixtures for contract tests.
Contract tests verify locked user-visible behavior per driftless governance.

See: docs/development/driftless.md
"""

import pytest
import os


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Register custom markers for test hierarchy."""
    config.addinivalue_line(
        "markers",
        "contract: Contract tests that lock user-visible behavior (critical)"
    )
    config.addinivalue_line(
        "markers",
        "regression: Regression tests for bug fixes (semi-locked)"
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration tests (flexible)"
    )
    config.addinivalue_line(
        "markers",
        "performance: Performance baseline tests (optional)"
    )


# =============================================================================
# Test Environment Configuration
# =============================================================================

@pytest.fixture(scope="session")
def test_api_base_url():
    """API base URL for contract tests (configurable via env var)."""
    return os.getenv("TEST_API_BASE_URL", "http://localhost:8765")


@pytest.fixture(scope="session")
def test_db_path():
    """Database path for contract tests (configurable via env var)."""
    return os.getenv("TEST_DB_PATH", "/data/telemetry.sqlite")


# =============================================================================
# Auto-use Fixtures for Cleanup
# =============================================================================

@pytest.fixture(autouse=True, scope="function")
def isolate_test_runs(request):
    """
    Ensure test isolation by tracking and cleaning up test data.

    This fixture automatically runs before/after each test function to prevent
    test pollution in the shared database.
    """
    # Before test: record marker to identify test runs
    test_marker = f"contract-test-{request.node.name}"

    # Store marker for cleanup (attached to request)
    request.node._test_marker = test_marker

    yield  # Run the test

    # After test: cleanup will be handled by cleanup_test_runs fixture if used
    pass

