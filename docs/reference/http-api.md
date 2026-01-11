# Telemetry API HTTP Reference

## Service
- Name: local-telemetry-api
- Version: 2.1.0
- Container: local-telemetry-api
- Image: local-telemetry-api:2.1.0
- Base URL: http://localhost:8765
- OpenAPI (FastAPI default): /openapi.json
- Docs UI (FastAPI default): /docs, /redoc

## Authentication
- Optional and disabled by default.
- Enable with `TELEMETRY_API_AUTH_ENABLED=true`.
- When enabled, send `Authorization: Bearer <token>` where `<token>` matches `TELEMETRY_API_AUTH_TOKEN`.
- Missing/invalid auth returns `401` with `WWW-Authenticate: Bearer`.

## Rate Limiting
- Optional and disabled by default.
- Enable with `TELEMETRY_RATE_LIMIT_ENABLED=true`.
- Limit configured by `TELEMETRY_RATE_LIMIT_RPM` (requests per minute per client IP).
- Exceeded limit returns `429` with headers:
  - `Retry-After: 60`
  - `X-RateLimit-Limit: <rpm>`
  - `X-RateLimit-Remaining: 0`

## Common Headers
- `Content-Type: application/json` for all request bodies.
- `Authorization: Bearer <token>` required only when auth is enabled on endpoints that enforce auth.

## Error Format
- Most errors use FastAPI standard shape:
  - `{"detail": "<message>"}`
- Validation errors (422) use:
  - `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`

## Schemas (Examples)

