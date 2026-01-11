# Test Environment Setup Guide

## Overview

The local-telemetry test suite follows the architectural principle: **NO MOCKING - tests use real logic/real data/real LLM calls/real everything**.

This document describes the test environment requirements and setup procedures.

## Core Testing Philosophy

### No Mocking Policy

All tests use real dependencies:
- **Real HTTP API** - Tests connect to actual API servers (localhost or production)
- **Real Database** - Tests use real SQLite databases (in temp directories or test databases)
- **Real File System** - Tests create and manipulate actual files and directories
- **Real Environment Variables** - Tests set real OS environment variables (via pytest monkeypatch)
- **Real Network Requests** - Tests make actual HTTP requests (no mock responses)
- **Real Subprocess Calls** - Tests execute real system commands
- **Real Threads/Concurrency** - Tests use actual threading and async operations

### Why No Mocking?

1. **Catches Real Integration Issues** - Mocks can hide actual compatibility problems
2. **Tests Actual Behavior** - Real dependencies behave differently than mocks
3. **Better Production Confidence** - If tests pass with real components, production will work
4. **Simpler Test Code** - No complex mock setup, just real operations
5. **Catches Timing Issues** - Real operations expose race conditions and timing bugs

## Test Environment Requirements

### 1. Python Environment

- **Python 3.9+** required
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  pip install -r requirements-dev.txt
  ```

### 2. pytest and Test Tools

Required packages:
- `pytest>=7.0.0`
- `pytest-cov` (for coverage reports)
- `pytest-timeout` (for test timeouts)
- `pytest-xdist` (for parallel test execution)

Install:
```bash
pip install pytest pytest-cov pytest-timeout pytest-xdist
```

### 3. Telemetry HTTP API Server (REQUIRED for some tests)

**IMPORTANT:** After HEAL-TS-02 refactoring, many tests now use REAL HTTP API calls.

The telemetry HTTP API server must be running for:
- `tests/test_client.py` - Uses real HTTP POST/PATCH to localhost:8765
- `tests/test_integration_custom_run_id.py` - Integration tests with real API calls
- Other integration tests that verify end-to-end telemetry flow

**Start the API server:**
```bash
python -m api.main
```

The server runs on `http://localhost:8765` by default.

**Graceful Degradation:**
- If API is NOT running, tests will gracefully failover to buffer files
- Some tests are marked with `@pytest.mark.skipif(not API_AVAILABLE)` and will be skipped
- Tests verify that the system handles API unavailability correctly (buffer failover)

**Exception: test_api.py**
- `tests/test_api.py` tests the external Google Sheets API client
- This file uses httpx mocking (acceptable exception to NO MOCKING policy)
- Reason: Cannot make real calls to Google Sheets without credentials and side effects

### 4. Database Setup

Tests create temporary SQLite databases automatically in pytest temp directories.

**No manual setup required** - each test creates its own isolated database.

**Database location:**
- Temporary databases: `pytest` creates temp dirs automatically
- Test databases are cleaned up after tests complete

### 5. File System

Tests require write access to:
- Temporary directories (created by pytest)
- `D:\agent-metrics` or `C:\agent-metrics` (configurable via env vars)

**Temp directories:**
- pytest provides `tmp_path` fixture for isolated file operations
- Tests clean up after themselves

### 6. Environment Variables

Tests use `pytest.monkeypatch` to set environment variables safely:

**Key environment variables:**
- `AGENT_METRICS_DIR` - Base directory for telemetry data
- `METRICS_API_URL` - API server URL (default: `http://localhost:8765`)
- `METRICS_API_TOKEN` - API authentication token
- `METRICS_API_ENABLED` - Enable/disable API posting
- `TELEMETRY_TEST_MODE` - Set test mode behavior
- `AGENT_OWNER` - Agent owner identifier

**Example test using real env vars:**
```python
def test_config_with_api_url(monkeypatch):
    monkeypatch.setenv("METRICS_API_URL", "https://api.example.com")
    config = TelemetryConfig.from_env()
    assert config.api_url == "https://api.example.com"
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_config.py
```

### Run Specific Test

```bash
pytest tests/test_config.py::TestTelemetryConfigCreation::test_config_creation_with_defaults
```

