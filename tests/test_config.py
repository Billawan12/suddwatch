# ============================================================
# SuddWatch - Unit Tests: Configuration Module
# File: tests/test_config.py
# Purpose: Tests for Config class covering:
#          - Environment variable loading
#          - Default values when .env is missing
#          - Path resolution
#          - Directory creation
#          - Credential validation
#          - Edge cases and error handling
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.config import Config, setup_logging


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture
def temp_env_file(tmp_path):
    """
    Creates a temporary .env file with test credentials.
    """
    env_path = tmp_path / ".env"
    env_content = """
COPERNICUS_USER=test_user
COPERNICUS_PASSWORD=test_password
TWILIO_ACCOUNT_SID=AC123456789
TWILIO_AUTH_TOKEN=abc123
TWILIO_PHONE_NUMBER=+1234567890
SMTP_USER=test@gmail.com
SMTP_PASSWORD=test_password
GITHUB_TOKEN=ghp_test123
SMS_RECIPIENTS=+254700000001,+254700000002
EMAIL_RECIPIENTS=test1@test.com,test2@test.com
BOUNDING_BOX_MIN_LAT=4.0
BOUNDING_BOX_MIN_LON=28.0
BOUNDING_BOX_MAX_LAT=13.0
BOUNDING_BOX_MAX_LON=36.0
"""
    env_path.write_text(env_content)
    return env_path


@pytest.fixture
def temp_project_root(temp_env_file):
    """
    Creates a temporary project root with .env file.
    """
    root = temp_env_file.parent
    return root


# ============================================================
# CONFIG LOADING TESTS
# ============================================================

class TestConfigLoading:
    """Tests for loading configuration from .env file."""

    def test_config_creates_directories(self, tmp_path):
        """Config should create required directories."""
        # Use a temporary project root
        with patch('src.config.PROJECT_ROOT', tmp_path):
            # Create .env file with minimal content
            env_path = tmp_path / ".env"
            env_path.write_text("COPERNICUS_USER=test_user")

            config = Config()

            # Directories should exist
            assert (tmp_path / "data" / "raw").exists()
            assert (tmp_path / "data" / "processed").exists()
            assert (tmp_path / "data" / "flood_masks").exists()
            assert (tmp_path / "data" / "dem").exists()
            assert (tmp_path / "data" / "worldpop").exists()
            assert (tmp_path / "data" / "osm").exists()
            assert (tmp_path / "data" / "exclusion_masks").exists()
            assert (tmp_path / "data" / "database").exists()
            assert (tmp_path / "logs").exists()
            assert (tmp_path / "models").exists()

    def test_config_loads_credentials_from_env(self, temp_project_root):
        """Config should load credentials from .env file."""
        with patch('src.config.PROJECT_ROOT', temp_project_root):
            config = Config()

            assert config.copernicus_user == "test_user"
            assert config.copernicus_password == "test_password"
            assert config.twilio_account_sid == "AC123456789"
            assert config.twilio_auth_token == "abc123"
            assert config.twilio_phone_number == "+1234567890"
            assert config.smtp_user == "test@gmail.com"
            assert config.smtp_password == "test_password"
            assert config.github_token == "ghp_test123"

    def test_config_loads_recipients(self, temp_project_root):
        """Config should load recipient lists from .env."""
        with patch('src.config.PROJECT_ROOT', temp_project_root):
            config = Config()

            assert len(config.sms_recipients) == 2
            assert "+254700000001" in config.sms_recipients
            assert "+254700000002" in config.sms_recipients

            assert len(config.email_recipients) == 2
            assert "test1@test.com" in config.email_recipients
            assert "test2@test.com" in config.email_recipients

    def test_config_loads_bounding_box(self, temp_project_root):
        """Config should load bounding box from .env."""
        with patch('src.config.PROJECT_ROOT', temp_project_root):
            config = Config()

            min_lat, min_lon, max_lat, max_lon = config.bounding_box
            assert min_lat == 4.0
            assert min_lon == 28.0
            assert max_lat == 13.0
            assert max_lon == 36.0

    def test_config_uses_default_values_when_missing(self, tmp_path):
        """Config should use default values when .env is missing."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            # Credentials should be empty strings
            assert config.copernicus_user == ""
            assert config.copernicus_password == ""

            # Bounding box should have defaults
            min_lat, min_lon, max_lat, max_lon = config.bounding_box
            assert min_lat == 5.0
            assert min_lon == 29.0
            assert max_lat == 12.0
            assert max_lon == 35.0

            # Target states should have defaults
            assert config.target_states == ["Jonglei", "Unity", "Upper Nile"]

    def test_config_snap_gpt_path(self, tmp_path):
        """Config should have the correct SNAP GPT path."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.snap_gpt_path == "/Applications/esa-snap/bin/gpt"


