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
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

try:
    from fastapi import FastAPI, HTTPException, status
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
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
    version="2.0.0"
)

# Global lock guard
lock_guard: Optional[SingleWriterGuard] = None


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
    duration_ms: int = 0

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
        conn = sqlite3.connect(TelemetryAPIConfig.DB_PATH)

        # Set PRAGMAs for corruption prevention
        conn.execute(f"PRAGMA journal_mode={TelemetryAPIConfig.DB_JOURNAL_MODE}")
        conn.execute(f"PRAGMA synchronous={TelemetryAPIConfig.DB_SYNCHRONOUS}")

        yield conn

    finally:
        if conn:
            conn.close()


def ensure_schema():
    """Ensure database schema exists."""
    with get_db() as conn:
        # Check if schema_migrations table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='schema_migrations'
        """)

        if not cursor.fetchone():
            logger.info("Database not initialized. Creating schema...")

            # Read and execute schema file
            schema_file = Path(__file__).parent / "schema" / "telemetry_v6.sql"

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
        "version": "2.0.0",
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
async def create_run(run: TelemetryRun):
    """
    Create a single telemetry run.

    Args:
        run: TelemetryRun event

    Returns:
        dict: Success message with event_id

    Raises:
        HTTPException: If validation fails or database error occurs
    """
    try:
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
                run.agent_name, run.job_type, run.status,
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

        logger.info(f"[OK] Created run: {run.event_id} (agent: {run.agent_name})")

        return {
            "status": "created",
            "event_id": run.event_id,
            "run_id": run.run_id
        }

    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: agent_runs.event_id" in str(e):
            # Idempotent - event already exists
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


@app.post("/api/v1/runs/batch", response_model=BatchResponse)
async def create_runs_batch(runs: List[TelemetryRun]):
    """
    Create multiple telemetry runs with deduplication.

    Args:
        runs: List of TelemetryRun events

    Returns:
        BatchResponse: Statistics about insertion (inserted, duplicates, errors)
    """
    inserted = 0
    duplicates = 0
    errors = []

    with get_db() as conn:
        for run in runs:
            try:
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
                    run.agent_name, run.job_type, run.status,
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

    logger.info(f"[OK] Batch insert: {inserted} new, {duplicates} duplicates, {len(errors)} errors")

    return BatchResponse(
        inserted=inserted,
        duplicates=duplicates,
        errors=errors,
        total=len(runs)
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
