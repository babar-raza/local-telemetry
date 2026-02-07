# Testing Guide

## Testing Philosophy: No Mocking

Tests use real dependencies (real SQLite, real HTTP, real filesystem, real env vars). The only exception is `tests/test_api.py` which mocks httpx for Google Sheets (cannot make real calls without credentials).

## Required Test Tools

```bash
pip install -e ".[dev]"
# or individually:
pip install pytest pytest-cov pytest-timeout pytest-xdist
```

## Running Tests

```bash
pytest                           # All tests
pytest -v                        # Verbose
pytest tests/test_client.py      # Single file
pytest tests/contract/ -v        # Contract tests only
pytest tests/integration/ -v     # Integration tests (may need API)
pytest -m "not integration"      # Skip API-dependent tests
pytest --cov=src/telemetry       # With coverage
python tests/smoke_test.py       # Quick smoke test
```

## API Server for Integration Tests

Some tests require the telemetry HTTP API running at `localhost:8765`:
```bash
python telemetry_service.py       # Start before running tests
# or
docker compose up -d              # Use Docker
```
Tests with `@pytest.mark.skipif(not API_AVAILABLE)` skip gracefully if the API is down.

## Test Organization

```
tests/
├── contract/              # User-visible behavior (locked -- do not change without spec review)
│   ├── http_api/          # HTTP endpoint contracts
│   └── invariants/        # Core data invariants
├── integration/           # Component interactions (may need running API)
│   ├── test_basic_write.py
│   ├── test_context_manager.py
│   ├── test_error_handling.py
│   ├── test_production_pragma.py
│   └── test_queries.py
├── durability/            # Crash recovery tests
├── edge_cases/            # Edge case handling
├── regression/            # Bug fix tests (semi-locked)
├── stress/                # Load and concurrency tests
├── smoke_test.py          # Quick validation
├── load_test.py           # Performance baseline
└── test_*.py              # Unit tests (one per module)
```

## Test Markers

Defined in `pyproject.toml`:

| Marker | Description |
|--------|-------------|
| `contract` | Critical user-visible behavior |
| `regression` | Bug fix tests |
| `integration` | Requires component interactions |
| `unit` | Isolated unit tests |
| `performance` | Performance baseline |
| `fast` | < 1 second |
| `slow` | Slow-running |
| `requires_api` | Needs HTTP API running |
| `requires_db` | Needs real database I/O |
| `serial` | Must run sequentially |

## Testing Against Real Storage

```bash
# Real storage
export TELEMETRY_TEST_MODE=live
export AGENT_METRICS_DIR=D:\agent-metrics
pytest tests/integration/ -v

# Mock mode (no real writes)
export TELEMETRY_TEST_MODE=mock
pytest tests/
```

## Test Data Cleanup

Tests use identifiable agent names (e.g., `test_agent`, `query_test_agent`):
```sql
DELETE FROM agent_runs WHERE agent_name LIKE '%test%';
```