### Run with Coverage

```bash
pytest --cov=src --cov-report=html
```

### Run in Parallel

```bash
pytest -n auto
```

### Run with Verbose Output

```bash
pytest -v
```

### Skip Integration Tests (API-dependent)

```bash
pytest -m "not integration"
```

## Test Organization

### Test File Categories

1. **Unit Tests** - Test individual components in isolation
   - `tests/test_config.py` - Configuration loading
   - `tests/test_database_writer.py` - Database operations
   - `tests/test_file_extraction.py` - File extraction utilities

2. **Integration Tests** - Test component interactions
   - `tests/test_client.py` - Telemetry client with HTTP API
   - `tests/test_integration_custom_run_id.py` - Custom run ID workflows

3. **End-to-End Tests** - Test complete workflows
   - `tests/test_api_e2e.py` - Full API workflows (requires API server)
   - `tests/test_hugo_translator_integration.py` - Hugo translator integration

4. **Quality Assurance Tests** - Test validation and quality gates
   - `tests/test_quality_gate.py` - Quality gate validation
   - `tests/test_verify_analysis.py` - Analysis verification
   - `tests/test_verified_todo_update.py` - Verified todo updates

5. **Infrastructure Tests** - Test deployment and infrastructure
   - `tests/test_deployment.py` - Deployment verification
   - `tests/test_storage_setup.py` - Storage directory setup

### Standalone Test Scripts

Some tests are standalone scripts (not pytest tests):
- `tests/test_api_e2e.py` - Run directly: `python tests/test_api_e2e.py`
- `tests/test_deployment.py` - Run directly: `python tests/test_deployment.py`
- `tests/test_hugo_translator_integration.py` - Run directly: `python tests/test_hugo_translator_integration.py`

**Note:** These scripts have guards to prevent execution during pytest import.

## Test Data Management

### Temporary Files

Tests use pytest's `tmp_path` fixture for temporary file operations:

```python
def test_file_operations(tmp_path):
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello, World!")
    assert test_file.read_text() == "Hello, World!"
```

### Temporary Databases

Tests create isolated SQLite databases in temp directories:

```python
def test_database_operations(tmp_path):
    db_path = tmp_path / "test.sqlite"
    writer = DatabaseWriter(db_path)
    # ... test database operations
```

### Test Data Fixtures

Fixtures provide reusable test data:

```python
@pytest.fixture
def sample_run_record():
    return {
        "event_id": "test-event-123",
        "run_id": "test-run-001",
        "agent_name": "test-agent",
        "status": "success"
    }
```

## Common Test Patterns

### 1. Testing Configuration with Real Env Vars

```python
def test_api_configuration(monkeypatch):
    monkeypatch.setenv("METRICS_API_URL", "https://api.example.com")
    monkeypatch.setenv("METRICS_API_TOKEN", "secret-token")

    config = TelemetryConfig.from_env()

    assert config.api_url == "https://api.example.com"
    assert config.api_token == "secret-token"
```

### 2. Testing Database Operations with Real SQLite

```python
def test_database_insert(tmp_path):
    db_path = tmp_path / "test.sqlite"
    create_schema(str(db_path))

    writer = DatabaseWriter(db_path)

    run = {
        "event_id": "evt-123",
        "run_id": "run-001",
        "agent_name": "test-agent",
        "status": "success"
    }

    success, error = writer.insert_run(run)

    assert success is True
    assert error is None
```

### 3. Testing HTTP Client with Real API Server

```python
def test_post_event_to_api():
    """Requires API server running on localhost:8765"""
    client = HTTPClient("http://localhost:8765")

    event = {
        "event_id": str(uuid.uuid4()),
        "run_id": "test-run-001",
        "agent_name": "test-agent"
    }

    response = client.post_event(event)

    assert response["status"] == "created"
```

### 4. Testing File Operations with Real File System

```python
def test_file_extraction(tmp_path):
    # Create a real test file
    input_file = tmp_path / "agent_output.txt"
    input_file.write_text("""
    File: test.py
    ```python
    print("Hello, World!")
    ```
    """)

    # Extract files using real file operations
    result = extract_files_from_agent_output(input_file, tmp_path / "output")

    assert result.files_extracted == 1
    assert (tmp_path / "output" / "test.py").exists()
```

