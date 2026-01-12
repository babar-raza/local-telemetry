# Feature Spec: HTTP Get Repository URL

**Feature ID:** `http.repo.url.get`
**Category:** HTTP API
**Route:** `GET /api/v1/runs/{event_id}/repo-url`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-12

---

## Summary

Generate a normalized repository browse URL for a telemetry run by converting the stored git_repo field into a clean HTTPS format suitable for browsers.

**Key Features:**
- Converts SSH URLs to HTTPS format
- Removes .git extension and trailing slashes
- Returns null if git_repo is missing
- Platform-agnostic (works with any git hosting)
- Validates run existence before URL generation

**Common Use Cases:**
- Dashboard "View Repository" links
- CLI tools displaying repo URLs
- Slack/email notifications with repo links
- API clients needing repository references

---

## Entry Points

### Route Registration
```python
@app.get("/api/v1/runs/{event_id}/repo-url")
async def get_repo_url(
    event_id: str,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
```

**Evidence:** `telemetry_service.py:1267-1272`

### Handler Function
**File:** `telemetry_service.py:1267-1316`
**Function:** `get_repo_url()`

---

## Inputs/Outputs

### HTTP Request

**Method:** GET
**Path:** `/api/v1/runs/{event_id}/repo-url`
**Query Parameters:** None

**Path Parameters:**
- `event_id` (string, required) - Unique event ID of the run

**Example:**
```
GET /api/v1/runs/evt_123/repo-url
```

---

### HTTP Response

#### Success Response - Repository URL Available (200 OK)

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:**
```json
{
  "repo_url": "https://github.com/owner/repo"
}
```

**Fields:**
- `repo_url` (string) - Normalized HTTPS URL to repository root

**URL Normalization:**
- SSH format → HTTPS format
- `.git` extension removed
- Trailing slashes removed

**Evidence:** `src/telemetry/url_builder.py:116-142` (build_repo_url function)

**Evidence:** `telemetry_service.py:1306-1307` (build_repo_url call)

---

#### Success Response - No Git Repository (200 OK)

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:**
```json
{
  "repo_url": null
}
```

**Trigger:** `git_repo` is NULL in database

**Evidence:** `telemetry_service.py:1303-1304`

**Rationale:** Not an error - run may not have repository association.

---

## Processing Logic

### Step 1: Fetch Git Repository URL

**SQL Query:**
```sql
SELECT git_repo FROM agent_runs WHERE event_id = ?
```

**Evidence:** `telemetry_service.py:1289-1293`

**Extracted Field:**
- `git_repo` - Repository URL (HTTPS or SSH format, may be NULL)

---

### Step 2: Validate Run Exists

**Check:**
```python
if not row:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Run not found: {event_id}"
    )
```

**Evidence:** `telemetry_service.py:1295-1299`

**Response:** 404 if run doesn't exist

---

### Step 3: Check Git Repository Availability

**Check:**
```python
if not repo_url:
    return {"repo_url": None}
```

**Evidence:** `telemetry_service.py:1303-1304`

**Behavior:** Return null if git_repo is NULL (not an error)

---

### Step 4: Normalize Repository URL

**Function Call:**
```python
normalized_url = build_repo_url(repo_url)
```

**Evidence:** `telemetry_service.py:1306`

**Normalization Logic:**

1. **Strip Whitespace** (`src/telemetry/url_builder.py:92`)
   - Remove leading/trailing spaces

2. **Convert SSH to HTTPS** (`src/telemetry/url_builder.py:95-103`)
   - Pattern: `git@host:path` → `https://host/path`
   - Example: `git@github.com:owner/repo.git` → `https://github.com/owner/repo.git`

3. **Remove .git Extension** (`src/telemetry/url_builder.py:106-107`)
   - `https://github.com/owner/repo.git` → `https://github.com/owner/repo`

4. **Remove Trailing Slashes** (`src/telemetry/url_builder.py:110-111`)
   - `https://github.com/owner/repo/` → `https://github.com/owner/repo`

5. **Validate Result** (`src/telemetry/url_builder.py:139-140`)
   - Must start with `https://`
   - Return None if invalid

**Evidence:** `src/telemetry/url_builder.py:116-142`

---

### Step 5: Return Response

**Response:**
```python
return {"repo_url": normalized_url}
```

**Evidence:** `telemetry_service.py:1307`

**Note:** `normalized_url` may be None if URL is malformed or doesn't start with https://.

