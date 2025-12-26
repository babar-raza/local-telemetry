"""
Telemetry Platform - Data Models

Data classes representing telemetry records, events, and API payloads.

KEY FIELDS:
- insight_id: Links actions to originating insights (for SEO Intelligence integration)
- metrics_json: Flexible JSON field for storing ANY custom metrics
  Store complex nested data, arrays, or arbitrary key-value pairs here.
  Examples: {"severity": "high", "pages_affected": 42, "custom_field": "value"}
- git_commit_hash: SHA of the git commit associated with this run
- git_commit_source: How the commit was created ('manual', 'llm', 'ci')
- git_commit_author: Author of the git commit
- git_commit_timestamp: When the commit was made (ISO8601)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import json
import uuid


# Schema version constant
# v2: Added insight_id column for SEO Intelligence integration
# v3: Added product_family and subdomain columns for business context tracking
# v4: Added git commit tracking fields (hash, source, author, timestamp)
# v5: Added website, website_section, item_name for API spec compliance
# v6: Added event_id with UNIQUE constraint for idempotency
SCHEMA_VERSION = 6


@dataclass
class RunRecord:
    """
    Represents a single agent execution run.

    Matches the schema of the agent_runs table in SQLite.
    """

    run_id: str
    agent_name: str
    job_type: str
    trigger_type: str
    start_time: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))  # v6: Idempotency
    schema_version: int = SCHEMA_VERSION
    agent_owner: Optional[str] = None
    end_time: Optional[str] = None
    status: str = "running"
    items_discovered: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    duration_ms: int = 0  # Default to 0 for running jobs (API requires int, not null)
    input_summary: Optional[str] = None
    output_summary: Optional[str] = None
    error_summary: Optional[str] = None
    metrics_json: Optional[str] = None
    insight_id: Optional[str] = None  # Links actions to originating insights (SEO Intelligence integration)
    product: Optional[str] = None
    platform: Optional[str] = None
    product_family: Optional[str] = None  # Business context: Aspose product family (slides, words, cells, etc.)
    subdomain: Optional[str] = None  # Business context: Site subdomain (products, docs, etc.)
    website: Optional[str] = None  # API spec: Root domain (e.g., "aspose.com")
    website_section: Optional[str] = None  # API spec: Subdomain/section (e.g., "products", "docs", "main")
    item_name: Optional[str] = None  # API spec: Specific page/entity being tracked (e.g., "/slides/net/")
    git_repo: Optional[str] = None
    git_branch: Optional[str] = None
    git_run_tag: Optional[str] = None
    git_commit_hash: Optional[str] = None  # SHA of the git commit associated with this run
    git_commit_source: Optional[str] = None  # How commit was created: 'manual', 'llm', 'ci'
    git_commit_author: Optional[str] = None  # Author of the git commit
    git_commit_timestamp: Optional[str] = None  # When the commit was made (ISO8601)
    host: Optional[str] = None
    api_posted: int = 0
    api_posted_at: Optional[str] = None
    api_retry_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        data = asdict(self)
        data["record_type"] = "run"
        return data

    def to_json(self) -> str:
        """Convert to JSON string for NDJSON logging."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunRecord":
        """Create RunRecord from dictionary."""
        # Get valid field names from dataclass
        import dataclasses
        valid_fields = {f.name for f in dataclasses.fields(cls)}

        # Filter out fields not in the dataclass (like 'record_type', 'custom_metadata', etc.)
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}

        # Convert SQLite integer booleans to Python booleans
        if "api_posted" in filtered_data and isinstance(filtered_data["api_posted"], int):
            filtered_data["api_posted"] = bool(filtered_data["api_posted"])

        return cls(**filtered_data)