### 5. Testing Concurrent Database Access

```python
def test_database_lock_handling(tmp_path):
    """Test real database locking with threads"""
    db_path = tmp_path / "test.sqlite"
    create_schema(str(db_path))

    writer = DatabaseWriter(db_path, max_retries=5)

    def create_lock():
        # Create REAL database lock
        conn = sqlite3.connect(str(db_path))
        conn.execute("BEGIN EXCLUSIVE")
        time.sleep(0.5)
        conn.rollback()
        conn.close()

    # Start lock in background thread
    lock_thread = threading.Thread(target=create_lock)
    lock_thread.start()
    time.sleep(0.1)  # Let lock acquire

    # This should retry and succeed
    success, result, message = writer._execute_with_retry("SELECT 1", ())

    assert success is True
    lock_thread.join()
```

## Troubleshooting

### Tests Fail with "Connection Refused"

**Problem:** API-dependent tests fail because API server is not running.

**Solution:** Start the API server:
```bash
python telemetry_service.py
```

### Tests Fail with "Permission Denied"

**Problem:** Tests cannot write to required directories.

**Solution:** Ensure write permissions or set `AGENT_METRICS_DIR` to a writable location:
```bash
export AGENT_METRICS_DIR=/tmp/agent-metrics
```

### Tests Hang or Timeout

**Problem:** Database lock tests may hang if locks are not released.

**Solution:**
- Check for zombie threads
- Restart the test run
- Use `pytest-timeout` to enforce test timeouts:
  ```bash
  pytest --timeout=300
  ```

### Import Errors

**Problem:** Tests cannot import telemetry modules.

**Solution:** Ensure `src` is in Python path (tests handle this automatically).

### Temporary Directory Issues

**Problem:** Temp directories fill up or are not cleaned.

**Solution:** pytest cleans up temp directories automatically. If issues persist:
```bash
# Manually clean pytest cache
rm -rf .pytest_cache
pytest --cache-clear
```

## Test Execution Report

To generate a comprehensive test execution report:

```bash
pytest --verbose --cov=src --cov-report=html --cov-report=term > test_execution_report.txt 2>&1
```

View HTML coverage report:
```bash
open htmlcov/index.html  # macOS
start htmlcov/index.html  # Windows
```

## Continuous Integration

### GitHub Actions

Example workflow (`.github/workflows/test.yml`):

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
    - uses: actions/checkout@v3

    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install -r requirements-dev.txt

    - name: Start API server
      run: |
        python telemetry_service.py &
        sleep 5  # Wait for server to start

    - name: Run tests
      run: pytest --cov=src --cov-report=xml

    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## Best Practices

### 1. Use Real Dependencies

Always use real dependencies instead of mocks:
- ✅ Real SQLite database
- ✅ Real HTTP requests
- ✅ Real file system operations
- ✅ Real environment variables
- ❌ No unittest.mock
- ❌ No mock HTTP responses
- ❌ No mock file system

### 2. Isolate Tests

Each test should be isolated:
- Use `tmp_path` for file operations
- Use separate database files
- Use `monkeypatch` for environment variables
- Clean up resources in `finally` blocks

### 3. Test Real Workflows

Test complete workflows, not just units:
- Start run → log events → end run
- Create insight → generate action → execute action
- POST event → verify in database → query via API

### 4. Handle Timing

Real dependencies have timing considerations:
- Use `time.sleep()` for thread synchronization
- Use `threading.Event` for coordination
- Set appropriate timeouts for HTTP requests
- Use retry logic for database locks

### 5. Document Requirements

Clearly document test requirements:
- API server running
- Required environment variables
- File system permissions
- External dependencies

## Summary

The local-telemetry test suite uses **real dependencies** to ensure production-ready code. Tests verify actual behavior with real databases, real HTTP APIs, real file systems, and real environment variables.

This approach provides high confidence that the system works correctly in production environments.

For questions or issues, refer to:
- [Architecture](../plans/healing/HEAL-TS-02.md)
- [Test Files](../tests/)
- [Source Code](../src/)
