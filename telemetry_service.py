#!/usr/bin/env python3
"""
Telemetry API Service - Single-Writer HTTP API

This is the central telemetry service that receives events from multiple applications
via HTTP POST requests and writes them to a SQLite database. It enforces the
single-writer pattern to prevent database corruption.

Architecture:
- FastAPI HTTP server (single worker)
- Single-writer enforcement via file lock
- SQLite with DELETE journal mode
- Event idempotency via event_id UNIQUE constraint

Endpoints:
- POST /api/v1/runs - Create single telemetry run
- POST /api/v1/runs/batch - Create multiple runs (with deduplication)
- GET /api/v1/runs - Query runs with filtering (v2.1.0+)
- PATCH /api/v1/runs/{event_id} - Update run fields (v2.1.0+)
- GET /health - Health check
- GET /metrics - System metrics

Usage:
    # Development
    python telemetry_service.py

    # Production with uvicorn
    uvicorn telemetry_service:app --host 0.0.0.0 --port 8765 --workers 1
"""

import os
import sys
import json
import sqlite3
import signal
import logging
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

try:
    from fastapi import FastAPI, HTTPException, status, Query, Header, Depends, Request
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field, field_validator
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    print("[ERROR] FastAPI and uvicorn required. Install with: pip install fastapi uvicorn")
    sys.exit(1)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from telemetry.config import TelemetryAPIConfig
from telemetry.single_writer_guard import SingleWriterGuard
from telemetry.logger import log_query, log_update, log_error, track_duration
from telemetry.url_builder import build_commit_url, build_repo_url

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(
    title="Telemetry API",
    description="Single-writer telemetry collection service",
    version="3.0.0"
)

# Global lock guard
lock_guard: Optional[SingleWriterGuard] = None

# One-time flag to avoid spamming PRAGMA verification logs
_PRAGMA_LOGGED_ONCE = False


def _is_sqlite_lock_error(err: BaseException) -> bool:
    """Return True if the exception looks like a SQLite lock/busy error."""
    if not isinstance(err, sqlite3.OperationalError):
        return False
    msg = str(err).lower()
    return ("database is locked" in msg) or ("database is busy" in msg) or ("locked" in msg) or ("busy" in msg)


def _configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    """Apply production SQLite PRAGMA settings consistently.

    These settings are part of the documented production decision:
    - busy_timeout: avoids immediate failures under transient contention
    - journal_mode=DELETE: Docker/Windows volume compatibility
    - synchronous=FULL: corruption prevention on crashes
    """
    global _PRAGMA_LOGGED_ONCE

    conn.execute(f"PRAGMA busy_timeout={TelemetryAPIConfig.DB_BUSY_TIMEOUT_MS}")
    conn.execute(f"PRAGMA journal_mode={TelemetryAPIConfig.DB_JOURNAL_MODE}")
    conn.execute(f"PRAGMA synchronous={TelemetryAPIConfig.DB_SYNCHRONOUS}")

    # Verify once per process for evidence/debugging (avoid log spam)
    if not _PRAGMA_LOGGED_ONCE:
        try:
            cur = conn.cursor()
            actual_timeout = cur.execute("PRAGMA busy_timeout").fetchone()[0]
            actual_journal = cur.execute("PRAGMA journal_mode").fetchone()[0]
            actual_sync = cur.execute("PRAGMA synchronous").fetchone()[0]
            logger.info(
                "SQLite PRAGMA settings: "
                f"busy_timeout={actual_timeout}ms, journal_mode={actual_journal}, synchronous={actual_sync}"
            )
        except Exception as e:
            logger.warning(f"Failed to verify SQLite PRAGMAs: {e}")
        _PRAGMA_LOGGED_ONCE = True


def _execute_with_retry(fn, *, operation: str):
    """Execute a DB operation with retries for lock/busy errors."""
    last_err: Optional[BaseException] = None
    for attempt in range(max(1, TelemetryAPIConfig.DB_MAX_RETRIES + 1)):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if _is_sqlite_lock_error(e) and attempt < TelemetryAPIConfig.DB_MAX_RETRIES:
                delay = TelemetryAPIConfig.DB_RETRY_BASE_DELAY_SECONDS * (2 ** attempt)
                logger.warning(
                    f"SQLite lock contention during {operation}; "
                    f"retrying in {delay:.2f}s (attempt {attempt + 1}/{TelemetryAPIConfig.DB_MAX_RETRIES + 1}): {e}"
                )
                time.sleep(delay)
                continue
            raise
    # Should not reach here
    raise last_err  # type: ignore[misc]


