# ============================================================
# SuddWatch - Central Configuration Module
# File: src/config.py
# Purpose: Loads all settings (credentials, paths, thresholds)
#          and provides a single Config object used by every
#          other module. Nothing else in the system hardcodes
#          credentials or paths.
#
# Where values come from (highest priority first):
#   1. config/runtime_settings.json  (written by the dashboard's
#      Admin → Pipeline "Apply calibration" and Alert Config pages;
#      only covers detection/alert tuning values)
#   2. Real environment variables (e.g. exported in the shell / cron)
#   3. The project's .env file
#   4. The defaults written below
#
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import dotenv_values

# Project root (~/suddwatch/). Read at call time by the helpers below so
# tests can point Config at a temporary directory by patching this value.
PROJECT_ROOT = Path(__file__).parent.parent

logger = logging.getLogger(__name__)

# Name of the file the dashboard writes tuning values into
RUNTIME_SETTINGS_FILE = "runtime_settings.json"

# Settings that may be overridden from config/runtime_settings.json
RUNTIME_OVERRIDABLE = {
    "alert_flood_threshold_ha": float,
    "alert_population_threshold": int,
    "tpi_threshold": float,
    "change_detection_threshold": float,
    "otsu_relaxation_factor": float,
    "min_flood_area_ha": float,
}


# ------------------------------------------------------------
# Helpers — resolved every time a Config() is created
# ------------------------------------------------------------

def _root() -> Path:
    """Current project root (patchable in tests)."""
    return Path(PROJECT_ROOT)


def _env(key: str, default: str = "") -> str:
    """
    Look up a setting: real environment variable first, then the
    project's .env file, then the default.

    The .env file is read with dotenv_values() rather than load_dotenv()
    so it never leaks into os.environ — that keeps tests and multiple
    project copies isolated from each other.
    """
    if key in os.environ and os.environ[key] != "":
        return os.environ[key]
    env_file = _root() / ".env"
    if env_file.exists():
        value = dotenv_values(env_file).get(key)
        if value not in (None, ""):
            return value
    return default


def _env_list(key: str) -> List[str]:
    """Comma-separated env value → list of stripped, non-empty strings."""
    return [v.strip() for v in _env(key, "").split(",") if v.strip()]


def _resolve(path: str) -> Path:
    """Relative paths in .env are relative to the project root."""
    p = Path(path).expanduser()
    return p if p.is_absolute() else _root() / p


def _data(*parts: str) -> Path:
    """Path under <project_root>/data/."""
    return _root().joinpath("data", *parts)


