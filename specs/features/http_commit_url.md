# Feature Spec: HTTP Get Commit URL

**Feature ID:** `http.commit.url.get`
**Category:** HTTP API
**Route:** `GET /api/v1/runs/{event_id}/commit-url`
**Status:** VERIFIED (evidence-backed)
**Version:** 2.1.0
**Last Updated:** 2026-01-12

---

## Summary

Generate a clickable commit URL for a telemetry run by combining git_repo and git_commit_hash into a platform-specific browse URL (GitHub, GitLab, or Bitbucket).

**Key Features:**
- Auto-detects platform (GitHub, GitLab, Bitbucket)
- Converts SSH URLs to HTTPS format
- Returns null if git metadata is incomplete
- Handles self-hosted platforms gracefully (returns null)
- Validates run existence before URL generation

**Common Use Cases:**
- Dashboard "View Commit" links
- CLI tools displaying commit URLs
- Slack/email notifications with commit links
- API clients needing commit references

---

## Entry Points

### Route Registration
```python
@app.get("/api/v1/runs/{event_id}/commit-url")
async def get_commit_url(
    event_id: str,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
```

**Evidence:** `telemetry_service.py:1215-1220`

### Handler Function
**File:** `telemetry_service.py:1215-1264`
**Function:** `get_commit_url()`

---

## Inputs/Outputs

### HTTP Request

**Method:** GET
**Path:** `/api/v1/runs/{event_id}/commit-url`
**Query Parameters:** None

**Path Parameters:**
- `event_id` (string, required) - Unique event ID of the run

**Example:**
```
GET /api/v1/runs/evt_123/commit-url
```

---

### HTTP Response

#### Success Response - Commit URL Available (200 OK)

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:**
```json
{
  "commit_url": "https://github.com/owner/repo/commit/a1b2c3d4e5f6789"
}
```

**Fields:**
- `commit_url` (string) - Full HTTPS URL to view commit on hosting platform

**Platform-Specific Formats:**

| Platform | URL Format |
|----------|------------|
| GitHub | `https://github.com/{owner}/{repo}/commit/{hash}` |
| GitLab | `https://gitlab.com/{owner}/{repo}/-/commit/{hash}` |
| Bitbucket | `https://bitbucket.org/{owner}/{repo}/commits/{hash}` |

**Evidence:** `src/telemetry/url_builder.py:185-190` (platform-specific formatting)

**Evidence:** `telemetry_service.py:1254-1255` (build_commit_url call)

---

#### Success Response - Git Data Incomplete (200 OK)

**Status:** 200 OK
**Content-Type:** `application/json`

**Body:**
```json
{
  "commit_url": null
}
```

**Trigger:** Either `git_repo` or `git_commit_hash` is NULL in database

**Evidence:** `telemetry_service.py:1251-1252`

**Rationale:** Not an error - run may not have commit association yet.

---

## Processing Logic

### Step 1: Fetch Git Metadata

**SQL Query:**
```sql
SELECT git_repo, git_commit_hash FROM agent_runs WHERE event_id = ?
```

**Evidence:** `telemetry_service.py:1237-1241`

**Extracted Fields:**
- `git_repo` - Repository URL (HTTPS or SSH format)
- `git_commit_hash` - Commit SHA (7-40 characters)

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

**Evidence:** `telemetry_service.py:1243-1247`

**Response:** 404 if run doesn't exist

---

### Step 3: Check Git Data Completeness

**Check:**
```python
if not repo_url or not commit_hash:
    return {"commit_url": None}
```

**Evidence:** `telemetry_service.py:1251-1252`

**Behavior:** Return null if either field is missing (not an error)

---

### Step 4: Build Commit URL

**Function Call:**
```python
commit_url = build_commit_url(repo_url, commit_hash)
```

**Evidence:** `telemetry_service.py:1254`

**URL Builder Logic:**

1. **Detect Platform** (`src/telemetry/url_builder.py:172`)
   - Check for "github.com" → "github"
   - Check for "gitlab.com" → "gitlab"
   - Check for "bitbucket.org" → "bitbucket"
   - Unknown → None

