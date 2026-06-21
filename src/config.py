# ============================================================
# SuddWatch - Central Configuration Module
# File: src/config.py
# Purpose: Loads all environment variables and provides a
#          single Config object used by every other module.
#          No hardcoded values anywhere in the system.
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import os
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple
from dotenv import load_dotenv

# --- Load .env file from project root ---
# This must run before any os.getenv() calls
PROJECT_ROOT = Path(__file__).parent.parent  # Points to ~/suddwatch/
load_dotenv(PROJECT_ROOT / ".env")

# --- Set up module-level logger ---
# All modules use logging instead of print() for structured output
logger = logging.getLogger(__name__)


@dataclass
class Config:
    """
    Central configuration class for SuddWatch.

    Reads all settings from environment variables loaded from .env file.
    Used by every module in the system — instantiate once and pass around.

    Example usage:
        from src.config import Config
        config = Config()
        print(config.copernicus_user)
    """

    # --------------------------------------------------------
    # API Credentials
    # --------------------------------------------------------

    # Copernicus Data Space — used by data_acquisition.py
    copernicus_user: str = field(default_factory=lambda: os.getenv("COPERNICUS_USER", ""))
    copernicus_password: str = field(default_factory=lambda: os.getenv("COPERNICUS_PASSWORD", ""))

    # Twilio SMS — used by alerts.py
    twilio_account_sid: str = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", ""))
    twilio_auth_token: str = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", ""))
    twilio_phone_number: str = field(default_factory=lambda: os.getenv("TWILIO_PHONE_NUMBER", ""))

    # Gmail SMTP — used by alerts.py
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    smtp_host: str = "smtp.gmail.com"   # Gmail SMTP server
    smtp_port: int = 587                # TLS port for Gmail

    # GitHub — used by pipeline.py to export flood outputs
    github_token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    github_repo: str = "Billawan12/suddwatch"  # Target repo for flood output commits

    # --------------------------------------------------------
    # Alert Recipients
    # --------------------------------------------------------

    # SMS recipients — comma-separated in .env, split into list here
    sms_recipients: List[str] = field(
        default_factory=lambda: [
            r.strip() for r in os.getenv("SMS_RECIPIENTS", "").split(",") if r.strip()
        ]
    )

    # Email recipients — comma-separated in .env, split into list here
    email_recipients: List[str] = field(
        default_factory=lambda: [
            r.strip() for r in os.getenv("EMAIL_RECIPIENTS", "").split(",") if r.strip()
        ]
    )

    # --------------------------------------------------------
    # Geographic Bounding Box
    # Covers Jonglei, Unity, and Upper Nile states, South Sudan
    # --------------------------------------------------------

    bounding_box: Tuple[float, float, float, float] = field(
        default_factory=lambda: (
            float(os.getenv("BOUNDING_BOX_MIN_LAT", "5.0")),   # South boundary
            float(os.getenv("BOUNDING_BOX_MIN_LON", "29.0")),  # West boundary
            float(os.getenv("BOUNDING_BOX_MAX_LAT", "12.0")),  # North boundary
            float(os.getenv("BOUNDING_BOX_MAX_LON", "35.0")),  # East boundary
        )
    )

    # Target states for filtering and reporting
    target_states: List[str] = field(
        default_factory=lambda: ["Jonglei", "Unity", "Upper Nile"]
    )

    # --------------------------------------------------------
    # SNAP GPT Processing Parameters
    # Used by preprocessing.py for SAR processing pipeline
    # --------------------------------------------------------

    # Path to SNAP GPT executable — confirmed working on this machine
    snap_gpt_path: str = "/Applications/esa-snap/bin/gpt"

    # DEM source for SNAP terrain correction operator
    # Using SNAP built-in SRTM 3Sec as the operator parameter
    snap_dem: str = "SRTM 3Sec"

    # Speckle filter type — Lee filter reduces SAR speckle noise
    snap_speckle_filter: str = "Lee"

    # Speckle filter window size — 5x5 is standard for Sentinel-1
    snap_speckle_size: int = 5

    # --------------------------------------------------------
    # Flood Detection Thresholds
    # Used by flood_detection.py
    # --------------------------------------------------------

    # TPI (Topographic Position Index) windows for terrain filtering
    # Inner window (100px) captures local terrain, outer (500px) captures regional
    tpi_inner_window: int = 100
    tpi_outer_window: int = 500

    # Pixels with TPI above this are ridges/hills — excluded from flood mask
    tpi_threshold: float = 0.5

    # Change detection threshold in dB — difference > 2dB indicates flooding
    change_detection_threshold: float = 2.0

    # Otsu relaxation factor — 1.0 means use Otsu threshold as-is
    otsu_relaxation_factor: float = 1.0

    # --------------------------------------------------------
    # File Paths
    # All paths relative to project root for portability
    # --------------------------------------------------------

    # Root project directory
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    # Raw downloaded Sentinel-1 scenes (.zip files)
    raw_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "raw")

    # Preprocessed GeoTIFF files (SNAP output)
    processed_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "processed")

    # Flood mask GeoTIFF files (detection output)
    masks_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "flood_masks")

    # DEM data directory
    dem_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "dem")

    # Local Copernicus DEM 30m GeoTIFF — downloaded during setup
    # Used by flood_detection.py for TPI filtering (faster than SNAP downloading on the fly)
    local_dem_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "dem" / "south_sudan_dem.tif"
    )

    # WorldPop population GeoTIFF — downloaded during setup
    worldpop_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "worldpop" / "south_sudan_pop_2020_1km.tif"
    )

    # WorldPop directory
    worldpop_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "worldpop")

    # OSM vector data (roads, villages, health facilities)
    osm_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "osm")

    # OSM individual file paths — used directly by risk_assessment.py
    osm_roads_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "osm" / "roads.geojson"
    )
    osm_health_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "osm" / "health_facilities.geojson"
    )
    osm_villages_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "osm" / "villages.geojson"
    )

    # Exclusion masks (permanent water bodies, urban areas)
    exclusion_masks_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "exclusion_masks")

    # SQLite database file
    db_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "database" / "suddwatch.db")

    # Log files directory
    log_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "logs")

    # Machine learning model path — used by ml_flood_detection.py
    ml_model_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "models" / "random_forest.pkl")

    # Downloaded scenes registry — JSON file tracking already-downloaded scenes
    # Prevents re-downloading scenes that were already processed
    scenes_registry_path: Path = field(
        default_factory=lambda: Path(__file__).parent.parent / "data" / "downloaded_scenes.json"
    )

    def __post_init__(self):
        """
        Runs automatically after __init__.
        Creates all required directories if they don't exist yet,
        validates that critical credentials are set,
        and verifies key data files are present.
        """

        # --- Create all directories ---
        # This ensures the pipeline never fails due to missing folders
        dirs_to_create = [
            self.raw_dir,
            self.processed_dir,
            self.masks_dir,
            self.dem_dir,
            self.worldpop_dir,
            self.osm_dir,
            self.exclusion_masks_dir,
            self.db_path.parent,        # data/database/
            self.log_dir,
            self.ml_model_path.parent,  # models/
        ]

        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)

        # --- Validate critical credentials ---
        # Warn (not crash) if any required credential is missing
        # This allows partial testing without all credentials set
        required_credentials = {
            "COPERNICUS_USER": self.copernicus_user,
            "COPERNICUS_PASSWORD": self.copernicus_password,
            "TWILIO_ACCOUNT_SID": self.twilio_account_sid,
            "TWILIO_AUTH_TOKEN": self.twilio_auth_token,
            "TWILIO_PHONE_NUMBER": self.twilio_phone_number,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASSWORD": self.smtp_password,
            "GITHUB_TOKEN": self.github_token,
        }

        missing = [name for name, value in required_credentials.items() if not value]

        if missing:
            # Log warning but don't crash — allows running individual modules
            logger.warning(
                f"Missing credentials in .env file: {', '.join(missing)}. "
                f"Some modules may not function correctly."
            )
        else:
            logger.info("All credentials loaded successfully from .env file.")

        # --- Validate SNAP GPT path ---
        if not Path(self.snap_gpt_path).exists():
            logger.warning(
                f"SNAP GPT not found at {self.snap_gpt_path}. "
                f"Preprocessing module will not function."
            )
        else:
            logger.info(f"SNAP GPT found at {self.snap_gpt_path}")

        # --- Validate key data files ---
        # These are downloaded during setup — warn if missing
        key_data_files = {
            "Copernicus DEM": self.local_dem_path,
            "WorldPop population": self.worldpop_path,
            "OSM roads": self.osm_roads_path,
            "OSM health facilities": self.osm_health_path,
            "OSM villages": self.osm_villages_path,
        }

        for name, path in key_data_files.items():
            if path.exists():
                logger.info(f"Data file found: {name} ({path.name})")
            else:
                logger.warning(f"Data file missing: {name} at {path}")

        logger.info(f"SuddWatch configuration loaded. Project root: {self.project_root}")


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configures the logging system for the entire SuddWatch pipeline.

    Sets up two handlers:
    - Console handler: shows logs in Terminal during development
    - File handler: writes logs to logs/pipeline.log for monitoring

    Args:
        log_level: Logging level string ('DEBUG', 'INFO', 'WARNING', 'ERROR')

    Usage:
        from src.config import setup_logging
        setup_logging()
    """

    # --- Create logs directory if it doesn't exist ---
    log_dir = Path(__file__).parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    # --- Configure root logger ---
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Console handler — human-readable format for development
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    # File handler — writes to logs/pipeline.log
    file_handler = logging.FileHandler(log_dir / "pipeline.log")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )

    # Apply handlers to root logger so all modules inherit them
    logging.basicConfig(
        level=numeric_level,
        handlers=[console_handler, file_handler]
    )

    logger.info("Logging system initialised.")


# ============================================================
# Quick self-test — run this file directly to verify config
# Usage: python3 src/config.py
# ============================================================
if __name__ == "__main__":
    setup_logging()
    config = Config()

    print("\n" + "=" * 55)
    print("SuddWatch Configuration Verification")
    print("=" * 55)
    print(f"  Project root     : {config.project_root}")
    print(f"  Bounding box     : {config.bounding_box}")
    print(f"  Target states    : {config.target_states}")
    print(f"  SNAP GPT         : {config.snap_gpt_path}")
    print(f"  Database         : {config.db_path}")
    print(f"  Local DEM        : {config.local_dem_path}")
    print(f"  WorldPop         : {config.worldpop_path}")
    print(f"  OSM roads        : {config.osm_roads_path}")
    print(f"  OSM health       : {config.osm_health_path}")
    print(f"  OSM villages     : {config.osm_villages_path}")
    print(f"  Scenes registry  : {config.scenes_registry_path}")
    print(f"  SMS recipients   : {config.sms_recipients}")
    print(f"  Email recipients : {config.email_recipients}")
    print(f"  Copernicus user  : {config.copernicus_user[:4]}****")
    print(f"  Twilio SID       : {config.twilio_account_sid[:6]}****")
    print(f"  GitHub token     : {config.github_token[:6]}****")
    print("=" * 55)
    print("Config loaded successfully.\n")
