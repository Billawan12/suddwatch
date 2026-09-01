# ============================================================
# SuddWatch - Unit Tests: Risk Assessment Module
# File: tests/test_risk_assessment.py
# Purpose: Tests for RiskAssessor class covering:
#          - Population data loading
#          - OSM data loading
#          - Population estimation
#          - Village identification
#          - Road identification
#          - Health facility identification
#          - JSON summary generation
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import json
import pytest
import tempfile
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds
from shapely.geometry import Point, box

from src.config import Config
from src.risk_assessment import RiskAssessor


# ============================================================
# FIXTURES
# Shared test setup reused across multiple tests
# ============================================================

@pytest.fixture
def config(tmp_path):
    """
    Provides a Config object with temporary paths for testing.
    """
    config = Config()
    # Override paths with temporary directories
    config.project_root = tmp_path
    config.worldpop_path = tmp_path / "worldpop" / "south_sudan_pop_2020_1km.tif"
    config.osm_roads_path = tmp_path / "osm" / "roads.geojson"
    config.osm_health_path = tmp_path / "osm" / "health_facilities.geojson"
    config.osm_villages_path = tmp_path / "osm" / "villages.geojson"
    config.masks_dir = tmp_path / "flood_masks"
    config.db_path = tmp_path / "database" / "suddwatch.db"

    # Create directories
    config.worldpop_path.parent.mkdir(parents=True, exist_ok=True)
    config.osm_roads_path.parent.mkdir(parents=True, exist_ok=True)
    config.masks_dir.mkdir(parents=True, exist_ok=True)
    config.db_path.parent.mkdir(parents=True, exist_ok=True)

    return config


@pytest.fixture
def assessor(config):
    """
    Provides a RiskAssessor instance for testing.
    """
    return RiskAssessor(config)