2. **Normalize Repository URL** (`src/telemetry/url_builder.py:179`)
   - Convert SSH to HTTPS: `git@github.com:owner/repo.git` → `https://github.com/owner/repo`
   - Remove `.git` extension
   - Remove trailing slashes

3. **Build Platform-Specific URL** (`src/telemetry/url_builder.py:185-190`)
   - GitHub: `{repo}/commit/{hash}`
   - GitLab: `{repo}/-/commit/{hash}`
   - Bitbucket: `{repo}/commits/{hash}`

**Evidence:** `src/telemetry/url_builder.py:145-194`

---

### Step 5: Return Response

**Response:**
```python
return {"commit_url": commit_url}
```

**Evidence:** `telemetry_service.py:1255`

**Note:** `commit_url` may be None if platform is unsupported or URL is malformed.

---

## Invariants

### INV-1: Run Must Exist

**Statement:** Endpoint MUST return 404 if event_id doesn't exist in database.

**Enforcement:** SELECT query before URL building

**Evidence:** `telemetry_service.py:1243-1247`

---

### INV-2: Null Safety

**Statement:** Missing git_repo or git_commit_hash MUST return null, not error.

**Enforcement:** Explicit null check before URL building

**Evidence:** `telemetry_service.py:1251-1252`

**Rationale:** Run may exist without commit association (not an error state).

---

### INV-3: Platform Support

**Statement:** Only GitHub.com, GitLab.com, and Bitbucket.org are supported.

**Enforcement:** Platform detection in url_builder.py

**Evidence:** `src/telemetry/url_builder.py:54-67`

**Behavior:** Self-hosted instances (e.g., gitlab.mycompany.com) return null.

---

### INV-4: URL Format

**Statement:** All returned URLs MUST be HTTPS format (never SSH).

**Enforcement:** normalize_repo_url() converts SSH to HTTPS

**Evidence:** `src/telemetry/url_builder.py:94-103`

**Rationale:** Browser-clickable URLs must be HTTPS.

---

## Errors and Edge Cases

### Error: Run Not Found (404)

**Trigger:** event_id doesn't exist in database

**Response:**
- **Status:** 404 Not Found
- **Body:** `{"detail": "Run not found: <event_id>"}`

**Evidence:** `telemetry_service.py:1243-1247`

**Example:**
```
GET /api/v1/runs/nonexistent/commit-url
→ 404 {"detail": "Run not found: nonexistent"}
```

---

### Error: Database Failure (500)

**Trigger:** SQLite error during query execution

**Response:**
- **Status:** 500 Internal Server Error
- **Body:** `{"detail": "Failed to get commit URL: <error>"}`
- **Log:** `logger.error(f"[ERROR] Failed to get commit URL for {event_id}: {e}")`

**Evidence:** `telemetry_service.py:1257-1264`

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

### Edge Case: No Git Metadata (200 OK with null)

**Trigger:** Run exists but `git_repo` or `git_commit_hash` is NULL

**Response:**
```json
{
  "commit_url": null
}
```

**Status:** 200 OK (not an error)

**Evidence:** `telemetry_service.py:1251-1252`

**Use Case:** Run created before commit association, or run not linked to commit.

---

### Edge Case: Unsupported Platform (200 OK with null)

**Trigger:** git_repo points to self-hosted or unknown platform

**Examples:**
- `"https://gitlab.mycompany.com/owner/repo"` (self-hosted GitLab)
- `"https://git.example.com/repo"` (unknown platform)

**Response:**
```json
{
  "commit_url": null
}
```

**Status:** 200 OK (not an error)

**Evidence:** `src/telemetry/url_builder.py:174-176` (unsupported platform returns None)

**Rationale:** Graceful degradation - API doesn't fail for unsupported platforms.

---

### Edge Case: SSH URL Format

**Trigger:** git_repo stored as SSH format

**Example:**
- Database: `git_repo = "git@github.com:owner/repo.git"`
- Commit: `git_commit_hash = "abc1234"`

**Response:**
```json
{
  "commit_url": "https://github.com/owner/repo/commit/abc1234"
}
```

