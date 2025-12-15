# Docs Refactor Report

## Summary of changes
- Created new IA layout with landing page (`docs/README.md`) and persona-based quickstarts.
- Moved/archived historical docs (`plans/`, `reports/`, `.pytest_cache/README.md`, legacy extraction doc) into `docs/_archive/`.
- Migrated and renamed core docs into new buckets (overview/product-purpose, guides, reference, operations, development).
- Authored canonical references: `reference/config.md`, `reference/cli.md`, `reference/file-contracts.md`, plus `reference/api.md` and `reference/schema.md`.
- Added new scenario guides (instrumentation, backup-and-restore, recovery-from-ndjson, monitoring-and-health) and contributor/operator quickstarts.
- Updated root `README.md` to point to docs home.

## Docs coverage checklist (mapped to traceability features)
- Run lifecycle / API surface → `guides/instrumentation.md`, `reference/api.md`
- NDJSON writer + locking → `reference/file-contracts.md`
- SQLite writer + WAL/retry → `reference/file-contracts.md`, `reference/schema.md`
- Schema v3 fields/indexes → `reference/schema.md`, `reference/file-contracts.md`
- Config resolution/validation → `reference/config.md`
- Storage/bootstrap scripts → `getting-started/quickstart-operator.md`, `reference/cli.md`
- Backup/restore → `guides/backup-and-restore.md`, `reference/cli.md`
- NDJSON recovery → `guides/recovery-from-ndjson.md`
- Health/monitoring → `guides/monitoring-and-health.md`
- API posting behavior → `reference/api.md`
- Extraction → `guides/file-extraction.md`, `reference/cli.md`
- Quality gates → `guides/quality-gates.md`, `reference/cli.md`
- Analysis verification → `guides/analysis-verification.md`, `reference/cli.md`
- Testing harness/markers → `development/testing.md`, `reference/cli.md`

## Verification commands run
- `rg "docs/" docs -g"*.md" --glob "!docs/_archive/**" --glob "!docs/_audit/**"` (check legacy links)
- `Get-Content` on scripts for argparse sections to document flags
- Directory moves via `Move-Item` into new structure and `_archive`

## Known gaps
- `scripts/recover_database.py` rebuilds schema v2; docs call this out in `guides/recovery-from-ndjson.md` but operational follow-up may be needed after recovery to align to v3.
- `scripts/measure_performance.py` uses `RunContext.update_metrics` (nonexistent); documented in `reference/cli.md` note—needs code fix later.
- Legacy example file names remain in some guide examples (now labeled as illustrative).
- Architecture diagram in `architecture/system.md` still contains mojibake/needs cleanup (content retained for history).
