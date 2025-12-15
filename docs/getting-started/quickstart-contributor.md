# Contributor Quickstart

## Steps
1. **Clone and install**
   ```bash
   git clone <repo>
   cd local-telemetry
   pip install -e ".[dev]"
   ```
2. **Run formatting/lint (optional)**
   ```bash
   ruff check .
   black --check .
   ```
3. **Run tests (unit)**
   ```bash
   python scripts/run_tests.py --unit -v
   ```
   - For integration tests, ensure `{base}` storage exists (see `reference/config.md`), then:
   ```bash
   python scripts/run_tests.py --integration -v
   ```
4. **Review architecture**
   - `architecture/system.md` and `reference/api.md` for core surfaces.
5. **Open dev docs**
   - `development/contributing.md`
   - `development/testing.md`

## Environment tips
- Set `AGENT_METRICS_DIR` to a temp path for integration tests if desired.
- httpx is optional but required for API posting tests.