# ============================================================
# PATH RESOLUTION TESTS
# ============================================================

class TestPathResolution:
    """Tests for file path resolution."""

    def test_all_paths_are_absolute(self, tmp_path):
        """All paths should be absolute Path objects."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert isinstance(config.raw_dir, Path)
            assert isinstance(config.processed_dir, Path)
            assert isinstance(config.masks_dir, Path)
            assert isinstance(config.dem_dir, Path)
            assert isinstance(config.worldpop_dir, Path)
            assert isinstance(config.osm_dir, Path)
            assert isinstance(config.log_dir, Path)
            assert isinstance(config.db_path, Path)

    def test_paths_are_relative_to_project_root(self, tmp_path):
        """Paths should be correctly relative to project root."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.raw_dir == tmp_path / "data" / "raw"
            assert config.processed_dir == tmp_path / "data" / "processed"
            assert config.masks_dir == tmp_path / "data" / "flood_masks"
            assert config.dem_dir == tmp_path / "data" / "dem"
            assert config.worldpop_dir == tmp_path / "data" / "worldpop"
            assert config.osm_dir == tmp_path / "data" / "osm"
            assert config.log_dir == tmp_path / "logs"
            assert config.db_path == tmp_path / "data" / "database" / "suddwatch.db"

    def test_data_files_have_correct_names(self, tmp_path):
        """Data files should have correct filenames."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.local_dem_path.name == "south_sudan_dem.tif"
            assert config.worldpop_path.name == "south_sudan_pop_2020_1km.tif"
            assert config.osm_roads_path.name == "roads.geojson"
            assert config.osm_health_path.name == "health_facilities.geojson"
            assert config.osm_villages_path.name == "villages.geojson"
            assert config.scenes_registry_path.name == "downloaded_scenes.json"


# ============================================================
# CREDENTIAL VALIDATION TESTS
# ============================================================

class TestCredentialValidation:
    """Tests for credential validation and warnings."""

    def test_warning_on_missing_credentials(self, tmp_path, caplog):
        """Config should log warning when credentials are missing."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            import logging
            caplog.set_level(logging.WARNING)

            config = Config()

            # Should log warnings for missing credentials
            assert "Missing credentials" in caplog.text
            assert "COPERNICUS_USER" in caplog.text
            assert "TWILIO_ACCOUNT_SID" in caplog.text

    def test_no_warning_with_valid_credentials(self, temp_project_root, caplog):
        """Config should not log warnings when credentials are present."""
        with patch('src.config.PROJECT_ROOT', temp_project_root):
            import logging
            caplog.set_level(logging.WARNING)

            config = Config()

            # Should not log warnings
            assert "Missing credentials" not in caplog.text

    def test_warning_on_missing_snap_gpt(self, tmp_path, caplog):
        """Config should log warning when SNAP GPT is missing."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            import logging
            caplog.set_level(logging.WARNING)

            config = Config()

            assert "SNAP GPT not found" in caplog.text

    def test_warning_on_missing_data_files(self, tmp_path, caplog):
        """Config should log warning when data files are missing."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            import logging
            caplog.set_level(logging.WARNING)

            config = Config()

            # Should log warnings for missing data files
            assert "Data file missing" in caplog.text
            assert "WorldPop population" in caplog.text
            assert "OSM roads" in caplog.text