### TelemetryRun (request body for POST /api/v1/runs and /api/v1/runs/batch)
Required fields: `event_id`, `run_id`, `agent_name`, `job_type`, `start_time`

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_id": "2026-01-05T18:40:27Z-seo-intelligence-abc123",
  "created_at": "2026-01-05T18:40:27.000000+00:00",
  "start_time": "2026-01-05T18:40:27.000000+00:00",
  "end_time": null,
  "agent_name": "seo_intelligence.insight_engine",
  "job_type": "insight_generation",
  "status": "running",
  "product": "seo-intelligence",
  "product_family": "content",
  "platform": "web",
  "subdomain": "docs",
  "website": "example.com",
  "website_section": "blog",
  "item_name": "how-to-optimize",
  "items_discovered": 10,
  "items_succeeded": 8,
  "items_failed": 2,
  "items_skipped": 0,
  "duration_ms": 0,
  "input_summary": "Indexed blog posts",
  "output_summary": "Generated insights",
  "source_ref": "s3://bucket/input.csv",
  "target_ref": "s3://bucket/output.json",
  "error_summary": null,
  "error_details": null,
  "git_repo": "https://github.com/example/repo",
  "git_branch": "main",
  "git_commit_hash": "abc1234567890",
  "git_run_tag": "nightly",
  "git_commit_source": "llm",
  "git_commit_author": "Claude <noreply@anthropic.com>",
  "git_commit_timestamp": "2026-01-05T18:40:27Z",
  "host": "worker-01",
  "environment": "prod",
  "trigger_type": "scheduler",
  "metrics_json": {"token_count": 1234},
  "context_json": {"pipeline": "seo-ingest"},
  "api_posted": false,
  "api_posted_at": null,
  "api_retry_count": 0,
  "insight_id": "insight-001",
  "parent_run_id": "run-parent-123"
}
```

Notes:
- `duration_ms` accepts `null` and is converted to `0`.
- `git_commit_source` must be one of `manual`, `llm`, `ci` (422 if invalid).
- `git_commit_source`, `git_commit_author`, `git_commit_timestamp` are accepted on POST but are only persisted when updated via PATCH or associate-commit.

### RunUpdate (request body for PATCH /api/v1/runs/{event_id})
All fields optional; at least one non-null field required.

```json
{
  "status": "success",
  "end_time": "2026-01-05T18:45:10.000000+00:00",
  "duration_ms": 275000,
  "error_summary": null,
  "error_details": null,
  "output_summary": "Completed successfully",
  "items_succeeded": 10,
  "items_failed": 0,
  "items_skipped": 0,
  "metrics_json": {"token_count": 2500},
  "context_json": {"stage": "final"},
  "git_commit_source": "llm",
  "git_commit_author": "Claude <noreply@anthropic.com>",
  "git_commit_timestamp": "2026-01-05T18:45:10Z"
}
```

Notes:
- `status` must be one of `running`, `success`, `failure`, `partial`, `timeout`, `cancelled`.
- `duration_ms`, `items_succeeded`, `items_failed`, `items_skipped` must be non-negative.
- Fields explicitly set to `null` are ignored (cannot be cleared to null).

### CommitAssociation (request body for POST /api/v1/runs/{event_id}/associate-commit)
```json
{
  "commit_hash": "abc1234567890abcdef",
  "commit_source": "llm",
  "commit_author": "Claude Code <noreply@anthropic.com>",
  "commit_timestamp": "2026-01-02T10:00:00Z"
}
```

Notes:
- `commit_hash` length 7-40 characters.
- `commit_source` must be one of `manual`, `llm`, `ci`.

### RunRecord (response item for GET /api/v1/runs)
```json
{
  "id": 123,
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_id": "2026-01-05T18:40:27Z-seo-intelligence-abc123",
  "created_at": "2026-01-05T18:40:27.000000+00:00",
  "start_time": "2026-01-05T18:40:27.000000+00:00",
  "end_time": "2026-01-05T18:45:10.000000+00:00",
  "agent_name": "seo_intelligence.insight_engine",
  "job_type": "insight_generation",
  "status": "success",
  "product": "seo-intelligence",
  "product_family": "content",
  "platform": "web",
  "subdomain": "docs",
  "website": "example.com",
  "website_section": "blog",
  "item_name": "how-to-optimize",
  "items_discovered": 10,
  "items_succeeded": 10,
  "items_failed": 0,
  "items_skipped": 0,
  "duration_ms": 275000,
  "input_summary": "Indexed blog posts",
  "output_summary": "Generated insights",
  "source_ref": "s3://bucket/input.csv",
  "target_ref": "s3://bucket/output.json",
  "error_summary": null,
  "error_details": null,
  "git_repo": "https://github.com/example/repo",
  "git_branch": "main",
  "git_commit_hash": "abc1234567890",
  "git_run_tag": "nightly",
  "git_commit_source": "llm",
  "git_commit_author": "Claude <noreply@anthropic.com>",
  "git_commit_timestamp": "2026-01-05T18:45:10Z",
  "host": "worker-01",
  "environment": "prod",
  "trigger_type": "scheduler",
  "metrics_json": {"token_count": 2500},
  "context_json": {"stage": "final"},
  "api_posted": false,
  "api_posted_at": null,
  "api_retry_count": 0,
  "insight_id": "insight-001",
  "parent_run_id": "run-parent-123",
  "commit_url": "https://github.com/example/repo/commit/abc1234567890",
  "repo_url": "https://github.com/example/repo"
}
```

Notes:
- `metrics_json` and `context_json` are parsed from stored JSON strings.
- If JSON parsing fails, the original string is preserved and an additional field is added:
  - `metrics_json_parse_error` or `context_json_parse_error`
- `commit_url` and `repo_url` are derived fields.

### BatchResponse (response body for POST /api/v1/runs/batch)
```json
{
  "inserted": 3,
  "duplicates": 1,
  "errors": [],
  "total": 4
}
```

### HealthResponse (GET /health)
```json
{
  "status": "ok",
  "version": "2.1.0",
  "db_path": "/data/telemetry.sqlite",
  "journal_mode": "DELETE",
  "synchronous": "FULL"
}
```

### MetricsResponse (GET /metrics)
```json
{
  "total_runs": 12345,
  "agents": {"seo_intelligence.insight_engine": 8400},
  "recent_24h": 120,
  "performance": {
    "db_path": "/data/telemetry.sqlite",
    "journal_mode": "DELETE"
  }
}
```

### MetadataResponse (GET /api/v1/metadata)
```json
{
  "agent_names": ["seo_intelligence.insight_engine", "seo_intelligence.scheduler"],
  "job_types": ["insight_generation", "scheduling"],
  "counts": {"agent_names": 2, "job_types": 2}
}
```

## Endpoints

### GET /health
Health check for the service.

Auth: not required
Rate limit: not enforced

Status codes:
- 200 OK: returns HealthResponse

Example:
```bash
curl http://localhost:8765/health
```

### GET /metrics
Returns system-level metrics (counts by agent, total runs, recent runs).

Auth: not required
Rate limit: not enforced

Status codes:
- 200 OK: returns MetricsResponse
- 500 Internal Server Error: database errors

Example:
```bash
curl http://localhost:8765/metrics
```

### GET /api/v1/metadata
Returns distinct agent names and job types seen in the database.

Auth: not required
Rate limit: enforced if enabled

Status codes:
- 200 OK: returns MetadataResponse
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: database errors

Example:
```bash
curl http://localhost:8765/api/v1/metadata
```

### POST /api/v1/runs
Create a single telemetry run (idempotent by `event_id`).

Auth: required if enabled
Rate limit: enforced if enabled

Request body: TelemetryRun

Status codes:
- 201 Created: new run created
- 200 OK: duplicate `event_id` (idempotent)
- 400 Bad Request: database integrity error (e.g., constraint failure)
- 401 Unauthorized: auth required/invalid
- 422 Unprocessable Entity: validation error
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: unexpected database error

Example:
```bash
curl -X POST http://localhost:8765/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{"event_id":"550e8400-e29b-41d4-a716-446655440000","run_id":"2026-01-05T18:40:27Z-seo-intelligence-abc123","agent_name":"seo_intelligence.insight_engine","job_type":"insight_generation","start_time":"2026-01-05T18:40:27Z","status":"running"}'
```

### POST /api/v1/runs/batch
Create multiple telemetry runs in one request.

Auth: required if enabled
Rate limit: enforced if enabled

Request body: JSON array of TelemetryRun (no wrapper object)

Status codes:
- 200 OK: returns BatchResponse
- 401 Unauthorized: auth required/invalid
- 422 Unprocessable Entity: validation error
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: unexpected database error

Example:
```bash
curl -X POST http://localhost:8765/api/v1/runs/batch \
  -H "Content-Type: application/json" \
  -d '[{"event_id":"11111111-1111-1111-1111-111111111111","run_id":"run-1","agent_name":"agent-a","job_type":"job-a","start_time":"2026-01-05T18:40:27Z"},{"event_id":"22222222-2222-2222-2222-222222222222","run_id":"run-2","agent_name":"agent-b","job_type":"job-b","start_time":"2026-01-05T18:41:00Z"}]'