---

## URL Transformation Examples

### Example 1: GitHub SSH URL

**Input (Database):**
```
git_repo = "git@github.com:anthropics/claude-code.git"
```

**Output (API Response):**
```json
{
  "repo_url": "https://github.com/anthropics/claude-code"
}
```

**Transformations:**
1. `git@github.com:` → `https://github.com/`
2. Remove `.git` extension
3. No trailing slash to remove

**Evidence:** `src/telemetry/url_builder.py:95-111`

---

### Example 2: GitLab HTTPS URL with .git

**Input (Database):**
```
git_repo = "https://gitlab.com/myorg/myproject.git"
```

**Output (API Response):**
```json
{
  "repo_url": "https://gitlab.com/myorg/myproject"
}
```

**Transformations:**
1. Already HTTPS (no conversion)
2. Remove `.git` extension
3. No trailing slash to remove

---

### Example 3: Bitbucket with Trailing Slash

**Input (Database):**
```
git_repo = "https://bitbucket.org/team/project/"
```

**Output (API Response):**
```json
{
  "repo_url": "https://bitbucket.org/team/project"
}
```

**Transformations:**
1. Already HTTPS (no conversion)
2. No `.git` to remove
3. Remove trailing slash

---

### Example 4: Self-Hosted GitLab SSH

**Input (Database):**
```
git_repo = "git@gitlab.mycompany.com:engineering/platform.git"
```

**Output (API Response):**
```json
{
  "repo_url": "https://gitlab.mycompany.com/engineering/platform"
}
```

**Transformations:**
1. `git@gitlab.mycompany.com:` → `https://gitlab.mycompany.com/`
2. Remove `.git` extension

**Note:** Works with ANY git hosting platform, not just GitHub/GitLab/Bitbucket.

---

## Invariants

### INV-1: Run Must Exist

**Statement:** Endpoint MUST return 404 if event_id doesn't exist in database.

**Enforcement:** SELECT query before URL building

**Evidence:** `telemetry_service.py:1295-1299`

---

### INV-2: Null Safety

**Statement:** Missing git_repo MUST return null, not error.

**Enforcement:** Explicit null check before URL normalization

**Evidence:** `telemetry_service.py:1303-1304`

**Rationale:** Run may exist without repository association (not an error state).

---

### INV-3: HTTPS Format Only

**Statement:** All returned URLs MUST be HTTPS format (never SSH).

**Enforcement:** normalize_repo_url() converts SSH to HTTPS

**Evidence:** `src/telemetry/url_builder.py:95-103`

**Rationale:** Browser-clickable URLs must be HTTPS.

---

### INV-4: Clean URL Format

**Statement:** URLs MUST NOT have .git extension or trailing slashes.

**Enforcement:** Explicit removal in normalize_repo_url()

**Evidence:** `src/telemetry/url_builder.py:106-111`

**Rationale:** Consistent, clean URLs for display and linking.

---

## Errors and Edge Cases

### Error: Run Not Found (404)

**Trigger:** event_id doesn't exist in database

**Response:**
- **Status:** 404 Not Found
- **Body:** `{"detail": "Run not found: <event_id>"}`

**Evidence:** `telemetry_service.py:1295-1299`

**Example:**
```
GET /api/v1/runs/nonexistent/repo-url
→ 404 {"detail": "Run not found: nonexistent"}
```

---

### Error: Database Failure (500)

**Trigger:** SQLite error during query execution

**Response:**
- **Status:** 500 Internal Server Error
- **Body:** `{"detail": "Failed to get repo URL: <error>"}`
- **Log:** `logger.error(f"[ERROR] Failed to get repo URL for {event_id}: {e}")`

**Evidence:** `telemetry_service.py:1309-1316`

---

### Error: Rate Limit Exceeded (429)

**Trigger:** Client exceeds `TELEMETRY_RATE_LIMIT_RPM` (if enabled)

**Response:**
- **Status:** 429 Too Many Requests
- **Headers:** `Retry-After: 60`
- **Body:** `{"detail": "Rate limit exceeded. Max <rpm> requests per minute."}`

**Evidence:** `telemetry_service.py:325-335` (check_rate_limit dependency)

---

### Error: Authentication Failed (401)

**Trigger:** Invalid/missing Bearer token when `TELEMETRY_API_AUTH_ENABLED=true`

**Response:**
- **Status:** 401 Unauthorized
- **Headers:** `WWW-Authenticate: Bearer`
- **Body:** `{"detail": "Invalid or missing authentication token"}`