# Pydantic models
class TelemetryRun(BaseModel):
    """Telemetry run event model."""
    # Idempotency
    event_id: str = Field(..., description="UUID for idempotency")
    run_id: str = Field(..., description="Application-level run identifier")

    # Timestamps
    created_at: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    start_time: str
    end_time: Optional[str] = None

    # Agent identity
    agent_name: str
    job_type: str
    status: str = Field(default="running")

    # Product/Domain context
    product: Optional[str] = None
    product_family: Optional[str] = None
    platform: Optional[str] = None
    subdomain: Optional[str] = None

    # Website context
    website: Optional[str] = None
    website_section: Optional[str] = None
    item_name: Optional[str] = None

    # Volume metrics
    items_discovered: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    items_skipped: int = 0

    # Performance
    duration_ms: Optional[int] = 0  # Accepts null from clients, converts to 0

    @field_validator('duration_ms', mode='before')
    @classmethod
    def convert_null_duration(cls, v):
        """Convert null/None to 0 for running jobs."""
        return 0 if v is None else v

    # Input/Output
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    source_ref: Optional[str] = None
    target_ref: Optional[str] = None

    # Error details
    error_summary: Optional[str] = None
    error_details: Optional[str] = None

    # Git context
    git_repo: Optional[str] = None
    git_branch: Optional[str] = None
    git_commit_hash: Optional[str] = None
    git_run_tag: Optional[str] = None
    git_commit_source: Optional[str] = Field(
        None,
        description="How commit was created: 'manual', 'llm', 'ci'"
    )
    git_commit_author: Optional[str] = Field(
        None,
        description="Author of the git commit (e.g., 'Name <email>')"
    )
    git_commit_timestamp: Optional[str] = Field(
        None,
        description="ISO8601 timestamp of when commit was made"
    )

    @field_validator('git_commit_source')
    @classmethod
    def validate_commit_source(cls, v):
        """Validate git_commit_source is one of allowed values."""
        if v is not None and v not in ['manual', 'llm', 'ci']:
            raise ValueError("git_commit_source must be 'manual', 'llm', or 'ci'")
        return v

    # Environment
    host: Optional[str] = None
    environment: Optional[str] = None
    trigger_type: Optional[str] = None

    # Extended metadata (JSON)
    metrics_json: Optional[Dict[str, Any]] = None
    context_json: Optional[Dict[str, Any]] = None

    # API sync tracking (server-side)
    api_posted: bool = False
    api_posted_at: Optional[str] = None
    api_retry_count: int = 0

    # Insight linking
    insight_id: Optional[str] = None
    parent_run_id: Optional[str] = None


class BatchResponse(BaseModel):
    """Response for batch insert operations."""
    inserted: int
    duplicates: int
    errors: List[str]
    total: int


class RunUpdate(BaseModel):
    """Pydantic model for partial run updates."""
    status: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    error_summary: Optional[str] = None
    error_details: Optional[str] = None
    output_summary: Optional[str] = None
    items_succeeded: Optional[int] = None
    items_failed: Optional[int] = None
    items_skipped: Optional[int] = None
    metrics_json: Optional[Dict[str, Any]] = None
    context_json: Optional[Dict[str, Any]] = None
    git_commit_source: Optional[str] = Field(
        None,
        description="How commit was created: 'manual', 'llm', 'ci'"
    )
    git_commit_author: Optional[str] = Field(
        None,
        description="Author of the git commit (e.g., 'Name <email>')"
    )
    git_commit_timestamp: Optional[str] = Field(
        None,
        description="ISO8601 timestamp of when commit was made"
    )

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is not None:
            allowed = ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']
            if v not in allowed:
                raise ValueError(f"Status must be one of: {allowed}")
        return v

    @field_validator('duration_ms', 'items_succeeded', 'items_failed', 'items_skipped')
    @classmethod
    def validate_non_negative(cls, v):
        if v is not None and v < 0:
            raise ValueError("Value must be non-negative")
        return v

    @field_validator('git_commit_source')
    @classmethod
    def validate_commit_source(cls, v):
        """Validate git_commit_source is one of allowed values."""
        if v is not None and v not in ['manual', 'llm', 'ci']:
            raise ValueError("git_commit_source must be 'manual', 'llm', or 'ci'")
        return v


class CommitAssociation(BaseModel):
    """Associate a git commit with a telemetry run."""
    commit_hash: str = Field(..., min_length=7, max_length=40, description="Git commit SHA (7-40 hex characters)")
    commit_source: str = Field(..., description="How commit was created: 'manual', 'llm', 'ci'")
    commit_author: Optional[str] = Field(None, description="Author of the commit (e.g., 'Name <email>')")
    commit_timestamp: Optional[str] = Field(None, description="ISO8601 timestamp of when commit was made")

    @field_validator('commit_source')
    @classmethod
    def validate_source(cls, v):
        """Validate commit_source is one of allowed values."""
        if v not in ['manual', 'llm', 'ci']:
            raise ValueError("commit_source must be 'manual', 'llm', or 'ci'")
        return v


# Authentication dependency
async def verify_auth(authorization: Optional[str] = Header(None)):
    """
    Verify API authentication if enabled.

    Args:
        authorization: Authorization header value (e.g., "Bearer <token>")

    Raises:
        HTTPException: 401 Unauthorized if auth is enabled and token is invalid

    Notes:
        - Authentication is disabled by default (TELEMETRY_API_AUTH_ENABLED=false)
        - When disabled, this dependency passes through without validation
        - When enabled, requires "Bearer <token>" format matching TELEMETRY_API_AUTH_TOKEN
    """
    # If auth is disabled, allow all requests
    if not TelemetryAPIConfig.API_AUTH_ENABLED:
        return None

    # Auth is enabled - validate token
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check for Bearer token format
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format. Use: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]

    # Validate token matches configured value
    if token != TelemetryAPIConfig.API_AUTH_TOKEN:
        logger.warning(f"Invalid API token attempted")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return token