```

### GET /api/v1/runs
Query telemetry runs with filters and pagination.

Auth: not required
Rate limit: enforced if enabled

Query parameters:
- `agent_name` (string, optional): exact match
- `status` (string, optional): one of `running`, `success`, `failure`, `partial`, `timeout`, `cancelled`
- `job_type` (string, optional): exact match
- `created_before` (string, optional): ISO8601 timestamp
- `created_after` (string, optional): ISO8601 timestamp
- `start_time_from` (string, optional): ISO8601 timestamp
- `start_time_to` (string, optional): ISO8601 timestamp
- `limit` (int, optional): 1-1000, default 100
- `offset` (int, optional): >= 0, default 0

Status codes:
- 200 OK: returns array of RunRecord
- 400 Bad Request: invalid status or timestamp format
- 422 Unprocessable Entity: invalid limit/offset
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: database errors

Example:
```bash
curl "http://localhost:8765/api/v1/runs?agent_name=seo_intelligence.scheduler&status=running&limit=50"
```

### PATCH /api/v1/runs/{event_id}
Update selected fields of an existing run.

Auth: required if enabled
Rate limit: enforced if enabled

Path parameters:
- `event_id` (string, required): event identifier

Request body: RunUpdate

Status codes:
- 200 OK: update applied
- 400 Bad Request: no valid fields to update
- 401 Unauthorized: auth required/invalid
- 404 Not Found: event_id not found
- 422 Unprocessable Entity: validation error
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: database errors

Example:
```bash
curl -X PATCH http://localhost:8765/api/v1/runs/550e8400-e29b-41d4-a716-446655440000 \
  -H "Content-Type: application/json" \
  -d '{"status":"success","end_time":"2026-01-05T18:45:10Z","duration_ms":275000}'
```

### GET /api/v1/runs/{event_id}/commit-url
Returns a normalized commit URL for the run (GitHub/GitLab/Bitbucket).

Auth: required if enabled
Rate limit: enforced if enabled

Path parameters:
- `event_id` (string, required): event identifier

Status codes:
- 200 OK: returns `{"commit_url": "<url or null>"}`
- 401 Unauthorized: auth required/invalid
- 404 Not Found: event_id not found
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: database errors

Example:
```bash
curl http://localhost:8765/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/commit-url
```

### GET /api/v1/runs/{event_id}/repo-url
Returns a normalized repository URL for the run.

Auth: required if enabled
Rate limit: enforced if enabled

Path parameters:
- `event_id` (string, required): event identifier

Status codes:
- 200 OK: returns `{"repo_url": "<url or null>"}`
- 401 Unauthorized: auth required/invalid
- 404 Not Found: event_id not found
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: database errors

Example:
```bash
curl http://localhost:8765/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/repo-url
```

### POST /api/v1/runs/{event_id}/associate-commit
Associate a git commit with an existing run.

Auth: required if enabled
Rate limit: enforced if enabled

Path parameters:
- `event_id` (string, required): event identifier

Request body: CommitAssociation

Status codes:
- 200 OK: association saved
- 401 Unauthorized: auth required/invalid
- 404 Not Found: event_id not found
- 422 Unprocessable Entity: validation error
- 429 Too Many Requests: rate limit exceeded
- 500 Internal Server Error: database errors

Example:
```bash
curl -X POST http://localhost:8765/api/v1/runs/550e8400-e29b-41d4-a716-446655440000/associate-commit \
  -H "Content-Type: application/json" \
  -d '{"commit_hash":"abc1234567890abcdef","commit_source":"llm","commit_author":"Claude Code <noreply@anthropic.com>","commit_timestamp":"2026-01-02T10:00:00Z"}'
```
