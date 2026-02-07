# Contract Tests

**Status:** Active
**Governance:** Contract tests are LOCKED - if a contract test fails, the code is wrong (not the test)

---

## Purpose

Contract tests lock **user-visible behavior**:

- **If a contract test fails, the code is wrong** (not the test)
- Tests document the system's intended behavior
- Changes to contract tests require explicit approval (fail-explain-modify protocol)

---

## Test Structure

```
tests/contract/
├── invariants/          # Core system invariants
│   └── test_core_invariants.py
├── http_api/            # HTTP API contracts
│   └── test_http_contracts.py
├── conftest.py          # Shared fixtures
├── fixtures.py          # Test data factories
└── helpers.py           # Test utilities
```

---

## Running Tests

### Run All Contract Tests
```bash
pytest -m contract
```

### Run Specific Categories
```bash
# Core invariants only
pytest -m contract tests/contract/invariants/

# HTTP API only
pytest -m contract tests/contract/http_api/

# Exclude performance tests
pytest -m "contract and not performance"
```

---

## Test Markers

Defined in [pytest.ini](../../pytest.ini):

- `@pytest.mark.contract` - Contract tests (LOCKED)
- `@pytest.mark.regression` - Regression tests (semi-locked)
- `@pytest.mark.integration` - Integration tests (flexible)
- `@pytest.mark.unit` - Unit tests (flexible)
- `@pytest.mark.performance` - Performance baselines (optional)

---

## Core Invariants

| Test | Invariant |
|------|-----------|
| `test_invariant_never_crash_agent` | Client never throws exceptions to calling agent |
| `test_invariant_single_writer_enforcement` | Only one process writes to DB at a time |
| `test_invariant_event_idempotency` | Duplicate event_id inserts are rejected safely |
| `test_invariant_at_least_once_delivery` | Events reach at least one storage backend |
| `test_invariant_corruption_prevention_pragmas` | SQLite PRAGMA settings enforced |
| `test_invariant_non_negative_metrics` | Metric counters are non-negative |
| `test_invariant_status_constraints` | Run status values are constrained to valid enum |

## HTTP API Contracts

See [test_http_contracts.py](http_api/test_http_contracts.py) for the full set of HTTP API contract tests covering:
- `POST /api/v1/runs` - Run creation and idempotency
- `GET /api/v1/runs` - Query with filters and pagination
- `PATCH /api/v1/runs/{event_id}` - Partial updates
- `POST /api/v1/runs/{event_id}/associate-commit` - Git commit association
- `GET /health` and `GET /metrics` - Service health

---

## Fail-Explain-Modify Protocol

If a contract test fails:

1. **STOP** - Do not modify the test
2. **EXPLAIN** - Understand why the code changed
3. **DECIDE**:
   - If code is wrong: fix the code
   - If behavior intentionally changed: update test WITH approval
4. **DOCUMENT** - Record the decision in commit message

### Test Modification Rules

- **Allowed**: Adding new contract tests
- **Allowed**: Fixing test bugs (if test logic is wrong)
- **Requires Approval**: Changing expected behavior
- **Forbidden**: Deleting contract tests without explanation