**Status:** 200 OK

**Evidence:** `src/telemetry/url_builder.py:94-103` (SSH to HTTPS conversion)

**Behavior:** Automatically converted to HTTPS for browser compatibility.

---

### Edge Case: Malformed Repository URL

**Trigger:** git_repo is malformed or doesn't match expected patterns

**Examples:**
- `"not-a-url"`
- `"ftp://invalid.com/repo"`

**Response:**
```json
{
  "commit_url": null
}
```

**Status:** 200 OK (graceful failure)

**Evidence:** `src/telemetry/url_builder.py:139-140` (validation check)

**Rationale:** Don't crash on bad data - return null.

---

## Platform-Specific Behavior

### GitHub

**Detection:** `"github.com"` in URL (case-insensitive)

**URL Format:** `https://github.com/{owner}/{repo}/commit/{hash}`

**Example:**
```
Input:  git_repo = "git@github.com:anthropics/claude-code.git"
        git_commit_hash = "abc1234"
Output: "https://github.com/anthropics/claude-code/commit/abc1234"
```

**Evidence:** `src/telemetry/url_builder.py:55-56`, `185-186`

---

### GitLab

**Detection:** `"gitlab.com"` in URL (case-insensitive)

**URL Format:** `https://gitlab.com/{owner}/{repo}/-/commit/{hash}`

**Example:**
```
Input:  git_repo = "https://gitlab.com/myorg/myproject.git"
        git_commit_hash = "def5678"
Output: "https://gitlab.com/myorg/myproject/-/commit/def5678"
```

**Evidence:** `src/telemetry/url_builder.py:59-60`, `187-188`

**Note:** `/-/` is GitLab's URL separator for commit pages.

---

### Bitbucket

**Detection:** `"bitbucket.org"` in URL (case-insensitive)

**URL Format:** `https://bitbucket.org/{owner}/{repo}/commits/{hash}`

**Example:**
```
Input:  git_repo = "git@bitbucket.org:team/project.git"
        git_commit_hash = "123abcd"
Output: "https://bitbucket.org/team/project/commits/123abcd"
```

**Evidence:** `src/telemetry/url_builder.py:63-64`, `189-190`

**Note:** Bitbucket uses `/commits/{hash}` (plural).

---

## Side Effects

### Database Operations

**Table:** `agent_runs`
**Operation:** SELECT (read-only, git_repo and git_commit_hash fields)

**Query:**
```sql
SELECT git_repo, git_commit_hash FROM agent_runs WHERE event_id = ?
```

**Evidence:** `telemetry_service.py:1237-1240`

**Performance:** Fast lookup via event_id UNIQUE index

---

### Logging

**Error Log:**
```python
logger.error(f"[ERROR] Failed to get commit URL for {event_id}: {e}")
```

**Evidence:** `telemetry_service.py:1260`

**Trigger:** Database error or unexpected exception

---

## Use Cases

### Use Case 1: Dashboard "View Commit" Link

**Scenario:** Dashboard displays list of runs. User clicks "View Commit" to see code changes.

**Flow:**
1. Dashboard fetches runs: `GET /api/v1/runs?limit=10`
2. For each run with commit data, display "View Commit" button
3. On click: `GET /api/v1/runs/{event_id}/commit-url`
4. Response: `{"commit_url": "https://github.com/owner/repo/commit/abc1234"}`
5. Open URL in new tab

**Dashboard Code:**
```python
def get_commit_link(event_id: str) -> Optional[str]:
    response = requests.get(f"{api_url}/api/v1/runs/{event_id}/commit-url")
    response.raise_for_status()
    return response.json().get('commit_url')

# Usage
commit_url = get_commit_link("evt_123")
if commit_url:
    print(f"View commit: {commit_url}")
```

**Evidence:** Inferred from API design

---

### Use Case 2: CLI Tool Displaying Commit URLs

**Scenario:** CLI tool shows recent agent runs with commit links.

**Flow:**
```bash
$ telemetry-cli recent --limit 5

Recent Runs:
1. evt_001 - hugo-translator - success
   Commit: https://github.com/myorg/hugo-translator/commit/abc1234

2. evt_002 - seo-analyzer - failure
   Commit: (no commit associated)
```

