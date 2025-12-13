"""
Tests for telemetry.config module

Tests cover:
- TelemetryConfig creation from environment variables
- Configuration validation
- Default values
- Path construction
- Environment variable parsing
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
from telemetry.config import TelemetryConfig


class TestTelemetryConfigCreation:
    """Test TelemetryConfig creation and defaults."""

    def test_config_creation_with_defaults(self):
        """Test creating config with default values."""
        with patch.dict(os.environ, {}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.metrics_dir is not None
            assert config.database_path is not None
            assert config.ndjson_dir is not None
            assert config.api_enabled is True

    def test_config_detects_d_drive(self):
        """Test that config prefers D drive if it exists."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("telemetry.config.Path.exists") as mock_exists:
                # Mock D drive exists
                mock_exists.return_value = True

                config = TelemetryConfig.from_env()

                # Should use D drive
                assert str(config.metrics_dir).startswith("D:")

    def test_config_fallback_to_c_drive(self):
        """Test that config falls back to C drive if D doesn't exist."""
        with patch.dict(os.environ, {}, clear=True):
            with patch("telemetry.config.Path") as mock_path_class:
                # Setup mock path instances
                mock_d_path = MagicMock()
                mock_d_path.exists.return_value = False  # D doesn't exist
                mock_d_path.__str__.return_value = "D:\\agent-metrics"

                mock_c_path = MagicMock()
                mock_c_path.exists.return_value = True  # C exists
                mock_c_path.__str__.return_value = "C:\\agent-metrics"

                # Return appropriate mock based on path argument
                def path_side_effect(path_str):
                    if "D:" in str(path_str):
                        return mock_d_path
                    elif "C:" in str(path_str):
                        return mock_c_path
                    return Path(path_str)

                mock_path_class.side_effect = path_side_effect

                config = TelemetryConfig.from_env()

                # Should use C drive (mock_c_path will be assigned to metrics_dir)
                assert "C:" in str(config.metrics_dir)

    def test_config_custom_metrics_dir(self):
        """Test config with custom METRICS_DIR."""
        with patch.dict(
            os.environ, {"AGENT_METRICS_DIR": "C:\\custom\\metrics"}, clear=True
        ):
            config = TelemetryConfig.from_env()

            assert config.metrics_dir == Path("C:\\custom\\metrics")

    def test_config_database_path_derived(self):
        """Test that database_path is derived from metrics_dir."""
        with patch.dict(
            os.environ, {"AGENT_METRICS_DIR": "C:\\custom\\metrics"}, clear=True
        ):
            config = TelemetryConfig.from_env()

            expected = Path("C:\\custom\\metrics") / "db" / "telemetry.sqlite"
            assert config.database_path == expected

    def test_config_ndjson_dir_derived(self):
        """Test that ndjson_dir is derived from metrics_dir."""
        with patch.dict(
            os.environ, {"AGENT_METRICS_DIR": "C:\\custom\\metrics"}, clear=True
        ):
            config = TelemetryConfig.from_env()

            expected = Path("C:\\custom\\metrics") / "raw"
            assert config.ndjson_dir == expected