@dataclass
class RunEvent:
    """
    Represents a single event within an agent run.

    Matches the schema of the run_events table in SQLite.
    Note: Per TEL-03 design, events are written to NDJSON only,
    not to the run_events table (to avoid SQLite contention).
    """

    run_id: str
    event_type: str
    timestamp: str
    payload_json: Optional[str] = None
    id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        data = asdict(self)
        data["record_type"] = "event"
        return data

    def to_json(self) -> str:
        """Convert to JSON string for NDJSON logging."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RunEvent":
        """Create RunEvent from dictionary."""
        # Filter out record_type field if present (added by to_dict())
        filtered_data = {k: v for k, v in data.items() if k != "record_type"}
        return cls(**filtered_data)


@dataclass
class APIPayload:
    """
    Payload for posting to Google Sheets API.

    Simplified representation of RunRecord for API consumption.
    """

    run_id: str
    agent_name: str
    job_type: str
    trigger_type: str
    start_time: str
    status: str
    agent_owner: Optional[str] = None
    end_time: Optional[str] = None
    items_discovered: int = 0
    items_succeeded: int = 0
    items_failed: int = 0
    duration_ms: int = 0  # Default to 0 for running jobs (API requires int, not null)
    error_summary: Optional[str] = None
    product: Optional[str] = None
    platform: Optional[str] = None
    product_family: Optional[str] = None  # Business context: Aspose product family
    subdomain: Optional[str] = None  # Business context: Site subdomain
    website: Optional[str] = None  # API spec: Root domain
    website_section: Optional[str] = None  # API spec: Subdomain/section
    item_name: Optional[str] = None  # API spec: Specific page/entity
    git_repo: Optional[str] = None
    git_branch: Optional[str] = None
    git_commit_hash: Optional[str] = None  # SHA of the git commit
    git_commit_source: Optional[str] = None  # How commit was created: 'manual', 'llm', 'ci'
    git_commit_author: Optional[str] = None  # Author of the git commit
    git_commit_timestamp: Optional[str] = None  # When the commit was made
    host: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API posting, excluding None values."""
        data = asdict(self)
        # Filter out None values for cleaner API payloads
        return {k: v for k, v in data.items() if v is not None}

    def to_json(self) -> str:
        """Convert to JSON string for API posting."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_run_record(cls, record: RunRecord) -> "APIPayload":
        """Create APIPayload from RunRecord."""
        return cls(
            run_id=record.run_id,
            agent_name=record.agent_name,
            agent_owner=record.agent_owner,
            job_type=record.job_type,
            trigger_type=record.trigger_type,
            start_time=record.start_time,
            end_time=record.end_time,
            status=record.status,
            items_discovered=record.items_discovered,
            items_succeeded=record.items_succeeded,
            items_failed=record.items_failed,
            duration_ms=record.duration_ms,
            error_summary=record.error_summary,
            product=record.product,
            platform=record.platform,
            product_family=record.product_family,
            subdomain=record.subdomain,
            website=record.website,
            website_section=record.website_section,
            item_name=record.item_name,
            git_repo=record.git_repo,
            git_branch=record.git_branch,
            git_commit_hash=record.git_commit_hash,
            git_commit_source=record.git_commit_source,
            git_commit_author=record.git_commit_author,
            git_commit_timestamp=record.git_commit_timestamp,
            host=record.host,
        )


def generate_run_id(agent_name: str) -> str:
    """
    Generate a unique run ID.

    Format: {YYYYMMDD}T{HHMMSS}Z-{agent_name}-{uuid8}

    Args:
        agent_name: Name of the agent

    Returns:
        str: Unique run ID

    Example:
        "20251210T120530Z-artifactguard-a1b2c3d4"
    """
    import uuid

    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%Y%m%dT%H%M%SZ")
    uuid_short = str(uuid.uuid4())[:8]

    return f"{timestamp}-{agent_name}-{uuid_short}"


def get_iso8601_timestamp() -> str:
    """
    Get current timestamp in ISO8601 UTC format.

    Returns:
        str: ISO8601 timestamp with timezone offset

    Example:
        "2025-12-10T12:05:30.000000+00:00"
    """
    return datetime.now(timezone.utc).isoformat()


def calculate_duration_ms(start_time_str: str, end_time_str: str) -> int:
    """
    Calculate duration in milliseconds between two ISO8601 timestamps.

    Args:
        start_time_str: ISO8601 start timestamp
        end_time_str: ISO8601 end timestamp

    Returns:
        int: Duration in milliseconds

    Raises:
        ValueError: If timestamps cannot be parsed
    """
    try:
        # Parse ISO8601 timestamps
        start = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))

        # Calculate duration
        duration = end - start
        duration_ms = int(duration.total_seconds() * 1000)

        return duration_ms

    except Exception as e:
        raise ValueError(f"Failed to calculate duration: {e}")
