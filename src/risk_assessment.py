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
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.warp import reproject, transform_bounds

from src.config import Config
from src import raster_utils as ru

# --- Module logger ---
logger = logging.getLogger(__name__)


def _clean_name(value, fallback: str) -> str:
    """OSM names can be missing (None/NaN) — return a readable fallback."""
    if value is None:
        return fallback
    if isinstance(value, float) and math.isnan(value):
        return fallback
    text = str(value).strip()
    return text if text and text.lower() != "nan" else fallback


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

        # Optional state boundaries — loaded lazily by _load_states()
        self._states: Optional[gpd.GeoDataFrame] = None

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
    # SHARED HELPERS
    # ============================================================

    def _mask_grid(self, mask_data: np.ndarray, mask_profile: dict):
        """(transform, crs, shape, pixel_size_m) of a flood mask."""
        transform = mask_profile["transform"]
        crs = ru.grid_crs(mask_profile)
        shape = mask_data.shape
        return transform, crs, shape, ru.pixel_size_m(transform, crs, shape[0])

    def _buffer_px(self, pixel_m: float) -> int:
        """Near-flood search radius in mask pixels (at least 1)."""
        buffer_m = float(getattr(self.config, "near_flood_buffer_m", 1000.0))
        return max(1, int(math.ceil(buffer_m / max(pixel_m, 1e-6))))

    def _points_in_grid(self, gdf: gpd.GeoDataFrame, mask_data, mask_profile):
        """
        Keep only features inside the mask's footprint and work out the
        mask pixel each falls in. Returns (subset, rows, cols).
        """
        transform, crs, shape, _ = self._mask_grid(mask_data, mask_profile)
        if gdf.crs is not None and CRS.from_user_input(gdf.crs) != crs:
            gdf = gdf.to_crs(crs)
        west, south, east, north = ru.grid_bounds(transform, *shape)
        subset = gdf.cx[west:east, south:north]
        subset = subset[subset.geometry.notna() & ~subset.geometry.is_empty]
        if len(subset) == 0:
            return subset, np.array([], int), np.array([], int)
        pts = subset.geometry.representative_point()
        rows, cols, inside = ru.sample_points(pts.x.values, pts.y.values, transform, shape)
        return subset[inside], rows[inside], cols[inside]

    def _classify_points(self, mask_data, rows, cols, pixel_m):
        """For each point: 'flooded', 'near' or None."""
        in_flood = mask_data[rows, cols] == 1
        near = ru.any_in_radius(mask_data, rows, cols, self._buffer_px(pixel_m))
        return np.where(in_flood, "flooded", np.where(near, "near", None))

    def _population_at(self, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
        """People in the WorldPop 1 km cell containing each point (0 if unknown)."""
        if self._population_data is None:
            return np.zeros(len(lons), dtype=int)
        t = self._population_profile["transform"]
        rows, cols, inside = ru.sample_points(lons, lats, t, self._population_data.shape)
        out = np.zeros(len(lons), dtype=float)
        out[inside] = self._population_data[rows[inside], cols[inside]]
        return np.round(out).astype(int)

    def _load_states(self) -> Optional[gpd.GeoDataFrame]:
        """
        Optional state (admin-1) boundaries used to label villages with
        their state. Put a GeoJSON at data/admin/south_sudan_states.geojson
        (e.g. the OCHA COD-AB admin1 layer from data.humdata.org).
        """
        if self._states is not None:
            return self._states if len(self._states) else None
        path = Path(getattr(self.config, "admin_states_path", ""))
        if not path or not path.exists():
            self._states = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            return None
        try:
            states = gpd.read_file(str(path)).to_crs("EPSG:4326")
            name_col = next((c for c in ["ADM1_EN", "admin1Name_en", "NAME_1",
                                         "state", "name", "NAME"] if c in states.columns), None)
            if name_col is None:
                logger.warning(f"No state-name column found in {path.name}")
                self._states = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
                return None
            self._states = states[[name_col, "geometry"]].rename(columns={name_col: "state_name"})
            logger.info(f"State boundaries loaded: {len(self._states)} states")
            return self._states
        except Exception as e:
            logger.warning(f"Could not load state boundaries: {e}")
            self._states = gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
            return None

    def _state_for(self, gdf: gpd.GeoDataFrame) -> list:
        """State name for each feature: OSM tag if present, else boundary lookup, else 'Unknown'."""
        names = []
        for col in ["is_in:state", "addr:state", "is_in"]:
            if col in gdf.columns:
                names = [str(v) if v not in (None, "") and str(v) != "nan" else None
                         for v in gdf[col]]
                break
        if not names:
            names = [None] * len(gdf)
        states = self._load_states()
        if states is not None and any(n is None for n in names):
            pts = gpd.GeoDataFrame(geometry=gdf.geometry.representative_point(),
                                   crs=gdf.crs).to_crs("EPSG:4326")
            joined = gpd.sjoin(pts, states, how="left", predicate="within")
            joined = joined[~joined.index.duplicated(keep="first")]
            lookup = joined["state_name"].reindex(pts.index).tolist()
            names = [n if n is not None else (l if isinstance(l, str) else None)
                     for n, l in zip(names, lookup)]
        return [n or "Unknown" for n in names]

    # ============================================================
    # POPULATION ESTIMATION
    # ============================================================

    def _estimate_population(self, mask_data: np.ndarray, mask_profile: dict) -> int:
        """
        People living in flooded areas.

        WorldPop stores a head-count per ~1 km cell. For each cell we work
        out what fraction of it is flooded (by averaging the flood mask onto
        the WorldPop grid) and count that fraction of its people:

            affected = Σ  population(cell) × flooded_fraction(cell)

        (Resampling the head-counts DOWN to the 10 m mask grid and summing,
        as the original code did, counts every person ~10,000 times.)
        """
        if self._population_data is None:
            logger.warning("Population data not loaded. Call load_population_data() first.")
            return 0
        try:
            transform, crs, shape, _ = self._mask_grid(mask_data, mask_profile)
            pop_t = self._population_profile["transform"]
            pop_crs = ru.grid_crs(self._population_profile)
            H, W = self._population_data.shape

            west, south, east, north = transform_bounds(
                crs, pop_crs, *ru.grid_bounds(transform, *shape))
            inv = ~pop_t
            c0, r0 = ru.apply_affine(inv, west, north)
            c1, r1 = ru.apply_affine(inv, east, south)
            r0, r1 = sorted((r0, r1))
            c0, c1 = sorted((c0, c1))
            r0, c0 = max(int(math.floor(r0)), 0), max(int(math.floor(c0)), 0)
            r1, c1 = min(int(math.ceil(r1)), H), min(int(math.ceil(c1)), W)
            if r0 >= r1 or c0 >= c1:
                logger.info("Flood mask does not overlap the WorldPop grid.")
                return 0

            sub = self._population_data[r0:r1, c0:c1]
            sub_t = Affine(pop_t.a, pop_t.b, pop_t.c + c0 * pop_t.a,
                           pop_t.d, pop_t.e, pop_t.f + r0 * pop_t.e)
            frac = np.zeros(sub.shape, dtype=np.float32)
            reproject(
                source=(mask_data == 1).astype(np.float32), destination=frac,
                src_transform=transform, src_crs=crs,
                dst_transform=sub_t, dst_crs=pop_crs,
                resampling=Resampling.average,
            )
            frac = np.clip(np.nan_to_num(frac, nan=0.0), 0.0, 1.0)
            affected = int(round(float(np.sum(sub * frac))))
            logger.info(f"Estimated affected population: {affected:,} people")
            return affected
        except Exception as e:
            logger.error(f"Population estimation failed: {e}")
            return 0

    # ============================================================
    # VILLAGES
    # ============================================================

    def _identify_affected_villages(self, mask_data: np.ndarray, mask_profile: dict) -> list:
        """
        Villages that are flooded or close to flooding.

        - village pixel is flooded                      → 90 % risk, "High"
        - flooded pixel within near_flood_buffer_m      → 50 % risk, "Medium"
        - otherwise the village is not listed.

        estimated_population = people in the village's WorldPop 1 km cell.
        """
        if self._villages is None or len(self._villages) == 0:
            logger.warning("Villages data not loaded. Skipping village identification.")
            return []
        try:
            _, _, _, pixel_m = self._mask_grid(mask_data, mask_profile)
            subset, rows, cols = self._points_in_grid(self._villages, mask_data, mask_profile)
            if len(subset) == 0:
                logger.info("No villages inside the flood mask footprint.")
                return []
            status = self._classify_points(mask_data, rows, cols, pixel_m)
            keep = status != None  # noqa: E711 — numpy elementwise
            subset, status = subset[keep], status[keep]
            if len(subset) == 0:
                logger.info("No villages flooded or near the flood extent.")
                return []

            pts = subset.geometry.representative_point().to_crs("EPSG:4326")
            pops = self._population_at(pts.x.values, pts.y.values)
            states = self._state_for(subset)

            villages = []
            for (_, v), st, pop, lon, lat, state in zip(
                    subset.iterrows(), status, pops, pts.x.values, pts.y.values, states):
                flooded = st == "flooded"
                villages.append({
                    "village_name": _clean_name(v.get("name"), "Unnamed settlement"),
                    "place_type": _clean_name(v.get("place"), ""),
                    "state": state,
                    "county": "",
                    "flood_risk_percentage": 90.0 if flooded else 50.0,
                    "risk_level": "High" if flooded else "Medium",
                    "status": st,
                    "recommended_action": "Evacuate / relocate" if flooded else "Monitor & prepare",
                    "latitude": round(float(lat), 6),
                    "longitude": round(float(lon), 6),
                    "estimated_population": int(pop),
                })
            villages.sort(key=lambda d: (-d["flood_risk_percentage"], -d["estimated_population"]))
            logger.info(
                f"Identified {len(villages)} affected villages "
                f"({sum(v['status'] == 'flooded' for v in villages)} flooded)."
            )
            return villages
        except Exception as e:
            logger.error(f"Village identification failed: {e}")
            return []

    # ============================================================
    # ROADS
    # ============================================================

    def _identify_inaccessible_roads(self, mask_data: np.ndarray, mask_profile: dict) -> list:
        """
        Road segments that cross flooded pixels.

        Each road is densified to roughly one point per mask pixel and every
        point is checked against the mask. A road is reported if any point is
        flooded; flooded_length_km = total length × share of flooded points.
        """
        if self._roads is None or len(self._roads) == 0:
            logger.warning("Roads data not loaded. Skipping road identification.")
            return []
        try:
            transform, crs, shape, _ = self._mask_grid(mask_data, mask_profile)
            roads = self._roads
            if roads.crs is not None and CRS.from_user_input(roads.crs) != crs:
                roads = roads.to_crs(crs)
            west, south, east, north = ru.grid_bounds(transform, *shape)
            roads = roads.cx[west:east, south:north]
            roads = roads[roads.geometry.notna() & ~roads.geometry.is_empty]
            if len(roads) == 0:
                logger.info("No roads inside the flood mask footprint.")
                return []

            step = max(min(abs(transform.a), abs(transform.e)), 1e-9)
            dense = shapely.segmentize(roads.geometry.values, step)
            coords, idx = shapely.get_coordinates(dense, return_index=True)
            r, c, inside = ru.sample_points(coords[:, 0], coords[:, 1], transform, shape)
            flooded = np.zeros(len(coords), dtype=float)
            flooded[inside] = (mask_data[r[inside], c[inside]] == 1)
            n = len(roads)
            n_pts = np.bincount(idx, minlength=n).astype(float)
            n_flood = np.bincount(idx, weights=flooded, minlength=n)
            hit = n_flood > 0
            if not hit.any():
                logger.info("No roads cross flooded pixels.")
                return []

            hit_roads = roads[hit]
            try:
                metric = hit_roads.to_crs(hit_roads.estimate_utm_crs())
                lengths_km = metric.geometry.length.values / 1000.0
            except Exception:
                lengths_km = hit_roads.geometry.length.values * 111.0
            share = n_flood[hit] / np.maximum(n_pts[hit], 1)

            result = []
            for (_, road), length, sh in zip(hit_roads.iterrows(), lengths_km, share):
                result.append({
                    "name": _clean_name(road.get("name"), "Unnamed road"),
                    "infrastructure_type": "road",
                    "facility_type": _clean_name(road.get("highway"), "road"),
                    "segment_length_km": round(float(length), 2),
                    "flooded_length_km": round(float(length * sh), 2),
                    "status": "inaccessible",
                    "alt_route": "",
                })
            result.sort(key=lambda d: -d["flooded_length_km"])
            logger.info(f"Identified {len(result)} road segments crossing flood water.")
            return result
        except Exception as e:
            logger.error(f"Road identification failed: {e}")
            return []

    # ============================================================
    # HEALTH FACILITIES
    # ============================================================

    @staticmethod
    def _facility_type(row) -> str:
        tags = str(row.get("other_tags") or "").lower()
        for key in ["healthcare", "amenity"]:
            m = re.search(rf'"{key}"=>"([^"]+)"', tags)
            if m:
                return m.group(1)
        for tag in ["hospital", "clinic", "health_post", "health_centre",
                    "dispensary", "pharmacy", "doctors"]:
            if tag in tags:
                return tag
        return str(row.get("facility_type") or "health_facility")

    def _identify_health_at_risk(self, mask_data: np.ndarray, mask_profile: dict) -> list:
        """
        Health facilities that are flooded (status 'flooded') or within
        near_flood_buffer_m of flooding (status 'at_risk').
        """
        if self._health_facilities is None or len(self._health_facilities) == 0:
            logger.warning("Health facilities data not loaded. Skipping.")
            return []
        try:
            _, _, _, pixel_m = self._mask_grid(mask_data, mask_profile)
            subset, rows, cols = self._points_in_grid(
                self._health_facilities, mask_data, mask_profile)
            if len(subset) == 0:
                logger.info("No health facilities inside the flood mask footprint.")
                return []
            status = self._classify_points(mask_data, rows, cols, pixel_m)
            keep = status != None  # noqa: E711
            subset, status = subset[keep], status[keep]
            pts = subset.geometry.representative_point().to_crs("EPSG:4326")

            result = []
            for (_, f), st, lon, lat in zip(subset.iterrows(), status, pts.x.values, pts.y.values):
                result.append({
                    "name": _clean_name(f.get("name"), "Unnamed facility"),
                    "infrastructure_type": "health_facility",
                    "facility_type": self._facility_type(f),
                    "status": "flooded" if st == "flooded" else "at_risk",
                    "latitude": round(float(lat), 6),
                    "longitude": round(float(lon), 6),
                    "coordinates": {"lat": round(float(lat), 6), "lon": round(float(lon), 6)},
                })
            logger.info(f"Identified {len(result)} health facilities flooded or at risk.")
            return result
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
                "population_in_affected_villages": int(sum(
                    v.get("estimated_population", 0) for v in affected_villages)),
                "flooded_road_km": round(sum(
                    r.get("flooded_length_km", 0) for r in inaccessible_roads), 2),
                "health_facilities_flooded": len(
                    [h for h in health_at_risk if h.get("status") == "flooded"]),
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