**Evidence:** `telemetry_service.py:195-243` (verify_auth dependency)

---

### Edge Case: No Git Repository (200 OK with null)

**Trigger:** Run exists but `git_repo` is NULL

**Response:**
```json
{
  "repo_url": null
}
```

**Status:** 200 OK (not an error)

**Evidence:** `telemetry_service.py:1303-1304`

**Use Case:** Run not associated with any repository.

---

### Edge Case: Malformed Repository URL (200 OK with null)

**Trigger:** git_repo is malformed or doesn't result in valid HTTPS URL

**Examples:**
- `"not-a-url"`
- `"ftp://invalid.com/repo"`
- `""`

**Response:**
```json
{
  "repo_url": null
}
```

**Status:** 200 OK (graceful failure)

**Evidence:** `src/telemetry/url_builder.py:139-140` (validation check)

**Rationale:** Don't crash on bad data - return null.

---

### Edge Case: Already Normalized URL

**Trigger:** git_repo is already in clean HTTPS format

**Example:**
```
git_repo = "https://github.com/owner/repo"
```

**Response:**
```json
{
  "repo_url": "https://github.com/owner/repo"
}
```

**Status:** 200 OK

**Behavior:** URL passes through unchanged (already normalized).

**Evidence:** `src/telemetry/url_builder.py:92-111` (normalization is idempotent)

---

## Side Effects

### Database Operations

**Table:** `agent_runs`
**Operation:** SELECT (read-only, git_repo field only)

**Query:**
```sql
SELECT git_repo FROM agent_runs WHERE event_id = ?
```

**Evidence:** `telemetry_service.py:1289-1292`

**Performance:** Fast lookup via event_id UNIQUE index

---

### Logging

**Error Log:**
```python
logger.error(f"[ERROR] Failed to get repo URL for {event_id}: {e}")
```

**Evidence:** `telemetry_service.py:1312`

**Trigger:** Database error or unexpected exception

---

## Use Cases

### Use Case 1: Dashboard "View Repository" Link

**Scenario:** Dashboard displays list of runs. User clicks "View Repository" to browse code.

**Flow:**
1. Dashboard fetches runs: `GET /api/v1/runs?limit=10`
2. For each run with git_repo, display "View Repository" button
3. On click: `GET /api/v1/runs/{event_id}/repo-url`
4. Response: `{"repo_url": "https://github.com/owner/repo"}`
5. Open URL in new tab

**Dashboard Code:**
```python
def get_repo_link(event_id: str) -> Optional[str]:
    response = requests.get(f"{api_url}/api/v1/runs/{event_id}/repo-url")
    response.raise_for_status()
    return response.json().get('repo_url')

# Usage
repo_url = get_repo_link("evt_123")
if repo_url:
    print(f"Repository: {repo_url}")
```

---

### Use Case 2: CLI Tool Displaying Repository URLs

**Scenario:** CLI tool shows recent agent runs with repository links.

**Flow:**
```bash
$ telemetry-cli recent --limit 5

Recent Runs:
1. evt_001 - hugo-translator - success
   Repository: https://github.com/myorg/hugo-translator

2. evt_002 - seo-analyzer - failure
   Repository: https://gitlab.com/myorg/seo-tools
```

**CLI Code:**
```python
for run in recent_runs:
    event_id = run['event_id']
    repo_url_resp = requests.get(f"{api_url}/api/v1/runs/{event_id}/repo-url").json()
    repo_url = repo_url_resp.get('repo_url')

    if repo_url:
        print(f"   Repository: {repo_url}")
```

---

### Use Case 3: Slack Notification with Repository Link

**Scenario:** Agent run fails, send Slack notification with repository link for debugging.

**Flow:**
1. Agent run fails
2. Notification service: `GET /api/v1/runs/{event_id}/repo-url`
3. Build Slack message:
   ```
   Agent run failed! :x:
   Error: Connection timeout
   Repository: https://github.com/owner/repo
   ```

**Notification Code:**
```python
repo_url_resp = requests.get(f"{api_url}/api/v1/runs/{event_id}/repo-url").json()
repo_url = repo_url_resp.get('repo_url')

slack_message = f"Agent run failed!\nError: {error_summary}\n"
if repo_url:
    slack_message += f"Repository: {repo_url}"

send_slack_message(slack_message)
```

---

### Use Case 4: Display Repository Info Without Commit

