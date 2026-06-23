# ============================================================
# SuddWatch - Unit Tests: Data Acquisition Module
# File: tests/test_data_acquisition.py
# Purpose: Tests for SentinelDownloader class covering
#          authentication, scene querying, registry management,
#          and download logic without hitting the actual API.
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import json
import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import Config
from src.data_acquisition import SentinelDownloader


# ============================================================
# FIXTURES
# Shared test setup reused across multiple tests
# ============================================================

@pytest.fixture
def config():
    """
    Provides a real Config object for tests.
    Uses actual .env credentials for integration tests.
    """
    return Config()


@pytest.fixture
def downloader(config):
    """
    Provides a SentinelDownloader instance for tests.
    Registry starts empty for each test.
    """
    d = SentinelDownloader(config)
    # Reset registry to empty for clean test state
    d._registry = {}
    return d


@pytest.fixture
def mock_token_response():
    """
    Mock response for successful Copernicus authentication.
    Returns a fake but structurally valid token response.
    """
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "access_token": "fake_token_for_testing_" + "x" * 100,
        "expires_in": 1800,
        "token_type": "Bearer",
    }
    return mock


@pytest.fixture
def mock_scene_response():
    """
    Mock response for a successful Copernicus scene query.
    Returns two fake scene entries matching the real API format.
    """
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {
        "value": [
            {
                "Id": "scene-uuid-001",
                "Name": "S1A_IW_GRDH_1SDV_20240701T033430_20240701T033455_TEST001.SAFE",
                "ContentLength": 1500 * 1024 * 1024,  # 1500 MB
                "ContentDate": {"Start": "2024-07-01T03:34:30.000Z"},
            },
            {
                "Id": "scene-uuid-002",
                "Name": "S1A_IW_GRDH_1SDV_20240707T033430_20240707T033455_TEST002.SAFE",
                "ContentLength": 1600 * 1024 * 1024,  # 1600 MB
                "ContentDate": {"Start": "2024-07-07T03:34:30.000Z"},
            },
        ]
    }
    return mock


# ============================================================
# REGISTRY TESTS
# Tests for _load_registry and _save_registry methods
# ============================================================

