"""
Telemetry Platform - Configuration

Configuration loading from environment variables with multi-tier resolution
for cross-platform and multi-deployment support.
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass
class TelemetryConfig:
    """
    Configuration for telemetry client.

    All configuration is loaded from environment variables with flexible
    path resolution to support Windows, Linux, Docker, and Kubernetes.
    """

    # Base directory for telemetry data
    metrics_dir: Path

    # Database path
    database_path: Path

    # NDJSON raw events directory
    ndjson_dir: Path

    # Local HTTP API configuration (for HTTPAPIClient)
    api_url: Optional[str]  # Local telemetry HTTP API (e.g., http://localhost:8765)

    # Google Sheets API configuration (for APIClient)
    google_sheets_api_url: Optional[str]  # External Google Sheets API endpoint
    google_sheets_api_enabled: bool  # Enable Google Sheets export

    # Legacy fields (backward compatibility)
    api_token: Optional[str]  # Shared authentication token
    api_enabled: bool  # Deprecated: use google_sheets_api_enabled
    retry_backoff_factor: float  # Exponential backoff multiplier (default: 1.0)

    # Agent metadata
    agent_owner: Optional[str]

    # Test mode
    test_mode: Optional[str]  # "mock" or "live"

    # Skip validation (for containers where dirs created later)
    skip_validation: bool = False

    @classmethod
    def from_env(cls) -> "TelemetryConfig":
        """
        Load configuration from environment variables with multi-tier resolution.

        Environment variables (priority order):
            TELEMETRY_DB_PATH: Direct database path (highest priority)
            TELEMETRY_BASE_DIR: Base directory (new, clearer name)
            AGENT_METRICS_DIR: Base directory (legacy, backward compat)
            TELEMETRY_NDJSON_DIR: NDJSON directory override
            TELEMETRY_SKIP_VALIDATION: Skip directory validation (true/false)

            TELEMETRY_API_URL: Local HTTP API URL (default: http://localhost:8765)
            GOOGLE_SHEETS_API_URL: External Google Sheets API endpoint
            GOOGLE_SHEETS_API_ENABLED: Enable Google Sheets export (default: false)
            METRICS_API_TOKEN: API authentication token
            METRICS_API_ENABLED: Deprecated, use GOOGLE_SHEETS_API_ENABLED
            AGENT_OWNER: Default agent owner name
            TELEMETRY_TEST_MODE: Test mode (mock|live)

        Returns:
            TelemetryConfig: Configuration instance
        """
        # Try explicit database path first (highest priority)
        db_path_str = os.getenv("TELEMETRY_DB_PATH")
        if db_path_str:
            database_path = Path(db_path_str)
            # Infer base directory from database path (db is in {base}/db/)
            metrics_dir = database_path.parent.parent
            logger.info(f"Using explicit database path: {database_path}")
        else:
            # Try base directory (multiple options for flexibility)
            metrics_dir_str = (
                os.getenv("TELEMETRY_BASE_DIR") or      # New preferred name
                os.getenv("AGENT_METRICS_DIR") or       # Legacy compatibility
                None
            )

            if metrics_dir_str:
                metrics_dir = Path(metrics_dir_str)
                logger.info(f"Using base directory from env: {metrics_dir}")
            else:
                # Auto-detection (improved, cross-platform)
                metrics_dir = cls._auto_detect_base_dir()
                logger.info(f"Auto-detected base directory: {metrics_dir}")

            # Derive database path from base
            database_path = metrics_dir / "db" / "telemetry.sqlite"

        # Check for explicit NDJSON directory
        ndjson_dir_str = os.getenv("TELEMETRY_NDJSON_DIR")
        if ndjson_dir_str:
            ndjson_dir = Path(ndjson_dir_str)
            logger.info(f"Using explicit NDJSON directory: {ndjson_dir}")
        else:
            ndjson_dir = metrics_dir / "raw"

        # Check skip validation flag
        skip_validation_str = os.getenv("TELEMETRY_SKIP_VALIDATION", "false").lower()
        skip_validation = skip_validation_str in ("true", "1", "yes", "on")

        # Local HTTP API configuration
        api_url = os.getenv("TELEMETRY_API_URL") or os.getenv("METRICS_API_URL", "http://localhost:8765")

        # Google Sheets API configuration
        google_sheets_api_url = os.getenv("GOOGLE_SHEETS_API_URL")

        # Google Sheets enabled flag (defaults to false for safety)
        google_sheets_enabled_str = os.getenv("GOOGLE_SHEETS_API_ENABLED", "false").lower()
        google_sheets_api_enabled = google_sheets_enabled_str in ("true", "1", "yes", "on")

        # Legacy API configuration (backward compatibility)
        api_token = os.getenv("METRICS_API_TOKEN")

        # Legacy METRICS_API_ENABLED (deprecated, use GOOGLE_SHEETS_API_ENABLED)
        api_enabled_str = os.getenv("METRICS_API_ENABLED", "false").lower()
        api_enabled = api_enabled_str in ("true", "1", "yes", "on")

        # Retry backoff factor (default: 1.0)
        retry_backoff_factor_str = os.getenv("TELEMETRY_RETRY_BACKOFF_FACTOR", "1.0")
        try:
            retry_backoff_factor = float(retry_backoff_factor_str)
        except ValueError:
            logger.warning(
                f"Invalid TELEMETRY_RETRY_BACKOFF_FACTOR: {retry_backoff_factor_str}, "
                f"using default 1.0"
            )
            retry_backoff_factor = 1.0

        # Agent metadata
        agent_owner = os.getenv("AGENT_OWNER")

        # Test mode
        test_mode = os.getenv("TELEMETRY_TEST_MODE")

        return cls(
            metrics_dir=metrics_dir,
            database_path=database_path,
            ndjson_dir=ndjson_dir,
            api_url=api_url,
            google_sheets_api_url=google_sheets_api_url,
            google_sheets_api_enabled=google_sheets_api_enabled,
            api_token=api_token,
            api_enabled=api_enabled,
            retry_backoff_factor=retry_backoff_factor,
            agent_owner=agent_owner,
            test_mode=test_mode,
            skip_validation=skip_validation,
        )

    @classmethod
    def _auto_detect_base_dir(cls) -> Path:
        """
        Auto-detect base directory with cross-platform support.

        Checks common locations in priority order and returns the first
        existing directory, or a platform-appropriate default.

        Returns:
            Path: Detected or default base directory
        """
        # Check common locations in priority order
        candidates = [
            Path("/agent-metrics"),           # Docker/Linux standard
            Path("/opt/telemetry"),           # Alternative Linux
            Path("/data/telemetry"),          # Kubernetes-style
            Path("D:/agent-metrics"),         # Windows D: drive
            Path("C:/agent-metrics"),         # Windows C: drive
            Path.home() / ".telemetry",       # User home fallback
        ]

        for candidate in candidates:
            if candidate.exists():
                logger.debug(f"Found existing directory: {candidate}")
                return candidate

        # No existing directory found, return platform-appropriate default
        if os.name == 'nt':  # Windows
            default = Path("D:/agent-metrics")
        else:  # Linux/Mac
            default = Path("/agent-metrics")

        logger.debug(f"No existing directory found, using default: {default}")
        return default

    def validate(self, strict: bool = True) -> tuple[bool, list[str]]:
        """
        Validate configuration.

        Args:
            strict: If False, directory checks become warnings instead of errors.
                   Useful for containers where directories are created on first write.

        Returns:
            Tuple of (is_valid: bool, errors: list[str])
        """
        errors = []
        warnings = []

        # Check that metrics directory exists
        if not self.metrics_dir.exists():
            msg = (
                f"Metrics directory does not exist: {self.metrics_dir}. "
                f"Run setup_storage.py first, or set TELEMETRY_SKIP_VALIDATION=true."
            )
            if strict and not self.skip_validation:
                errors.append(msg)
            else:
                warnings.append(msg)

        # Check that database directory exists
        if not self.database_path.parent.exists():
            msg = (
                f"Database directory does not exist: {self.database_path.parent}. "
                f"Run setup_storage.py first, or set TELEMETRY_SKIP_VALIDATION=true."
            )
            if strict and not self.skip_validation:
                errors.append(msg)
            else:
                warnings.append(msg)

        # Check that NDJSON directory exists
        if not self.ndjson_dir.exists():
            msg = (
                f"NDJSON directory does not exist: {self.ndjson_dir}. "
                f"Run setup_storage.py first, or set TELEMETRY_SKIP_VALIDATION=true."
            )
            if strict and not self.skip_validation:
                errors.append(msg)
            else:
                warnings.append(msg)

        # Log warnings if any
        if warnings:
            for warning in warnings:
                logger.warning(f"Configuration warning: {warning}")

        # Validate Google Sheets API configuration
        if self.google_sheets_api_enabled:
            # Requirement 1: GOOGLE_SHEETS_API_URL is required when enabled
            if not self.google_sheets_api_url or self.google_sheets_api_url.strip() == "":
                errors.append(
                    "GOOGLE_SHEETS_API_ENABLED=true but GOOGLE_SHEETS_API_URL is not set. "
                    "Either set GOOGLE_SHEETS_API_URL to your Google Sheets endpoint, or set "
                    "GOOGLE_SHEETS_API_ENABLED=false. See docs/MIGRATION_GUIDE.md for help."
                )
            else:
                # Validate URL format
                try:
                    parsed_url = urlparse(self.google_sheets_api_url)
                    if not parsed_url.scheme or not parsed_url.netloc:
                        errors.append(
                            f"GOOGLE_SHEETS_API_URL is not a valid URL: {self.google_sheets_api_url}. "
                            f"URL must include scheme (http/https) and host. "
                            f"Example: https://sheets.googleapis.com/v4/spreadsheets/..."
                        )
                except Exception as e:
                    errors.append(
                        f"GOOGLE_SHEETS_API_URL is invalid: {self.google_sheets_api_url}. "
                        f"Error: {e}"
                    )

            # Token only required if auth is explicitly required
            # Default: false (for auth-disabled endpoints)
            auth_required_str = os.getenv("METRICS_API_AUTH_REQUIRED", "false").lower()
            auth_required = auth_required_str in ("true", "1", "yes", "on")

            if auth_required and not self.api_token:
                errors.append(
                    "GOOGLE_SHEETS_API_ENABLED=true and METRICS_API_AUTH_REQUIRED=true "
                    "but METRICS_API_TOKEN is not set. Google Sheets export will fail."
                )
            elif not self.api_token:
                # Info-level log instead of error for auth-disabled endpoints
                logger.info(
                    "API token not set - assuming auth-disabled Google Sheets endpoint. "
                    "Set METRICS_API_AUTH_REQUIRED=true if auth is needed."
                )

        # Validate local API URL format (if provided)
        if self.api_url:
            try:
                parsed_api_url = urlparse(self.api_url)
                if not parsed_api_url.scheme or not parsed_api_url.netloc:
                    errors.append(
                        f"TELEMETRY_API_URL is not a valid URL: {self.api_url}. "
                        f"URL must include scheme (http/https) and host. "
                        f"Example: http://localhost:8765"
                    )
            except Exception as e:
                errors.append(
                    f"TELEMETRY_API_URL is invalid: {self.api_url}. Error: {e}"
                )

        # Requirement 2: Warn if both URLs point to same host (likely misconfiguration)
        if (self.google_sheets_api_enabled and
            self.google_sheets_api_url and
            self.api_url):
            try:
                google_sheets_host = urlparse(self.google_sheets_api_url).netloc
                api_host = urlparse(self.api_url).netloc

                if google_sheets_host and api_host and google_sheets_host == api_host:
                    warning_msg = (
                        f"WARNING: Both TELEMETRY_API_URL and GOOGLE_SHEETS_API_URL point to "
                        f"the same host ({api_host}). This is likely a misconfiguration. "
                        f"TELEMETRY_API_URL should point to your local-telemetry API (e.g., "
                        f"http://localhost:8765), while GOOGLE_SHEETS_API_URL should point to "
                        f"the external Google Sheets API endpoint. See docs/MIGRATION_GUIDE.md "
                        f"for proper configuration."
                    )
                    warnings.append(warning_msg)
                    logger.warning(warning_msg)
            except Exception:
                # If URL parsing fails, skip same-host check (other validations will catch it)
                pass

        # Check legacy METRICS_API_ENABLED (deprecated)
        if self.api_enabled and not self.google_sheets_api_enabled:
            logger.warning(
                "METRICS_API_ENABLED is deprecated. Use GOOGLE_SHEETS_API_ENABLED instead. "
                "This setting is ignored when GOOGLE_SHEETS_API_ENABLED is explicitly set."
            )

        is_valid = len(errors) == 0
        return is_valid, errors

    def is_test_mode(self) -> bool:
        """Check if running in test mode."""
        return self.test_mode in ("mock", "live")

    def is_mock_mode(self) -> bool:
        """Check if running in mock test mode."""
        return self.test_mode == "mock"

    def is_live_mode(self) -> bool:
        """Check if running in live test mode."""
        return self.test_mode == "live"

    def __str__(self) -> str:
        """String representation with masked API token."""
        masked_token = "***REDACTED***" if self.api_token else None
        return (
            f"TelemetryConfig("
            f"metrics_dir={self.metrics_dir}, "
            f"database_path={self.database_path}, "
            f"ndjson_dir={self.ndjson_dir}, "
            f"api_url={self.api_url}, "
            f"google_sheets_api_url={self.google_sheets_api_url}, "
            f"google_sheets_api_enabled={self.google_sheets_api_enabled}, "
            f"api_token={masked_token}, "
            f"api_enabled={self.api_enabled}, "
            f"agent_owner={self.agent_owner}, "
            f"test_mode={self.test_mode})"
        )


class TelemetryAPIConfig:
    """
    Centralized configuration management for Telemetry API server.
    All values loaded from environment variables with sensible defaults.
    """

    # API Configuration
    API_URL: str = os.getenv("TELEMETRY_API_URL", "http://localhost:8765")
    API_PORT: int = int(os.getenv("TELEMETRY_API_PORT", "8765"))
    API_HOST: str = os.getenv("TELEMETRY_API_HOST", "0.0.0.0")
    API_WORKERS: int = int(os.getenv("TELEMETRY_API_WORKERS", "1"))

    # Database Configuration
    DB_PATH: str = os.getenv("TELEMETRY_DB_PATH", "./data/telemetry.sqlite")
    DB_JOURNAL_MODE: str = os.getenv("TELEMETRY_DB_JOURNAL_MODE", "DELETE")
    DB_SYNCHRONOUS: str = os.getenv("TELEMETRY_DB_SYNCHRONOUS", "FULL")

    # SQLite lock contention handling
    # NOTE: busy_timeout is the primary mechanism to avoid "database is locked" errors
    # in DELETE journal mode under transient contention.
    DB_BUSY_TIMEOUT_MS: int = int(os.getenv("TELEMETRY_DB_BUSY_TIMEOUT_MS", "30000"))
    DB_CONNECT_TIMEOUT_SECONDS: float = float(
        os.getenv("TELEMETRY_DB_CONNECT_TIMEOUT_SECONDS", "30")
    )

    # Retry logic (only for lock/busy errors)
    DB_MAX_RETRIES: int = int(os.getenv("TELEMETRY_DB_MAX_RETRIES", "3"))
    DB_RETRY_BASE_DELAY_SECONDS: float = float(
        os.getenv("TELEMETRY_DB_RETRY_BASE_DELAY_SECONDS", "0.1")
    )

    # PostgreSQL (optional)
    DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")

    # Buffer Configuration
    BUFFER_DIR: str = os.getenv("TELEMETRY_BUFFER_DIR", "./telemetry_buffer")
    BUFFER_MAX_SIZE_MB: int = int(os.getenv("TELEMETRY_BUFFER_MAX_SIZE_MB", "10"))
    BUFFER_MAX_AGE_HOURS: int = int(os.getenv("TELEMETRY_BUFFER_MAX_AGE_HOURS", "24"))

    # Sync Worker
    SYNC_INTERVAL_SECONDS: int = int(os.getenv("TELEMETRY_SYNC_INTERVAL_SECONDS", "60"))
    SYNC_BATCH_SIZE: int = int(os.getenv("TELEMETRY_SYNC_BATCH_SIZE", "100"))

    # Security
    LOCK_FILE: str = os.getenv("TELEMETRY_LOCK_FILE", "./telemetry_api.lock")
    API_AUTH_ENABLED: bool = os.getenv("TELEMETRY_API_AUTH_ENABLED", "false").lower() in ("true", "1", "yes", "on")
    API_AUTH_TOKEN: Optional[str] = os.getenv("TELEMETRY_API_AUTH_TOKEN")

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = os.getenv("TELEMETRY_RATE_LIMIT_ENABLED", "false").lower() in ("true", "1", "yes", "on")
    RATE_LIMIT_RPM: int = int(os.getenv("TELEMETRY_RATE_LIMIT_RPM", "60"))  # Requests per minute

    # Logging
    # Prefer TELEMETRY_LOG_LEVEL; fall back to LOG_LEVEL for backward compatibility
    LOG_LEVEL: str = os.getenv("TELEMETRY_LOG_LEVEL") or os.getenv("LOG_LEVEL", "INFO")

    # Telemetry Optimization
    TELEMETRY_LEVEL: str = os.getenv("TELEMETRY_LEVEL", "INFO")
    TELEMETRY_SAMPLING_RATE: float = float(os.getenv("TELEMETRY_SAMPLING_RATE", "1.0"))
    TELEMETRY_MAX_PAYLOAD_BYTES: int = int(os.getenv("TELEMETRY_MAX_PAYLOAD_BYTES", "1024"))
    TELEMETRY_RETENTION_DAYS: int = int(os.getenv("TELEMETRY_RETENTION_DAYS", "30"))
    TELEMETRY_DRY_RUN_CLEANUP: bool = os.getenv("TELEMETRY_DRY_RUN_CLEANUP", "1") == "1"

    @classmethod
    def validate(cls):
        """Validate configuration before startup."""
        errors = []
        warnings = []

        # API workers MUST be 1
        if cls.API_WORKERS != 1:
            errors.append(
                f"CRITICAL: TELEMETRY_API_WORKERS must be 1 (single writer), "
                f"got {cls.API_WORKERS}"
            )

        # Journal mode MUST be DELETE
        if cls.DB_JOURNAL_MODE.upper() != "DELETE":
            warnings.append(
                f"WARNING: TELEMETRY_DB_JOURNAL_MODE should be DELETE for "
                f"Docker/Windows compatibility, got {cls.DB_JOURNAL_MODE}"
            )

        # Synchronous MUST be FULL
        if cls.DB_SYNCHRONOUS.upper() != "FULL":
            errors.append(
                f"CRITICAL: TELEMETRY_DB_SYNCHRONOUS must be FULL for corruption "
                f"prevention, got {cls.DB_SYNCHRONOUS}"
            )

        # busy_timeout must be set to a sane value (prevents lock timeouts)
        if cls.DB_BUSY_TIMEOUT_MS < 1000:
            warnings.append(
                f"WARNING: TELEMETRY_DB_BUSY_TIMEOUT_MS is very low ({cls.DB_BUSY_TIMEOUT_MS}ms). "
                "This can cause 'database is locked' errors under contention."
            )

        if cls.DB_CONNECT_TIMEOUT_SECONDS <= 0:
            errors.append(
                f"CRITICAL: TELEMETRY_DB_CONNECT_TIMEOUT_SECONDS must be > 0, "
                f"got {cls.DB_CONNECT_TIMEOUT_SECONDS}"
            )

        if cls.DB_MAX_RETRIES < 0:
            errors.append(
                f"CRITICAL: TELEMETRY_DB_MAX_RETRIES must be >= 0, got {cls.DB_MAX_RETRIES}"
            )

        if cls.DB_RETRY_BASE_DELAY_SECONDS < 0:
            errors.append(
                f"CRITICAL: TELEMETRY_DB_RETRY_BASE_DELAY_SECONDS must be >= 0, "
                f"got {cls.DB_RETRY_BASE_DELAY_SECONDS}"
            )

        # DB path directory must exist or be creatable
        db_dir = Path(cls.DB_PATH).parent
        if not db_dir.exists():
            try:
                db_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created DB directory: {db_dir}")
            except Exception as e:
                errors.append(f"Cannot create DB directory {db_dir}: {e}")

        # Buffer directory must exist or be creatable
        buffer_dir = Path(cls.BUFFER_DIR)
        if not buffer_dir.exists():
            try:
                buffer_dir.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created buffer directory: {buffer_dir}")
            except Exception as e:
                errors.append(f"Cannot create buffer directory {buffer_dir}: {e}")

        # Authentication validation
        if cls.API_AUTH_ENABLED and not cls.API_AUTH_TOKEN:
            errors.append(
                "CRITICAL: TELEMETRY_API_AUTH_ENABLED=true but TELEMETRY_API_AUTH_TOKEN "
                "is not set. Provide a bearer token or disable authentication."
            )

        # Print warnings
        for warning in warnings:
            logger.warning(warning)

        if errors:
            print("=" * 70)
            print("[CRITICAL] CONFIGURATION ERRORS")
            print("=" * 70)
            for error in errors:
                print(f"  - {error}")
            print("=" * 70)
            raise ValueError("Configuration validation failed. See errors above.")

        logger.info("[OK] Configuration validated successfully")

    @classmethod
    def print_config(cls):
        """Print current configuration (for debugging)."""
        masked_token = "***REDACTED***" if cls.API_AUTH_TOKEN else "None"
        print("=" * 70)
        print("TELEMETRY API CONFIGURATION")
        print("=" * 70)
        print(f"API URL:         {cls.API_URL}")
        print(f"API Port:        {cls.API_PORT}")
        print(f"API Workers:     {cls.API_WORKERS} (MUST BE 1)")
        print(f"DB Path:         {cls.DB_PATH}")
        print(f"DB Journal Mode: {cls.DB_JOURNAL_MODE} (MUST BE DELETE)")
        print(f"DB Synchronous:  {cls.DB_SYNCHRONOUS} (MUST BE FULL)")
        print(f"DB busy_timeout: {cls.DB_BUSY_TIMEOUT_MS}ms")
        print(f"DB conn timeout: {cls.DB_CONNECT_TIMEOUT_SECONDS}s")
        print(f"DB retries:      {cls.DB_MAX_RETRIES} (base_delay={cls.DB_RETRY_BASE_DELAY_SECONDS}s)")
        print(f"Buffer Dir:      {cls.BUFFER_DIR}")
        print(f"Lock File:       {cls.LOCK_FILE}")
        print(f"Auth Enabled:    {cls.API_AUTH_ENABLED}")
        print(f"Auth Token:      {masked_token}")
        print(f"Rate Limit:      {'Enabled' if cls.RATE_LIMIT_ENABLED else 'Disabled'} ({cls.RATE_LIMIT_RPM} req/min)")
        print(f"Log Level:       {cls.LOG_LEVEL}")
        print("=" * 70)
