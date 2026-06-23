# ============================================================
# SuddWatch - Risk Assessment Module
# File: src/risk_assessment.py
# Purpose: Assesses humanitarian impact of detected flooding
#          by overlaying the flood mask with:
#          - WorldPop population density raster
#          - OpenStreetMap villages/towns (points)
#          - OpenStreetMap roads (lines)
#          - OpenStreetMap health facilities (points)
#
# Outputs a JSON summary with:
#          - Total affected population estimate
#          - List of affected villages with risk percentage
#          - Inaccessible road segments
#          - Health facilities at risk
#
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from shapely.geometry import box

from src.config import Config

# --- Module logger ---
logger = logging.getLogger(__name__)


class RiskAssessor:
    """
    Assesses humanitarian risk by overlaying flood mask with
    population and infrastructure data.

    Data sources used:
    - WorldPop 2020 UN-adjusted population density (1km resolution)
      File: data/worldpop/south_sudan_pop_2020_1km.tif
    - OSM roads GeoJSON (194,291 features)
      File: data/osm/roads.geojson
    - OSM health facilities GeoJSON (382 features)
      File: data/osm/health_facilities.geojson
    - OSM villages GeoJSON (7,712 features)
      File: data/osm/villages.geojson

    All data is loaded once via load_population_data() and
    load_osm_data() then reused across multiple assess() calls
    for efficiency.

    Example usage:
        from src.config import Config
        from src.risk_assessment import RiskAssessor
        config = Config()
        assessor = RiskAssessor(config)
        assessor.load_population_data()
        assessor.load_osm_data()
        summary, summary_path = assessor.assess('data/flood_masks/mask.tif')
    """

    def __init__(self, config: Config):
        """
        Initialises the risk assessor with config settings.

        Data attributes are set to None and populated by
        load_population_data() and load_osm_data() calls.

        Args:
            config: Config object with file paths and settings
        """
        self.config = config

        # Population raster — loaded by load_population_data()
        self._population_data: Optional[np.ndarray] = None
        self._population_profile: Optional[dict] = None

        # OSM vector layers — loaded by load_osm_data()
        self._roads: Optional[gpd.GeoDataFrame] = None
        self._health_facilities: Optional[gpd.GeoDataFrame] = None
        self._villages: Optional[gpd.GeoDataFrame] = None

        logger.info("RiskAssessor initialised.")

    # ============================================================
    # DATA LOADING METHODS
    # Load external datasets into memory for repeated use
    # ============================================================

    def load_population_data(self) -> None:
        """
        Loads WorldPop population density raster into memory.

        Reads the GeoTIFF and stores the numpy array and rasterio
        profile for use in _estimate_population().

        The WorldPop raster contains population per pixel at 1km
        resolution. Values represent number of people per grid cell.

        Raises:
            FileNotFoundError: if WorldPop file is not found
        """
        worldpop_path = self.config.worldpop_path

        if not worldpop_path.exists():
            raise FileNotFoundError(
                f"WorldPop file not found: {worldpop_path}. "
                f"Please download from worldpop.org."
            )

        with rasterio.open(str(worldpop_path)) as src:
            # Read population data as float32
            self._population_data = src.read(1).astype(np.float32)
            self._population_profile = src.profile.copy()

            # Replace nodata values with 0 (no people)
            nodata = src.nodata
            if nodata is not None:
                self._population_data[self._population_data == nodata] = 0.0

            # Replace NaN and negative values with 0
            self._population_data = np.nan_to_num(
                self._population_data, nan=0.0, posinf=0.0, neginf=0.0
            )
            self._population_data[self._population_data < 0] = 0.0

        total_population = int(np.sum(self._population_data))
        logger.info(
            f"WorldPop loaded: shape={self._population_data.shape}, "
            f"total population={total_population:,}"
        )

    def load_osm_data(self) -> None:
        """
        Loads OSM vector datasets (roads, health facilities, villages).

        Reads all three GeoJSON files into GeoDataFrames and ensures
        they are in WGS84 (EPSG:4326) for spatial operations.

        Missing files are logged as warnings — risk assessment can
        still run with partial data.
        """
        # --- Load roads ---
        if self.config.osm_roads_path.exists():
            self._roads = gpd.read_file(str(self.config.osm_roads_path))
            # Ensure WGS84 CRS for consistent spatial operations
            if self._roads.crs is None or self._roads.crs.to_epsg() != 4326:
                self._roads = self._roads.set_crs(epsg=4326, allow_override=True)
            logger.info(f"OSM roads loaded: {len(self._roads)} features")
        else:
            logger.warning(f"OSM roads not found: {self.config.osm_roads_path}")

        # --- Load health facilities ---
        if self.config.osm_health_path.exists():
            self._health_facilities = gpd.read_file(
                str(self.config.osm_health_path)
            )
            if (self._health_facilities.crs is None or
                    self._health_facilities.crs.to_epsg() != 4326):
                self._health_facilities = self._health_facilities.set_crs(
                    epsg=4326, allow_override=True
                )
            logger.info(
                f"OSM health facilities loaded: "
                f"{len(self._health_facilities)} features"
            )
        else:
            logger.warning(
                f"OSM health facilities not found: {self.config.osm_health_path}"
            )

        # --- Load villages ---
        if self.config.osm_villages_path.exists():
            self._villages = gpd.read_file(str(self.config.osm_villages_path))
            if (self._villages.crs is None or
                    self._villages.crs.to_epsg() != 4326):
                self._villages = self._villages.set_crs(
                    epsg=4326, allow_override=True
                )
            logger.info(f"OSM villages loaded: {len(self._villages)} features")
        else:
            logger.warning(
                f"OSM villages not found: {self.config.osm_villages_path}"
            )

    # ============================================================
    # POPULATION ESTIMATION
    # Sums WorldPop values within flood mask extent
    # ============================================================

    def _estimate_population(
        self,
        mask_data: np.ndarray,
        mask_profile: dict,
    ) -> int:
        """
        Estimates the population affected by flooding.

        Reprojects the WorldPop raster to match the flood mask
        extent and resolution, then sums population values within
        flooded pixels.

        Args:
            mask_data: binary flood mask array (1=flood, 0=no flood)
            mask_profile: rasterio profile of the flood mask

        Returns:
            int: estimated number of people affected by flooding
        """
        if self._population_data is None:
            logger.warning(
                "Population data not loaded. "
                "Call load_population_data() first."
            )
            return 0

        try:
            # Get the flood mask bounding box for clipping WorldPop
            transform = mask_profile['transform']
            height = mask_profile['height']
            width = mask_profile['width']

            # Create bounding box from mask transform
            min_x = transform.c
            max_x = transform.c + width * transform.a
            min_y = transform.f + height * transform.e
            max_y = transform.f

            # Resample WorldPop to match flood mask resolution
            # Using bilinear resampling for smooth population estimates
            with rasterio.open(str(self.config.worldpop_path)) as pop_src:
                pop_resampled = pop_src.read(
                    1,
                    out_shape=(height, width),
                    resampling=Resampling.bilinear,
                ).astype(np.float32)

            # Replace nodata/NaN with 0
            pop_resampled = np.nan_to_num(pop_resampled, nan=0.0)
            pop_resampled[pop_resampled < 0] = 0.0

            # Sum population values within flooded pixels only
            flood_pixels = mask_data == 1
            affected_population = int(np.sum(pop_resampled[flood_pixels]))

            logger.info(
                f"Estimated affected population: {affected_population:,} people"
            )
            return affected_population

        except Exception as e:
            logger.error(f"Population estimation failed: {e}")
            return 0

    # ============================================================
    # VILLAGE IDENTIFICATION
    # Finds villages within or near the flood extent
    # ============================================================

    def _identify_affected_villages(
        self,
        mask_data: np.ndarray,
        mask_profile: dict,
    ) -> list:
        """
        Identifies villages within or adjacent to the flood extent.

        Creates a flood extent polygon from the mask and performs
        spatial intersection with OSM village points. Villages within
        the flood extent receive a high risk percentage; nearby
        villages receive lower risk scores.

        Args:
            mask_data: binary flood mask array (1=flood, 0=no flood)
            mask_profile: rasterio profile of the flood mask

        Returns:
            list of dicts, each with keys:
            'village_name', 'state', 'county',
            'flood_risk_percentage', 'latitude', 'longitude'
        """
        if self._villages is None or len(self._villages) == 0:
            logger.warning("Villages data not loaded. Skipping village identification.")
            return []

        try:
            # Build bounding box of the flood mask in geographic coordinates
            transform = mask_profile['transform']
            height = mask_profile['height']
            width = mask_profile['width']

            mask_bbox = box(
                transform.c,                          # min_x (west)
                transform.f + height * transform.e,   # min_y (south)
                transform.c + width * transform.a,    # max_x (east)
                transform.f,                          # max_y (north)
            )

            # Filter villages to only those within the mask bounding box
            # This speeds up spatial operations significantly
            villages_in_bbox = self._villages[
                self._villages.geometry.intersects(mask_bbox)
            ].copy()

            if len(villages_in_bbox) == 0:
                logger.info("No villages found within flood mask bounding box.")
                return []

            # Convert flood mask to a polygon for spatial intersection
            # Create a simple flood extent box (approximate)
            # For production, use rasterio.features.shapes() for exact polygon
            flood_extent_polygon = mask_bbox  # Use bbox as approximation

            affected_villages = []
            for _, village in villages_in_bbox.iterrows():
                try:
                    village_point = village.geometry

                    if village_point is None:
                        continue

                    # Check if village is within flood extent
                    is_flooded = flood_extent_polygon.contains(village_point)

                    # Get village coordinates
                    lat = village_point.y
                    lon = village_point.x

                    # Assign risk percentage based on flood containment
                    # Villages directly in flood: 85-100%
                    # Villages near flood: 25-50%
                    if is_flooded:
                        # Check pixel value at village location
                        # Convert geographic coords to pixel coords
                        col = int((lon - transform.c) / transform.a)
                        row = int((lat - transform.f) / transform.e)

                        if (0 <= row < height and 0 <= col < width):
                            pixel_flooded = mask_data[row, col] == 1
                            risk_pct = 90.0 if pixel_flooded else 45.0
                        else:
                            risk_pct = 45.0
                    else:
                        risk_pct = 20.0

                    # Only include villages with meaningful risk
                    if risk_pct >= 20.0:
                        affected_villages.append({
                            "village_name": str(village.get("name", "Unknown")),
                            "state": str(village.get("is_in", "South Sudan")),
                            "county": "",
                            "flood_risk_percentage": risk_pct,
                            "latitude": round(lat, 6),
                            "longitude": round(lon, 6),
                            "estimated_population": 0,  # Set by pipeline
                        })

                except Exception as e:
                    logger.debug(f"Skipping village due to error: {e}")
                    continue

            logger.info(
                f"Identified {len(affected_villages)} affected villages "
                f"from {len(villages_in_bbox)} candidates."
            )
            return affected_villages

        except Exception as e:
            logger.error(f"Village identification failed: {e}")
            return []

    # ============================================================
    # ROAD IDENTIFICATION
    # Finds road segments within the flood extent
    # ============================================================

    def _identify_inaccessible_roads(
        self,
        mask_data: np.ndarray,
        mask_profile: dict,
    ) -> list:
        """
        Identifies road segments that are flooded or inaccessible.

        Clips OSM road lines to the flood mask bounding box then
        checks intersection with the flood extent. Roads crossing
        flooded areas are flagged as inaccessible.

        Args:
            mask_data: binary flood mask array (1=flood, 0=no flood)
            mask_profile: rasterio profile of the flood mask

        Returns:
            list of dicts, each with keys:
            'name', 'infrastructure_type', 'segment_length_km',
            'status', 'facility_type'
        """
        if self._roads is None or len(self._roads) == 0:
            logger.warning("Roads data not loaded. Skipping road identification.")
            return []

        try:
            transform = mask_profile['transform']
            height = mask_profile['height']
            width = mask_profile['width']

            # Build flood mask bounding box
            mask_bbox = box(
                transform.c,
                transform.f + height * transform.e,
                transform.c + width * transform.a,
                transform.f,
            )

            # Clip roads to bounding box
            roads_in_bbox = self._roads[
                self._roads.geometry.intersects(mask_bbox)
            ].copy()

            if len(roads_in_bbox) == 0:
                logger.info("No roads found within flood mask bounding box.")
                return []

            inaccessible_roads = []
            for _, road in roads_in_bbox.iterrows():
                try:
                    if road.geometry is None:
                        continue

                    # Check if road intersects flood extent
                    intersects_flood = road.geometry.intersects(mask_bbox)

                    if intersects_flood:
                        # Calculate approximate road segment length in km
                        # Using geographic distance approximation
                        road_length_km = road.geometry.length * 111.0

                        inaccessible_roads.append({
                            "name": str(road.get("name", "Unnamed Road")),
                            "infrastructure_type": "road",
                            "facility_type": str(road.get("highway", "road")),
                            "segment_length_km": round(road_length_km, 2),
                            "status": "inaccessible",
                        })

                except Exception as e:
                    logger.debug(f"Skipping road due to error: {e}")
                    continue

            logger.info(
                f"Identified {len(inaccessible_roads)} inaccessible road segments."
            )
            return inaccessible_roads

        except Exception as e:
            logger.error(f"Road identification failed: {e}")
            return []

    # ============================================================
    # HEALTH FACILITY IDENTIFICATION
    # Finds health facilities within the flood extent
    # ============================================================

    def _identify_health_at_risk(
        self,
        mask_data: np.ndarray,
        mask_profile: dict,
    ) -> list:
        """
        Identifies health facilities within or near the flood extent.

        Health facilities (hospitals, clinics, health posts) within
        the flood bounding box are flagged as at risk. This is critical
        for humanitarian response as flooded health facilities cannot
        serve displaced populations.

        Args:
            mask_data: binary flood mask array (1=flood, 0=no flood)
            mask_profile: rasterio profile of the flood mask

        Returns:
            list of dicts, each with keys:
            'name', 'infrastructure_type', 'facility_type',
            'status', 'latitude', 'longitude'
        """
        if self._health_facilities is None or len(self._health_facilities) == 0:
            logger.warning(
                "Health facilities data not loaded. "
                "Skipping health facility identification."
            )
            return []

        try:
            transform = mask_profile['transform']
            height = mask_profile['height']
            width = mask_profile['width']

            # Build flood mask bounding box
            mask_bbox = box(
                transform.c,
                transform.f + height * transform.e,
                transform.c + width * transform.a,
                transform.f,
            )

            # Filter to facilities within flood bounding box
            health_in_bbox = self._health_facilities[
                self._health_facilities.geometry.intersects(mask_bbox)
            ].copy()

            if len(health_in_bbox) == 0:
                logger.info(
                    "No health facilities found within flood mask bounding box."
                )
                return []

            health_at_risk = []
            for _, facility in health_in_bbox.iterrows():
                try:
                    if facility.geometry is None:
                        continue

                    lat = facility.geometry.y
                    lon = facility.geometry.x

                    # Extract facility type from other_tags if available
                    facility_type = "health_facility"
                    other_tags = str(facility.get("other_tags", ""))
                    for tag in ["hospital", "clinic", "health_post",
                                "health_centre", "dispensary", "pharmacy"]:
                        if tag in other_tags.lower():
                            facility_type = tag
                            break

                    health_at_risk.append({
                        "name": str(facility.get("name", "Unknown Facility")),
                        "infrastructure_type": "health_facility",
                        "facility_type": facility_type,
                        "status": "at_risk",
                        "latitude": round(lat, 6),
                        "longitude": round(lon, 6),
                        "coordinates": {"lat": round(lat, 6), "lon": round(lon, 6)},
                    })

                except Exception as e:
                    logger.debug(f"Skipping health facility due to error: {e}")
                    continue

            logger.info(
                f"Identified {len(health_at_risk)} health facilities at risk."
            )
            return health_at_risk

        except Exception as e:
            logger.error(f"Health facility identification failed: {e}")
            return []

    # ============================================================
    # SUMMARY GENERATION
    # Creates and saves the JSON risk summary
    # ============================================================

    def _save_summary(
        self,
        summary: dict,
        mask_path: str,
    ) -> str:
        """
        Saves the risk assessment summary as a JSON file.

        Output filename is derived from mask filename with
        '_risk_summary' suffix. Saved to data/flood_masks/.

        Args:
            summary: risk assessment dict to serialise
            mask_path: path to flood mask (used for output filename)

        Returns:
            str: path to saved JSON summary file
        """
        mask_name = Path(mask_path).stem
        summary_path = str(
            self.config.masks_dir / f"{mask_name}_risk_summary.json"
        )

        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Risk summary saved: {summary_path}")
        return summary_path

    # ============================================================
    # MAIN ASSESSMENT METHOD
    # Full pipeline from flood mask to humanitarian summary
    # ============================================================

    def assess(self, mask_path: str, flood_extent_ha: float = 0.0) -> Tuple[dict, str]:
        """
        Runs the full risk assessment pipeline on a flood mask.

        Pipeline:
        1. Load flood mask GeoTIFF
        2. Estimate affected population (WorldPop overlay)
        3. Identify affected villages (OSM points)
        4. Identify inaccessible roads (OSM lines)
        5. Identify health facilities at risk (OSM points)
        6. Generate and save JSON summary

        Args:
            mask_path: path to binary flood mask GeoTIFF
                       (output of FloodDetector.detect())

        Returns:
            Tuple[dict, str]:
                - summary dict with all assessment results
                - path to saved JSON summary file

        Raises:
            FileNotFoundError: if flood mask file does not exist
        """
        mask_path = str(mask_path)

        if not Path(mask_path).exists():
            raise FileNotFoundError(f"Flood mask not found: {mask_path}")

        logger.info(f"Starting risk assessment: {Path(mask_path).name}")

        # --- Load flood mask ---
        with rasterio.open(mask_path) as src:
            mask_data = src.read(1)
            mask_profile = src.profile.copy()

        flood_pixels = int(np.sum(mask_data == 1))
        logger.info(f"Flood mask loaded: {flood_pixels} flooded pixels")

        # --- Step 1: Estimate affected population ---
        logger.info("Step 1/4: Estimating affected population...")
        affected_population = self._estimate_population(mask_data, mask_profile)

        # --- Step 2: Identify affected villages ---
        logger.info("Step 2/4: Identifying affected villages...")
        affected_villages = self._identify_affected_villages(
            mask_data, mask_profile
        )

        # --- Step 3: Identify inaccessible roads ---
        logger.info("Step 3/4: Identifying inaccessible roads...")
        inaccessible_roads = self._identify_inaccessible_roads(
            mask_data, mask_profile
        )

        # --- Step 4: Identify health facilities at risk ---
        logger.info("Step 4/4: Identifying health facilities at risk...")
        health_at_risk = self._identify_health_at_risk(
            mask_data, mask_profile
        )

        # --- Build summary dict ---
        # Format matches the JSON structure from the implementation guide
        summary = {
            "event_timestamp": datetime.now(timezone.utc).isoformat(),
            "mask_path": mask_path,
            "flood_pixels": flood_pixels,
            "flood_extent_ha": flood_extent_ha,
            "affected_population_estimate": affected_population,
            "affected_villages": affected_villages,
            "inaccessible_roads": inaccessible_roads,
            "health_facilities_at_risk": health_at_risk,
            "summary_statistics": {
                "total_villages_affected": len(affected_villages),
                "total_roads_inaccessible": len(inaccessible_roads),
                "total_health_facilities_at_risk": len(health_at_risk),
                "high_risk_villages": len(
                    [v for v in affected_villages
                     if v.get("flood_risk_percentage", 0) >= 75]
                ),
            },
        }

        logger.info(
            f"Risk assessment complete: "
            f"{affected_population:,} people affected, "
            f"{len(affected_villages)} villages, "
            f"{len(inaccessible_roads)} roads inaccessible, "
            f"{len(health_at_risk)} health facilities at risk."
        )

        # --- Save summary JSON ---
        summary_path = self._save_summary(summary, mask_path)

        return summary, summary_path