# Rate Limiting
class RateLimiter:
    """
    Simple sliding window rate limiter using in-memory storage.

    Tracks request counts per IP address within a time window.
    For production with multiple workers, consider Redis-based rate limiting.
    """

    def __init__(self):
        self.requests: Dict[str, List[float]] = {}  # {client_ip: [timestamp1, timestamp2, ...]}

    def check_rate_limit(self, client_ip: str, rpm_limit: int) -> tuple[bool, int]:
        """
        Check if client has exceeded rate limit.

        Args:
            client_ip: Client IP address
            rpm_limit: Requests per minute limit

        Returns:
            Tuple of (is_allowed: bool, remaining: int)
        """
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - 60  # 60 seconds = 1 minute

        # Clean up old requests outside the window
        if client_ip in self.requests:
            self.requests[client_ip] = [
                ts for ts in self.requests[client_ip] if ts > window_start
            ]
        else:
            self.requests[client_ip] = []

        # Count requests in current window
        request_count = len(self.requests[client_ip])

        # Check if limit exceeded
        if request_count >= rpm_limit:
            return False, 0

        # Allow request and record timestamp
        self.requests[client_ip].append(now)
        remaining = rpm_limit - request_count - 1

        return True, remaining


# Global rate limiter instance
rate_limiter = RateLimiter()


# Metadata Cache
class MetadataCache:
    """
    In-memory TTL cache for metadata endpoint.

    Caches DISTINCT query results to avoid expensive full-table scans on every request.
    With 21M+ rows, DISTINCT queries can take >60 seconds without caching.

    Features:
    - TTL-based expiration (default 300 seconds / 5 minutes)
    - Per-key invalidation or full cache clear
    - Thread-safe for single-worker FastAPI (in-memory dict)

    Usage:
        cache = MetadataCache(ttl_seconds=300)
        cache.set("metadata", {"agent_names": [...], "job_types": [...]})
        result = cache.get("metadata")  # Returns cached value or None if expired
        cache.invalidate("metadata")  # Clear specific key
        cache.invalidate()  # Clear all keys
    """

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize cache with TTL.

        Args:
            ttl_seconds: Time-to-live in seconds (default 300 = 5 minutes)
        """
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Dict[str, Any]] = {}  # {key: {"value": data, "timestamp": float}}

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value if exists and not expired, None otherwise
        """
        if key not in self._cache:
            return None

        entry = self._cache[key]
        now = datetime.now(timezone.utc).timestamp()
        age = now - entry["timestamp"]

        if age > self.ttl_seconds:
            # Expired - remove and return None
            del self._cache[key]
            logger.debug(f"[CACHE] Key '{key}' expired (age={age:.1f}s > ttl={self.ttl_seconds}s)")
            return None

        logger.debug(f"[CACHE] Hit for key '{key}' (age={age:.1f}s)")
        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        """
        Cache value with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        self._cache[key] = {
            "value": value,
            "timestamp": datetime.now(timezone.utc).timestamp()
        }
        logger.debug(f"[CACHE] Set key '{key}'")

    def invalidate(self, key: Optional[str] = None) -> None:
        """
        Invalidate cache entry or all entries.

        Args:
            key: Specific key to invalidate, or None to clear all
        """
        if key is None:
            # Clear all cache
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"[CACHE] Invalidated all {count} entries")
        elif key in self._cache:
            del self._cache[key]
            logger.info(f"[CACHE] Invalidated key '{key}'")


# Global metadata cache instance (5 minute TTL)
metadata_cache = MetadataCache(ttl_seconds=300)


# Status normalization
STATUS_ALIASES = {
    'failed': 'failure',      # Legacy alias
    'completed': 'success',   # Legacy alias
    'succeeded': 'success',   # Alternative alias
}

def normalize_status(status: Optional[str]) -> Optional[str]:
    """
    Normalize status value from legacy aliases to canonical form.

    Accepts:
        - Canonical: running, success, failure, partial, timeout, cancelled
        - Aliases: failed → failure, completed → success, succeeded → success

    Args:
        status: Status value (may be canonical or alias)

    Returns:
        Canonical status value or None
    """
    if status is None:
        return None

    # Already canonical
    canonical_statuses = ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']
    if status in canonical_statuses:
        return status

    # Check aliases
    return STATUS_ALIASES.get(status, status)


async def check_rate_limit(request: Request):
    """
    Rate limiting dependency.

    Args:
        request: FastAPI Request object

    Raises:
        HTTPException: 429 Too Many Requests if rate limit exceeded

    Notes:
        - Rate limiting is disabled by default (TELEMETRY_RATE_LIMIT_ENABLED=false)
        - When disabled, this dependency passes through without validation
        - When enabled, enforces TELEMETRY_RATE_LIMIT_RPM requests per minute per IP
    """
    # If rate limiting is disabled, allow all requests
    if not TelemetryAPIConfig.RATE_LIMIT_ENABLED:
        return None

    # Get client IP (handle both direct and proxied requests)
    client_ip = request.client.host if request.client else "unknown"

    # Check rate limit
    allowed, remaining = rate_limiter.check_rate_limit(
        client_ip, TelemetryAPIConfig.RATE_LIMIT_RPM
    )

    if not allowed:
        logger.warning(f"Rate limit exceeded for IP: {client_ip}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {TelemetryAPIConfig.RATE_LIMIT_RPM} requests per minute.",
            headers={
                "Retry-After": "60",  # Tell client to retry after 60 seconds
                "X-RateLimit-Limit": str(TelemetryAPIConfig.RATE_LIMIT_RPM),
                "X-RateLimit-Remaining": "0",
            },
        )

    return remaining


# Database context manager
@contextmanager
def get_db():
    """
    Get database connection using configured path.

    Yields:
        sqlite3.Connection: Database connection with proper PRAGMA settings
    """
    conn = None
    try:
        conn = sqlite3.connect(
            TelemetryAPIConfig.DB_PATH,
            timeout=TelemetryAPIConfig.DB_CONNECT_TIMEOUT_SECONDS,
        )

        # Set PRAGMAs for corruption prevention + lock contention handling
        _configure_sqlite_connection(conn)

        yield conn

    finally:
        if conn:
            conn.close()


def ensure_schema():
    """Ensure database schema exists."""
    def _op():
        with get_db() as conn:
            # Check if schema_migrations table exists
            cursor = conn.execute("""
                SELECT name FROM sqlite_master
                WHERE type='table' AND name='schema_migrations'
            """)

            if not cursor.fetchone():
                logger.info("Database not initialized. Creating schema...")

                # Read and execute schema file
                schema_file = Path(__file__).parent / "schema" / "telemetry_v7.sql"

                if not schema_file.exists():
                    logger.error(f"Schema file not found: {schema_file}")
                    raise FileNotFoundError(f"Schema file not found: {schema_file}")

                with open(schema_file, 'r') as f:
                    schema_sql = f.read()

                # Execute schema
                conn.executescript(schema_sql)
                conn.commit()

                logger.info("[OK] Database schema created (v6)")
            else:
                logger.info("[OK] Database schema exists")

    _execute_with_retry(_op, operation="ensure_schema")


# API endpoints
@app.on_event("startup")
async def startup_event():
    """Initialize service on startup."""
    global lock_guard

    logger.info("=" * 70)
    logger.info("TELEMETRY API SERVICE STARTING")
    logger.info("=" * 70)

    # Print configuration
    TelemetryAPIConfig.print_config()

    # Validate configuration
    try:
        TelemetryAPIConfig.validate()
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        sys.exit(1)

    # Acquire single-writer lock
    lock_guard = SingleWriterGuard(TelemetryAPIConfig.LOCK_FILE)
    lock_guard.acquire()

    # Ensure database schema
    ensure_schema()

    logger.info("[OK] Telemetry API service ready")
    logger.info("=" * 70)


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    global lock_guard

    logger.info("Shutting down telemetry API service...")

    if lock_guard:
        lock_guard.release()

    logger.info("[OK] Shutdown complete")


@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        dict: Health status and version
    """
    return {
        "status": "ok",
        "version": "3.0.0",
        "db_path": str(TelemetryAPIConfig.DB_PATH),
        "journal_mode": TelemetryAPIConfig.DB_JOURNAL_MODE,
        "synchronous": TelemetryAPIConfig.DB_SYNCHRONOUS
    }