**Scenario:** Run is associated with repository but not yet with specific commit.

**Flow:**
1. Check commit URL: `GET /api/v1/runs/{event_id}/commit-url` → `{"commit_url": null}`
2. Fallback to repo URL: `GET /api/v1/runs/{event_id}/repo-url` → `{"repo_url": "https://..."}`
3. Display: "Repository: https://github.com/owner/repo (no commit associated)"

**Rationale:** Provides useful context even without commit hash.

---

## Performance

### Expected Latency

| Operation | Expected Time |
|-----------|---------------|
| SELECT git_repo | < 5ms |
| URL normalization | < 1ms (in-memory) |
| Total latency | < 10ms |

**Evidence:** Inferred from indexed lookup and simple string operations

---

### Indexes Used

**event_id Lookup:** UNIQUE constraint provides index for fast SELECT

**Evidence:** Schema v6 (event_id UNIQUE)

---

## Comparison with commit-url Endpoint

| Feature | `/repo-url` | `/commit-url` |
|---------|-------------|---------------|
| **SQL Query** | `SELECT git_repo` | `SELECT git_repo, git_commit_hash` |
| **Required Fields** | git_repo only | git_repo AND git_commit_hash |
| **URL Builder** | `build_repo_url()` | `build_commit_url()` |
| **Platform Detection** | Not needed (works with any git host) | Required (GitHub/GitLab/Bitbucket only) |
| **Output Format** | Repository root URL | Platform-specific commit URL |
| **Use Case** | View repository home | View specific commit changes |

**Evidence:** Compare `telemetry_service.py:1267-1316` with `1215-1264`

---

## Dependencies

### FastAPI Dependencies

**verify_auth:**
- Function: Bearer token authentication
- File: `telemetry_service.py:195-243`
- Skipped if: `TELEMETRY_API_AUTH_ENABLED=false`

**check_rate_limit:**
- Function: IP-based rate limiting
- File: `telemetry_service.py:298-337`
- Skipped if: `TELEMETRY_RATE_LIMIT_ENABLED=false`

**Evidence:** `telemetry_service.py:1270-1271`

---

### Database Connection

**Context Manager:** `get_db()`
- Evidence: `telemetry_service.py:341-361`
- Acquires SQLite connection
- Auto-closes on exit

**Used in:** `telemetry_service.py:1288`

---

### URL Builder Module

**build_repo_url() function:**
- Module: `src/telemetry/url_builder.py:116-142`
- Purpose: Normalize repository URLs to clean HTTPS format
- Evidence: `telemetry_service.py:1306`

**normalize_repo_url() function:**
- Module: `src/telemetry/url_builder.py:70-114`
- Purpose: Convert SSH to HTTPS, remove .git extension
- Called by: `build_repo_url()`

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:1267-1316`
- **SQL query:** `telemetry_service.py:1289-1292`
- **Run existence check:** `telemetry_service.py:1295-1299`
- **Null check:** `telemetry_service.py:1303-1304`
- **URL normalization:** `telemetry_service.py:1306-1307`
- **Error handling:** `telemetry_service.py:1309-1316`

### URL Builder Module
- **build_repo_url:** `src/telemetry/url_builder.py:116-142`
- **normalize_repo_url:** `src/telemetry/url_builder.py:70-114`
- **SSH conversion:** `src/telemetry/url_builder.py:95-103`
- **.git removal:** `src/telemetry/url_builder.py:106-107`
- **Trailing slash removal:** `src/telemetry/url_builder.py:110-111`
- **Validation:** `src/telemetry/url_builder.py:139-140`

### Dependencies
- **Authentication:** `telemetry_service.py:195-243`
- **Rate limiting:** `telemetry_service.py:298-337`
- **Database context:** `telemetry_service.py:341-361`

---

## Verification Status

**Status:** VERIFIED

**Verification Method:**
- Direct file read of handler implementation
- Direct file read of url_builder.py module
- SQL query confirmed
- URL normalization logic verified

**Confidence:** HIGH

**Inferred Behaviors:**
- Dashboard integration (use case inferred from API design)
- Latency estimates (based on indexed lookup)
- Platform-agnostic support (no platform detection in code)

**Evidence Strength:**
- Handler logic: STRONG (direct code read)
- URL normalization: STRONG (direct code read from url_builder.py)
- Database operations: STRONG (explicit SQL)
- Performance: MEDIUM (inferred from configuration)