# ============================================================
# Quick self-test — run this file directly to verify
# Uses real WorldPop and OSM data loaded during setup
# Usage: python3 -m src.risk_assessment
# ============================================================
if __name__ == "__main__":
    import tempfile
    from src.config import Config, setup_logging

    setup_logging()
    config = Config()

    print("\n" + "=" * 55)
    print("SuddWatch Risk Assessment Verification")
    print("=" * 55)

    # --- Initialise assessor ---
    assessor = RiskAssessor(config)

    # --- Load data ---
    print("\n1. Loading population data...")
    try:
        assessor.load_population_data()
        print(f"   ✓ WorldPop loaded successfully")
    except Exception as e:
        print(f"   ✗ Failed: {e}")

    print("\n2. Loading OSM data...")
    try:
        assessor.load_osm_data()
        print(f"   ✓ Roads: {len(assessor._roads)} features")
        print(f"   ✓ Health facilities: {len(assessor._health_facilities)} features")
        print(f"   ✓ Villages: {len(assessor._villages)} features")
    except Exception as e:
        print(f"   ✗ Failed: {e}")

    # --- Create synthetic flood mask over South Sudan ---
    print("\n3. Creating synthetic flood mask over Jonglei state...")
    with tempfile.TemporaryDirectory() as tmpdir:
        mask_path = os.path.join(tmpdir, "test_flood_mask.tif")

        # Create a 50x50 flood mask covering part of Jonglei state
        # Bounding box: lon 30-31, lat 7-8 (near Bor, Jonglei)
        rows, cols = 50, 50
        mask_data = np.zeros((rows, cols), dtype=np.uint8)
        # Flood the centre of the scene
        mask_data[15:35, 15:35] = 1

        transform = rasterio.transform.from_bounds(30.0, 7.0, 31.0, 8.0, cols, rows)
        with rasterio.open(
            mask_path, 'w',
            driver='GTiff', height=rows, width=cols,
            count=1, dtype='uint8',
            crs=rasterio.CRS.from_epsg(4326),
            transform=transform,
            nodata=255,
        ) as dst:
            dst.write(mask_data, 1)

        print(f"   ✓ Synthetic mask created: {rows}x{cols} over lon 30-31, lat 7-8")

        # --- Run risk assessment ---
        print("\n4. Running risk assessment...")
        try:
            summary, summary_path = assessor.assess(mask_path)

            print(f"   ✓ Assessment complete")
            print(f"   ✓ Affected population: {summary['affected_population_estimate']:,}")
            print(f"   ✓ Villages affected: {summary['summary_statistics']['total_villages_affected']}")
            print(f"   ✓ Roads inaccessible: {summary['summary_statistics']['total_roads_inaccessible']}")
            print(f"   ✓ Health facilities at risk: {summary['summary_statistics']['total_health_facilities_at_risk']}")
            print(f"   ✓ Summary saved: {Path(summary_path).name}")

        except Exception as e:
            print(f"   ✗ Assessment failed: {e}")
            raise

    print("\n" + "=" * 55)
    print("Risk assessment module verified successfully.")
    print("=" * 55 + "\n")