@app.get("/metrics")
async def get_metrics():
    """
    Get system metrics.

    Returns:
        dict: Metrics including total runs, agents, etc.
    """
    with get_db() as conn:
        # Total runs
        cursor = conn.execute("SELECT COUNT(*) FROM agent_runs")
        total_runs = cursor.fetchone()[0]

        # Runs by agent
        cursor = conn.execute("""
            SELECT agent_name, COUNT(*) as count
            FROM agent_runs
            GROUP BY agent_name
            ORDER BY count DESC
        """)
        agents = {row[0]: row[1] for row in cursor.fetchall()}

        # Recent runs (last 24h)
        cursor = conn.execute("""
            SELECT COUNT(*) FROM agent_runs
            WHERE created_at >= datetime('now', '-1 day')
        """)
        recent_runs = cursor.fetchone()[0]

    return {
        "total_runs": total_runs,
        "agents": agents,
        "recent_24h": recent_runs,
        "performance": {
            "db_path": str(TelemetryAPIConfig.DB_PATH),
            "journal_mode": TelemetryAPIConfig.DB_JOURNAL_MODE
        }
    }


@app.post("/api/v1/runs", status_code=status.HTTP_201_CREATED)
async def create_run(
    run: TelemetryRun,
    request: Request,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Create a single telemetry run.

    Args:
        run: TelemetryRun event
        _auth: Authentication dependency (optional, disabled by default)

    Returns:
        dict: Success message with event_id

    Raises:
        HTTPException: If validation fails or database error occurs
    """
    try:
        # Normalize status from legacy aliases (failed → failure, completed → success)
        normalized_status = normalize_status(run.status)

        with get_db() as conn:
            conn.execute("""
                INSERT INTO agent_runs (
                    event_id, run_id, created_at, start_time, end_time,
                    agent_name, job_type, status,
                    product, product_family, platform, subdomain,
                    website, website_section, item_name,
                    items_discovered, items_succeeded, items_failed, items_skipped,
                    duration_ms,
                    input_summary, output_summary, source_ref, target_ref,
                    error_summary, error_details,
                    git_repo, git_branch, git_commit_hash, git_run_tag,
                    host, environment, trigger_type,
                    metrics_json, context_json,
                    api_posted, api_posted_at, api_retry_count,
                    insight_id, parent_run_id
                ) VALUES (
                    ?, ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?, ?, ?,
                    ?,
                    ?, ?, ?, ?,
                    ?, ?,
                    ?, ?, ?, ?,
                    ?, ?, ?,
                    ?, ?,
                    ?, ?, ?,
                    ?, ?
                )
            """, (
                run.event_id, run.run_id, run.created_at, run.start_time, run.end_time,
                run.agent_name, run.job_type, normalized_status,
                run.product, run.product_family, run.platform, run.subdomain,
                run.website, run.website_section, run.item_name,
                run.items_discovered, run.items_succeeded, run.items_failed, run.items_skipped,
                run.duration_ms,
                run.input_summary, run.output_summary, run.source_ref, run.target_ref,
                run.error_summary, run.error_details,
                run.git_repo, run.git_branch, run.git_commit_hash, run.git_run_tag,
                run.host, run.environment, run.trigger_type,
                json.dumps(run.metrics_json) if run.metrics_json else None,
                json.dumps(run.context_json) if run.context_json else None,
                run.api_posted, run.api_posted_at, run.api_retry_count,
                run.insight_id, run.parent_run_id
            ))

            conn.commit()

        # Invalidate metadata cache (new agent_name/job_type may have been added)
        metadata_cache.invalidate("metadata")

        logger.info(f"[OK] Created run: {run.event_id} (agent: {run.agent_name})")

        return {
            "status": "created",
            "event_id": run.event_id,
            "run_id": run.run_id
        }

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: agent_runs.event_id" in str(e):
            # Idempotent - event already exists (no cache invalidation needed)
            logger.info(f"[OK] Duplicate event_id (idempotent): {run.event_id}")
            return {
                "status": "duplicate",
                "event_id": run.event_id,
                "message": "Event already exists (idempotent)"
            }
        else:
            logger.error(f"[ERROR] Database integrity error: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Database integrity error: {str(e)}"
            )
    except Exception as e:
        logger.error(f"[ERROR] Failed to create run: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create run: {str(e)}"
        )


@app.get("/api/v1/metadata")
async def get_metadata(
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Get metadata about available filter options.

    Returns:
        Dict with distinct agent_names and job_types from the database.
        Response includes cache_hit field indicating if result was from cache.

    Raises:
        HTTPException: 500 for database errors

    Performance:
        - Uses in-memory TTL cache (300 seconds / 5 minutes)
        - Cache reduces response time from >60s to <5ms on 21M+ row databases
        - Cache is invalidated on POST/PATCH/batch operations
    """
    with track_duration() as get_duration:
        # Check cache first
        cached_result = metadata_cache.get("metadata")
        if cached_result is not None:
            logger.info(f"[OK] Metadata cache hit (ttl={metadata_cache.ttl_seconds}s)")
            # Add cache_hit indicator to response
            result = cached_result.copy()
            result["cache_hit"] = True
            return result

        try:
            with get_db() as conn:
                cursor = conn.cursor()

                # Get distinct agent names
                cursor.execute("SELECT DISTINCT agent_name FROM agent_runs WHERE agent_name IS NOT NULL ORDER BY agent_name")
                agent_names = [row[0] for row in cursor.fetchall()]

                # Get distinct job types
                cursor.execute("SELECT DISTINCT job_type FROM agent_runs WHERE job_type IS NOT NULL ORDER BY job_type")
                job_types = [row[0] for row in cursor.fetchall()]

                duration_ms = get_duration()
                log_query(
                    query_params={},
                    result_count=len(agent_names) + len(job_types),
                    duration_ms=duration_ms
                )

                result = {
                    "agent_names": agent_names,
                    "job_types": job_types,
                    "counts": {
                        "agent_names": len(agent_names),
                        "job_types": len(job_types)
                    }
                }

                # Cache the result (without cache_hit field)
                metadata_cache.set("metadata", result)
                logger.info(f"[OK] Metadata cached (query took {duration_ms:.1f}ms, ttl={metadata_cache.ttl_seconds}s)")

                # Add cache_hit indicator to response
                result["cache_hit"] = False
                return result

        except Exception as e:
            log_error("/api/v1/metadata", "DatabaseError", str(e))
            logger.error(f"[ERROR] Failed to fetch metadata: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch metadata: {str(e)}"
            )


@app.get("/api/v1/runs/{event_id}")
async def get_run_by_event_id(
    event_id: str,
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Get a single run by event_id (direct fetch).

    Args:
        event_id: Unique event ID of the run
        _rate_limit: Rate limiting dependency

    Returns:
        dict: Run object with all fields

    Raises:
        HTTPException: 404 if run not found, 500 for database errors
    """
    with track_duration() as get_duration:
        try:
            with get_db() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM agent_runs WHERE event_id = ?",
                    (event_id,)
                )
                row = cursor.fetchone()

                if not row:
                    log_error(
                        f"/api/v1/runs/{event_id}",
                        "NotFound",
                        f"Run not found: {event_id}",
                        event_id=event_id
                    )
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Run not found: {event_id}"
                    )

                # Convert row to dict
                columns = [description[0] for description in cursor.description]
                run_dict = dict(zip(columns, row))

                # Parse JSON fields
                for json_field in ['metrics_json', 'context_json']:
                    if run_dict.get(json_field):
                        try:
                            run_dict[json_field] = json.loads(run_dict[json_field])
                        except (json.JSONDecodeError, TypeError) as e:
                            log_error(
                                f"/api/v1/runs/{event_id}",
                                "JSONParseError",
                                f"Failed to parse {json_field}",
                                event_id=event_id,
                                field=json_field,
                                error=str(e)
                            )
                            run_dict[f'{json_field}_parse_error'] = str(e)

                # Convert api_posted to bool
                if 'api_posted' in run_dict:
                    run_dict['api_posted'] = bool(run_dict['api_posted'])

                # Add URL fields
                git_repo = run_dict.get('git_repo')
                git_commit_hash = run_dict.get('git_commit_hash')

                if git_repo and git_commit_hash:
                    run_dict['commit_url'] = build_commit_url(git_repo, git_commit_hash)
                else:
                    run_dict['commit_url'] = None

                if git_repo:
                    run_dict['repo_url'] = build_repo_url(git_repo)
                else:
                    run_dict['repo_url'] = None

                logger.info(f"[OK] Fetched run by event_id: {event_id}")
                return run_dict

        except HTTPException:
            raise
        except Exception as e:
            log_error(
                f"/api/v1/runs/{event_id}",
                type(e).__name__,
                str(e),
                event_id=event_id
            )
            logger.error(f"[ERROR] Failed to fetch run {event_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch run: {str(e)}"
            )


@app.get("/api/v1/runs")
async def query_runs(
    request: Request,
    agent_name: Optional[str] = None,
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    created_before: Optional[str] = None,
    created_after: Optional[str] = None,
    start_time_from: Optional[str] = None,
    start_time_to: Optional[str] = None,
    limit: int = Query(default=100, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Query telemetry runs with filtering support.

    Args:
        agent_name: Filter by agent name (exact match)
        status: Filter by status (running, success, failure, etc.)
        job_type: Filter by job type
        created_before: ISO8601 timestamp - runs created before this time
        created_after: ISO8601 timestamp - runs created after this time
        start_time_from: ISO8601 timestamp - runs started after this time
        start_time_to: ISO8601 timestamp - runs started before this time
        limit: Maximum results to return (1-1000, default 100)
        offset: Pagination offset (default 0)

    Returns:
        List[Dict]: Array of run objects with all database fields

    Raises:
        HTTPException: 400 if validation fails, 500 for database errors
    """
    with track_duration() as get_duration:
        # Normalize status from legacy aliases (failed → failure)
        normalized_status = normalize_status(status)

        # Validate status if provided
        if normalized_status:
            allowed_statuses = ['running', 'success', 'failure', 'partial', 'timeout', 'cancelled']
            if normalized_status not in allowed_statuses:
                log_error("/api/v1/runs", "ValidationError", f"Invalid status: {normalized_status}", status=normalized_status)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid status. Must be one of: {allowed_statuses}"
                )

        # Validate timestamps if provided
        for ts_name, ts_value in [
            ('created_before', created_before),
            ('created_after', created_after),
            ('start_time_from', start_time_from),
            ('start_time_to', start_time_to)
        ]:
            if ts_value:
                try:
                    datetime.fromisoformat(ts_value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    log_error("/api/v1/runs", "ValidationError", f"Invalid ISO8601 timestamp for {ts_name}: '{ts_value}'",
                             timestamp_field=ts_name, timestamp_value=ts_value)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid ISO8601 timestamp for {ts_name}: '{ts_value}'"
                    )

        try:
            with get_db() as conn:
                conn.row_factory = sqlite3.Row

                # Build dynamic query
                query = "SELECT * FROM agent_runs WHERE 1=1"
                params = []

                if agent_name:
                    query += " AND agent_name = ?"
                    params.append(agent_name)

                if normalized_status:
                    query += " AND status = ?"
                    params.append(normalized_status)

                if job_type:
                    query += " AND job_type = ?"
                    params.append(job_type)

                if created_before:
                    query += " AND created_at < ?"
                    params.append(created_before)

                if created_after:
                    query += " AND created_at > ?"
                    params.append(created_after)

                if start_time_from:
                    query += " AND start_time >= ?"
                    params.append(start_time_from)

                if start_time_to:
                    query += " AND start_time <= ?"
                    params.append(start_time_to)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                # Execute query
                cursor = conn.execute(query, params)
                columns = [description[0] for description in cursor.description]
                results = []

                for row in cursor.fetchall():
                    run_dict = dict(zip(columns, row))

                    # Parse JSON fields from strings to objects (with error handling)
                    for json_field in ['metrics_json', 'context_json']:
                        if run_dict.get(json_field):
                            try:
                                run_dict[json_field] = json.loads(run_dict[json_field])
                            except (json.JSONDecodeError, TypeError) as e:
                                # Log parse failure for debugging
                                log_error(
                                    "/api/v1/runs",
                                    "JSONParseError",
                                    f"Failed to parse {json_field}",
                                    event_id=run_dict.get('event_id'),
                                    field=json_field,
                                    error=str(e),
                                    value_preview=run_dict[json_field][:100] if isinstance(run_dict[json_field], str) else None
                                )

                                # Preserve original string value with error indicator
                                run_dict[f'{json_field}_parse_error'] = str(e)
                                # Keep run_dict[json_field] as original string (don't set to None)

                    # Convert SQLite integer booleans to Python bool
                    if 'api_posted' in run_dict:
                        run_dict['api_posted'] = bool(run_dict['api_posted'])

                    # Add URL fields (commit_url and repo_url)
                    git_repo = run_dict.get('git_repo')
                    git_commit_hash = run_dict.get('git_commit_hash')

                    if git_repo and git_commit_hash:
                        run_dict['commit_url'] = build_commit_url(git_repo, git_commit_hash)
                    else:
                        run_dict['commit_url'] = None

                    if git_repo:
                        run_dict['repo_url'] = build_repo_url(git_repo)
                    else:
                        run_dict['repo_url'] = None

                    results.append(run_dict)

                # Build query_params dict for logging (exclude None values)
                query_params = {k: v for k, v in {
                    "agent_name": agent_name,
                    "status": status,
                    "job_type": job_type,
                    "created_before": created_before,
                    "created_after": created_after,
                    "start_time_from": start_time_from,
                    "start_time_to": start_time_to,
                    "limit": limit,
                    "offset": offset
                }.items() if v is not None}

                # Log successful query with metrics
                log_query(query_params, len(results), get_duration())

                logger.info(f"[OK] Query returned {len(results)} runs (limit={limit}, offset={offset})")
                return results

        except HTTPException:
            raise
        except Exception as e:
            log_error("/api/v1/runs", type(e).__name__, str(e),
                     agent_name=agent_name, status=status, limit=limit)
            logger.error(f"[ERROR] Failed to query runs: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to query runs: {str(e)}"
            )


@app.post("/api/v1/runs/batch", response_model=BatchResponse)
async def create_runs_batch(
    runs: List[TelemetryRun],
    request: Request,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Create multiple telemetry runs with deduplication.

    Args:
        runs: List of TelemetryRun events
        _auth: Authentication dependency (optional, disabled by default)

    Returns:
        BatchResponse: Statistics about insertion (inserted, duplicates, errors)
    """
    inserted = 0
    duplicates = 0
    errors = []

    with get_db() as conn:
        for run in runs:
            try:
                # Normalize status from legacy aliases
                normalized_status = normalize_status(run.status)

                conn.execute("""
                    INSERT INTO agent_runs (
                        event_id, run_id, created_at, start_time, end_time,
                        agent_name, job_type, status,
                        product, product_family, platform, subdomain,
                        website, website_section, item_name,
                        items_discovered, items_succeeded, items_failed, items_skipped,
                        duration_ms,
                        input_summary, output_summary, source_ref, target_ref,
                        error_summary, error_details,
                        git_repo, git_branch, git_commit_hash, git_run_tag,
                        host, environment, trigger_type,
                        metrics_json, context_json,
                        api_posted, api_posted_at, api_retry_count,
                        insight_id, parent_run_id
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?,
                        ?, ?, ?, ?,
                        ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?,
                        ?, ?
                    )
                """, (
                    run.event_id, run.run_id, run.created_at, run.start_time, run.end_time,
                    run.agent_name, run.job_type, normalized_status,
                    run.product, run.product_family, run.platform, run.subdomain,
                    run.website, run.website_section, run.item_name,
                    run.items_discovered, run.items_succeeded, run.items_failed, run.items_skipped,
                    run.duration_ms,
                    run.input_summary, run.output_summary, run.source_ref, run.target_ref,
                    run.error_summary, run.error_details,
                    run.git_repo, run.git_branch, run.git_commit_hash, run.git_run_tag,
                    run.host, run.environment, run.trigger_type,
                    json.dumps(run.metrics_json) if run.metrics_json else None,
                    json.dumps(run.context_json) if run.context_json else None,
                    run.api_posted, run.api_posted_at, run.api_retry_count,
                    run.insight_id, run.parent_run_id
                ))

                inserted += 1

            except sqlite3.IntegrityError as e:
                if "UNIQUE constraint failed: agent_runs.event_id" in str(e):
                    duplicates += 1  # Idempotent - already processed
                else:
                    errors.append(f"{run.event_id}: {str(e)}")
            except Exception as e:
                errors.append(f"{run.event_id}: {str(e)}")

        conn.commit()

    # Invalidate metadata cache if any new runs were inserted
    if inserted > 0:
        metadata_cache.invalidate("metadata")

    logger.info(f"[OK] Batch insert: {inserted} new, {duplicates} duplicates, {len(errors)} errors")

    return BatchResponse(
        inserted=inserted,
        duplicates=duplicates,
        errors=errors,
        total=len(runs)
    )


@app.patch("/api/v1/runs/{event_id}")
async def update_run(
    event_id: str,
    update: RunUpdate,
    request: Request,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Update specific fields of an existing run record.

    Args:
        event_id: Unique event ID of the run to update
        update: RunUpdate model with fields to update
        _auth: Authentication dependency (optional, disabled by default)

    Returns:
        dict: Update confirmation with list of updated fields

    Raises:
        HTTPException: 404 if run not found, 400 for validation errors, 500 for database errors
    """
    with track_duration() as get_duration:
        updated_field_names = []
        success = False

        try:
            with get_db() as conn:
                # Check if run exists
                cursor = conn.execute("SELECT 1 FROM agent_runs WHERE event_id = ?", (event_id,))
                if not cursor.fetchone():
                    log_error("/api/v1/runs/{event_id}", "NotFound", f"Run not found: {event_id}",
                             event_id=event_id)
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Run not found: {event_id}"
                    )

                # Build dynamic UPDATE query
                update_fields = []
                params = []

                # Get only the fields that were explicitly set (exclude unset fields)
                update_data = update.model_dump(exclude_unset=True)

                for field, value in update_data.items():
                    if value is not None:
                        # Handle JSON fields
                        if field in ['metrics_json', 'context_json']:
                            update_fields.append(f"{field} = ?")
                            params.append(json.dumps(value))
                        else:
                            update_fields.append(f"{field} = ?")
                            params.append(value)
                        updated_field_names.append(field)

                if not update_fields:
                    log_error("/api/v1/runs/{event_id}", "ValidationError", "No valid fields to update",
                             event_id=event_id)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No valid fields to update"
                    )

                # Execute UPDATE
                params.append(event_id)
                query = f"UPDATE agent_runs SET {', '.join(update_fields)} WHERE event_id = ?"

                conn.execute(query, params)
                conn.commit()
                success = True

                # Invalidate metadata cache (status updates may affect metadata)
                # Note: PATCH doesn't change agent_name/job_type but we invalidate
                # for safety in case schema changes in the future
                metadata_cache.invalidate("metadata")

                # Log successful update
                log_update(event_id, updated_field_names, get_duration(), success=True)

                logger.info(f"[OK] Updated run {event_id}: {updated_field_names}")

                return {
                    "event_id": event_id,
                    "updated": True,
                    "fields_updated": updated_field_names
                }

        except HTTPException:
            # Re-raise HTTP exceptions (404, 400)
            raise
        except Exception as e:
            log_error("/api/v1/runs/{event_id}", type(e).__name__, str(e),
                     event_id=event_id, fields=updated_field_names)
            logger.error(f"[ERROR] Failed to update run {event_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to update run: {str(e)}"
            )


