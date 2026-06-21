# ============================================================
# SuddWatch - Data Acquisition Module
# File: src/data_acquisition.py
# Purpose: Downloads Sentinel-1 SAR scenes from Copernicus
#          Data Space for the South Sudan bounding box.
#          Maintains a local registry to avoid re-downloading
#          scenes that have already been processed.
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import json
import logging
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
import requests

from src.config import Config

# --- Module logger ---
logger = logging.getLogger(__name__)

# --- Copernicus Data Space API endpoints ---
# Token endpoint for OAuth2 authentication
AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

# OData API for searching available scenes
SEARCH_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"

# Download endpoint for scene files
DOWNLOAD_URL = "https://download.dataspace.copernicus.eu/odata/v1/Products"


class SentinelDownloader:
    """
    Downloads Sentinel-1 SAR scenes from Copernicus Data Space.

    Workflow:
    1. Authenticate with Copernicus using OAuth2 token
    2. Query OData API for new IW GRD scenes over South Sudan
    3. Compare results against local registry of downloaded scenes
    4. Download new scenes with retry logic and integrity verification
    5. Update registry to prevent re-downloading

    The registry is stored as a JSON file at data/downloaded_scenes.json.
    Each entry maps scene_id -> local file path.

    Example usage:
        from src.config import Config
        from src.data_acquisition import SentinelDownloader
        config = Config()
        downloader = SentinelDownloader(config)
        downloaded = downloader.check_and_download_new_scenes()
    """

    def __init__(self, config: Config):
        """
        Initialises the downloader with config and sets up HTTP session.

        Args:
            config: Config object with Copernicus credentials and paths
        """
        self.config = config

        # Requests session — reuses TCP connections for efficiency
        self.session = requests.Session()

        # OAuth2 access token — refreshed when expired
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

        # Load existing registry of downloaded scenes
        self._registry = self._load_registry()

        logger.info(
            f"SentinelDownloader initialised. "
            f"Registry contains {len(self._registry)} scenes. "
            f"Raw dir: {config.raw_dir}"
        )

    # ============================================================
    # REGISTRY MANAGEMENT
    # Tracks which scenes have already been downloaded
    # ============================================================

    def _load_registry(self) -> dict:
        """
        Loads the downloaded scenes registry from JSON file.

        The registry maps scene_id -> local file path.
        Prevents re-downloading scenes already on disk.

        Returns:
            dict: {scene_id: filepath} or empty dict if no registry yet
        """
        registry_path = self.config.scenes_registry_path

        if registry_path.exists():
            try:
                with open(registry_path, "r") as f:
                    registry = json.load(f)
                logger.info(f"Registry loaded: {len(registry)} scenes from {registry_path}")
                return registry
            except (json.JSONDecodeError, IOError) as e:
                # Corrupted registry — start fresh rather than crashing
                logger.warning(f"Registry file corrupted, starting fresh: {e}")
                return {}
        else:
            logger.info("No existing registry found — starting fresh.")
            return {}

    def _save_registry(self) -> None:
        """
        Saves the current registry to the JSON file.

        Called after every successful download to persist state.
        Safe to call repeatedly — overwrites existing file.
        """
        try:
            registry_path = self.config.scenes_registry_path

            # Ensure parent directory exists
            registry_path.parent.mkdir(parents=True, exist_ok=True)

            with open(registry_path, "w") as f:
                json.dump(self._registry, f, indent=2)

            logger.debug(f"Registry saved: {len(self._registry)} scenes.")

        except IOError as e:
            # Log error but don't crash — registry save failure is non-fatal
            logger.error(f"Failed to save registry: {e}")

    # ============================================================
    # AUTHENTICATION
    # OAuth2 token management for Copernicus Data Space
    # ============================================================

    def _get_access_token(self) -> str:
        """
        Gets a valid OAuth2 access token for Copernicus Data Space.

        Tokens expire after 10 minutes. This method checks expiry
        and refreshes automatically when needed.

        Returns:
            str: valid access token

        Raises:
            RuntimeError: if authentication fails after retrying
        """
        # Check if existing token is still valid (with 60s buffer)
        now = datetime.now(timezone.utc)
        if (
            self._access_token
            and self._token_expires_at
            and now < self._token_expires_at - timedelta(seconds=60)
        ):
            # Token still valid — reuse it
            return self._access_token

        # Token expired or not yet obtained — request a new one
        logger.info("Requesting new Copernicus access token...")

        try:
            response = self.session.post(
                AUTH_URL,
                data={
                    "client_id": "cdse-public",
                    "grant_type": "password",
                    "username": self.config.copernicus_user,
                    "password": self.config.copernicus_password,
                },
                timeout=30,
            )

            if response.status_code == 200:
                token_data = response.json()
                self._access_token = token_data["access_token"]

                # Token valid for expires_in seconds (typically 600 = 10 min)
                expires_in = token_data.get("expires_in", 600)
                self._token_expires_at = now + timedelta(seconds=expires_in)

                logger.info(f"Access token obtained. Expires in {expires_in}s.")
                return self._access_token

            else:
                raise RuntimeError(
                    f"Authentication failed: HTTP {response.status_code} — {response.text[:200]}"
                )

        except requests.RequestException as e:
            raise RuntimeError(f"Network error during authentication: {e}")

    # ============================================================
    # SCENE SEARCH
    # Queries Copernicus OData API for available scenes
    # ============================================================

    def query_scenes(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list:
        """
        Queries Copernicus Data Space for Sentinel-1 IW GRD scenes
        over the South Sudan bounding box.

        Searches for:
        - Product type: GRD (Ground Range Detected)
        - Sensor mode: IW (Interferometric Wide swath)
        - Polarisation: VH (sensitive to surface water)
        - Area: bounding box from config (lat 5-12, lon 29-35)

        Args:
            start_date: ISO format string e.g. '2024-07-01T00:00:00.000Z'
                        Defaults to 7 days ago if not provided.
            end_date: ISO format string e.g. '2024-07-07T00:00:00.000Z'
                      Defaults to now if not provided.

        Returns:
            list of dicts, each with keys:
            - 'id': Copernicus product UUID
            - 'title': scene name e.g. 'S1A_IW_GRDH_1SDV_...'
            - 'size': file size in bytes
            - 'date': acquisition date string
        """
        # Default to last 7 days if no date range provided
        if not end_date:
            end_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if not start_date:
            start_date = (
                datetime.now(timezone.utc) - timedelta(days=7)
            ).strftime("%Y-%m-%dT%H:%M:%S.000Z")

        # Build bounding box WKT polygon from config
        min_lat, min_lon, max_lat, max_lon = self.config.bounding_box
        bbox_wkt = (
            f"POLYGON(({min_lon} {min_lat},"
            f"{max_lon} {min_lat},"
            f"{max_lon} {max_lat},"
            f"{min_lon} {max_lat},"
            f"{min_lon} {min_lat}))"
        )

        # OData filter string — Sentinel-1 IW GRD VV+VH over bounding box
        # VH polarisation is more sensitive to surface water than VV
        # Requesting dual-pol (VV+VH) scenes to get VH band for flood detection
        odata_filter = (
            f"Collection/Name eq 'SENTINEL-1' "
            f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
            f"and att/OData.CSC.StringAttribute/Value eq 'GRD') "
            f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'operationalMode' "
            f"and att/OData.CSC.StringAttribute/Value eq 'IW') "
            f"and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'polarisationChannels' "
            f"and att/OData.CSC.StringAttribute/Value eq 'VV&VH') "
            f"and ContentDate/Start gt {start_date} "
            f"and ContentDate/Start lt {end_date} "
            f"and OData.CSC.Intersects(area=geography'SRID=4326;{bbox_wkt}')"
        )

        logger.info(f"Querying Copernicus for scenes from {start_date} to {end_date}...")

        try:
            token = self._get_access_token()

            response = self.session.get(
                SEARCH_URL,
                params={
                    "$filter": odata_filter,
                    "$orderby": "ContentDate/Start desc",
                    "$top": 20,        # Max 20 scenes per query
                    "$expand": "Attributes",
                },
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )

            if response.status_code != 200:
                logger.error(f"Scene query failed: HTTP {response.status_code}")
                return []

            data = response.json()
            products = data.get("value", [])

            # Parse results into clean list of dicts
            scenes = []
            for product in products:
                scenes.append({
                    "id": product.get("Id"),
                    "title": product.get("Name", ""),
                    "size": product.get("ContentLength", 0),
                    "date": product.get("ContentDate", {}).get("Start", ""),
                })

            logger.info(f"Query returned {len(scenes)} scenes.")
            return scenes

        except requests.RequestException as e:
            logger.error(f"Network error during scene query: {e}")
            return []

    # ============================================================
    # SCENE DOWNLOAD
    # Downloads scenes with retry logic and integrity verification
    # ============================================================

    def download_scene(
        self,
        scene_id: str,
        scene_title: str,
    ) -> Optional[str]:
        """
        Downloads a single Sentinel-1 scene from Copernicus Data Space.

        Features:
        - Streaming download (memory efficient for large files)
        - Up to 3 retries with exponential backoff (2^attempt seconds)
        - File integrity check (compares received vs expected size)
        - Saves to data/raw/{scene_title}.zip

        Args:
            scene_id: Copernicus product UUID (used in download URL)
            scene_title: scene name used as filename

        Returns:
            str: local file path if successful, None if all retries failed
        """
        # Build output file path
        output_path = self.config.raw_dir / f"{scene_title}.zip"

        # Skip if already downloaded and file exists on disk
        if output_path.exists():
            logger.info(f"Scene already on disk: {output_path.name} — skipping download.")
            return str(output_path)

        # Build download URL using Copernicus OData format
        download_url = f"{DOWNLOAD_URL}({scene_id})/$value"

        logger.info(f"Downloading scene: {scene_title}")

        # --- Retry loop with exponential backoff ---
        max_retries = 3
        for attempt in range(max_retries):
            try:
                token = self._get_access_token()

                # Stream download — writes chunks to disk without loading
                # entire file into memory (scenes can be 1-2GB)
                response = self.session.get(
                    download_url,
                    headers={"Authorization": f"Bearer {token}"},
                    stream=True,
                    timeout=3600,  # 1 hour timeout for large files
                )

                if response.status_code != 200:
                    logger.warning(
                        f"Download attempt {attempt + 1} failed: "
                        f"HTTP {response.status_code}"
                    )
                    # Wait before retrying (exponential backoff)
                    time.sleep(2 ** attempt)
                    continue

                # Get expected file size from Content-Length header
                expected_size = int(response.headers.get("Content-Length", 0))

                # Stream write to disk in 1MB chunks
                bytes_written = 0
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            bytes_written += len(chunk)

                # --- File integrity check ---
                # Compare bytes written vs Content-Length header
                if expected_size > 0 and bytes_written < expected_size * 0.99:
                    logger.warning(
                        f"Integrity check failed: expected {expected_size} bytes, "
                        f"got {bytes_written}. Retrying..."
                    )
                    # Delete incomplete file before retrying
                    output_path.unlink(missing_ok=True)
                    time.sleep(2 ** attempt)
                    continue

                # Download successful
                size_mb = bytes_written / 1024 / 1024
                logger.info(
                    f"Scene downloaded successfully: {scene_title} "
                    f"({size_mb:.1f} MB)"
                )
                return str(output_path)

            except requests.RequestException as e:
                logger.warning(f"Network error on attempt {attempt + 1}: {e}")
                # Clean up partial download
                output_path.unlink(missing_ok=True)
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time}s...")
                    time.sleep(wait_time)

        # All retries exhausted
        logger.error(f"Failed to download scene after {max_retries} attempts: {scene_title}")
        return None

    # ============================================================
    # MAIN METHOD
    # Called by pipeline.py on every scheduled run
    # ============================================================

    def check_and_download_new_scenes(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list:
        """
        Main method — checks for new scenes and downloads any not yet processed.

        Workflow:
        1. Query Copernicus for scenes in date range
        2. Filter out scenes already in the registry
        3. Download each new scene
        4. Update registry with downloaded scene paths
        5. Return list of local file paths for preprocessing

        Called by pipeline.py on every scheduled run (every 6 hours).

        Args:
            start_date: optional ISO date string for query start
            end_date: optional ISO date string for query end

        Returns:
            list of str: local file paths of newly downloaded scenes.
                         Empty list if no new scenes found.
        """
        logger.info("Checking for new Sentinel-1 scenes...")

        # Step 1: Query Copernicus for available scenes
        scenes = self.query_scenes(start_date=start_date, end_date=end_date)

        if not scenes:
            logger.info("No scenes returned from Copernicus query.")
            return []

        # Step 2: Filter out already-downloaded scenes
        new_scenes = [
            scene for scene in scenes
            if scene["id"] not in self._registry
        ]

        logger.info(
            f"Found {len(scenes)} scenes, {len(new_scenes)} new "
            f"(not in registry)."
        )

        if not new_scenes:
            logger.info("All scenes already downloaded. Nothing to do.")
            return []

        # Step 3: Download each new scene
        downloaded_paths = []
        for scene in new_scenes:
            scene_id = scene["id"]
            scene_title = scene["title"]

            logger.info(f"Processing new scene: {scene_title}")

            filepath = self.download_scene(
                scene_id=scene_id,
                scene_title=scene_title,
            )

            if filepath:
                # Step 4: Update registry with successful download
                self._registry[scene_id] = filepath
                self._save_registry()
                downloaded_paths.append(filepath)
                logger.info(f"Scene added to registry: {scene_title}")
            else:
                # Log failure but continue with other scenes
                logger.error(f"Skipping failed scene: {scene_title}")

        logger.info(
            f"Download complete. {len(downloaded_paths)} new scenes ready for preprocessing."
        )
        return downloaded_paths

    def get_registry_summary(self) -> dict:
        """
        Returns a summary of the downloaded scenes registry.

        Used for monitoring and dashboard display.

        Returns:
            dict with 'total_scenes' and 'scene_list' keys
        """
        return {
            "total_scenes": len(self._registry),
            "scene_list": list(self._registry.keys()),
        }


# ============================================================
# Quick self-test — run this file directly to verify
# Tests authentication and scene query (no actual download)
# Usage: python3 -m src.data_acquisition
# ============================================================
if __name__ == "__main__":
    from src.config import Config, setup_logging
    setup_logging()

    config = Config()
    downloader = SentinelDownloader(config)

    print("\n" + "=" * 55)
    print("SuddWatch Data Acquisition Verification")
    print("=" * 55)

    # --- Test 1: Authentication ---
    print("\n1. Testing Copernicus authentication...")
    try:
        token = downloader._get_access_token()
        print(f"   ✓ Token obtained: {token[:20]}...")
    except Exception as e:
        print(f"   ✗ Authentication failed: {e}")

    # --- Test 2: Scene query (last 30 days) ---
    print("\n2. Querying for scenes (last 30 days)...")
    try:
        start = (datetime.now(timezone.utc) - timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        scenes = downloader.query_scenes(start_date=start)
        print(f"   ✓ Found {len(scenes)} scenes")
        if scenes:
            print(f"   ✓ Most recent: {scenes[0]['title']}")
            print(f"   ✓ Date: {scenes[0]['date']}")
            size_mb = scenes[0]['size'] / 1024 / 1024
            print(f"   ✓ Size: {size_mb:.0f} MB")
    except Exception as e:
        print(f"   ✗ Query failed: {e}")

    # --- Test 3: Registry ---
    print("\n3. Registry status...")
    summary = downloader.get_registry_summary()
    print(f"   ✓ Scenes in registry: {summary['total_scenes']}")

    print("\n" + "=" * 55)
    print("Data acquisition verification complete.")
    print("Note: No scenes downloaded in this test.")
    print("=" * 55 + "\n")
