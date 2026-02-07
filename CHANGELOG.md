# Changelog - Local Telemetry Platform

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [3.0.0] - 2026-02-07

### Changed
- Repo cleanup for GitLab: removed 150 development artifacts, consolidated documentation
- Version aligned to 3.0.0 across Dockerfile, docker-compose, pyproject.toml, and code
- Docker deployment is now the primary deployment method
- Removed external `seo-intelligence-network` from docker-compose
- Documentation consolidated from 41 files to 16 concise guides
- Scripts reduced from 87 to 12 essential operational scripts
- Test suite reduced from 53 to 39 files (removed tests for deleted scripts)
- SQLite PRAGMA settings: DELETE journal mode, FULL synchronous (corruption prevention)

### Removed
- Interactive Streamlit dashboard (`scripts/dashboard.py`, `requirements-dashboard.txt`)
- GitHub Actions CI workflows (`.github/`)
- Internal specs directory (`specs/`)
- Development reports, healing plans, and validation scripts
- 75 one-off/migration/diagnostic scripts
- 25 redundant or outdated documentation files

---

## [2.1.0] - 2026-01-09

### Added
- Separated API URLs: `TELEMETRY_API_URL` (local) and `GOOGLE_SHEETS_API_URL` (external)
- Configuration validation via `TelemetryConfig.validate()` with clear error messages
- Smart retry logic: 4xx client errors not retried, only transient 5xx/network errors
- Google Sheets disabled by default (`GOOGLE_SHEETS_API_ENABLED=false`)
- Two-client architecture documentation

### Fixed
- 404 errors caused by Google Sheets client posting to localhost
- Configuration ambiguity with single `METRICS_API_URL` serving two purposes
- Unnecessary retries on permanent client errors

### Deprecated
- `METRICS_API_URL` - use `TELEMETRY_API_URL` instead
- `METRICS_API_ENABLED` - use `GOOGLE_SHEETS_API_ENABLED` instead

---

## [2.0.0] - 2026-01-02

### Added
- Automatic Git context detection (`git_detector.py`) with caching
- GitHub/GitLab/Bitbucket URL construction endpoints (`url_builder.py`)
- Pydantic validation for `git_commit_source` enum ('manual', 'llm', 'ci')
- HTTP-first commit association endpoint (`POST /api/v1/runs/{event_id}/associate-commit`)
- Commit URL and repo URL endpoints (`GET /api/v1/runs/{event_id}/commit-url`, `/repo-url`)

### Changed
- Commit association uses HTTP-first with graceful database fallback

---

## [1.0.0] - 2025-12-15

### Added
- FastAPI HTTP API server with single-writer pattern
- Query endpoint (`GET /api/v1/runs`) with filtering by agent, status, date
- Update endpoint (`PATCH /api/v1/runs/{event_id}`) for run modifications
- Batch create endpoint (`POST /api/v1/runs/batch`)
- Health check and metrics endpoints
- Event idempotency via `event_id` UNIQUE constraint
- Metadata endpoint with 5-minute TTL caching
- Optimized composite indexes for query performance

---

## [0.1.0] - 2025-11-01

### Added
- Initial release: TelemetryClient with context manager support
- Dual-write storage: NDJSON + SQLite
- Cross-platform path detection (Windows, Linux, macOS, Docker)
- Optional remote API posting with retry logic
- Run lifecycle management (start, log event, end)
- Database schema v1 with migrations
