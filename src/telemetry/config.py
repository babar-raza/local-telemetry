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

    # API configuration
    api_url: Optional[str]
    api_token: Optional[str]
    api_enabled: bool

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

            METRICS_API_URL: Google Apps Script URL
            METRICS_API_TOKEN: API authentication token
            METRICS_API_ENABLED: Enable API posting (default: true)
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

        # API configuration
        api_url = os.getenv("METRICS_API_URL")
        api_token = os.getenv("METRICS_API_TOKEN")

        # API enabled by default, but can be disabled
        api_enabled_str = os.getenv("METRICS_API_ENABLED", "true").lower()
        api_enabled = api_enabled_str in ("true", "1", "yes", "on")

        # Agent metadata
        agent_owner = os.getenv("AGENT_OWNER")

        # Test mode
        test_mode = os.getenv("TELEMETRY_TEST_MODE")

        return cls(
            metrics_dir=metrics_dir,
            database_path=database_path,
            ndjson_dir=ndjson_dir,
            api_url=api_url,
            api_token=api_token,
            api_enabled=api_enabled,
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

        # Warn if API is enabled but URL or token is missing
        if self.api_enabled:
            if not self.api_url:
                errors.append(
                    "METRICS_API_ENABLED=true but METRICS_API_URL is not set. "
                    "API posting will fail."
                )
            if not self.api_token:
                errors.append(
                    "METRICS_API_ENABLED=true but METRICS_API_TOKEN is not set. "
                    "API posting will fail."
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
            f"api_token={masked_token}, "
            f"api_enabled={self.api_enabled}, "
            f"agent_owner={self.agent_owner}, "
            f"test_mode={self.test_mode})"
        )
