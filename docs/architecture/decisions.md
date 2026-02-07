# Architecture Decision Records

## ADR-001: DELETE Journal Mode over WAL

**Date:** 2025-12-19
**Status:** Accepted

**Context:** SQLite offers WAL (Write-Ahead Logging) for better concurrency, but the primary deployment target is Docker on Windows with volume mounts.

**Decision:** Use `journal_mode=DELETE` with `synchronous=FULL` and `busy_timeout=30000`.

**Rationale:**
- WAL creates `-shm` and `-wal` sidecar files that fail on Docker Desktop Windows volumes and network mounts.
- Container restarts orphan `-shm`/`-wal` files, causing "database is locked" errors.
- `synchronous=FULL` is the critical corruption-prevention setting regardless of journal mode.
- DELETE mode works universally: Docker, Windows, Linux, NFS, CIFS.

**Testing:** DELETE mode achieved 100% success rate across 6 concurrent runs with no lock errors. WAL mode exhibited intermittent lock errors and orphaned sidecar files on Docker restarts.

**Trade-offs:** DELETE has slightly slower concurrent writes, mitigated by `busy_timeout=30000`.

**Revisit if:** Deployment moves to native Linux processes on local filesystems (no Docker, no network mounts).

## ADR-002: Single-Writer Pattern

**Date:** 2025-12-15
**Status:** Accepted

**Context:** SQLite does not support concurrent writes from multiple processes safely, especially in Docker.

**Decision:** Enforce single-writer via `TELEMETRY_API_WORKERS=1` and file-lock (`telemetry_api.lock`).

**Rationale:**
- Multiple Uvicorn workers would each open separate SQLite connections, causing lock contention and potential corruption.
- A single-writer FastAPI process handles all writes; clients POST via HTTP.
- File lock prevents accidental double-start.

**Trade-offs:** Single worker limits throughput. Mitigated by SQLite's fast write path (<50ms per operation) and batch endpoint for bulk inserts.

## ADR-003: Dual-Write Storage (NDJSON + SQLite)

**Date:** 2025-12-10
**Status:** Accepted

**Context:** Agent telemetry must survive crashes and be queryable.

**Decision:** Write every event to both NDJSON files (append-only) and SQLite (structured queries).

**Rationale:**
- NDJSON is crash-resilient (append-only, no corruption risk).
- SQLite enables structured queries and aggregation.
- If SQLite corrupts, NDJSON provides complete replay source.

**Trade-offs:** Double write cost (~10ms overhead). Acceptable for telemetry workloads.
