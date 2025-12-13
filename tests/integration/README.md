# Integration Tests

This directory contains integration tests for the telemetry library. These tests verify end-to-end functionality by writing to real storage (D:\agent-metrics) and querying actual data.

## Test Files

### test_basic_write.py (5 tests)
Tests basic telemetry write operations:
- NDJSON file writes
- SQLite database writes
- Dual-write consistency
- Metadata handling
- Custom metrics JSON

### test_context_manager.py (9 tests)
Tests the context manager usage pattern:
- Basic `with client.track_run()` usage
- Automatic run lifecycle management
- Metrics and event updates
- Exception handling
- Nested exceptions
- Custom metrics and insight relations

### test_error_handling.py (9 tests)
Tests error handling and graceful degradation:
- Invalid input handling
- Partial failure recovery
- Concurrent write safety
- Missing environment variables
- Large payloads
- Special characters

### test_queries.py (15 tests)
Tests querying telemetry data:
- Basic SELECT queries
- WHERE clause filtering
- Aggregate functions (COUNT, SUM, AVG)
- Grouping and ordering
- Time-based queries
- Complex multi-condition queries

## Running Tests

### Quick Verification
```bash
python verify_day2.py
```

### Run All Integration Tests
```bash
python run_all_integration_tests.py
```

### Run Specific Test File
```bash
python -c "import sys; sys.path.insert(0, 'src'); sys.path.insert(0, r'C:\Users\prora\AppData\Roaming\Python\Python313\site-packages'); import pytest; pytest.main(['-v', 'tests/integration/test_basic_write.py'])"
```

### Run Single Test
```bash
python -c "import sys; sys.path.insert(0, 'src'); sys.path.insert(0, r'C:\Users\prora\AppData\Roaming\Python\Python313\site-packages'); import pytest; pytest.main(['-v', 'tests/integration/test_basic_write.py::TestBasicWrite::test_basic_ndjson_write'])"
```

## Test Requirements

- **Python:** 3.9+
- **Dependencies:** pytest, telemetry package
- **Storage:** D:\agent-metrics (or set AGENT_METRICS_DIR)
- **Database:** SQLite (auto-created)

## Test Characteristics

### Real Storage
These tests write to **REAL** storage locations:
- NDJSON: `D:\agent-metrics\raw\`
- SQLite: `D:\agent-metrics\db\telemetry.sqlite`

**Warning:** Tests may create many records. Clean up test data periodically.

### Test Isolation
- Each test uses unique run IDs (timestamps)
- Tests are independent (no shared state)
- Tests can run in parallel (thread-safe)

### Test Data Cleanup
Tests use identifiable agent names (e.g., `test_agent`, `query_test_agent`) for easy cleanup:

```sql
-- Clean up test data
DELETE FROM agent_runs WHERE agent_name LIKE '%test%';
```

## Fixtures

### telemetry_client
Creates a TelemetryClient with real configuration:
```python
@pytest.fixture
def telemetry_client():
    config = TelemetryConfig.from_env()
    return TelemetryClient(config)
```

## Common Patterns

### Basic Write
```python
def test_example(telemetry_client):
    run_id = telemetry_client.start_run(
        agent_name="test_agent",
        job_type="test_job",
        trigger_type="test"
    )
    telemetry_client.end_run(run_id, status="success")
```

### Context Manager
```python
def test_example(telemetry_client):
    with telemetry_client.track_run(
        agent_name="test_agent",
        job_type="test_job"
    ) as run_ctx:
        run_ctx.set_metrics(items_discovered=10)
        run_ctx.log_event("checkpoint", {"step": 1})
```

### Query Data
```python
def test_example(telemetry_client):
    config = TelemetryConfig.from_env()
    conn = sqlite3.connect(str(config.database_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM agent_runs")
    count = cursor.fetchone()[0]

    conn.close()
```

## Test Coverage

Total: **38 tests**

| Category | Tests | Coverage |
|----------|-------|----------|
| Basic Write | 5 | ✅ High |
| Context Manager | 9 | ✅ High |
| Error Handling | 9 | ✅ High |
| Queries | 15 | ✅ High |

## Troubleshooting

### ModuleNotFoundError: No module named 'telemetry'
**Solution:** Add src/ to Python path:
```bash
export PYTHONPATH=src:$PYTHONPATH  # Linux/Mac
set PYTHONPATH=src;%PYTHONPATH%    # Windows
```

### Database is locked
**Solution:** Close any open database connections. Ensure no other process is accessing the database.

### NDJSON file not found
**Solution:** Ensure D:\agent-metrics\raw\ exists or set AGENT_METRICS_DIR environment variable.

### Tests fail with permission errors
**Solution:** Ensure write permissions for D:\agent-metrics\

## Best Practices

1. **Use unique IDs** - Always use timestamps or unique identifiers in test data
2. **Clean up** - Periodically remove test data from database
3. **Verify results** - Always check both NDJSON and SQLite
4. **Handle errors** - Expect graceful failures, not exceptions
5. **Test isolation** - Don't depend on other tests

## Development

### Adding New Tests

1. Choose the appropriate test file
2. Add a test method to the test class
3. Use the `telemetry_client` fixture
4. Verify results in both NDJSON and SQLite
5. Use descriptive names and docstrings

### Test Naming Convention
- Test files: `test_*.py`
- Test classes: `Test*`
- Test methods: `test_*`

---

**Last Updated:** 2025-12-11
**Day 2 Status:** ✅ Complete