class TestRegistry:
    """Tests for the downloaded scenes registry management."""

    def test_load_registry_empty_when_no_file(self, config):
        """
        Registry should return empty dict when no JSON file exists yet.
        This is the expected state on first run.
        """
        # Point registry to a non-existent path
        config.scenes_registry_path = Path("/tmp/nonexistent_registry.json")

        downloader = SentinelDownloader(config)

        # Registry should be empty — no file to load from
        assert downloader._registry == {}

    def test_load_registry_reads_existing_file(self, config):
        """
        Registry should correctly load scene entries from existing JSON file.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake registry file with one scene entry
            registry_path = Path(tmpdir) / "downloaded_scenes.json"
            fake_registry = {
                "scene-uuid-abc": "/data/raw/S1A_test_scene.zip"
            }
            with open(registry_path, "w") as f:
                json.dump(fake_registry, f)

            # Point config to the temp registry
            config.scenes_registry_path = registry_path
            downloader = SentinelDownloader(config)

            # Registry should contain the loaded entry
            assert "scene-uuid-abc" in downloader._registry
            assert downloader._registry["scene-uuid-abc"] == "/data/raw/S1A_test_scene.zip"

    def test_load_registry_handles_corrupted_file(self, config):
        """
        Registry should return empty dict (not crash) if JSON file is corrupted.
        Graceful degradation is important for production reliability.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write invalid JSON to simulate file corruption
            registry_path = Path(tmpdir) / "downloaded_scenes.json"
            with open(registry_path, "w") as f:
                f.write("this is not valid json {{{")

            config.scenes_registry_path = registry_path
            downloader = SentinelDownloader(config)

            # Should not crash — should return empty dict
            assert downloader._registry == {}

    def test_save_registry_persists_to_disk(self, config):
        """
        Save registry should write entries to disk as valid JSON.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "downloaded_scenes.json"
            config.scenes_registry_path = registry_path

            downloader = SentinelDownloader(config)

            # Add an entry and save
            downloader._registry["test-scene-id"] = "/data/raw/test.zip"
            downloader._save_registry()

            # Verify file was written and contains the entry
            assert registry_path.exists()
            with open(registry_path, "r") as f:
                loaded = json.load(f)
            assert loaded["test-scene-id"] == "/data/raw/test.zip"

    def test_registry_summary_returns_correct_count(self, downloader):
        """
        get_registry_summary should return correct scene count.
        """
        # Add 3 fake entries to registry
        downloader._registry = {
            "id-001": "/data/raw/scene1.zip",
            "id-002": "/data/raw/scene2.zip",
            "id-003": "/data/raw/scene3.zip",
        }

        summary = downloader.get_registry_summary()

        assert summary["total_scenes"] == 3
        assert "id-001" in summary["scene_list"]
        assert "id-003" in summary["scene_list"]


# ============================================================
# AUTHENTICATION TESTS
# Tests for _get_access_token method
# ============================================================

class TestAuthentication:
    """Tests for Copernicus OAuth2 token management."""

    def test_get_access_token_success(self, downloader, mock_token_response):
        """
        Should return access token string on successful authentication.
        """
        # Mock the HTTP POST to return a successful token response
        with patch.object(downloader.session, "post", return_value=mock_token_response):
            token = downloader._get_access_token()

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 10  # Token should be a non-trivial string

    def test_get_access_token_raises_on_failure(self, downloader):
        """
        Should raise RuntimeError when authentication fails (401).
        """
        # Mock a failed authentication response
        mock_fail = MagicMock()
        mock_fail.status_code = 401
        mock_fail.text = "Unauthorized"

        with patch.object(downloader.session, "post", return_value=mock_fail):
            with pytest.raises(RuntimeError, match="Authentication failed"):
                downloader._get_access_token()

    def test_get_access_token_reuses_valid_token(self, downloader, mock_token_response):
        """
        Should reuse existing token if it hasn't expired yet.
        This avoids unnecessary authentication requests.
        """
        with patch.object(downloader.session, "post", return_value=mock_token_response) as mock_post:
            # First call — should request a new token
            token1 = downloader._get_access_token()
            # Second call — token still valid, should reuse it
            token2 = downloader._get_access_token()

        # POST should only be called once — second call reused the token
        assert mock_post.call_count == 1
        assert token1 == token2

    def test_get_access_token_refreshes_expired_token(self, downloader, mock_token_response):
        """
        Should request a new token when existing token has expired.
        """
        with patch.object(downloader.session, "post", return_value=mock_token_response) as mock_post:
            # First call — get initial token
            downloader._get_access_token()

            # Force token to appear expired by setting expiry to the past
            downloader._token_expires_at = datetime.now(timezone.utc) - timedelta(seconds=100)

            # Second call — token expired, should request new one
            downloader._get_access_token()

        # POST should be called twice — once for each token request
        assert mock_post.call_count == 2


# ============================================================
# SCENE QUERY TESTS
# Tests for query_scenes method
# ============================================================

class TestSceneQuery:
    """Tests for Copernicus scene search queries."""

    def test_query_scenes_returns_list(self, downloader, mock_token_response, mock_scene_response):
        """
        query_scenes should return a list of scene dicts.
        """
        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_scene_response):
                scenes = downloader.query_scenes()

        assert isinstance(scenes, list)
        assert len(scenes) == 2

    def test_query_scenes_returns_correct_fields(self, downloader, mock_token_response, mock_scene_response):
        """
        Each scene in results should have required fields: id, title, size, date.
        """
        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_scene_response):
                scenes = downloader.query_scenes()

        # Check first scene has all required fields
        scene = scenes[0]
        assert "id" in scene
        assert "title" in scene
        assert "size" in scene
        assert "date" in scene

        # Verify field values match our mock data
        assert scene["id"] == "scene-uuid-001"
        assert "S1A_IW_GRDH" in scene["title"]

    def test_query_scenes_returns_empty_on_api_error(self, downloader, mock_token_response):
        """
        query_scenes should return empty list (not crash) on API error.
        """
        # Mock a failed query response
        mock_error = MagicMock()
        mock_error.status_code = 500

        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_error):
                scenes = downloader.query_scenes()

        assert scenes == []

    def test_query_scenes_uses_bounding_box(self, downloader, mock_token_response, mock_scene_response):
        """
        Query should include the South Sudan bounding box coordinates.
        Verifies that the bounding box from config is used in the API call.
        """
        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_scene_response) as mock_get:
                downloader.query_scenes()

        # Check that the GET request params include the bounding box
        call_kwargs = mock_get.call_args

        # The filter string should contain our bounding box coordinates
        filter_str = str(call_kwargs)
        assert "29" in filter_str  # min_lon
        assert "35" in filter_str  # max_lon


# ============================================================
# DOWNLOAD LOGIC TESTS
# Tests for check_and_download_new_scenes method
# ============================================================

class TestDownloadLogic:
    """Tests for the scene filtering and download orchestration."""

    def test_skips_scenes_already_in_registry(self, downloader, mock_token_response, mock_scene_response):
        """
        Scenes already in the registry should not be downloaded again.
        """
        # Pre-populate registry with one of the mock scenes
        downloader._registry["scene-uuid-001"] = "/data/raw/scene1.zip"

        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_scene_response):
                # Mock download_scene to track calls
                with patch.object(downloader, "download_scene", return_value="/data/raw/scene2.zip") as mock_dl:
                    downloaded = downloader.check_and_download_new_scenes()

        # Only scene-uuid-002 should be downloaded (scene-uuid-001 was in registry)
        assert mock_dl.call_count == 1
        call_args = mock_dl.call_args
        assert call_args[1]["scene_id"] == "scene-uuid-002"

    def test_returns_empty_list_when_no_new_scenes(self, downloader, mock_token_response, mock_scene_response):
        """
        Should return empty list when all queried scenes are already downloaded.
        """
        # Pre-populate registry with ALL mock scenes
        downloader._registry["scene-uuid-001"] = "/data/raw/scene1.zip"
        downloader._registry["scene-uuid-002"] = "/data/raw/scene2.zip"

        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_scene_response):
                downloaded = downloader.check_and_download_new_scenes()

        assert downloaded == []

    def test_returns_empty_list_when_query_returns_nothing(self, downloader, mock_token_response):
        """
        Should return empty list when Copernicus query returns no scenes.
        """
        # Mock query returning empty results
        mock_empty = MagicMock()
        mock_empty.status_code = 200
        mock_empty.json.return_value = {"value": []}

        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_empty):
                downloaded = downloader.check_and_download_new_scenes()

        assert downloaded == []

    def test_updates_registry_after_successful_download(self, downloader, mock_token_response, mock_scene_response):
        """
        Registry should be updated with new scene after successful download.
        """
        fake_filepath = "/data/raw/S1A_IW_GRDH_TEST002.zip"

        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_scene_response):
                with patch.object(downloader, "download_scene", return_value=fake_filepath):
                    with patch.object(downloader, "_save_registry"):
                        downloader.check_and_download_new_scenes()

        # Both scenes should now be in the registry
        assert "scene-uuid-001" in downloader._registry
        assert "scene-uuid-002" in downloader._registry

    def test_continues_after_failed_download(self, downloader, mock_token_response, mock_scene_response):
        """
        If one scene fails to download, processing should continue with the next.
        A single failure should not stop all remaining downloads.
        """
        # First download fails, second succeeds
        fake_filepath = "/data/raw/scene2.zip"
        with patch.object(downloader.session, "post", return_value=mock_token_response):
            with patch.object(downloader.session, "get", return_value=mock_scene_response):
                with patch.object(
                    downloader, "download_scene",
                    side_effect=[None, fake_filepath]  # First fails, second succeeds
                ):
                    with patch.object(downloader, "_save_registry"):
                        downloaded = downloader.check_and_download_new_scenes()

        # Only the successful download should be in results
        assert len(downloaded) == 1
        assert fake_filepath in downloaded


# ============================================================
# INTEGRATION TEST
# Tests against real Copernicus API (requires credentials)
# ============================================================

class TestIntegration:
    """
    Integration tests that hit the real Copernicus API.
    These tests require valid credentials in .env file.
    Mark with @pytest.mark.integration to run selectively.
    """

    @pytest.mark.integration
    def test_real_authentication(self, downloader):
        """
        Verifies real Copernicus authentication works with .env credentials.
        Requires COPERNICUS_USER and COPERNICUS_PASSWORD in .env.
        """
        token = downloader._get_access_token()
        assert token is not None
        assert len(token) > 100  # Real JWT tokens are long

    @pytest.mark.integration
    def test_real_scene_query(self, downloader):
        """
        Verifies real Copernicus scene query returns results over South Sudan.
        Requires valid credentials and internet connection.
        """
        start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        scenes = downloader.query_scenes(start_date=start)

        # Should find at least some scenes over South Sudan in 30 days
        assert isinstance(scenes, list)
        # Each scene should have required fields
        if scenes:
            assert "id" in scenes[0]
            assert "title" in scenes[0]
            assert "S1" in scenes[0]["title"]  # Should be Sentinel-1


# ============================================================
# Run tests directly
# Usage: python3 -m pytest tests/test_data_acquisition.py -v
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