@app.get("/api/v1/runs/{event_id}/commit-url")
async def get_commit_url(
    event_id: str,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Get GitHub/GitLab/Bitbucket commit URL for a run.

    Args:
        event_id: Unique event ID of the run
        _auth: Authentication dependency (optional, disabled by default)
        _rate_limit: Rate limiting dependency

    Returns:
        dict: Commit URL or null if git data is missing

    Raises:
        HTTPException: 404 if run not found, 500 for database errors
    """
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT git_repo, git_commit_hash FROM agent_runs WHERE event_id = ?",
                (event_id,)
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Run not found: {event_id}"
                )

            repo_url, commit_hash = row

            if not repo_url or not commit_hash:
                return {"commit_url": None}

            commit_url = build_commit_url(repo_url, commit_hash)
            return {"commit_url": commit_url}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Failed to get commit URL for {event_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get commit URL: {str(e)}"
        )


@app.get("/api/v1/runs/{event_id}/repo-url")
async def get_repo_url(
    event_id: str,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Get GitHub/GitLab/Bitbucket repository URL for a run.

    Args:
        event_id: Unique event ID of the run
        _auth: Authentication dependency (optional, disabled by default)
        _rate_limit: Rate limiting dependency

    Returns:
        dict: Repository URL or null if git data is missing

    Raises:
        HTTPException: 404 if run not found, 500 for database errors
    """
    try:
        with get_db() as conn:
            cursor = conn.execute(
                "SELECT git_repo FROM agent_runs WHERE event_id = ?",
                (event_id,)
            )
            row = cursor.fetchone()

            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Run not found: {event_id}"
                )

            repo_url = row[0]

            if not repo_url:
                return {"repo_url": None}

            normalized_url = build_repo_url(repo_url)
            return {"repo_url": normalized_url}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] Failed to get repo URL for {event_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get repo URL: {str(e)}"
        )