class TestAPIConfiguration:
    """Test API-related configuration."""

    def test_api_url_from_env(self):
        """Test setting API URL from environment."""
        with patch.dict(
            os.environ,
            {"METRICS_API_URL": "https://api.example.com/metrics"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()

            assert config.api_url == "https://api.example.com/metrics"

    def test_api_token_from_env(self):
        """Test setting API token from environment."""
        with patch.dict(
            os.environ, {"METRICS_API_TOKEN": "secret-token-123"}, clear=True
        ):
            config = TelemetryConfig.from_env()

            assert config.api_token == "secret-token-123"

    def test_api_enabled_default_true(self):
        """Test that API is enabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.api_enabled is True

    def test_api_enabled_false_from_env(self):
        """Test disabling API from environment."""
        with patch.dict(os.environ, {"METRICS_API_ENABLED": "false"}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.api_enabled is False

    def test_api_enabled_false_variations(self):
        """Test various false values for METRICS_API_ENABLED."""
        false_values = ["false", "False", "FALSE", "0", "no", "No", "NO"]

        for value in false_values:
            with patch.dict(os.environ, {"METRICS_API_ENABLED": value}, clear=True):
                config = TelemetryConfig.from_env()
                assert config.api_enabled is False, f"Failed for value: {value}"

    def test_api_enabled_true_variations(self):
        """Test various true values for METRICS_API_ENABLED."""
        true_values = ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]

        for value in true_values:
            with patch.dict(os.environ, {"METRICS_API_ENABLED": value}, clear=True):
                config = TelemetryConfig.from_env()
                assert config.api_enabled is True, f"Failed for value: {value}"


class TestAgentOwnerConfiguration:
    """Test agent_owner configuration."""

    def test_agent_owner_from_env(self):
        """Test setting agent_owner from environment."""
        with patch.dict(os.environ, {"AGENT_OWNER": "test_owner"}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.agent_owner == "test_owner"

    def test_agent_owner_default_none(self):
        """Test that agent_owner defaults to None."""
        with patch.dict(os.environ, {}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.agent_owner is None


class TestTestModeConfiguration:
    """Test test_mode configuration."""

    def test_test_mode_from_env(self):
        """Test setting test_mode from environment."""
        with patch.dict(os.environ, {"TELEMETRY_TEST_MODE": "mock"}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.test_mode == "mock"

    def test_test_mode_default_none(self):
        """Test that test_mode defaults to None."""
        with patch.dict(os.environ, {}, clear=True):
            config = TelemetryConfig.from_env()

            assert config.test_mode is None


class TestConfigValidation:
    """Test configuration validation."""

    def test_validate_fully_configured(self):
        """Test validation with fully configured setup."""
        with patch.dict(
            os.environ,
            {
                "AGENT_METRICS_DIR": "C:\\metrics",
                "METRICS_API_URL": "https://api.example.com",
                "METRICS_API_TOKEN": "token123",
                "AGENT_OWNER": "test_owner",
            },
            clear=True,
        ):
            config = TelemetryConfig.from_env()

            # Mock directory existence for validation
            with patch.object(Path, "exists", return_value=True):
                is_valid, errors = config.validate()

                assert is_valid is True
                assert len(errors) == 0

    def test_validate_api_enabled_without_url(self):
        """Test validation when API is enabled but URL is missing."""
        with patch.dict(
            os.environ,
            {
                "METRICS_API_ENABLED": "true",
                "METRICS_API_TOKEN": "token123",
            },
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            is_valid, errors = config.validate()

            assert is_valid is False
            assert any("METRICS_API_URL" in error for error in errors)

    def test_validate_api_enabled_without_token(self):
        """Test validation when API is enabled but token is missing."""
        with patch.dict(
            os.environ,
            {
                "METRICS_API_ENABLED": "true",
                "METRICS_API_URL": "https://api.example.com",
            },
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            is_valid, errors = config.validate()

            assert is_valid is False
            assert any("METRICS_API_TOKEN" in error for error in errors)

    def test_validate_api_disabled_no_warnings(self):
        """Test validation when API is disabled (should not complain about missing URL/token)."""
        with patch.dict(
            os.environ,
            {"METRICS_API_ENABLED": "false"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            is_valid, errors = config.validate()

            # Should be valid (or only have non-API-related errors)
            # No errors about missing API URL/token
            assert not any("METRICS_API_URL" in error for error in errors)
            assert not any("METRICS_API_TOKEN" in error for error in errors)

    def test_validate_missing_agent_owner(self):
        """Test validation when agent_owner is missing (agent_owner is optional, so no error expected)."""
        with patch.dict(
            os.environ,
            {
                "METRICS_API_URL": "https://api.example.com",
                "METRICS_API_TOKEN": "token123",
            },
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            is_valid, errors = config.validate()

            # agent_owner is optional, so no validation error expected for it being missing
            # The test should fail validation due to missing directories, not missing agent_owner
            assert not any("AGENT_OWNER" in error for error in errors)

    def test_validate_returns_all_errors(self):
        """Test that validation returns all errors at once."""
        with patch.dict(
            os.environ,
            {"METRICS_API_ENABLED": "true"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            is_valid, errors = config.validate()

            # Should have multiple errors
            assert len(errors) >= 2
            assert any("METRICS_API_URL" in error for error in errors)
            assert any("METRICS_API_TOKEN" in error for error in errors)


class TestConfigRepresentation:
    """Test config string representation."""

    def test_config_str_masks_token(self):
        """Test that __str__ masks the API token."""
        with patch.dict(
            os.environ,
            {
                "METRICS_API_URL": "https://api.example.com",
                "METRICS_API_TOKEN": "secret-token-12345",
            },
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            config_str = str(config)

            # Token should be masked
            assert "secret-token-12345" not in config_str
            assert "***" in config_str or "REDACTED" in config_str or "****" in config_str

    def test_config_str_shows_url(self):
        """Test that __str__ shows the API URL."""
        with patch.dict(
            os.environ,
            {"METRICS_API_URL": "https://api.example.com"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()
            config_str = str(config)

            # URL should be visible
            assert "https://api.example.com" in config_str


class TestPathConstruction:
    """Test path construction logic."""

    def test_paths_are_pathlib_objects(self):
        """Test that paths are Path objects, not strings."""
        with patch.dict(os.environ, {}, clear=True):
            config = TelemetryConfig.from_env()

            assert isinstance(config.metrics_dir, Path)
            assert isinstance(config.database_path, Path)
            assert isinstance(config.ndjson_dir, Path)

    def test_paths_use_correct_separators(self):
        """Test that paths use correct OS separators."""
        with patch.dict(
            os.environ,
            {"AGENT_METRICS_DIR": "C:\\custom\\metrics"},
            clear=True,
        ):
            config = TelemetryConfig.from_env()

            # Paths should be properly formed for the OS
            assert config.database_path.is_absolute()
            assert config.ndjson_dir.is_absolute()