**CLI Code:**
```python
for run in recent_runs:
    event_id = run['event_id']
    commit_url_resp = requests.get(f"{api_url}/api/v1/runs/{event_id}/commit-url").json()
    commit_url = commit_url_resp.get('commit_url')

    if commit_url:
        print(f"   Commit: {commit_url}")
    else:
        print(f"   Commit: (no commit associated)")
```

---

### Use Case 3: Slack Notification with Commit Link

**Scenario:** Agent run completes, send Slack notification with commit link.

**Flow:**
1. Agent finishes run, associates commit
2. Notification service: `GET /api/v1/runs/{event_id}/commit-url`
3. Build Slack message:
   ```
   Agent run completed! :white_check_mark:
   View commit: https://github.com/owner/repo/commit/abc1234
   ```

**Notification Code:**
```python
commit_url_resp = requests.get(f"{api_url}/api/v1/runs/{event_id}/commit-url").json()
commit_url = commit_url_resp.get('commit_url')

slack_message = f"Agent run completed!\n"
if commit_url:
    slack_message += f"View commit: {commit_url}"

send_slack_message(slack_message)
```

---

### Use Case 4: API Client Needing Commit References

**Scenario:** External system needs to correlate telemetry runs with git commits.

**Flow:**
1. Query runs: `GET /api/v1/runs?status=success&limit=100`
2. For each run, fetch commit URL
3. Cross-reference with CI/CD system using commit hash

---

## Performance

### Expected Latency

| Operation | Expected Time |
|-----------|---------------|
| SELECT git fields | < 5ms |
| URL building | < 1ms (in-memory) |
| Total latency | < 10ms |

**Evidence:** Inferred from indexed lookup and simple string operations

---

### Indexes Used

**event_id Lookup:** UNIQUE constraint provides index for fast SELECT

**Evidence:** Schema v6 (event_id UNIQUE)

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

**Evidence:** `telemetry_service.py:1218-1219`

---

### Database Connection

**Context Manager:** `get_db()`
- Evidence: `telemetry_service.py:341-361`
- Acquires SQLite connection
- Auto-closes on exit

**Used in:** `telemetry_service.py:1236`

---

### URL Builder Module

**build_commit_url() function:**
- Module: `src/telemetry/url_builder.py:145-194`
- Purpose: Platform-specific URL construction
- Evidence: `telemetry_service.py:1254`

**detect_platform() function:**
- Module: `src/telemetry/url_builder.py:30-68`
- Purpose: Auto-detect GitHub/GitLab/Bitbucket

**normalize_repo_url() function:**
- Module: `src/telemetry/url_builder.py:70-114`
- Purpose: Convert SSH to HTTPS, remove .git extension

---

## Evidence

### Code Locations
- **Route handler:** `telemetry_service.py:1215-1264`
- **SQL query:** `telemetry_service.py:1237-1241`
- **Run existence check:** `telemetry_service.py:1243-1247`
- **Null check:** `telemetry_service.py:1251-1252`
- **URL building:** `telemetry_service.py:1254-1255`
- **Error handling:** `telemetry_service.py:1257-1264`

### URL Builder Module
- **build_commit_url:** `src/telemetry/url_builder.py:145-194`
- **detect_platform:** `src/telemetry/url_builder.py:30-68`
- **normalize_repo_url:** `src/telemetry/url_builder.py:70-114`
- **GitHub format:** `src/telemetry/url_builder.py:185-186`
- **GitLab format:** `src/telemetry/url_builder.py:187-188`
- **Bitbucket format:** `src/telemetry/url_builder.py:189-190`

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
- Platform detection logic verified

**Confidence:** HIGH

**Inferred Behaviors:**
- Dashboard integration (use case inferred from API design)
- Latency estimates (based on indexed lookup)

**Evidence Strength:**
- Handler logic: STRONG (direct code read)
- URL building: STRONG (direct code read from url_builder.py)
- Platform support: STRONG (explicit platform checks)
- Performance: MEDIUM (inferred from configuration)