@app.post("/api/v1/runs/{event_id}/associate-commit")
async def associate_commit(
    event_id: str,
    association: CommitAssociation,
    _auth: None = Depends(verify_auth),
    _rate_limit: None = Depends(check_rate_limit)
):
    """
    Associate a git commit with a telemetry run.

    Args:
        event_id: Unique event ID of the run
        association: CommitAssociation model with commit details
        _auth: Authentication dependency (optional, disabled by default)
        _rate_limit: Rate limiting dependency

    Returns:
        dict: Success confirmation with event_id, run_id, and commit_hash

    Raises:
        HTTPException: 404 if run not found, 422 for validation errors, 500 for database errors
    """
    try:
        with get_db() as conn:
            # Verify run exists and get run_id
            cursor = conn.execute(
                "SELECT run_id FROM agent_runs WHERE event_id = ?",
                (event_id,)
            )
            row = cursor.fetchone()
            if not row:
                log_error(
                    f"/api/v1/runs/{event_id}/associate-commit",
                    "NotFound",
                    f"Run not found: {event_id}",
                    event_id=event_id
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Run not found: {event_id}"
                )

            run_id = row[0]

            # Update commit fields
            conn.execute(
                """
                UPDATE agent_runs SET
                    git_commit_hash = ?,
                    git_commit_source = ?,
                    git_commit_author = ?,
                    git_commit_timestamp = ?,
                    updated_at = ?
                WHERE event_id = ?
                """,
                (
                    association.commit_hash,
                    association.commit_source,
                    association.commit_author,
                    association.commit_timestamp,
                    datetime.now(timezone.utc).isoformat(),
                    event_id
                )
            )
            conn.commit()

            logger.info(
                f"[OK] Associated commit {association.commit_hash} with run {event_id}"
            )

            return {
                "status": "success",
                "event_id": event_id,
                "run_id": run_id,
                "commit_hash": association.commit_hash
            }

    except HTTPException:
        raise
    except Exception as e:
        log_error(
            f"/api/v1/runs/{event_id}/associate-commit",
            type(e).__name__,
            str(e),
            event_id=event_id
        )
        logger.error(f"[ERROR] Failed to associate commit: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {e}"
        )


# Signal handlers for graceful shutdown
def signal_handler(signum, frame):
    """Handle shutdown signals."""
    global lock_guard

    logger.info(f"Received signal {signum}, shutting down...")

    if lock_guard:
        lock_guard.release()

    sys.exit(0)


# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


if __name__ == "__main__":
    # Development server
    uvicorn.run(
        "telemetry_service:app",
        host=TelemetryAPIConfig.API_HOST,
        port=TelemetryAPIConfig.API_PORT,
        workers=1,  # CRITICAL: Must be 1 for single-writer
        log_level=TelemetryAPIConfig.LOG_LEVEL.lower()
    )