@dataclass
class Config:
    """
    Central configuration class for SuddWatch.

    Instantiate once and pass it to every module:
        from src.config import Config
        config = Config()
    """

    # --------------------------------------------------------
    # API credentials
    # --------------------------------------------------------
    copernicus_user: str = field(default_factory=lambda: _env("COPERNICUS_USER"))
    copernicus_password: str = field(default_factory=lambda: _env("COPERNICUS_PASSWORD"))

    twilio_account_sid: str = field(default_factory=lambda: _env("TWILIO_ACCOUNT_SID"))
    twilio_auth_token: str = field(default_factory=lambda: _env("TWILIO_AUTH_TOKEN"))
    twilio_phone_number: str = field(default_factory=lambda: _env("TWILIO_PHONE_NUMBER"))

    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    # Optional — not used by the pipeline at present (kept for a future
    # "publish outputs to GitHub" feature). Not required.
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN"))
    github_repo: str = "Billawan12/suddwatch"

    # --------------------------------------------------------
    # Alert recipients and alert behaviour
    # --------------------------------------------------------
    sms_recipients: List[str] = field(default_factory=lambda: _env_list("SMS_RECIPIENTS"))
    email_recipients: List[str] = field(default_factory=lambda: _env_list("EMAIL_RECIPIENTS"))

    # An alert is sent if EITHER threshold is met or exceeded
    alert_flood_threshold_ha: float = field(
        default_factory=lambda: float(_env("ALERT_FLOOD_THRESHOLD_HA", "500")))
    alert_population_threshold: int = field(
        default_factory=lambda: int(float(_env("ALERT_POPULATION_THRESHOLD", "1000"))))

    # Public URL of the dashboard, included in SMS/email if set.
    # Leave empty when the dashboard only runs on localhost — a
    # localhost link is useless on a recipient's phone.
    dashboard_url: str = field(default_factory=lambda: _env("DASHBOARD_URL", ""))

    # --------------------------------------------------------
    # Geographic area — Jonglei, Unity and Upper Nile states
    # (min_lat, min_lon, max_lat, max_lon)
    # --------------------------------------------------------
    bounding_box: Tuple[float, float, float, float] = field(
        default_factory=lambda: (
            float(_env("BOUNDING_BOX_MIN_LAT", "5.0")),
            float(_env("BOUNDING_BOX_MIN_LON", "29.0")),
            float(_env("BOUNDING_BOX_MAX_LAT", "12.0")),
            float(_env("BOUNDING_BOX_MAX_LON", "35.0")),
        )
    )
    target_states: List[str] = field(
        default_factory=lambda: ["Jonglei", "Unity", "Upper Nile"]
    )

    # How many days back each run searches Copernicus for new scenes
    scene_search_days: int = field(
        default_factory=lambda: int(_env("SCENE_SEARCH_DAYS", "7")))

    # --------------------------------------------------------
    # ESA SNAP GPT
    # --------------------------------------------------------
    snap_gpt_path: str = field(
        default_factory=lambda: str(Path(_env("SNAP_GPT_PATH",
                                              "/Applications/esa-snap/bin/gpt")).expanduser()))
    snap_dem: str = "SRTM 3Sec"
    snap_speckle_filter: str = "Lee"
    snap_speckle_size: int = 5

    # --------------------------------------------------------
    # Flood detection parameters
    # --------------------------------------------------------
    # TPI neighbourhood, expressed in 10 m scene pixels:
    #   inner = 100 px  (1 km)   outer = 500 px  (5 km)
    # TPI = elevation − mean elevation of the ring between the
    # inner and outer windows. Pixels more than tpi_threshold metres
    # above their surroundings are treated as un-floodable high ground.
    tpi_inner_window: int = 100
    tpi_outer_window: int = 500
    tpi_threshold: float = 0.5

    # Change detection: a pixel counts as newly flooded only if its
    # backscatter dropped by more than this many dB vs the dry-season
    # baseline (only applied when a baseline image is available).
    change_detection_threshold: float = 2.0

    # Multiplier applied to the final (negative, dB) threshold.
    # 1.0 = use the Otsu/GMM threshold unchanged.
    otsu_relaxation_factor: float = 1.0

    # Which detector the pipeline uses:
    #   "threshold"     — the 6-stage Otsu/GMM detector (default, recommended)
    #   "random_forest" — experimental ML detector (src/ml_flood_detection.py);
    #                     falls back to "threshold" if no trained model exists.
    detection_method: str = field(
        default_factory=lambda: _env("DETECTION_METHOD", "threshold").strip().lower())

    # Events smaller than this (after cleaning) are recorded but treated
    # as "no flood" for alerting purposes. 0 disables the check.
    min_flood_area_ha: float = 0.0

    # Villages / health facilities within this distance of a flooded
    # pixel are reported as "near flood" (medium risk).
    near_flood_buffer_m: float = field(
        default_factory=lambda: float(_env("NEAR_FLOOD_BUFFER_M", "1000")))

    # --------------------------------------------------------
    # File paths (all relative to the project root)
    # --------------------------------------------------------
    project_root: Path = field(default_factory=_root)
    raw_dir: Path = field(default_factory=lambda: _data("raw"))
    processed_dir: Path = field(default_factory=lambda: _data("processed"))
    masks_dir: Path = field(default_factory=lambda: _data("flood_masks"))
    dem_dir: Path = field(default_factory=lambda: _data("dem"))
    local_dem_path: Path = field(default_factory=lambda: _data("dem", "south_sudan_dem.tif"))
    worldpop_dir: Path = field(default_factory=lambda: _data("worldpop"))
    worldpop_path: Path = field(
        default_factory=lambda: _data("worldpop", "south_sudan_pop_2020_1km.tif"))
    osm_dir: Path = field(default_factory=lambda: _data("osm"))
    osm_roads_path: Path = field(default_factory=lambda: _data("osm", "roads.geojson"))
    osm_health_path: Path = field(
        default_factory=lambda: _data("osm", "health_facilities.geojson"))
    osm_villages_path: Path = field(default_factory=lambda: _data("osm", "villages.geojson"))
    exclusion_masks_dir: Path = field(default_factory=lambda: _data("exclusion_masks"))

    # Optional state (admin-1) boundaries used to label villages by state,
    # e.g. the OCHA COD-AB South Sudan admin1 layer from data.humdata.org
    admin_states_path: Path = field(
        default_factory=lambda: _data("admin", "south_sudan_states.geojson"))

    # Dry-season baseline (preprocessed dB GeoTIFF) for change detection.
    # Optional: if the file is missing, change detection is skipped.
    baseline_path: Path = field(
        default_factory=lambda: _resolve(_env(
            "DRY_SEASON_BASELINE_PATH",
            str(_data("processed", "baseline_dry_season_db.tif")))))

    # Hand-labelled reference masks used to compute IoU:
    # data/reference_masks/<scene_id>_reference.tif
    reference_masks_dir: Path = field(default_factory=lambda: _data("reference_masks"))

    db_path: Path = field(default_factory=lambda: _data("database", "suddwatch.db"))
    log_dir: Path = field(default_factory=lambda: _root() / "logs")
    ml_model_path: Path = field(default_factory=lambda: _root() / "models" / "random_forest.pkl")
    scenes_registry_path: Path = field(default_factory=lambda: _data("downloaded_scenes.json"))
    runtime_settings_path: Path = field(
        default_factory=lambda: _root() / "config" / RUNTIME_SETTINGS_FILE)

    def __post_init__(self):
        """Create folders, apply dashboard overrides, and report anything missing."""
        for directory in [
            self.raw_dir, self.processed_dir, self.masks_dir, self.dem_dir,
            self.worldpop_dir, self.osm_dir, self.exclusion_masks_dir,
            self.reference_masks_dir, self.db_path.parent, self.log_dir,
            self.ml_model_path.parent,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

        self.apply_runtime_overrides()

        # Warn (don't crash) about missing credentials so individual
        # modules can still be run and tested.
        required_credentials = {
            "COPERNICUS_USER": self.copernicus_user,
            "COPERNICUS_PASSWORD": self.copernicus_password,
            "TWILIO_ACCOUNT_SID": self.twilio_account_sid,
            "TWILIO_AUTH_TOKEN": self.twilio_auth_token,
            "TWILIO_PHONE_NUMBER": self.twilio_phone_number,
            "SMTP_USER": self.smtp_user,
            "SMTP_PASSWORD": self.smtp_password,
        }
        missing = [name for name, value in required_credentials.items() if not value]
        if missing:
            logger.warning(
                f"Missing credentials in .env file: {', '.join(missing)}. "
                f"Some modules may not function correctly."
            )
        else:
            logger.info("All credentials loaded successfully.")

        if not Path(self.snap_gpt_path).exists():
            logger.warning(
                f"SNAP GPT not found at {self.snap_gpt_path}. "
                f"Preprocessing module will not function. "
                f"Set SNAP_GPT_PATH in .env if SNAP is installed elsewhere."
            )
        else:
            logger.info(f"SNAP GPT found at {self.snap_gpt_path}")

        for name, path in {
            "Copernicus DEM": self.local_dem_path,
            "WorldPop population": self.worldpop_path,
            "OSM roads": self.osm_roads_path,
            "OSM health facilities": self.osm_health_path,
            "OSM villages": self.osm_villages_path,
        }.items():
            if path.exists():
                logger.info(f"Data file found: {name} ({path.name})")
            else:
                logger.warning(f"Data file missing: {name} at {path}")

        logger.info(f"SuddWatch configuration loaded. Project root: {self.project_root}")

    # --------------------------------------------------------
    # Runtime overrides (dashboard → pipeline)
    # --------------------------------------------------------
    def apply_runtime_overrides(self) -> dict:
        """Apply tuning values saved by the dashboard, if any. Returns what was applied."""
        applied = {}
        path = Path(self.runtime_settings_path)
        if not path.exists():
            return applied
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Ignoring unreadable runtime settings {path}: {e}")
            return applied
        for key, cast in RUNTIME_OVERRIDABLE.items():
            if key in data and data[key] is not None:
                try:
                    setattr(self, key, cast(data[key]))
                    applied[key] = getattr(self, key)
                except (TypeError, ValueError):
                    logger.warning(f"Ignoring invalid runtime setting {key}={data[key]!r}")
        if applied:
            logger.info(f"Runtime overrides applied from {path.name}: {applied}")
        return applied


def save_runtime_settings(updates: dict, path: Optional[Path] = None) -> Path:
    """
    Merge `updates` into config/runtime_settings.json (used by the dashboard).
    Only keys in RUNTIME_OVERRIDABLE are accepted.
    """
    path = Path(path) if path else _root() / "config" / RUNTIME_SETTINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    current = {}
    if path.exists():
        try:
            current = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            current = {}
    for key, value in updates.items():
        if key not in RUNTIME_OVERRIDABLE:
            raise KeyError(f"{key} is not a runtime-overridable setting")
        current[key] = RUNTIME_OVERRIDABLE[key](value)
    path.write_text(json.dumps(current, indent=2))
    return path


def load_runtime_settings(path: Optional[Path] = None) -> dict:
    """Read config/runtime_settings.json (empty dict if missing/unreadable)."""
    path = Path(path) if path else _root() / "config" / RUNTIME_SETTINGS_FILE
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure logging for the whole pipeline: console + logs/pipeline.log.

    Uses force=True so calling it again (e.g. from tests or a second
    entry point) replaces the handlers instead of silently doing nothing.
    """
    log_dir = _root() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, str(log_level).upper(), None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(fmt)
    file_handler = logging.FileHandler(log_dir / "pipeline.log")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(fmt)

    logging.basicConfig(level=numeric_level,
                        handlers=[console_handler, file_handler], force=True)
    logger.info("Logging system initialised.")


# Quick self-test: python3 src/config.py
if __name__ == "__main__":
    setup_logging()
    config = Config()
    print("\n" + "=" * 55)
    print("SuddWatch Configuration Verification")
    print("=" * 55)
    for label, value in [
        ("Project root", config.project_root),
        ("Bounding box", config.bounding_box),
        ("SNAP GPT", config.snap_gpt_path),
        ("Database", config.db_path),
        ("Local DEM", config.local_dem_path),
        ("WorldPop", config.worldpop_path),
        ("Baseline", config.baseline_path),
        ("SMS recipients", config.sms_recipients),
        ("Email recipients", config.email_recipients),
        ("Alert thresholds", f"{config.alert_flood_threshold_ha} ha / "
                             f"{config.alert_population_threshold} people"),
        ("Copernicus user", (config.copernicus_user[:4] + "****") if config.copernicus_user else "(not set)"),
    ]:
        print(f"  {label:<17}: {value}")
    print("=" * 55 + "\n")
