# Product Purpose

Local Telemetry is a Python library for tracking agent runs with local-first storage and optional API posting.

## What it does
- Records run lifecycle (start/end, status, metrics) and checkpoint events.
- Dual writes: NDJSON append-only logs + SQLite for structured queries.
- Optional API posting with retries; never crashes the agent on telemetry failures.
- Cross-platform with path auto-detection and lock-aware writes.

## Core components
- Library: `TelemetryClient`, `NDJSONWriter`, `DatabaseWriter`, `APIClient` (`src/telemetry/*`).
- Storage: `{base}/raw` NDJSON, `{base}/db/telemetry.sqlite` (WAL), backups in `{base}/backups`.
- Scripts: setup, backup/recovery, health, extraction, quality gates, analysis verification (`scripts/`).

## Learn more
- Quickstarts: `../getting-started/`
- Instrumentation guide: `../guides/instrumentation.md`
- Configuration reference: `../reference/config.md`
- CLI reference: `../reference/cli.md`
- File and schema contracts: `../reference/file-contracts.md`, `../reference/schema.md`
- Architecture: `../architecture/system.md`