@pytest.fixture
def synthetic_worldpop_tif(tmp_path):
    """
    Creates a synthetic WorldPop GeoTIFF for testing.
    """
    tif_path = tmp_path / "worldpop" / "south_sudan_pop_2020_1km.tif"
    tif_path.parent.mkdir(parents=True, exist_ok=True)

    # Create a 10x10 population raster
    # Values represent people per pixel (1km resolution)
    data = np.array([
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        [0, 5, 10, 15, 20, 25, 30, 35, 40, 0],
        [0, 10, 20, 30, 40, 50, 60, 70, 80, 0],
        [0, 15, 30, 45, 60, 75, 90, 105, 120, 0],
        [0, 20, 40, 60, 80, 100, 120, 140, 160, 0],
        [0, 25, 50, 75, 100, 125, 150, 175, 200, 0],
        [0, 30, 60, 90, 120, 150, 180, 210, 240, 0],
        [0, 35, 70, 105, 140, 175, 210, 245, 280, 0],
        [0, 40, 80, 120, 160, 200, 240, 280, 320, 0],
        [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    ], dtype=np.float32)

    # Bounding box covering part of South Sudan (Jonglei area)
    transform = from_bounds(30.0, 7.0, 31.0, 8.0, 10, 10)

    with rasterio.open(
        str(tif_path), 'w',
        driver='GTiff',
        height=10, width=10,
        count=1,
        dtype='float32',
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)

    return tif_path


@pytest.fixture
def synthetic_flood_mask(tmp_path):
    """
    Creates a synthetic flood mask GeoTIFF for testing.
    """
    mask_path = tmp_path / "flood_masks" / "test_mask.tif"
    mask_path.parent.mkdir(parents=True, exist_ok=True)

    # Create a 10x10 flood mask with flood in centre
    data = np.zeros((10, 10), dtype=np.uint8)
    data[3:7, 3:7] = 1  # Flooded area in centre

    transform = from_bounds(30.0, 7.0, 31.0, 8.0, 10, 10)

    with rasterio.open(
        str(mask_path), 'w',
        driver='GTiff',
        height=10, width=10,
        count=1,
        dtype='uint8',
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=255,
    ) as dst:
        dst.write(data, 1)

    return mask_path


@pytest.fixture
def mock_osm_data():
    """
    Creates mock OSM GeoDataFrame data.
    """
    import geopandas as gpd
    from shapely.geometry import Point, LineString

    # Mock villages
    villages_data = {
        'name': ['Village A', 'Village B', 'Village C', 'Village D'],
        'is_in': ['Jonglei', 'Jonglei', 'Unity', 'Upper Nile'],
        'geometry': [
            Point(30.3, 7.3),  # Within flood
            Point(30.5, 7.5),  # Within flood
            Point(30.7, 7.7),  # Within flood
            Point(31.0, 7.0),  # Outside flood (boundary)
        ]
    }
    villages_gdf = gpd.GeoDataFrame(villages_data, crs="EPSG:4326")

    # Mock roads
    roads_data = {
        'name': ['Road A', 'Road B', 'Road C'],
        'highway': ['primary', 'secondary', 'track'],
        'geometry': [
            LineString([(30.0, 7.0), (30.5, 7.5), (31.0, 8.0)]),
            LineString([(30.0, 7.5), (30.5, 7.0), (31.0, 7.5)]),
            LineString([(30.0, 8.0), (31.0, 8.0)]),
        ]
    }
    roads_gdf = gpd.GeoDataFrame(roads_data, crs="EPSG:4326")

    # Mock health facilities
    health_data = {
        'name': ['Hospital A', 'Clinic B', 'Health Post C'],
        'other_tags': ['hospital', 'clinic', 'health_post'],
        'geometry': [
            Point(30.3, 7.3),
            Point(30.5, 7.5),
            Point(30.7, 7.7),
        ]
    }
    health_gdf = gpd.GeoDataFrame(health_data, crs="EPSG:4326")

    return {
        'villages': villages_gdf,
        'roads': roads_gdf,
        'health': health_gdf,
    }


# ============================================================
# INITIALISATION TESTS
# ============================================================

class TestInitialisation:
    """Tests for RiskAssessor initialisation."""

    def test_initialises_with_config(self, assessor):
        """RiskAssessor should initialise with a Config object."""
        assert assessor is not None
        assert assessor.config is not None

    def test_data_attributes_are_none_by_default(self, assessor):
        """Data attributes should be None before loading."""
        assert assessor._population_data is None
        assert assessor._population_profile is None
        assert assessor._roads is None
        assert assessor._health_facilities is None
        assert assessor._villages is None


# ============================================================
# POPULATION DATA LOADING TESTS
# ============================================================

class TestPopulationLoading:
    """Tests for load_population_data() method."""

    def test_load_population_data_success(self, assessor, synthetic_worldpop_tif):
        """load_population_data should load population data successfully."""
        # Ensure config points to the synthetic file
        assessor.config.worldpop_path = synthetic_worldpop_tif

        assessor.load_population_data()

        assert assessor._population_data is not None
        assert assessor._population_profile is not None
        assert assessor._population_data.shape == (10, 10)
        # Total population should be sum of all values
        assert int(np.sum(assessor._population_data)) > 0

    def test_load_population_data_raises_if_file_missing(self, assessor):
        """load_population_data should raise FileNotFoundError if file missing."""
        # Point to non-existent file
        assessor.config.worldpop_path = Path("/nonexistent/worldpop.tif")

        with pytest.raises(FileNotFoundError):
            assessor.load_population_data()

    def test_load_population_data_handles_nodata(self, assessor, tmp_path):
        """load_population_data should replace nodata with 0."""
        tif_path = tmp_path / "worldpop_with_nodata.tif"
        tif_path.parent.mkdir(parents=True, exist_ok=True)

        data = np.array([
            [1.0, 2.0, -9999],
            [3.0, 4.0, 5.0],
            [6.0, 7.0, 8.0],
        ], dtype=np.float32)

        transform = from_bounds(30, 7, 31, 8, 3, 3)

        with rasterio.open(
            str(tif_path), 'w',
            driver='GTiff', height=3, width=3,
            count=1, dtype='float32',
            crs=CRS.from_epsg(4326),
            transform=transform,
            nodata=-9999,
        ) as dst:
            dst.write(data, 1)

        assessor.config.worldpop_path = tif_path
        assessor.load_population_data()

        # The -9999 at [0,2] should be replaced with 0
        assert assessor._population_data[0, 2] == 0.0

    def test_load_population_data_handles_negative_values(self, assessor, tmp_path):
        """load_population_data should replace negative values with 0."""
        tif_path = tmp_path / "worldpop_negative.tif"
        tif_path.parent.mkdir(parents=True, exist_ok=True)

        data = np.array([
            [1.0, -5.0, 3.0],
            [4.0, 5.0, 6.0],
            [7.0, 8.0, 9.0],
        ], dtype=np.float32)

        transform = from_bounds(30, 7, 31, 8, 3, 3)

        with rasterio.open(
            str(tif_path), 'w',
            driver='GTiff', height=3, width=3,
            count=1, dtype='float32',
            crs=CRS.from_epsg(4326),
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        assessor.config.worldpop_path = tif_path
        assessor.load_population_data()

        # Negative value at [0,1] should be replaced with 0
        assert assessor._population_data[0, 1] == 0.0


# ============================================================
# OSM DATA LOADING TESTS
# ============================================================

class TestOsmLoading:
    """Tests for load_osm_data() method."""

    def test_load_osm_data_with_valid_files(self, assessor, mock_osm_data, tmp_path):
        """load_osm_data should load all OSM files successfully."""
        import geopandas as gpd

        # Save mock data to temporary files
        osm_dir = tmp_path / "osm"
        osm_dir.mkdir(parents=True, exist_ok=True)

        mock_osm_data['villages'].to_file(str(osm_dir / "villages.geojson"), driver='GeoJSON')
        mock_osm_data['roads'].to_file(str(osm_dir / "roads.geojson"), driver='GeoJSON')
        mock_osm_data['health'].to_file(str(osm_dir / "health_facilities.geojson"), driver='GeoJSON')

        assessor.config.osm_villages_path = osm_dir / "villages.geojson"
        assessor.config.osm_roads_path = osm_dir / "roads.geojson"
        assessor.config.osm_health_path = osm_dir / "health_facilities.geojson"

        assessor.load_osm_data()

        assert assessor._villages is not None
        assert len(assessor._villages) == 4
        assert assessor._roads is not None
        assert len(assessor._roads) == 3
        assert assessor._health_facilities is not None
        assert len(assessor._health_facilities) == 3

    def test_load_osm_data_handles_missing_files(self, assessor):
        """load_osm_data should handle missing files gracefully."""
        # No files exist
        assessor.load_osm_data()

        # Should not crash — data remains None
        assert assessor._villages is None
        assert assessor._roads is None
        assert assessor._health_facilities is None

    def test_load_osm_data_handles_partial_files(self, assessor, mock_osm_data, tmp_path):
        """load_osm_data should handle case where only some files exist."""
        import geopandas as gpd

        osm_dir = tmp_path / "osm"
        osm_dir.mkdir(parents=True, exist_ok=True)

        # Only save villages file
        mock_osm_data['villages'].to_file(str(osm_dir / "villages.geojson"), driver='GeoJSON')

        assessor.config.osm_villages_path = osm_dir / "villages.geojson"
        assessor.config.osm_roads_path = osm_dir / "roads.geojson"
        assessor.config.osm_health_path = osm_dir / "health_facilities.geojson"

        assessor.load_osm_data()

        # Villages should be loaded, others should be None
        assert assessor._villages is not None
        assert len(assessor._villages) == 4
        assert assessor._roads is None
        assert assessor._health_facilities is None


# ============================================================
# POPULATION ESTIMATION TESTS
# ============================================================

class TestPopulationEstimation:
    """Tests for _estimate_population() method."""

    def test_estimate_population_returns_zero_if_no_data(self, assessor):
        """_estimate_population should return 0 if population data not loaded."""
        mask_data = np.zeros((10, 10), dtype=np.uint8)
        mask_profile = {'transform': from_bounds(30, 7, 31, 8, 10, 10), 'height': 10, 'width': 10}

        result = assessor._estimate_population(mask_data, mask_profile)

        assert result == 0

    def test_estimate_population_counts_flood_pixels(self, assessor, synthetic_worldpop_tif, synthetic_flood_mask):
        """_estimate_population should sum population values within flood pixels."""
        assessor.config.worldpop_path = synthetic_worldpop_tif
        assessor.load_population_data()

        with rasterio.open(str(synthetic_flood_mask)) as src:
            mask_data = src.read(1)
            mask_profile = src.profile.copy()

        result = assessor._estimate_population(mask_data, mask_profile)

        # Flood is in centre (3:7, 3:7) = 4x4 = 16 pixels
        # Population in centre should be summed
        assert result > 0

    def test_estimate_population_handles_nan_values(self, assessor, tmp_path):
        """_estimate_population should handle NaN values in population data."""
        # Create population data with NaN
        tif_path = tmp_path / "worldpop_nan.tif"
        tif_path.parent.mkdir(parents=True, exist_ok=True)

        data = np.array([
            [1.0, 2.0, np.nan],
            [3.0, 4.0, 5.0],
            [6.0, 7.0, 8.0],
        ], dtype=np.float32)

        transform = from_bounds(30, 7, 31, 8, 3, 3)

        with rasterio.open(
            str(tif_path), 'w',
            driver='GTiff', height=3, width=3,
            count=1, dtype='float32',
            crs=CRS.from_epsg(4326),
            transform=transform,
        ) as dst:
            dst.write(data, 1)

        assessor.config.worldpop_path = tif_path
        assessor.load_population_data()

        # Mask where [0,0] is flooded (should be 1.0)
        mask_data = np.zeros((3, 3), dtype=np.uint8)
        mask_data[0, 0] = 1

        mask_profile = {'transform': transform, 'height': 3, 'width': 3}

        result = assessor._estimate_population(mask_data, mask_profile)

        # Should return 1.0 (the non-NaN value at [0,0])
        assert result == 1


# ============================================================
# VILLAGE IDENTIFICATION TESTS
# ============================================================

class TestVillageIdentification:
    """Tests for _identify_affected_villages() method."""

    def test_identify_villages_returns_empty_if_no_villages_data(self, assessor):
        """_identify_affected_villages should return empty list if no villages data."""
        mask_data = np.zeros((10, 10), dtype=np.uint8)
        mask_profile = {'transform': from_bounds(30, 7, 31, 8, 10, 10), 'height': 10, 'width': 10}

        result = assessor._identify_affected_villages(mask_data, mask_profile)

        assert result == []

    def test_identify_villages_finds_villages_in_flood(self, assessor, synthetic_flood_mask, mock_osm_data):
        """_identify_affected_villages should find villages within flood extent."""
        # Load mock villages data
        assessor._villages = mock_osm_data['villages']

        with rasterio.open(str(synthetic_flood_mask)) as src:
            mask_data = src.read(1)
            mask_profile = src.profile.copy()

        result = assessor._identify_affected_villages(mask_data, mask_profile)

        # Village A (30.3, 7.3), B (30.5, 7.5), C (30.7, 7.7) are in flood area
        # Village D is outside
        assert len(result) >= 3

        # Check that village names are present
        village_names = [v['village_name'] for v in result]
        assert 'Village A' in village_names
        assert 'Village B' in village_names

    def test_identify_villages_returns_empty_if_no_villages_in_bbox(self, assessor, tmp_path):
        """_identify_affected_villages should return empty if no villages in bounding box."""
        import geopandas as gpd
        from shapely.geometry import Point

        # Create villages far away from the flood mask
        villages_data = {
            'name': ['Far Village'],
            'is_in': ['Jonglei'],
            'geometry': [Point(35.0, 10.0)],  # Far from flood mask
        }
        villages_gdf = gpd.GeoDataFrame(villages_data, crs="EPSG:4326")
        assessor._villages = villages_gdf

        # Flood mask at 30-31 lon, 7-8 lat
        mask_data = np.zeros((10, 10), dtype=np.uint8)
        mask_data[3:7, 3:7] = 1
        mask_profile = {'transform': from_bounds(30, 7, 31, 8, 10, 10), 'height': 10, 'width': 10}

        result = assessor._identify_affected_villages(mask_data, mask_profile)

        assert result == []


# ============================================================
# ROAD IDENTIFICATION TESTS
# ============================================================

class TestRoadIdentification:
    """Tests for _identify_inaccessible_roads() method."""

    def test_identify_roads_returns_empty_if_no_roads_data(self, assessor):
        """_identify_inaccessible_roads should return empty list if no roads data."""
        mask_data = np.zeros((10, 10), dtype=np.uint8)
        mask_profile = {'transform': from_bounds(30, 7, 31, 8, 10, 10), 'height': 10, 'width': 10}

        result = assessor._identify_inaccessible_roads(mask_data, mask_profile)

        assert result == []

    def test_identify_roads_finds_roads_in_flood(self, assessor, synthetic_flood_mask, mock_osm_data):
        """_identify_inaccessible_roads should find roads within flood extent."""
        # Load mock roads data
        assessor._roads = mock_osm_data['roads']

        with rasterio.open(str(synthetic_flood_mask)) as src:
            mask_data = src.read(1)
            mask_profile = src.profile.copy()

        result = assessor._identify_inaccessible_roads(mask_data, mask_profile)

        # Roads that intersect the flood bbox should be identified
        assert len(result) > 0

        # Check that road names are present
        road_names = [r['name'] for r in result]
        assert 'Road A' in road_names or 'Road B' in road_names

    def test_identify_roads_has_correct_fields(self, assessor, synthetic_flood_mask, mock_osm_data):
        """_identify_inaccessible_roads should return dicts with correct fields."""
        assessor._roads = mock_osm_data['roads']

        with rasterio.open(str(synthetic_flood_mask)) as src:
            mask_data = src.read(1)
            mask_profile = src.profile.copy()

        result = assessor._identify_inaccessible_roads(mask_data, mask_profile)

        if result:
            road = result[0]
            assert 'name' in road
            assert 'infrastructure_type' in road
            assert road['infrastructure_type'] == 'road'
            assert 'facility_type' in road
            assert 'segment_length_km' in road
            assert 'status' in road


# ============================================================
# HEALTH FACILITY IDENTIFICATION TESTS
# ============================================================

class TestHealthFacilityIdentification:
    """Tests for _identify_health_at_risk() method."""

    def test_identify_health_returns_empty_if_no_health_data(self, assessor):
        """_identify_health_at_risk should return empty list if no health data."""
        mask_data = np.zeros((10, 10), dtype=np.uint8)
        mask_profile = {'transform': from_bounds(30, 7, 31, 8, 10, 10), 'height': 10, 'width': 10}

        result = assessor._identify_health_at_risk(mask_data, mask_profile)

        assert result == []

    def test_identify_health_finds_facilities_in_flood(self, assessor, synthetic_flood_mask, mock_osm_data):
        """_identify_health_at_risk should find health facilities within flood extent."""
        # Load mock health facilities data
        assessor._health_facilities = mock_osm_data['health']

        with rasterio.open(str(synthetic_flood_mask)) as src:
            mask_data = src.read(1)
            mask_profile = src.profile.copy()

        result = assessor._identify_health_at_risk(mask_data, mask_profile)

        # All three facilities are within the flood bbox
        assert len(result) == 3

        # Check facility names
        facility_names = [f['name'] for f in result]
        assert 'Hospital A' in facility_names
        assert 'Clinic B' in facility_names

    def test_identify_health_has_correct_fields(self, assessor, synthetic_flood_mask, mock_osm_data):
        """_identify_health_at_risk should return dicts with correct fields."""
        assessor._health_facilities = mock_osm_data['health']

        with rasterio.open(str(synthetic_flood_mask)) as src:
            mask_data = src.read(1)
            mask_profile = src.profile.copy()

        result = assessor._identify_health_at_risk(mask_data, mask_profile)

        if result:
            facility = result[0]
            assert 'name' in facility
            assert 'infrastructure_type' in facility
            assert facility['infrastructure_type'] == 'health_facility'
            assert 'facility_type' in facility
            assert 'status' in facility
            assert 'latitude' in facility
            assert 'longitude' in facility


# ============================================================
# SUMMARY GENERATION TESTS
# ============================================================

class TestSummaryGeneration:
    """Tests for _save_summary() method."""

    def test_save_summary_creates_json_file(self, assessor, tmp_path):
        """_save_summary should create a JSON file."""
        assessor.config.masks_dir = tmp_path

        summary = {"test": "data", "value": 123}
        mask_path = str(tmp_path / "test_mask.tif")

        result = assessor._save_summary(summary, mask_path)

        assert Path(result).exists()
        assert result.endswith("_risk_summary.json")

    def test_save_summary_contains_correct_data(self, assessor, tmp_path):
        """_save_summary should write correct data to JSON."""
        assessor.config.masks_dir = tmp_path

        summary = {"test": "data", "value": 123, "list": [1, 2, 3]}
        mask_path = str(tmp_path / "test_mask.tif")

        result = assessor._save_summary(summary, mask_path)

        with open(result, 'r') as f:
            loaded = json.load(f)

        assert loaded["test"] == "data"
        assert loaded["value"] == 123
        assert loaded["list"] == [1, 2, 3]


# ============================================================
# FULL ASSESSMENT TESTS
# ============================================================

class TestFullAssessment:
    """Tests for the main assess() method."""

    def test_assess_raises_if_mask_missing(self, assessor):
        """assess() should raise FileNotFoundError if mask file missing."""
        with pytest.raises(FileNotFoundError):
            assessor.assess("/nonexistent/mask.tif")

    def test_assess_returns_summary_dict(self, assessor, synthetic_flood_mask):
        """assess() should return a summary dictionary."""
        # Load data
        assessor.load_population_data()

        result, summary_path = assessor.assess(str(synthetic_flood_mask))

        assert isinstance(result, dict)
        assert 'event_timestamp' in result
        assert 'mask_path' in result
        assert 'flood_pixels' in result
        assert 'affected_population_estimate' in result
        assert 'summary_statistics' in result

    def test_assess_returns_summary_path(self, assessor, synthetic_flood_mask):
        """assess() should return a path to the saved summary."""
        assessor.load_population_data()

        result, summary_path = assessor.assess(str(synthetic_flood_mask))

        assert Path(summary_path).exists()
        assert summary_path.endswith("_risk_summary.json")

    def test_assess_handles_missing_osm_data(self, assessor, synthetic_flood_mask):
        """assess() should handle missing OSM data gracefully."""
        # Only load population data, not OSM
        assessor.load_population_data()

        result, summary_path = assessor.assess(str(synthetic_flood_mask))

        # Should still return a summary
        assert 'summary_statistics' in result
        # Villages, roads, health should be empty or 0
        assert result['summary_statistics']['total_villages_affected'] == 0
        assert result['summary_statistics']['total_roads_inaccessible'] == 0
        assert result['summary_statistics']['total_health_facilities_at_risk'] == 0

    def test_assess_has_all_summary_keys(self, assessor, synthetic_flood_mask):
        """assess() summary should have all expected keys."""
        assessor.load_population_data()

        result, summary_path = assessor.assess(str(synthetic_flood_mask))

        expected_keys = [
            'event_timestamp',
            'mask_path',
            'flood_pixels',
            'flood_extent_ha',
            'affected_population_estimate',
            'affected_villages',
            'inaccessible_roads',
            'health_facilities_at_risk',
            'summary_statistics'
        ]

        for key in expected_keys:
            assert key in result, f"Missing key: {key}"


# ============================================================
# Run tests directly
# Usage: python3 -m pytest tests/test_risk_assessment.py -v
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])