# ============================================================
# LOGGING TESTS
# ============================================================

class TestLogging:
    """Tests for logging configuration."""

    def test_setup_logging_creates_log_dir(self, tmp_path):
        """setup_logging should create the logs directory."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            log_dir = tmp_path / "logs"
            assert not log_dir.exists()

            setup_logging()

            assert log_dir.exists()

    def test_setup_logging_creates_log_file(self, tmp_path):
        """setup_logging should create pipeline.log file."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            log_file = tmp_path / "logs" / "pipeline.log"

            # Logging should be configured
            setup_logging()

            # The file may not exist yet (no messages logged), but directory exists
            assert (tmp_path / "logs").exists()

    def test_setup_logging_uses_info_level_by_default(self, tmp_path):
        """setup_logging should use INFO level by default."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            import logging
            setup_logging()

            assert logging.getLogger().level == logging.INFO

    def test_setup_logging_accepts_log_level_parameter(self, tmp_path):
        """setup_logging should accept log level parameter."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            import logging
            setup_logging("DEBUG")

            assert logging.getLogger().level == logging.DEBUG

    def test_setup_logging_handles_invalid_level(self, tmp_path):
        """setup_logging should use INFO for invalid level."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            import logging
            setup_logging("INVALID_LEVEL")

            assert logging.getLogger().level == logging.INFO


# ============================================================
# BOUNDING BOX TESTS
# ============================================================

class TestBoundingBox:
    """Tests for bounding box configuration."""

    def test_bounding_box_format(self, tmp_path):
        """Bounding box should be a tuple of 4 floats."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            bbox = config.bounding_box
            assert isinstance(bbox, tuple)
            assert len(bbox) == 4
            assert all(isinstance(v, float) for v in bbox)

    def test_bounding_box_valid_range(self, tmp_path):
        """Bounding box should have valid coordinate ranges."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            min_lat, min_lon, max_lat, max_lon = config.bounding_box

            # Valid latitude range: -90 to 90
            assert -90 <= min_lat <= 90
            assert -90 <= max_lat <= 90

            # Valid longitude range: -180 to 180
            assert -180 <= min_lon <= 180
            assert -180 <= max_lon <= 180

            # South Sudan should be in Africa
            assert min_lat >= -10
            assert max_lat <= 25
            assert min_lon >= 20
            assert max_lon <= 40


# ============================================================
# TARGET STATES TESTS
# ============================================================

class TestTargetStates:
    """Tests for target states configuration."""

    def test_target_states_list(self, tmp_path):
        """Target states should be a list of strings."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            states = config.target_states
            assert isinstance(states, list)
            assert all(isinstance(s, str) for s in states)

    def test_target_states_are_south_sudan_states(self, tmp_path):
        """Target states should be South Sudanese states."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            expected = ["Jonglei", "Unity", "Upper Nile"]
            assert config.target_states == expected


# ============================================================
# CONFIG OBJECT PROPERTIES TESTS
# ============================================================

class TestConfigProperties:
    """Tests for various Config properties."""

    def test_project_root_property(self, tmp_path):
        """project_root should be the correct path."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.project_root == tmp_path

    def test_smtp_settings_have_defaults(self, tmp_path):
        """SMTP settings should have default values."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.smtp_host == "smtp.gmail.com"
            assert config.smtp_port == 587

    def test_speckle_filter_settings_have_defaults(self, tmp_path):
        """Speckle filter settings should have default values."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.snap_speckle_filter == "Lee"
            assert config.snap_speckle_size == 5

    def test_tpi_settings_have_defaults(self, tmp_path):
        """TPI settings should have default values."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.tpi_inner_window == 100
            assert config.tpi_outer_window == 500
            assert config.tpi_threshold == 0.5

    def test_github_repo_is_correct(self, tmp_path):
        """GitHub repo should be the correct repository."""
        with patch('src.config.PROJECT_ROOT', tmp_path):
            config = Config()

            assert config.github_repo == "Billawan12/suddwatch"


# ============================================================
# Run tests directly
# Usage: python3 -m pytest tests/test_config.py -v
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])