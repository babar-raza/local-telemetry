# Development Guide

## Prerequisites

- Python 3.9+
- pip
- Git
- Docker (for running the API)
- `httpx` (optional; required for API posting tests)

## Setup

```bash
# Clone repository
git clone <repo-url> local-telemetry
cd local-telemetry

# Install in development mode with dev dependencies
pip install -e ".[dev]"

# Create database schema (local development only)
python scripts/setup_database.py

# Run tests
pytest -v
```

## Project Structure

```
local-telemetry/
├── src/telemetry/          # Core library
│   ├── __init__.py         # Public API exports
│   ├── api.py              # Google Sheets API client
│   ├── buffer.py           # Local NDJSON buffer for failover
│   ├── client.py           # TelemetryClient, RunContext
│   ├── config.py           # TelemetryConfig
│   ├── database.py         # SQLite DatabaseWriter
│   ├── git_detector.py     # Auto-detect git metadata
│   ├── http_client.py      # HTTP API client
│   ├── local.py            # NDJSONWriter
│   ├── models.py           # Data models (RunRecord, etc.)
│   ├── schema.py           # Database schema definitions
│   ├── single_writer_guard.py  # File lock management
│   ├── status.py           # Status normalization
│   └── url_builder.py      # URL construction helpers
├── telemetry_service.py    # FastAPI HTTP server (entry point)
├── scripts/                # Operational scripts
├── tests/                  # Test suite
├── migrations/             # SQL schema migrations
├── schema/                 # SQL schema files
├── docs/                   # Documentation
└── pyproject.toml          # Package configuration
```

## Running Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_client.py

# Run contract tests
pytest tests/contract/ -v

# Run integration tests (requires API running)
pytest tests/integration/ -v

# Run with coverage
pytest --cov=src/telemetry --cov-report=term-missing

# Run smoke test directly
python tests/smoke_test.py

# Skip API-dependent tests
pytest -m "not integration"
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
2. Add migration SQL file in `migrations/`
3. Update `TABLES` dictionary in `schema.py`
4. Test migration path from previous version

## Continuous Integration

Tests are designed to run in CI environments:

```yaml
# CI workflow example
- name: Install dependencies
  run: pip install -e ".[dev]"

- name: Start API server
  run: |
    python telemetry_service.py &
    sleep 5

- name: Run tests
  env:
    TELEMETRY_SKIP_VALIDATION: "true"
  run: pytest -v --cov=src/telemetry --cov-report=xml
```

**Environment variables for CI:**
```bash
TELEMETRY_SKIP_VALIDATION=true    # Skip directory validation
TEST_API_BASE_URL=http://localhost:8765
```

## Debugging

### Enable Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect Database

```bash
# Via Docker
docker compose exec local-telemetry-api sqlite3 /data/telemetry.sqlite

# Useful queries
.schema                                    # Show all tables
SELECT * FROM agent_runs LIMIT 10;         # Recent runs
SELECT * FROM schema_migrations;           # Schema versions
PRAGMA integrity_check;                    # Check DB health
```
