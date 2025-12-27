# Contract Tests

**Status:** Skeleton (implementation in progress)
**Governance:** Driftless - contract tests are LOCKED
**Reference:** [reports/driftless/13_contract_seed_plan.md](../../reports/driftless/13_contract_seed_plan.md)

---

## Purpose

Contract tests lock **user-visible behavior** according to driftless governance principles:

- **If a contract test fails, the code is wrong** (not the test)
- Tests document the system's intended behavior
- Changes to contract tests require explicit approval (fail-explain-modify protocol)

See: [docs/development/driftless.md](../../docs/development/driftless.md)

---

## Test Structure

```
tests/contract/
├── invariants/          # Core system invariants (7 tests)
│   └── test_core_invariants.py
├── http_api/            # HTTP API contracts (12 tests)
│   └── test_http_contracts.py
├── client_library/      # Python client contracts (4 tests) [TO BE CREATED]
└── performance/         # Performance baselines (2 tests) [TO BE CREATED]
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

### Run All Tests (Including Non-Contract)
```bash
pytest
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

## Implementation Status

### ✅ Completed
- [pytest.ini](../../pytest.ini) - Test configuration with markers
- [test_core_invariants.py](invariants/test_core_invariants.py) - 7 skeleton tests
- [test_http_contracts.py](http_api/test_http_contracts.py) - 12 skeleton tests
- 2 fully implemented tests: `test_http_health_check`, `test_http_metrics`

### 🚧 In Progress (Skeletons Created)
- Core invariant tests (7 tests with TODO comments)
- HTTP API tests (10 tests with TODO comments)

### 📋 Pending
- Client library contract tests (4 tests)
- Performance baseline tests (2 tests)
- Test fixtures (API client, database setup/teardown)
- CI integration

---

## Test Categories

### 1. Core Invariants (7 tests)

**Priority:** CRITICAL
**Status:** Skeleton created

| Test | Invariant | Status |
|------|-----------|--------|
| `test_invariant_never_crash_agent` | INV-1 | TODO |
| `test_invariant_single_writer_enforcement` | INV-2 | TODO |
| `test_invariant_event_idempotency` | INV-3 | TODO |
| `test_invariant_at_least_once_delivery` | INV-4 | TODO |
| `test_invariant_corruption_prevention_pragmas` | INV-5 | ✅ Partial |
| `test_invariant_non_negative_metrics` | INV-6 | TODO |
| `test_invariant_status_constraints` | INV-7 | TODO |

**Reference:** [specs/_index.md](../../specs/_index.md)

---

### 2. HTTP API Contracts (12 tests)

**Priority:** HIGH
**Status:** Skeleton created

#### POST /api/v1/runs (3 tests)
- `test_http_create_run_minimal_payload` - TODO
- `test_http_create_run_idempotency` - TODO
- `test_http_create_run_required_fields_missing` - TODO

#### GET /api/v1/runs (3 tests)
- `test_http_query_runs_no_filters` - TODO
- `test_http_query_runs_pagination` - TODO
- `test_http_query_runs_filters` - TODO

#### PATCH /api/v1/runs/{event_id} (1 test)
- `test_http_update_run_partial_update` - TODO

#### GET /health (1 test)
- `test_http_health_check` - ✅ Implemented

#### GET /metrics (1 test)
- `test_http_metrics` - ✅ Implemented

#### POST /api/v1/runs/batch (1 test)
- `test_http_batch_create` - TODO

**Reference:** [specs/features/](../../specs/features/)

---

### 3. Client Library Contracts (NOT YET CREATED)

**Priority:** MEDIUM
**Status:** Not started

Planned tests:
- `test_client_start_run_returns_event_id`
- `test_client_track_run_context_manager`
- `test_client_never_raises_exceptions`
- `test_client_buffer_failover`

---

### 4. Performance Baselines (NOT YET CREATED)

**Priority:** OPTIONAL
**Status:** Not started

Planned tests:
- `test_performance_query_400_runs`
- `test_performance_api_latency_p95`

---

## Next Steps

1. **Implement TODO sections** in existing skeleton tests
2. **Create test fixtures**:
   - API client wrapper
   - Database setup/teardown
   - Test data factories
3. **Write missing specs**:
   - GET /health spec
   - GET /metrics spec
   - PATCH /api/v1/runs/{event_id} spec
   - POST /api/v1/runs/batch spec
4. **Create client library tests**
5. **Add CI integration** to prevent regressions

---

## Driftless Governance

### Fail-Explain-Modify Protocol

If a contract test fails:

1. **STOP** - Do not modify the test
2. **EXPLAIN** - Understand why the code changed
3. **DECIDE**:
   - If code is wrong → Fix the code
   - If behavior intentionally changed → Update test WITH approval
4. **DOCUMENT** - Record the decision in commit message

### Test Modification Rules

- ✅ **Allowed**: Adding new contract tests
- ✅ **Allowed**: Fixing test bugs (if test logic is wrong)
- ⚠️ **Requires Approval**: Changing expected behavior
- ❌ **Forbidden**: Deleting contract tests without explanation

---

## Evidence Chain

All tests reference their specification:

```
Contract Test
  ↓
@pytest.mark.contract
  ↓
SPEC: specs/features/XXX.md#section
  ↓
Evidence: src/file.py:line
  ↓
Source Code
```

**No hallucinations** - All tests verify documented behavior.

---

## Contact

For questions about contract tests:
- See: [13_contract_seed_plan.md](../../reports/driftless/13_contract_seed_plan.md)
- See: [driftless.md](../../docs/development/driftless.md)
- See: [spec_mining_manifest.yml](../../reports/driftless/spec_mining_manifest.yml)
