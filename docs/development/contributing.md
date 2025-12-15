# Development Guide

## Prerequisites

- Python 3.9-3.13
- pip
- Git

## Setup

```bash
# Clone repository
git clone <repo-url> local-telemetry
cd local-telemetry

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Initialize storage (creates D:\agent-metrics or C:\agent-metrics)
python scripts/setup_storage.py

# Create database schema
python scripts/setup_database.py

# Validate installation
python scripts/validate_installation.py
```

## Project Structure

```
local-telemetry/
├── src/
│   └── telemetry/          # Main package
│       ├── __init__.py     # Public API exports
│       ├── api.py          # API client for remote posting
│       ├── client.py       # TelemetryClient, RunContext
│       ├── config.py       # TelemetryConfig
│       ├── database.py     # SQLite DatabaseWriter
│       ├── local.py        # NDJSON NDJSONWriter
│       ├── models.py       # Data models (RunRecord, etc.)
│       └── schema.py       # Database schema definitions
├── tests/
│   ├── integration/        # Integration tests
│   ├── stress/             # Stress/load tests
│   ├── edge_cases/         # Edge case tests
│   ├── smoke_test.py       # Quick validation
│   └── test_*.py           # Unit tests
├── scripts/                # Utility scripts
├── config/                 # Configuration files
├── docs/                   # Documentation
└── pyproject.toml          # Project configuration
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_client.py

# Run integration tests only
pytest tests/integration/ -v

# Run with coverage
pytest --cov=src/telemetry --cov-report=term-missing

# Run smoke test directly
python tests/smoke_test.py
```

Alternatively, use the test runner script:

```bash
python scripts/run_tests.py              # All tests
python scripts/run_tests.py --unit       # Unit tests only
python scripts/run_tests.py --integration # Integration tests
python scripts/run_tests.py --smoke      # Smoke test only
python scripts/run_tests.py --coverage   # With coverage
```

## Code Style

The project uses:

- **Black** for formatting (line length: 100)
- **Ruff** for linting
- **Type hints** throughout

```bash
# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/
```

## Making Changes

1. **Read existing code** before modifying
2. **Add tests** for new functionality
3. **Update docs** if behavior changes
4. **Run tests** before committing

### Adding a New Feature

1. Update `models.py` if new data fields needed
2. Update `schema.py` if database schema changes
3. Implement in relevant module
4. Export in `__init__.py` if public API
5. Add tests
6. Update documentation

### Database Schema Changes

1. Increment `SCHEMA_VERSION` in `schema.py` and `models.py`
2. Add migration script in `scripts/`
3. Update `TABLES` dictionary in `schema.py`
4. Test migration path from previous version

## Testing Against Real Storage

Tests can run against real storage:

```bash
# Set environment for real storage testing
export TELEMETRY_TEST_MODE=live
export AGENT_METRICS_DIR=D:\agent-metrics

# Run integration tests
pytest tests/integration/ -v
```

Or use mock mode (no real writes):

```bash
export TELEMETRY_TEST_MODE=mock
pytest tests/
```

## Debugging

### Enable Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect Database

```bash
sqlite3 D:\agent-metrics\db\telemetry.sqlite

# Useful queries
.schema                                    # Show all tables
SELECT * FROM agent_runs LIMIT 10;         # Recent runs
SELECT * FROM schema_migrations;           # Schema versions
PRAGMA integrity_check;                    # Check DB health
```

### Inspect NDJSON

```bash
# View today's events
type D:\agent-metrics\raw\events_YYYYMMDD.ndjson

# Count records
python -c "print(sum(1 for _ in open(r'D:\agent-metrics\raw\events_YYYYMMDD.ndjson')))"
```

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `setup_storage.py` | Create directory structure |
| `setup_database.py` | Initialize SQLite schema |
| `validate_installation.py` | Verify everything works |
| `backup_telemetry_db.py` | Backup database |
| `monitor_telemetry_health.py` | Health check |
| `measure_performance.py` | Performance benchmarks |
| `recover_database.py` | Database recovery |
| `run_tests.py` | Test runner |

## Continuous Integration

Tests are designed to run in CI environments:

```yaml
# Example GitHub Actions
- name: Run tests
  run: |
    pip install -e ".[dev]"
    export TELEMETRY_SKIP_VALIDATION=true
    pytest -v
```
