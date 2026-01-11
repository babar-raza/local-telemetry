# Deferred Test Refactoring

## Overview

This document describes the 3 test files that were **deferred** during HEAL-TS-02 implementation because they require more complex refactoring approaches beyond simple "remove unittest.mock" changes.

## Deferred Files

### 1. `tests/test_client.py` (791 lines)

**Current State:**
- Uses extensive `unittest.mock` to mock `DatabaseWriter`, `NDJSONWriter`, and `APIClient`
- Has an autouse fixture that mocks these components globally
- Contains 40+ test methods, most using mocks

**Why Deferred:**
- Requires refactoring entire test suite (791 lines)
- Would need real SQLite database and real NDJSON file operations for each test
- The mock-free approach would require:
  - Real `tmp_path` fixtures for all tests
  - Real database setup/teardown for each test
  - Potential test isolation issues with concurrent database access
  - Significantly more complex test setup

**Recommended Approach:**
1. Create a pytest fixture that provides real `TelemetryConfig` with `tmp_path`
2. Replace the autouse fixture with real `DatabaseWriter` and `NDJSONWriter` instances
3. Keep `APIClient` disabled (api_enabled=False) to avoid HTTP mocking
4. Refactor tests one class at a time (12 test classes total)
5. Use real database operations and verify actual file content
6. Estimated effort: 4-6 hours

**Pattern to Follow:**
```python
@pytest.fixture
def test_config(tmp_path):
    """Create a test configuration with real temp directories."""
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    (metrics_dir / "raw").mkdir()
    (metrics_dir / "db").mkdir()

    return TelemetryConfig(
        metrics_dir=metrics_dir,
        database_path=metrics_dir / "db" / "telemetry.sqlite",
        ndjson_dir=metrics_dir / "raw",
        api_url=None,
        api_token=None,
        api_enabled=False,  # Disable API
        agent_owner="test_owner",
        test_mode=None,
    )

def test_start_run_minimal(test_config):
    """Test starting run with minimal parameters."""
    client = TelemetryClient(test_config)

    run_id = client.start_run("test_agent", "test_job")

    # Verify with real database
    assert run_id in client._active_runs

    # Verify real NDJSON file was created
    ndjson_files = list(test_config.ndjson_dir.glob("*.ndjson"))
    assert len(ndjson_files) > 0
```

---

### 2. `tests/test_api.py` (573 lines)

**Current State:**
- Uses extensive `unittest.mock` to mock `httpx` HTTP client
- Tests HTTP requests, retries, timeouts, authentication, error handling
- Mocks `httpx.Client` and `httpx.AsyncClient` with `MagicMock` and `AsyncMock`

**Why Deferred:**
- Requires real HTTP server or httpx test transport
- Current approach mocks at httpx level, which is an external HTTP library
- The proper "no mocking" approach would require:
  - Real HTTP test server (like httpbin.org or local test server)
  - OR httpx's `MockTransport` (which is still a form of mocking, but closer to real behavior)
  - OR using `respx` library (pytest plugin for httpx testing)

**Recommended Approach - Option 1: Use httpx MockTransport**
```python
import httpx

def test_post_run_sync_success():
    """Test successful API post."""
    # Create a mock transport that returns 200
    def mock_handler(request):
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(mock_handler)

    # Client uses real httpx with mock transport
    client = APIClient(
        api_url="https://api.example.com",
        api_token="test-token",
    )

    # Override the httpx client with mock transport
    with httpx.Client(transport=transport) as http_client:
        # Test with real httpx behavior
        ...
```

**Recommended Approach - Option 2: Use respx library**
```python
import respx
import httpx

@respx.mock
def test_post_run_sync_success():
    """Test successful API post."""
    # Mock specific route
    respx.post("https://api.example.com/runs").mock(
        return_value=httpx.Response(200, json={"status": "ok"})
    )

    client = APIClient(
        api_url="https://api.example.com",
        api_token="test-token",
    )

    payload = APIPayload(...)
    success, message = client.post_run_sync(payload)

    assert success is True
```

**Recommended Approach - Option 3: Use real test server**
```python
import httpx
from pytest_httpserver import HTTPServer

def test_post_run_sync_success(httpserver):
    """Test successful API post with real HTTP server."""
    # Setup test server
    httpserver.expect_request("/runs").respond_with_json(
        {"status": "ok"}, status=200
    )

    client = APIClient(
        api_url=httpserver.url_for("/"),
        api_token="test-token",
    )

    payload = APIPayload(...)
    success, message = client.post_run_sync(payload)

    assert success is True
```

**Estimated Effort:** 6-8 hours (depending on approach chosen)

---

### 3. `tests/test_integration_custom_run_id.py` (Unknown size)

**Current State:**
- Unknown exact mock usage (needs inspection)
- Likely mocks HTTP interactions similar to test_api.py

**Why Deferred:**
- Integration test that likely requires both database and HTTP mocking
- Needs investigation to determine exact requirements

**Recommended Approach:**
1. First, inspect the file to understand what it tests
2. Apply combination of approaches from test_client.py (real database) and test_api.py (httpx testing)
3. Estimated effort: 2-4 hours

---

## Summary

| File | Lines | Mock Usage | Approach | Estimated Effort |
|------|-------|------------|----------|------------------|
| test_client.py | 791 | DatabaseWriter, NDJSONWriter, APIClient | Real database + real file operations | 4-6 hours |
| test_api.py | 573 | httpx HTTP client | httpx MockTransport OR respx OR real test server | 6-8 hours |
| test_integration_custom_run_id.py | Unknown | Unknown | TBD after inspection | 2-4 hours |
| **Total** | **1364+** | | | **12-18 hours** |

---

## Philosophy: Why These Are Different

The other 7 test files that were successfully refactored had **simpler mock usage**:
- Mocking file operations → Use real temp files
- Mocking environment variables → Use monkeypatch with real env vars
- Mocking subprocess → Use real functions instead

These 3 deferred files have **complex external dependencies**:
- HTTP requests to external APIs → Requires test server or HTTP mocking library
- Database + file operations + HTTP all together → Requires coordinated real infrastructure

The "NO MOCKING" philosophy still applies, but the implementation requires:
1. **Real infrastructure** (databases, files) where possible
2. **Test doubles** (httpx MockTransport, test servers) for external services
3. **Not unittest.mock** - use proper testing libraries like `respx` or `pytest-httpserver`

---

## Next Steps

When continuing this work:

1. **Priority 1:** Refactor `test_client.py` (most impact)
   - Follow the pattern documented above
   - Refactor one test class at a time
   - Verify tests pass with real database and file operations

2. **Priority 2:** Refactor `test_api.py` (critical for API reliability)
   - Choose approach (MockTransport vs respx vs test server)
   - Add necessary dependencies to requirements.txt
   - Refactor HTTP tests to use chosen approach

3. **Priority 3:** Inspect and refactor `test_integration_custom_run_id.py`
   - Understand what it tests
   - Apply appropriate approach from above

---

## Dependencies Needed

Depending on approach chosen for HTTP testing:

### Option 1: httpx MockTransport (no additional deps)
- Already have httpx
- Use built-in MockTransport

### Option 2: respx library
```bash
pip install respx
```

### Option 3: pytest-httpserver
```bash
pip install pytest-httpserver
```

---

**Document Status:** Created during HEAL-TS-02 implementation (Phase 2)
**Last Updated:** 2026-01-01
**Related:** HEAL-TS-02_IMPLEMENTATION_SUMMARY.md, docs/TEST_ENVIRONMENT_SETUP.md
